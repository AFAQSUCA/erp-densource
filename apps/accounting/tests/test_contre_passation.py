"""Contre-passation : une écriture validée ne se corrige que par une écriture inverse (audit : ACC-07).

Annuler un règlement ou un mouvement manuel doit aussi retirer son effet du grand livre, sinon la
trésorerie et les comptes 521/571/411 divergent sans trace."""

from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounting import services
from apps.accounting.constants import COMPTE_CLIENTS
from apps.accounting.exceptions import ContrePassationImpossible, CompteInconnu, ExerciceCloture
from apps.accounting.models import (
    Compte,
    EcritureComptable,
    ExerciceComptable,
    Journal,
    SensEcriture,
    StatutExercice,
)
from apps.accounting.services import LigneSaisie
from apps.billing import services as billing_services
from apps.billing.models import ModePaiement, Reglement
from apps.billing.tests.helpers import emise, finances
from apps.finance import services as finance_services
from apps.finance.models import LigneReleve, MouvementManuel, NatureMouvement, SensMouvement

from .factories import CompteFactory

pytestmark = pytest.mark.django_db

JOUR = date(2026, 9, 5)


def _solde(numero):
    ligne = {l["compte__numero"]: l for l in services.balance()}.get(numero)
    return Decimal("0") if ligne is None else ligne["total_debit"] - ligne["total_credit"]


def _ecriture(*, date_ecriture=JOUR, montant="1000"):
    charge, tresorerie = CompteFactory(), CompteFactory()
    return services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date_ecriture, libelle="Achat",
        piece_reference="PIECE-1",
        lignes=[
            LigneSaisie(compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal(montant)),
            LigneSaisie(
                compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal(montant),
                tiers_type="CLIENT", tiers_id=7,
            ),
        ],
        origine="TEST", origine_id=1,
    )


# --- le service ---


def test_contre_passer_inverse_chaque_ligne_et_garde_l_original_intact():
    ecriture = _ecriture()

    inverse = services.contre_passer(ecriture, motif="Erreur de saisie")

    assert inverse.pk != ecriture.pk
    assert inverse.origine == "CONTRE_PASSATION" and inverse.origine_id == ecriture.pk
    assert inverse.journal == ecriture.journal and inverse.piece_reference == "PIECE-1"
    assert inverse.date_ecriture == timezone.localdate()
    assert inverse.numero and inverse.numero != ecriture.numero
    assert ecriture.numero in inverse.libelle and "Erreur de saisie" in inverse.libelle
    avant = {(l.compte_id, l.sens, l.montant) for l in ecriture.lignes.all()}
    apres = {(l.compte_id, l.sens, l.montant) for l in inverse.lignes.all()}
    inverse_sens = {SensEcriture.DEBIT: SensEcriture.CREDIT, SensEcriture.CREDIT: SensEcriture.DEBIT}
    assert apres == {(c, inverse_sens[s], m) for c, s, m in avant}
    ligne_tiers = inverse.lignes.exclude(tiers_type="").get()
    assert (ligne_tiers.tiers_type, ligne_tiers.tiers_id) == ("CLIENT", 7)
    assert ecriture.lignes.count() == 2  # l'écriture d'origine n'a pas bougé


def test_les_comptes_reviennent_a_zero_une_fois_contre_passee():
    ecriture = _ecriture(montant="2500")
    comptes = [l.compte.numero for l in ecriture.lignes.select_related("compte")]

    services.contre_passer(ecriture)

    assert [_solde(numero) for numero in comptes] == [Decimal("0"), Decimal("0")]


def test_contre_passer_est_idempotente():
    ecriture = _ecriture()

    premiere = services.contre_passer(ecriture)
    seconde = services.contre_passer(ecriture)

    assert premiere.pk == seconde.pk
    assert EcritureComptable.objects.filter(origine="CONTRE_PASSATION").count() == 1


def test_contre_passer_accepte_une_date_explicite():
    ecriture = _ecriture()

    assert services.contre_passer(ecriture, date_ecriture=date(2026, 9, 20)).date_ecriture == date(2026, 9, 20)


def test_un_brouillon_ne_se_contre_passe_pas():
    brouillon = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Brouillon")

    with pytest.raises(ContrePassationImpossible, match="brouillon"):
        services.contre_passer(brouillon)


def test_une_contre_passation_ne_se_contre_passe_pas():
    inverse = services.contre_passer(_ecriture())

    with pytest.raises(ContrePassationImpossible, match="ne se contre-passe pas"):
        services.contre_passer(inverse)


def test_une_ecriture_d_un_exercice_clos_se_contre_passe_dans_l_exercice_ouvert():
    ecriture = _ecriture(date_ecriture=date(2024, 6, 1))
    ExerciceComptable.objects.filter(annee=2024).update(statut=StatutExercice.CLOTURE)

    inverse = services.contre_passer(ecriture)

    assert inverse.date_ecriture == timezone.localdate()
    assert inverse.date_ecriture.year != 2024


def test_contre_passer_est_refusee_si_l_exercice_du_jour_est_clos():
    ecriture = _ecriture()
    services.exercice_pour(timezone.localdate())
    ExerciceComptable.objects.filter(annee=timezone.localdate().year).update(statut=StatutExercice.CLOTURE)

    with pytest.raises(ExerciceCloture):
        services.contre_passer(ecriture)

    assert not EcritureComptable.objects.filter(origine="CONTRE_PASSATION").exists()


def test_contre_passer_origine_ne_fait_rien_sans_ecriture_d_origine():
    assert services.contre_passer_origine("REGLEMENT", 999999) is None


def test_contre_passer_origine_retrouve_l_ecriture_par_son_evenement_source():
    ecriture = _ecriture()

    inverse = services.contre_passer_origine("TEST", 1, motif="Doublon")

    assert inverse.origine_id == ecriture.pk and "Doublon" in inverse.libelle


# --- l'annulation d'un règlement ---


def _reglement(montant="100000", mode=ModePaiement.VIREMENT, jour=JOUR):
    facture = emise(prix="1000000")
    return billing_services.enregistrer_reglement(
        facture, finances(), montant=Decimal(montant), mode=mode, date_reglement=jour
    )


def test_annuler_un_reglement_contre_passe_son_ecriture():
    reglement = _reglement("100000")
    assert _solde("521000") == Decimal("100000")

    billing_services.annuler_reglement(reglement, finances(), motif="Chèque sans provision")

    inverse = EcritureComptable.objects.get(origine="CONTRE_PASSATION")
    assert "Chèque sans provision" in inverse.libelle
    assert _solde("521000") == Decimal("0")
    # la créance du client est rétablie : 411 = TTC de la facture, comme avant le règlement
    assert _solde(COMPTE_CLIENTS) == reglement.facture.montant_ttc


def test_annuler_un_reglement_ancien_se_contre_passe_aujourd_hui():
    reglement = _reglement(jour=date(2026, 9, 1))

    billing_services.annuler_reglement(reglement, finances(), motif="Erreur")

    inverse = EcritureComptable.objects.get(origine="CONTRE_PASSATION")
    assert inverse.date_ecriture == timezone.localdate()


def test_annuler_un_reglement_est_tout_ou_rien_si_la_contre_passation_est_impossible():
    reglement = _reglement()
    Compte.objects.filter(numero="521000").update(actif=False)

    with pytest.raises(CompteInconnu):
        billing_services.annuler_reglement(reglement, finances(), motif="Erreur")

    assert Reglement.objects.filter(pk=reglement.pk).exists()  # l'annulation est annulée avec elle
    assert not EcritureComptable.objects.filter(origine="CONTRE_PASSATION").exists()


def test_annuler_un_reglement_jamais_comptabilise_n_echoue_pas():
    reglement = _reglement()
    EcritureComptable.objects.filter(origine="REGLEMENT", origine_id=reglement.pk).update(origine="ANCIEN")

    billing_services.annuler_reglement(reglement, finances(), motif="Erreur")

    assert not EcritureComptable.objects.filter(origine="CONTRE_PASSATION").exists()


# --- l'annulation d'un mouvement manuel ---


def _mouvement(sens=SensMouvement.ENTREE, montant="50000"):
    return finance_services.enregistrer_mouvement(
        finances(), sens=sens, date_mouvement=JOUR, libelle="Apport", montant=Decimal(montant),
        mode=ModePaiement.VIREMENT, nature=NatureMouvement.APPORT,
    )


@pytest.mark.parametrize("sens", [SensMouvement.ENTREE, SensMouvement.SORTIE])
def test_annuler_un_mouvement_manuel_contre_passe_son_ecriture(sens):
    mouvement = _mouvement(sens)
    assert _solde("521000") != Decimal("0")

    finance_services.annuler_mouvement(mouvement, finances(), motif="Doublon")

    assert EcritureComptable.objects.filter(origine="CONTRE_PASSATION").count() == 1
    assert _solde("521000") == Decimal("0")


# --- le pointage bancaire ---


def _releve(sens=SensMouvement.ENTREE, montant="50000"):
    return finance_services.saisir_ligne_releve(
        finances(), date_operation=JOUR, libelle="Relevé", montant=Decimal(montant), sens=sens
    )


def test_annuler_un_mouvement_defait_le_pointage_de_sa_ligne_de_releve():
    mouvement = _mouvement()
    ligne = _releve()
    finance_services.pointer_ligne_releve(ligne, finances(), origine="MANUEL", mouvement_id=mouvement.pk)

    finance_services.annuler_mouvement(mouvement, finances(), motif="Doublon")

    ligne.refresh_from_db()
    assert ligne.pointee is False and ligne.mouvement_origine == "" and ligne.mouvement_id is None


def test_annuler_un_reglement_defait_le_pointage_de_sa_ligne_de_releve():
    reglement = _reglement("100000")
    ligne = _releve(montant="100000")
    finance_services.pointer_ligne_releve(ligne, finances(), origine="REGLEMENT", mouvement_id=reglement.pk)
    autre = _releve(montant="1")  # une ligne sans rapport reste intacte
    finance_services.pointer_ligne_releve(autre, finances(), origine="MANUEL", mouvement_id=424242)

    billing_services.annuler_reglement(reglement, finances(), motif="Erreur")

    ligne.refresh_from_db()
    autre.refresh_from_db()
    assert ligne.pointee is False and autre.pointee is True
    assert LigneReleve.objects.count() == 2


def test_depointer_mouvement_renvoie_le_nombre_de_lignes_defaites():
    mouvement = _mouvement()
    finance_services.pointer_ligne_releve(_releve(), finances(), origine="MANUEL", mouvement_id=mouvement.pk)

    assert finance_services.depointer_mouvement("MANUEL", mouvement.pk) == 1
    assert finance_services.depointer_mouvement("MANUEL", mouvement.pk) == 0
    assert MouvementManuel.objects.filter(pk=mouvement.pk).exists()


# --- reprise de l'historique ---


def _annulation_ancienne(*objets):
    """Simule des annulations faites avant ce lot : les objets disparaissent sans contre-passation."""
    EcritureComptable.objects.filter(origine="CONTRE_PASSATION").delete()
    for objet in objets:
        type(objet).objects.filter(pk=objet.pk).update(is_deleted=True, deleted_at=timezone.now())


def test_la_reprise_contre_passe_les_annulations_anterieures_et_se_rejoue_sans_doublon():
    from io import StringIO

    from django.core.management import call_command

    reglement, mouvement = _reglement("100000"), _mouvement()
    _annulation_ancienne(reglement, mouvement)
    sortie = StringIO()

    call_command("contre_passer_historique_annulations", "--dry-run", stdout=sortie)
    assert "Simulation" in sortie.getvalue() and "2 annulation(s)" in sortie.getvalue()
    assert not EcritureComptable.objects.filter(origine="CONTRE_PASSATION").exists()

    call_command("contre_passer_historique_annulations", stdout=sortie)
    assert EcritureComptable.objects.filter(origine="CONTRE_PASSATION").count() == 2
    assert _solde("521000") == Decimal("0")

    sortie = StringIO()
    call_command("contre_passer_historique_annulations", stdout=sortie)
    assert "0 annulation(s) contre-passée(s) (2 déjà faites" in sortie.getvalue()
    assert EcritureComptable.objects.filter(origine="CONTRE_PASSATION").count() == 2


def test_la_reprise_ignore_ce_qui_n_a_jamais_ete_comptabilise_et_signale_l_impossible():
    from io import StringIO

    from django.core.management import call_command

    jamais, bloque = _reglement("1000"), _reglement("2000")
    EcritureComptable.objects.filter(origine="REGLEMENT", origine_id=jamais.pk).update(origine="ANCIEN")
    _annulation_ancienne(jamais, bloque)
    Compte.objects.filter(numero="521000").update(actif=False)
    sortie, erreurs = StringIO(), StringIO()

    call_command("contre_passer_historique_annulations", stdout=sortie, stderr=erreurs)

    assert "1 jamais comptabilisées, 1 impossible(s)" in sortie.getvalue()
    assert f"REGLEMENT #{bloque.pk} non contre-passé" in erreurs.getvalue()
