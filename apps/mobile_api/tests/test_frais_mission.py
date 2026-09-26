"""Déclaration d'un imprévu (R4) depuis l'espace mobile du chauffeur : PWA et API."""

from decimal import Decimal
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient

from apps.missions.models import FraisMission, StatutFraisMission, TypeFraisMission

from .helpers import chauffeur_avec_compte, mission_de

pytestmark = pytest.mark.django_db


def _preuve() -> SimpleUploadedFile:
    return SimpleUploadedFile("preuve.jpg", BytesIO(b"donnees").read(), content_type="image/jpeg")


@pytest.fixture
def chauffeur(client):
    fiche, compte = chauffeur_avec_compte()
    client.force_login(compte)
    return fiche, compte


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


# --- PWA ---


def test_declaration_d_un_imprevu_depuis_le_telephone(client, chauffeur):
    fiche, _ = chauffeur
    mission = mission_de(fiche)

    reponse = client.post(
        reverse("chauffeur:imprevu"),
        {"mission": mission.pk, "montant": "15000", "description": "Panne moteur", "justificatif": _preuve()},
        follow=True,
    )

    frais = FraisMission.objects.get()
    assert frais.mission == mission and frais.chauffeur == fiche and frais.montant == Decimal("15000")
    assert frais.statut == StatutFraisMission.PREVU
    assert any("Parc Auto est prévenu" in m for m in _messages(reponse))


def test_un_imprevu_sans_justificatif_est_refuse(client, chauffeur):
    fiche, _ = chauffeur
    mission = mission_de(fiche)

    client.post(reverse("chauffeur:imprevu"), {"mission": mission.pk, "montant": "15000", "description": "x"})

    assert not FraisMission.objects.exists()


def test_imprevu_sur_la_mission_d_un_autre_chauffeur_refuse(client, chauffeur):
    from apps.drivers.tests.factories import ChauffeurFactory

    autre_mission = mission_de(ChauffeurFactory())

    client.post(
        reverse("chauffeur:imprevu"),
        {"mission": autre_mission.pk, "montant": "1000", "description": "x", "justificatif": _preuve()},
    )

    assert not FraisMission.objects.exists()


# --- API ---


def _api(compte):
    client = APIClient()
    client.force_authenticate(compte)
    return client


def test_declaration_d_un_imprevu_par_l_api(chauffeur):
    fiche, compte = chauffeur
    mission = mission_de(fiche)
    api = _api(compte)

    reponse = api.post(
        reverse("api:mobile:imprevus"),
        {"mission": mission.pk, "montant": "15000", "description": "Panne", "justificatif": _preuve()},
        format="multipart",
    )

    assert reponse.status_code == 201
    assert reponse.data["type_frais"] == TypeFraisMission.IMPREVU
    assert reponse.data["statut"] == StatutFraisMission.PREVU
    assert [f["id"] for f in api.get(reverse("api:mobile:imprevus")).data] == [reponse.data["id"]]


def test_imprevu_sans_preuve_par_l_api_est_refuse(chauffeur):
    fiche, compte = chauffeur
    mission = mission_de(fiche)
    api = _api(compte)

    reponse = api.post(
        reverse("api:mobile:imprevus"),
        {"mission": mission.pk, "montant": "15000", "description": "x"},
        format="multipart",
    )

    assert reponse.status_code == 400
