"""Intégration : la validation d'une facture et l'enregistrement d'un règlement (billing)
génèrent toujours leur écriture comptable — cahier-des-charges.md:340."""

from datetime import date
from decimal import Decimal

import pytest

from apps.accounting.constants import COMPTE_CLIENTS, COMPTE_TVA_COLLECTEE, COMPTE_VENTES_TRANSPORT
from apps.accounting.models import EcritureComptable, Journal, SensEcriture
from apps.billing import services as billing_services
from apps.billing.models import CategorieDepense, ModePaiement, OrigineDepense
from apps.billing.tests.helpers import a_valider, direction, emise, finances
from apps.customers.tests.factories import ClientFactory
from apps.finance import services as finance_services
from apps.finance.models import NatureMouvement, SensMouvement

pytestmark = pytest.mark.django_db


def test_facture_validee_genere_une_ecriture_equilibree():
    facture = emise(prix="1000000")

    ecriture = EcritureComptable.objects.get(origine="FACTURE", origine_id=facture.pk)

    assert ecriture.journal == Journal.VENTES
    assert ecriture.numero.startswith("VTE-2026-")
    assert ecriture.piece_reference == facture.numero
    lignes = {l.compte.numero: (l.sens, l.montant) for l in ecriture.lignes.all()}
    assert lignes[COMPTE_CLIENTS] == (SensEcriture.DEBIT, facture.montant_ttc)
    assert lignes[COMPTE_VENTES_TRANSPORT] == (SensEcriture.CREDIT, facture.montant_ht)
    assert lignes[COMPTE_TVA_COLLECTEE] == (SensEcriture.CREDIT, facture.montant_tva)
    total_debit = sum(m for sens, m in lignes.values() if sens == SensEcriture.DEBIT)
    total_credit = sum(m for sens, m in lignes.values() if sens == SensEcriture.CREDIT)
    assert total_debit == total_credit == facture.montant_ttc


def test_ligne_clients_est_rattachee_au_client_de_la_facture():
    facture = emise()

    ecriture = EcritureComptable.objects.get(origine="FACTURE", origine_id=facture.pk)
    ligne_clients = ecriture.lignes.get(compte__numero=COMPTE_CLIENTS)

    assert ligne_clients.tiers_type == "CLIENT"
    assert ligne_clients.tiers_id == facture.client_id


def test_une_facture_exoneree_ne_cree_pas_de_ligne_tva():
    client = ClientFactory(taux_tva=Decimal("0"), motif_exoneration="EXPORT")

    facture = emise(client=client)

    assert facture.montant_tva == 0
    ecriture = EcritureComptable.objects.get(origine="FACTURE", origine_id=facture.pk)
    assert ecriture.lignes.count() == 2
    assert not ecriture.lignes.filter(compte__numero=COMPTE_TVA_COLLECTEE).exists()


def test_valider_une_facture_deja_validee_ne_duplique_pas_l_ecriture():
    facture = emise()
    nb_avant = EcritureComptable.objects.filter(origine="FACTURE", origine_id=facture.pk).count()

    from apps.billing.exceptions import TransitionFactureInterdite

    with pytest.raises(TransitionFactureInterdite):
        billing_services.valider(facture, direction())

    assert EcritureComptable.objects.filter(origine="FACTURE", origine_id=facture.pk).count() == nb_avant == 1


# --- règlements (Phase 2) ---


@pytest.mark.parametrize(
    ("mode", "compte_attendu", "journal_attendu"),
    [
        (ModePaiement.VIREMENT, "521000", Journal.BANQUE),
        (ModePaiement.CHEQUE, "521000", Journal.BANQUE),
        (ModePaiement.ESPECES, "571000", Journal.CAISSE),
        (ModePaiement.WAVE, "521900", Journal.BANQUE),
        (ModePaiement.ORANGE_MONEY, "521900", Journal.BANQUE),
        (ModePaiement.MTN_MONEY, "521900", Journal.BANQUE),
    ],
)
def test_reglement_enregistre_genere_une_ecriture_selon_le_mode(mode, compte_attendu, journal_attendu):
    facture = emise(prix="1000000")

    reglement = billing_services.enregistrer_reglement(
        facture, finances(), montant=Decimal("100000"), mode=mode, date_reglement=date(2026, 9, 5),
    )

    ecriture = EcritureComptable.objects.get(origine="REGLEMENT", origine_id=reglement.pk)
    assert ecriture.journal == journal_attendu
    assert ecriture.date_ecriture == date(2026, 9, 5)
    lignes = {l.compte.numero: (l.sens, l.montant) for l in ecriture.lignes.all()}
    assert lignes[compte_attendu] == (SensEcriture.DEBIT, Decimal("100000"))
    assert lignes[COMPTE_CLIENTS] == (SensEcriture.CREDIT, Decimal("100000"))


def test_ligne_clients_du_reglement_est_rattachee_au_client():
    facture = emise()

    reglement = billing_services.enregistrer_reglement(
        facture, finances(), montant=facture.montant_ttc, mode=ModePaiement.VIREMENT,
        date_reglement=date(2026, 9, 5),
    )

    ecriture = EcritureComptable.objects.get(origine="REGLEMENT", origine_id=reglement.pk)
    ligne_clients = ecriture.lignes.get(compte__numero=COMPTE_CLIENTS)
    assert ligne_clients.tiers_type == "CLIENT"
    assert ligne_clients.tiers_id == facture.client_id


def test_deux_reglements_sur_la_meme_facture_generent_deux_ecritures_distinctes():
    facture = emise(prix="1000000")

    premier = billing_services.enregistrer_reglement(
        facture, finances(), montant=Decimal("400000"), mode=ModePaiement.ESPECES,
        date_reglement=date(2026, 9, 5),
    )
    second = billing_services.enregistrer_reglement(
        facture, finances(), montant=Decimal("600000"), mode=ModePaiement.VIREMENT,
        date_reglement=date(2026, 9, 10),
    )

    ecritures = EcritureComptable.objects.filter(origine="REGLEMENT", origine_id__in=[premier.pk, second.pk])
    assert ecritures.count() == 2


# --- dépenses automatiques (Phase 3) ---


def _depense_automatique(origine_id, *, categorie=CategorieDepense.CARBURANT, mode=ModePaiement.ESPECES):
    return billing_services.comptabiliser_depense_automatique(
        origine=OrigineDepense.PLEIN, origine_id=origine_id, categorie=categorie,
        date_depense=date(2026, 9, 5), libelle="Plein — AB-1234-CI", montant=Decimal("50000"),
        mode=mode,
    )


@pytest.mark.parametrize(
    ("categorie", "compte_charge"),
    [
        (CategorieDepense.CARBURANT, "605100"),
        (CategorieDepense.PIECES, "605800"),
        (CategorieDepense.MAINTENANCE, "624100"),
        (CategorieDepense.FRAIS_MISSION, "628100"),
    ],
)
def test_depense_automatique_genere_une_ecriture_selon_la_categorie(categorie, compte_charge):
    depense = _depense_automatique(1001, categorie=categorie)

    ecriture = EcritureComptable.objects.get(origine="DEPENSE", origine_id=depense.pk)
    assert ecriture.journal == Journal.CAISSE  # ESPECES par défaut
    lignes = {l.compte.numero: (l.sens, l.montant) for l in ecriture.lignes.all()}
    assert lignes[compte_charge] == (SensEcriture.DEBIT, Decimal("50000"))
    assert lignes["571000"] == (SensEcriture.CREDIT, Decimal("50000"))


@pytest.mark.parametrize(
    ("categorie", "compte_charge"),
    [
        (CategorieDepense.PEAGES, "628100"),
        (CategorieDepense.ENTRETIEN, "624100"),
        (CategorieDepense.FRAIS_ADMIN, "658000"),
        (CategorieDepense.AUTRE, "658000"),
    ],
)
def test_depense_manuelle_genere_une_ecriture_selon_la_categorie(categorie, compte_charge):
    depense = billing_services.enregistrer_depense(
        finances(), categorie=categorie, date_depense=date(2026, 9, 5), libelle="Test",
        montant=Decimal("12000"), mode=ModePaiement.ESPECES,
    )

    ecriture = EcritureComptable.objects.get(origine="DEPENSE", origine_id=depense.pk)
    assert ecriture.journal == Journal.CAISSE
    lignes = {l.compte.numero: (l.sens, l.montant) for l in ecriture.lignes.all()}
    assert lignes[compte_charge] == (SensEcriture.DEBIT, Decimal("12000"))
    assert lignes["571000"] == (SensEcriture.CREDIT, Decimal("12000"))


def test_rejouer_la_meme_source_ne_duplique_pas_l_ecriture():
    premiere = _depense_automatique(1002)
    seconde = _depense_automatique(1002)  # même origine_id : Depense.get_or_create retombe dessus

    assert premiere.pk == seconde.pk
    assert EcritureComptable.objects.filter(origine="DEPENSE", origine_id=premiere.pk).count() == 1


def test_un_ordre_de_decaissement_avec_mode_reel_ne_passe_pas_par_la_caisse_provisoire():
    depense = _depense_automatique(1003, categorie=CategorieDepense.PIECES, mode=ModePaiement.VIREMENT)

    ecriture = EcritureComptable.objects.get(origine="DEPENSE", origine_id=depense.pk)
    assert ecriture.journal == Journal.BANQUE
    assert ecriture.lignes.filter(compte__numero="521000", sens=SensEcriture.CREDIT).exists()


def test_changer_le_mode_reclasse_la_tresorerie():
    depense = _depense_automatique(1004)  # ESPECES -> 571000 par défaut

    billing_services.changer_mode_depense(depense, finances(), mode=ModePaiement.VIREMENT)

    reclassements = EcritureComptable.objects.filter(journal=Journal.OPERATIONS_DIVERSES)
    ecriture = reclassements.latest("pk")
    lignes = {l.compte.numero: (l.sens, l.montant) for l in ecriture.lignes.all()}
    assert lignes["521000"] == (SensEcriture.DEBIT, Decimal("50000"))
    assert lignes["571000"] == (SensEcriture.CREDIT, Decimal("50000"))


def test_changer_le_mode_vers_le_meme_compte_de_tresorerie_ne_reclasse_rien():
    depense = _depense_automatique(1005, mode=ModePaiement.VIREMENT)  # Banque
    nb_avant = EcritureComptable.objects.filter(journal=Journal.OPERATIONS_DIVERSES).count()

    billing_services.changer_mode_depense(depense, finances(), mode=ModePaiement.CHEQUE)  # Banque aussi

    assert EcritureComptable.objects.filter(journal=Journal.OPERATIONS_DIVERSES).count() == nb_avant


# --- mouvements manuels de trésorerie (Phase 4) ---


@pytest.mark.parametrize(
    ("nature", "compte_contrepartie"),
    [
        (NatureMouvement.SOLDE_OUVERTURE, "101000"),
        (NatureMouvement.APPORT, "101000"),
        (NatureMouvement.RETRAIT, "108000"),
        (NatureMouvement.FRAIS_BANCAIRE, "631000"),
        (NatureMouvement.AUTRE, "658000"),
    ],
)
def test_une_entree_de_mouvement_manuel_debite_la_tresorerie(nature, compte_contrepartie):
    mouvement = finance_services.enregistrer_mouvement(
        finances(), sens=SensMouvement.ENTREE, date_mouvement=date(2026, 9, 5), libelle="Test",
        montant=Decimal("200000"), mode=ModePaiement.VIREMENT, nature=nature,
    )

    ecriture = EcritureComptable.objects.get(origine="MOUVEMENT", origine_id=mouvement.pk)
    assert ecriture.journal == Journal.BANQUE
    lignes = {l.compte.numero: (l.sens, l.montant) for l in ecriture.lignes.all()}
    assert lignes["521000"] == (SensEcriture.DEBIT, Decimal("200000"))
    assert lignes[compte_contrepartie] == (SensEcriture.CREDIT, Decimal("200000"))


def test_une_sortie_de_mouvement_manuel_credite_la_tresorerie():
    mouvement = finance_services.enregistrer_mouvement(
        finances(), sens=SensMouvement.SORTIE, date_mouvement=date(2026, 9, 5), libelle="Retrait",
        montant=Decimal("50000"), mode=ModePaiement.ESPECES, nature=NatureMouvement.RETRAIT,
    )

    ecriture = EcritureComptable.objects.get(origine="MOUVEMENT", origine_id=mouvement.pk)
    assert ecriture.journal == Journal.CAISSE
    lignes = {l.compte.numero: (l.sens, l.montant) for l in ecriture.lignes.all()}
    assert lignes["571000"] == (SensEcriture.CREDIT, Decimal("50000"))
    assert lignes["108000"] == (SensEcriture.DEBIT, Decimal("50000"))
