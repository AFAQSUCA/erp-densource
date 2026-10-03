"""Écriture de clôture : le résultat d'un exercice est viré au compte 120000, le bilan du 2e exercice reste
équilibré (audit : bilan déséquilibré dès le 2e exercice)."""

from datetime import date
from decimal import Decimal

import pytest

from apps.accounting import services
from apps.accounting.exceptions import CompteInconnu, ContrePassationImpossible
from apps.accounting.models import Compte, EcritureComptable, Journal, SensEcriture, StatutExercice
from apps.accounting.services import LigneSaisie
from apps.billing.tests.helpers import direction

pytestmark = pytest.mark.django_db

JOUR_2025 = date(2025, 6, 1)
JOUR_2026 = date(2026, 6, 1)


def _vente(jour, montant):
    services.passer_ecriture(
        journal=Journal.VENTES, date_ecriture=jour, libelle="Vente",
        lignes=[
            LigneSaisie(compte="411000", sens=SensEcriture.DEBIT, montant=Decimal(montant)),
            LigneSaisie(compte="706100", sens=SensEcriture.CREDIT, montant=Decimal(montant)),
        ],
    )


def _charge(jour, montant):
    services.passer_ecriture(
        journal=Journal.CAISSE, date_ecriture=jour, libelle="Carburant",
        lignes=[
            LigneSaisie(compte="605100", sens=SensEcriture.DEBIT, montant=Decimal(montant)),
            LigneSaisie(compte="571000", sens=SensEcriture.CREDIT, montant=Decimal(montant)),
        ],
    )


def _cloturer(jour):
    exercice = services.exercice_pour(jour)
    services.cloturer_exercice(exercice, direction())
    exercice.refresh_from_db()
    return exercice


def _ecriture_de_cloture(exercice):
    return EcritureComptable.objects.get(origine=services.ORIGINE_CLOTURE, origine_id=exercice.pk)


def _lignes(ecriture):
    return {(l.compte.numero, l.sens): l.montant for l in ecriture.lignes.select_related("compte")}


def test_la_cloture_vire_un_benefice_au_credit_du_120000():
    _vente(JOUR_2025, "1000")
    _charge(JOUR_2025, "300")

    exercice = _cloturer(JOUR_2025)

    ecriture = _ecriture_de_cloture(exercice)
    assert exercice.statut == StatutExercice.CLOTURE
    assert ecriture.date_ecriture == date(2025, 12, 31)
    assert ecriture.journal == Journal.OPERATIONS_DIVERSES
    assert _lignes(ecriture) == {
        ("706100", SensEcriture.DEBIT): Decimal("1000"),
        ("605100", SensEcriture.CREDIT): Decimal("300"),
        ("120000", SensEcriture.CREDIT): Decimal("700"),
    }


def test_la_cloture_vire_une_perte_au_debit_du_120000():
    _vente(JOUR_2025, "200")
    _charge(JOUR_2025, "500")

    ecriture = _ecriture_de_cloture(_cloturer(JOUR_2025))

    assert _lignes(ecriture)[("120000", SensEcriture.DEBIT)] == Decimal("300")


def test_un_exercice_sans_charge_ni_produit_ne_pose_aucune_ecriture_de_cloture():
    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=JOUR_2025, libelle="Apport",
        lignes=[
            LigneSaisie(compte="571000", sens=SensEcriture.DEBIT, montant=Decimal("900")),
            LigneSaisie(compte="101000", sens=SensEcriture.CREDIT, montant=Decimal("900")),
        ],
    )

    _cloturer(JOUR_2025)

    assert not EcritureComptable.objects.filter(origine=services.ORIGINE_CLOTURE).exists()


def test_le_bilan_du_2e_exercice_reste_equilibre():
    """Le défaut d'origine : le résultat 2025 disparaissait du passif du bilan 2026."""
    _vente(JOUR_2025, "1000")
    _charge(JOUR_2025, "300")
    _cloturer(JOUR_2025)
    _vente(JOUR_2026, "400")
    _charge(JOUR_2026, "100")

    rapport = services.bilan(services.exercice_pour(JOUR_2026))

    passif = {l["compte__numero"]: l["montant"] for l in rapport["passif"]}
    assert passif["120000"] == Decimal("700")  # résultat 2025 reporté
    assert rapport["resultat_net"] == Decimal("300")  # résultat 2026, pas encore viré
    assert rapport["total_actif"] == rapport["total_passif_avec_resultat"] == Decimal("1000")


def test_le_bilan_de_l_exercice_cloture_ne_compte_pas_deux_fois_son_resultat():
    _vente(JOUR_2025, "1000")
    _charge(JOUR_2025, "300")
    exercice = _cloturer(JOUR_2025)

    rapport = services.bilan(exercice)

    assert rapport["resultat_net"] == Decimal("0")
    assert rapport["total_actif"] == rapport["total_passif_avec_resultat"] == Decimal("700")


def test_le_bilan_s_equilibre_aussi_sans_cloture_des_exercices_precedents():
    _vente(JOUR_2025, "1000")
    _vente(JOUR_2026, "400")  # 2025 jamais clôturé

    rapport = services.bilan(services.exercice_pour(JOUR_2026))

    assert rapport["total_actif"] == rapport["total_passif_avec_resultat"] == Decimal("1400")


def test_le_compte_de_resultat_d_un_exercice_cloture_garde_son_activite():
    _vente(JOUR_2025, "1000")
    _charge(JOUR_2025, "300")
    exercice = _cloturer(JOUR_2025)

    rapport = services.compte_de_resultat(exercice)

    assert rapport["total_produits"] == Decimal("1000")
    assert rapport["total_charges"] == Decimal("300")
    assert rapport["resultat_net"] == Decimal("700")


def test_la_balance_ignore_la_cloture_par_defaut_et_reste_equilibree():
    _vente(JOUR_2025, "1000")
    _cloturer(JOUR_2025)

    sans = {l["compte__numero"]: l for l in services.balance()}
    avec = {l["compte__numero"]: l for l in services.balance(avec_cloture=True)}

    assert sans["706100"]["total_credit"] == Decimal("1000") and sans["706100"]["total_debit"] == 0
    assert "120000" not in sans
    assert avec["706100"]["solde_debiteur"] == avec["706100"]["solde_crediteur"] == 0
    assert avec["120000"]["solde_crediteur"] == Decimal("1000")
    for balance in (sans.values(), avec.values()):
        assert sum(l["total_debit"] for l in balance) == sum(l["total_credit"] for l in balance)


def test_l_ecriture_de_cloture_ne_se_contre_passe_pas():
    _vente(JOUR_2025, "1000")
    ecriture = _ecriture_de_cloture(_cloturer(JOUR_2025))

    with pytest.raises(ContrePassationImpossible, match="ne se rouvre jamais"):
        services.contre_passer(ecriture)


def test_ecriture_de_cloture_est_idempotente():
    _vente(JOUR_2025, "1000")
    exercice = _cloturer(JOUR_2025)

    de_nouveau = services.ecriture_de_cloture(exercice)

    assert de_nouveau == _ecriture_de_cloture(exercice)
    assert EcritureComptable.objects.filter(origine=services.ORIGINE_CLOTURE).count() == 1


def test_une_cloture_impossible_faute_de_compte_120000_ne_clot_rien():
    _vente(JOUR_2025, "1000")
    Compte.objects.filter(numero="120000").update(actif=False)
    exercice = services.exercice_pour(JOUR_2025)

    with pytest.raises(CompteInconnu, match="120000"):
        services.cloturer_exercice(exercice, direction())

    exercice.refresh_from_db()
    assert exercice.statut == StatutExercice.OUVERT
    assert not EcritureComptable.objects.filter(origine=services.ORIGINE_CLOTURE).exists()


# --- reprise des exercices clôturés avant ce lot ---


def _cloture_sans_ecriture(jour):
    """Un exercice clôturé à l'ancienne : statut posé sans écriture de clôture."""
    exercice = services.exercice_pour(jour)
    exercice.statut = StatutExercice.CLOTURE
    exercice.save(update_fields=["statut", "updated_at"])
    return exercice


def test_la_commande_de_reprise_pose_la_cloture_manquante_et_equilibre_le_bilan():
    from django.core.management import call_command

    _vente(JOUR_2025, "1000")
    _cloture_sans_ecriture(JOUR_2025)

    call_command("ecrire_clotures_historiques")
    call_command("ecrire_clotures_historiques")  # rejouable

    assert EcritureComptable.objects.filter(origine=services.ORIGINE_CLOTURE).count() == 1
    _vente(JOUR_2026, "400")
    rapport = services.bilan(services.exercice_pour(JOUR_2026))
    assert rapport["total_actif"] == rapport["total_passif_avec_resultat"] == Decimal("1400")


def test_la_commande_de_reprise_en_simulation_n_ecrit_rien():
    from django.core.management import call_command

    _vente(JOUR_2025, "1000")
    _cloture_sans_ecriture(JOUR_2025)

    call_command("ecrire_clotures_historiques", "--dry-run")

    assert not EcritureComptable.objects.filter(origine=services.ORIGINE_CLOTURE).exists()
