"""Reprise des reclassements de mode de paiement passés à l'envers avant la correction de l'audit AV-04."""

from datetime import date
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from apps.accounting import services
from apps.accounting.exceptions import ContrePassationImpossible
from apps.accounting.models import EcritureComptable, Journal, LigneEcriture, SensEcriture
from apps.accounting.services import LigneSaisie
from apps.billing import services as billing_services
from apps.billing.models import CategorieDepense, ModePaiement, OrigineDepense
from apps.billing.tests.helpers import finances

pytestmark = pytest.mark.django_db

CAISSE, BANQUE = "571000", "521000"
MONTANT = Decimal("50000")


def _depense_en_especes(origine_id=2001):
    return billing_services.comptabiliser_depense_automatique(
        origine=OrigineDepense.PLEIN, origine_id=origine_id, categorie=CategorieDepense.CARBURANT,
        date_depense=date(2026, 9, 5), libelle="Plein — AB-1234-CI", montant=MONTANT, mode=ModePaiement.ESPECES,
    )


def _reclassement_a_l_envers(montant=MONTANT):
    """Ce que l'ancien code écrivait pour Espèces -> Virement : débit Banque, crédit Caisse, sans pièce."""
    return services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date(2026, 9, 6),
        libelle=f"{services.LIBELLE_RECLASSEMENT_INVERSE}Plein — AB-1234-CI",
        lignes=[LigneSaisie(BANQUE, SensEcriture.DEBIT, montant), LigneSaisie(CAISSE, SensEcriture.CREDIT, montant)],
    )


def _solde(numero):
    lignes = LigneEcriture.objects.filter(compte__numero=numero)
    return sum((l.montant if l.sens == SensEcriture.DEBIT else -l.montant for l in lignes), Decimal("0"))


def test_la_correction_ramene_les_soldes_a_ce_qu_ils_auraient_du_etre():
    _depense_en_especes()
    faux = _reclassement_a_l_envers()
    assert (_solde(CAISSE), _solde(BANQUE)) == (Decimal("-100000"), Decimal("50000"))  # l'erreur de 2 x le montant

    correction = services.corriger_reclassement_inverse(faux)

    assert (_solde(CAISSE), _solde(BANQUE)) == (Decimal("0"), Decimal("-50000"))
    assert services.contre_passation_de(faux) is not None
    lignes = {l.compte.numero: l.sens for l in correction.lignes.all()}
    assert lignes == {CAISSE: SensEcriture.DEBIT, BANQUE: SensEcriture.CREDIT}
    assert correction.origine == services.ORIGINE_CORRECTION_RECLASSEMENT and correction.origine_id == faux.pk


def test_un_reclassement_corrige_ne_l_est_jamais_deux_fois():
    _depense_en_especes()
    faux = _reclassement_a_l_envers()
    services.corriger_reclassement_inverse(faux)
    nombre = EcritureComptable.objects.count()

    assert not services.reclassements_inverses().exists()
    services.corriger_reclassement_inverse(faux)

    assert EcritureComptable.objects.count() == nombre


def test_un_reclassement_passe_depuis_la_correction_n_est_pas_repris():
    depense = _depense_en_especes()

    billing_services.changer_mode_depense(depense, finances(), mode=ModePaiement.VIREMENT)

    assert EcritureComptable.objects.filter(libelle__startswith=services.LIBELLE_RECLASSEMENT).count() == 1
    assert depense.reference == ""  # sans pièce : seul le libellé distingue un reclassement correct
    assert not services.reclassements_inverses().exists()


def test_une_contre_passation_deja_faite_a_la_main_est_reutilisee():
    _depense_en_especes()
    faux = _reclassement_a_l_envers()
    services.contre_passer(faux, motif="vu par la comptable")

    services.corriger_reclassement_inverse(faux)

    assert EcritureComptable.objects.filter(origine=services.ORIGINE_CONTRE_PASSATION, origine_id=faux.pk).count() == 1
    assert (_solde(CAISSE), _solde(BANQUE)) == (Decimal("0"), Decimal("-50000"))


def test_une_ecriture_qui_n_a_pas_la_forme_d_un_reclassement_est_refusee():
    faux = services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date(2026, 9, 6),
        libelle=f"{services.LIBELLE_RECLASSEMENT_INVERSE}trois lignes",
        lignes=[
            LigneSaisie(BANQUE, SensEcriture.DEBIT, Decimal("100")),
            LigneSaisie(CAISSE, SensEcriture.CREDIT, Decimal("60")),
            LigneSaisie(CAISSE, SensEcriture.CREDIT, Decimal("40")),
        ],
    )

    with pytest.raises(ContrePassationImpossible):
        services.corriger_reclassement_inverse(faux)
    assert services.contre_passation_de(faux) is None


def test_la_commande_en_simulation_n_ecrit_rien():
    _depense_en_especes()
    _reclassement_a_l_envers()
    nombre = EcritureComptable.objects.count()
    sortie = StringIO()

    call_command("corriger_reclassements_inverses", "--dry-run", stdout=sortie)

    assert EcritureComptable.objects.count() == nombre
    assert "[Simulation, rien n'a été écrit] 1 reclassement(s) corrigé(s), 0 impossible(s)." in sortie.getvalue()


def test_la_commande_corrige_puis_ne_fait_plus_rien():
    _depense_en_especes()
    _reclassement_a_l_envers()
    erreurs = StringIO()

    call_command("corriger_reclassements_inverses", stdout=StringIO(), stderr=erreurs)
    sortie = StringIO()
    call_command("corriger_reclassements_inverses", stdout=sortie)

    assert (_solde(CAISSE), _solde(BANQUE)) == (Decimal("0"), Decimal("-50000"))
    assert "0 reclassement(s) corrigé(s)" in sortie.getvalue()
    assert erreurs.getvalue() == ""


def test_la_commande_signale_une_ecriture_impossible_sans_bloquer_les_autres():
    _depense_en_especes()
    _reclassement_a_l_envers()
    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date(2026, 9, 6),
        libelle=f"{services.LIBELLE_RECLASSEMENT_INVERSE}trois lignes",
        lignes=[
            LigneSaisie(BANQUE, SensEcriture.DEBIT, Decimal("100")),
            LigneSaisie(CAISSE, SensEcriture.CREDIT, Decimal("60")),
            LigneSaisie(CAISSE, SensEcriture.CREDIT, Decimal("40")),
        ],
    )
    sortie, erreurs = StringIO(), StringIO()

    call_command("corriger_reclassements_inverses", stdout=sortie, stderr=erreurs)

    assert "1 reclassement(s) corrigé(s), 1 impossible(s)." in sortie.getvalue()
    assert "non corrigée" in erreurs.getvalue()
