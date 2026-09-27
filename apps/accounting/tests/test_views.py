"""Écrans de la saisie manuelle d'opérations diverses (Phase 4)."""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounting import services
from apps.accounting.models import EcritureComptable, SensEcriture, StatutEcriture

from .factories import CompteFactory

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    compte = UserFactory(role=role)
    client.force_login(compte)
    return compte


def _brouillon(**kwargs):
    return services.creer_ecriture_manuelle(
        UserFactory(role=Role.FINANCES), date_ecriture="2026-09-05", libelle="Test OD", **kwargs
    )


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.FINANCES, Role.RH])
def test_la_liste_est_accessible_aux_roles_de_consultation(client, role):
    _connecte(client, role)

    assert client.get(reverse("accounting:ecritures_manuelles")).status_code == 200


@pytest.mark.parametrize("role", [Role.PARCAUTO, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR])
def test_la_liste_est_interdite_aux_autres_roles(client, role):
    _connecte(client, role)

    assert client.get(reverse("accounting:ecritures_manuelles")).status_code == 403


@pytest.mark.parametrize("role", [Role.PARCAUTO, Role.CHAUFFEUR])
def test_seuls_les_roles_de_saisie_creent_une_ecriture(client, role):
    _connecte(client, role)

    assert client.get(reverse("accounting:ecriture_manuelle_nouvelle")).status_code == 403


def test_creer_une_ecriture_manuelle_via_l_ecran(client):
    _connecte(client, Role.FINANCES)

    reponse = client.post(
        reverse("accounting:ecriture_manuelle_nouvelle"),
        {"date_ecriture": "2026-09-05", "libelle": "Régularisation caisse"},
    )

    ecriture = EcritureComptable.objects.get()
    assert reponse.status_code == 302
    assert ecriture.statut == StatutEcriture.BROUILLON
    assert ecriture.libelle == "Régularisation caisse"


def test_ajouter_puis_supprimer_une_ligne_via_l_ecran(client):
    _connecte(client, Role.FINANCES)
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = _brouillon()

    client.post(
        reverse("accounting:ligne_ajouter", args=[ecriture.pk]),
        {"compte": charge.numero, "sens": SensEcriture.DEBIT, "montant": "5000", "libelle": ""},
    )
    assert ecriture.lignes.count() == 1
    ligne = ecriture.lignes.first()

    reponse = client.post(reverse("accounting:ligne_supprimer", args=[ecriture.pk, ligne.pk]))

    assert reponse.status_code == 302
    assert ecriture.lignes.count() == 0


def test_la_fiche_propose_la_validation_a_la_direction_une_fois_equilibree(client):
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = _brouillon()
    services.ajouter_ligne_manuelle(
        ecriture, UserFactory(role=Role.FINANCES), compte=charge.numero, sens=SensEcriture.DEBIT,
        montant=Decimal("5000"),
    )
    services.ajouter_ligne_manuelle(
        ecriture, UserFactory(role=Role.FINANCES), compte=tresorerie.numero, sens=SensEcriture.CREDIT,
        montant=Decimal("5000"),
    )

    _connecte(client, Role.DIRECTION)
    page = client.get(reverse("accounting:ecriture_manuelle", args=[ecriture.pk])).content.decode()
    assert reverse("accounting:ecriture_manuelle_valider", args=[ecriture.pk]) in page

    _connecte(client, Role.FINANCES)
    page = client.get(reverse("accounting:ecriture_manuelle", args=[ecriture.pk])).content.decode()
    assert reverse("accounting:ecriture_manuelle_valider", args=[ecriture.pk]) not in page


def test_valider_via_l_ecran_est_reserve_a_la_direction(client):
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = _brouillon()
    services.ajouter_ligne_manuelle(
        ecriture, UserFactory(role=Role.FINANCES), compte=charge.numero, sens=SensEcriture.DEBIT,
        montant=Decimal("5000"),
    )
    services.ajouter_ligne_manuelle(
        ecriture, UserFactory(role=Role.FINANCES), compte=tresorerie.numero, sens=SensEcriture.CREDIT,
        montant=Decimal("5000"),
    )

    _connecte(client, Role.FINANCES)
    assert client.post(reverse("accounting:ecriture_manuelle_valider", args=[ecriture.pk])).status_code == 403

    _connecte(client, Role.DIRECTION)
    reponse = client.post(reverse("accounting:ecriture_manuelle_valider", args=[ecriture.pk]))
    assert reponse.status_code == 302
    ecriture.refresh_from_db()
    assert ecriture.statut == StatutEcriture.VALIDEE


def test_abandonner_via_l_ecran(client):
    _connecte(client, Role.FINANCES)
    ecriture = _brouillon()

    reponse = client.post(reverse("accounting:ecriture_manuelle_abandonner", args=[ecriture.pk]))

    assert reponse.status_code == 302
    assert not EcritureComptable.objects.filter(pk=ecriture.pk).exists()
