"""Moteur d'écritures : équilibre, idempotence, comptes inconnus/inactifs ; saisie manuelle
d'opérations diverses (Phase 4)."""

from datetime import date
from decimal import Decimal

import pytest

from apps.accounting import services
from apps.accounting.exceptions import (
    ActionComptableNonAutorisee,
    CompteInconnu,
    EcritureNonEquilibree,
    EcritureVerrouillee,
)
from apps.accounting.models import Journal, LigneEcriture, SensEcriture, StatutEcriture
from apps.accounting.services import LigneSaisie
from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing.tests.helpers import direction, finances

from .factories import CompteFactory

pytestmark = pytest.mark.django_db

JOUR = date(2026, 9, 1)


def _lignes_equilibrees(charge, tresorerie, montant="1000"):
    montant = Decimal(montant)
    return [
        LigneSaisie(compte=charge.numero, sens=SensEcriture.DEBIT, montant=montant),
        LigneSaisie(compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=montant),
    ]


def test_passer_ecriture_equilibree_cree_lignes():
    charge, tresorerie = CompteFactory(), CompteFactory()

    ecriture = services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES,
        date_ecriture=JOUR,
        libelle="Test",
        lignes=_lignes_equilibrees(charge, tresorerie),
    )

    assert ecriture.numero.startswith("OD-2026-")
    assert ecriture.lignes.count() == 2
    assert {l.compte_id for l in ecriture.lignes.all()} == {charge.pk, tresorerie.pk}


def test_passer_ecriture_desequilibree_leve_erreur_et_ne_cree_rien():
    charge, tresorerie = CompteFactory(), CompteFactory()
    lignes = [
        LigneSaisie(compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("1000")),
        LigneSaisie(compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("900")),
    ]

    with pytest.raises(EcritureNonEquilibree, match="1000.*900|900.*1000"):
        services.passer_ecriture(
            journal=Journal.OPERATIONS_DIVERSES, date_ecriture=JOUR, libelle="Test", lignes=lignes
        )

    assert LigneEcriture.objects.count() == 0


def test_passer_ecriture_refuse_un_montant_negatif_ou_nul():
    charge, tresorerie = CompteFactory(), CompteFactory()
    lignes = [
        LigneSaisie(compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("0")),
        LigneSaisie(compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("0")),
    ]

    with pytest.raises(EcritureNonEquilibree):
        services.passer_ecriture(
            journal=Journal.OPERATIONS_DIVERSES, date_ecriture=JOUR, libelle="Test", lignes=lignes
        )


def test_passer_ecriture_refuse_moins_de_deux_lignes():
    charge = CompteFactory()

    with pytest.raises(EcritureNonEquilibree):
        services.passer_ecriture(
            journal=Journal.OPERATIONS_DIVERSES,
            date_ecriture=JOUR,
            libelle="Test",
            lignes=[LigneSaisie(compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("1000"))],
        )


def test_passer_ecriture_refuse_un_compte_inconnu():
    tresorerie = CompteFactory()

    with pytest.raises(CompteInconnu, match="999999"):
        services.passer_ecriture(
            journal=Journal.OPERATIONS_DIVERSES,
            date_ecriture=JOUR,
            libelle="Test",
            lignes=[
                LigneSaisie(compte="999999", sens=SensEcriture.DEBIT, montant=Decimal("1000")),
                LigneSaisie(compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("1000")),
            ],
        )


def test_passer_ecriture_refuse_un_compte_inactif():
    charge, tresorerie = CompteFactory(actif=False), CompteFactory()

    with pytest.raises(CompteInconnu):
        services.passer_ecriture(
            journal=Journal.OPERATIONS_DIVERSES,
            date_ecriture=JOUR,
            libelle="Test",
            lignes=_lignes_equilibrees(charge, tresorerie),
        )


def test_passer_ecriture_idempotente_par_origine():
    charge, tresorerie = CompteFactory(), CompteFactory()
    lignes = _lignes_equilibrees(charge, tresorerie)

    premiere = services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=JOUR, libelle="Test",
        lignes=lignes, origine="TEST", origine_id=42,
    )
    seconde = services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=JOUR, libelle="Autre libellé",
        lignes=lignes, origine="TEST", origine_id=42,
    )

    assert premiere.pk == seconde.pk
    assert LigneEcriture.objects.count() == 2  # pas de doublon


def test_grand_livre_filtre_par_compte_et_periode():
    charge, tresorerie = CompteFactory(), CompteFactory()
    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date(2026, 1, 15), libelle="Janvier",
        lignes=_lignes_equilibrees(charge, tresorerie),
    )
    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date(2026, 6, 15), libelle="Juin",
        lignes=_lignes_equilibrees(charge, tresorerie),
    )

    lignes_annee = services.grand_livre(charge, debut=date(2026, 1, 1), fin=date(2026, 12, 31))
    lignes_premier_semestre = services.grand_livre(charge, debut=date(2026, 1, 1), fin=date(2026, 3, 31))

    assert lignes_annee.count() == 2
    assert lignes_premier_semestre.count() == 1


# --- saisie manuelle d'opérations diverses (Phase 4) ---


def test_creer_une_ecriture_manuelle_ouvre_un_brouillon_sans_numero():
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")

    assert ecriture.statut == StatutEcriture.BROUILLON
    assert ecriture.numero == ""
    assert ecriture.lignes.count() == 0


def test_creer_une_ecriture_manuelle_refuse_un_role_non_autorise():
    with pytest.raises(ActionComptableNonAutorisee):
        services.creer_ecriture_manuelle(
            UserFactory(role=Role.CHARGE_CLIENTELE), date_ecriture=JOUR, libelle="Test"
        )


def test_ajouter_puis_supprimer_une_ligne_sur_un_brouillon():
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")

    ligne = services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )
    assert ecriture.lignes.count() == 1

    services.supprimer_ligne_manuelle(ligne, finances())
    assert ecriture.lignes.count() == 0


def test_valider_une_ecriture_manuelle_equilibree_attribue_un_numero():
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("5000")
    )

    validee = services.valider_ecriture_manuelle(ecriture, direction())

    assert validee.statut == StatutEcriture.VALIDEE
    assert validee.numero.startswith("OD-2026-")
    assert validee.valide_par is not None


def test_valider_une_ecriture_desequilibree_est_refuse():
    charge = CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )

    with pytest.raises(EcritureNonEquilibree):
        services.valider_ecriture_manuelle(ecriture, direction())

    ecriture.refresh_from_db()
    assert ecriture.statut == StatutEcriture.BROUILLON


def test_seule_la_direction_valide_une_ecriture_manuelle_strict():
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("5000")
    )

    with pytest.raises(ActionComptableNonAutorisee):
        services.valider_ecriture_manuelle(ecriture, finances())
    with pytest.raises(ActionComptableNonAutorisee):
        services.valider_ecriture_manuelle(ecriture, UserFactory(role=Role.ADMIN, is_superuser=True))


def test_une_fois_validee_on_ne_peut_plus_ajouter_ni_supprimer_de_ligne():
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )
    ligne = services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("5000")
    )
    services.valider_ecriture_manuelle(ecriture, direction())

    with pytest.raises(EcritureVerrouillee):
        services.ajouter_ligne_manuelle(
            ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("1")
        )
    with pytest.raises(EcritureVerrouillee):
        services.supprimer_ligne_manuelle(ligne, finances())


def test_abandonner_un_brouillon():
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")

    services.abandonner_ecriture_manuelle(ecriture, finances())

    from apps.accounting.models import EcritureComptable

    assert not EcritureComptable.objects.filter(pk=ecriture.pk).exists()
    assert EcritureComptable.all_objects.get(pk=ecriture.pk).is_deleted


def test_on_ne_peut_pas_abandonner_une_ecriture_deja_validee():
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("5000")
    )
    services.valider_ecriture_manuelle(ecriture, direction())

    with pytest.raises(EcritureVerrouillee):
        services.abandonner_ecriture_manuelle(ecriture, finances())


def test_creer_une_ecriture_manuelle_refuse_un_libelle_vide():
    with pytest.raises(EcritureNonEquilibree):
        services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="   ")


def test_ajouter_une_ligne_refuse_un_montant_negatif_ou_nul():
    charge = CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")

    with pytest.raises(EcritureNonEquilibree):
        services.ajouter_ligne_manuelle(
            ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("0")
        )


def test_valider_une_ecriture_avec_deux_lignes_desequilibrees_est_refuse():
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("4000")
    )

    with pytest.raises(EcritureNonEquilibree, match="5000.*4000|4000.*5000"):
        services.valider_ecriture_manuelle(ecriture, direction())
