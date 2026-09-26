"""Écrans de la prévision de trésorerie des missions (R4) : accès, planification, validation."""

from decimal import Decimal
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.missions import terrain as missions_terrain
from apps.missions.models import StatutFraisMission, TypeFraisMission

from .test_frais_mission import _chauffeur, _finances, _mission_affectee, _parcauto

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    compte = UserFactory(role=role)
    client.force_login(compte)
    return compte


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.PARCAUTO, Role.FINANCES])
def test_les_frais_de_mission_sont_accessibles_aux_roles_concernes(client, role):
    _connecte(client, role)
    mission = _mission_affectee()

    for url in (reverse("missions:frais_liste"), reverse("missions:frais", args=[mission.pk])):
        assert client.get(url).status_code == 200, url


@pytest.mark.parametrize("role", [Role.RH, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR])
def test_les_frais_de_mission_sont_interdits_aux_autres_roles(client, role):
    _connecte(client, role)
    mission = _mission_affectee()

    assert client.get(reverse("missions:frais_liste")).status_code == 403
    assert client.get(reverse("missions:frais", args=[mission.pk])).status_code == 403


def test_le_lien_frais_de_mission_n_apparait_pas_pour_le_charge_clientele(client):
    mission = _mission_affectee()
    _connecte(client, Role.DIRECTION)
    assert "Frais de mission" in client.get(reverse("missions:detail", args=[mission.pk])).content.decode()

    _connecte(client, Role.CHARGE_CLIENTELE)
    assert "Frais de mission" not in client.get(reverse("missions:detail", args=[mission.pk])).content.decode()


def test_le_parc_auto_planifie_une_avance_via_l_ecran(client):
    mission = _mission_affectee()
    _connecte(client, Role.PARCAUTO)

    reponse = client.post(
        reverse("missions:frais_planifier", args=[mission.pk]),
        {"type_frais": TypeFraisMission.AVANCE_ROUTE, "montant": "50000", "description": "Avance essence"},
    )

    assert reponse.status_code == 302
    assert mission.frais.filter(type_frais=TypeFraisMission.AVANCE_ROUTE).exists()


def test_la_finance_confirme_une_avance_via_l_ecran(client):
    mission = _mission_affectee()
    frais = missions_terrain.planifier_frais(
        mission, _parcauto(), type_frais=TypeFraisMission.AVANCE_ROUTE, montant=Decimal("50000")
    )
    _connecte(client, Role.FINANCES)

    reponse = client.post(reverse("missions:frais_valider_finances", args=[frais.pk]))

    assert reponse.status_code == 302
    frais.refresh_from_db()
    assert frais.statut == StatutFraisMission.CONFIRME


def test_le_parc_auto_valide_puis_la_finance_confirme_un_imprevu_via_les_ecrans(client):
    chauffeur = _chauffeur()
    mission = _mission_affectee(chauffeur)
    preuve = SimpleUploadedFile("p.jpg", BytesIO(b"x").read(), content_type="image/jpeg")
    frais = missions_terrain.declarer_imprevu(mission, chauffeur, montant=Decimal("9000"), justificatif=preuve)

    _connecte(client, Role.PARCAUTO)
    reponse = client.post(reverse("missions:frais_valider_parcauto", args=[frais.pk]))
    assert reponse.status_code == 302
    frais.refresh_from_db()
    assert frais.statut == StatutFraisMission.PREVU and frais.valide_parcauto_par is not None

    _connecte(client, Role.FINANCES)
    reponse = client.post(reverse("missions:frais_valider_finances", args=[frais.pk]))
    assert reponse.status_code == 302
    frais.refresh_from_db()
    assert frais.statut == StatutFraisMission.CONFIRME


def test_rejeter_un_frais_via_l_ecran(client):
    mission = _mission_affectee()
    frais = missions_terrain.planifier_frais(
        mission, _parcauto(), type_frais=TypeFraisMission.AVANCE_ROUTE, montant=Decimal("50000")
    )
    _connecte(client, Role.FINANCES)

    reponse = client.post(reverse("missions:frais_rejeter", args=[frais.pk]), {"motif": "Montant excessif"})

    assert reponse.status_code == 302
    frais.refresh_from_db()
    assert frais.statut == StatutFraisMission.REJETE


def test_le_rapport_de_mission_s_imprime(client):
    mission = _mission_affectee()
    _connecte(client, Role.DIRECTION)

    reponse = client.get(reverse("missions:frais_imprimer", args=[mission.pk]))

    assert reponse.status_code == 200
