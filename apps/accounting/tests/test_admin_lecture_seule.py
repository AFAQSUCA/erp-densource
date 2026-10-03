"""Audit ACC-01 : le grand livre est en lecture seule dans l'admin, et un sens inconnu est refusé."""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounting import services
from apps.accounting.exceptions import EcritureNonEquilibree
from apps.accounting.models import Compte, EcritureComptable, Journal, SensEcriture, StatutEcriture
from apps.accounting.services import LigneSaisie
from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _ecriture():
    return services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date(2026, 3, 1), libelle="Apport",
        lignes=[
            LigneSaisie(compte="571000", sens=SensEcriture.DEBIT, montant=Decimal("500")),
            LigneSaisie(compte="101000", sens=SensEcriture.CREDIT, montant=Decimal("500")),
        ],
    )


@pytest.fixture
def admin_client(client):
    client.force_login(UserFactory(role=Role.ADMIN, is_staff=True, is_superuser=True))
    return client


def test_un_sens_inconnu_est_refuse_au_lieu_d_etre_stocke_hors_des_totaux():
    with pytest.raises(EcritureNonEquilibree, match="Sens inconnu"):
        services.passer_ecriture(
            journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date(2026, 3, 1), libelle="Piège",
            lignes=[
                LigneSaisie(compte="571000", sens=SensEcriture.DEBIT, montant=Decimal("500")),
                LigneSaisie(compte="101000", sens=SensEcriture.CREDIT, montant=Decimal("500")),
                LigneSaisie(compte="108000", sens="X", montant=Decimal("999")),
            ],
        )

    assert not EcritureComptable.objects.exists()


def test_l_admin_ne_permet_pas_de_creer_ni_de_modifier_une_ecriture(admin_client):
    ecriture = _ecriture()

    ajout = admin_client.get(reverse("admin:accounting_ecriturecomptable_add"))
    modification = admin_client.post(
        reverse("admin:accounting_ecriturecomptable_change", args=[ecriture.pk]), {"statut": StatutEcriture.BROUILLON}
    )

    assert ajout.status_code == 403
    ecriture.refresh_from_db()
    assert ecriture.statut == StatutEcriture.VALIDEE
    assert modification.status_code in (200, 302, 403)  # jamais une modification appliquée


def test_l_admin_affiche_une_ecriture_en_lecture_seule(admin_client):
    ecriture = _ecriture()

    reponse = admin_client.get(reverse("admin:accounting_ecriturecomptable_change", args=[ecriture.pk]))

    assert reponse.status_code == 200
    assert b'name="_save"' not in reponse.content  # pas de bouton « Enregistrer »


def test_l_admin_ne_peut_pas_rouvrir_un_exercice(admin_client):
    exercice = services.exercice_pour(date(2025, 6, 1))
    exercice.statut = "CLOTURE"
    exercice.save(update_fields=["statut", "updated_at"])

    admin_client.post(
        reverse("admin:accounting_exercicecomptable_change", args=[exercice.pk]), {"statut": "OUVERT"}
    )

    exercice.refresh_from_db()
    assert exercice.statut == "CLOTURE"


def test_le_numero_et_la_nature_d_un_compte_ne_se_modifient_plus_dans_l_admin(admin_client):
    compte = Compte.objects.get(numero="571000")

    admin_client.post(
        reverse("admin:accounting_compte_change", args=[compte.pk]),
        {"numero": "999999", "libelle": "Caisse", "nature": "CHARGE", "actif": "on"},
    )

    compte.refresh_from_db()
    assert (compte.numero, compte.nature) == ("571000", "ACTIF")
