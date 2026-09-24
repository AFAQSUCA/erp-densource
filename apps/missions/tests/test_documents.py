"""PDF des codes d'une mission : une page par partie, jamais un code devenu inutile."""

import re

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.missions import documents, permissions
from apps.missions.models import StatutMission

from .factories import MissionFactory

pytestmark = pytest.mark.django_db

CODES = {"expediteur": "ABCD2345", "destinataire": "WXYZ6789"}


def _pages(pdf: bytes) -> int:
    return len(re.findall(rb"/Type /Page(?![s\w])", pdf))


def test_le_pdf_a_une_page_par_partie_avec_son_code_et_son_qr():
    mission = MissionFactory(numero="MIS-2026-0042")

    pdf = documents.generer_pdf_codes(mission, CODES)

    assert pdf.startswith(b"%PDF")
    assert _pages(pdf) == 2
    assert b"MIS-2026-0042" in pdf
    # chaque code sert de contenu à son QR ; à l'écran il est écrit espacé (« A B C D … »)
    assert b"(A B C D 2 3 4 5) Tj" in pdf and b"(W X Y Z 6 7 8 9) Tj" in pdf
    assert pdf.count(b"/Subtype /Image") >= 2  # le logo et les QR


def test_un_seul_code_utile_donne_une_seule_page():
    pdf = documents.generer_pdf_codes(MissionFactory(), {"expediteur": None, "destinataire": "WXYZ6789"})

    assert _pages(pdf) == 1
    assert b"ABCD2345" not in pdf and b"A B C D 2 3 4 5" not in pdf  # le code de l'autre partie n'y est pas


def test_aucun_code_utile_est_une_erreur():
    with pytest.raises(ValueError):
        documents.generer_pdf_codes(MissionFactory(), {"expediteur": None, "destinataire": None})


def test_l_entete_porte_le_nom_de_l_entreprise(settings):
    settings.ENTREPRISE_NOM = "Transport Essai SA"
    settings.ENTREPRISE_ADRESSE = "Zone 4, Abidjan"

    pdf = documents.generer_pdf_codes(MissionFactory(), CODES)

    assert b"Transport Essai SA" in pdf and b"Zone 4, Abidjan" in pdf


# --- écran ---


@pytest.mark.parametrize("role", sorted(permissions.VOIR_CODES))
def test_les_roles_qui_voient_les_codes_telechargent_le_pdf(client, role):
    client.force_login(UserFactory(role=role))
    mission = MissionFactory()

    reponse = client.get(reverse("missions:codes_pdf", args=[mission.pk]))

    assert reponse.status_code == 200
    assert reponse["Content-Type"] == "application/pdf"
    assert reponse["Content-Disposition"] == f'attachment; filename="codes-{mission.numero}.pdf"'
    assert "no-store" in reponse["Cache-Control"]


@pytest.mark.parametrize("role", [Role.CHAUFFEUR, Role.RH, Role.PARCAUTO, Role.FINANCES])
def test_les_autres_roles_n_ont_pas_le_pdf(client, role):
    client.force_login(UserFactory(role=role))

    assert client.get(reverse("missions:codes_pdf", args=[MissionFactory().pk])).status_code == 403


def test_le_pdf_ne_contient_plus_le_code_expediteur_apres_la_recuperation(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    mission = MissionFactory(
        statut=StatutMission.EN_COURS_COLIS_RECUPERE, vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory(), km_depart=1000
    )

    pdf = client.get(reverse("missions:codes_pdf", args=[mission.pk])).content

    assert _pages(pdf) == 1
    assert b"A B C D 2 3 4 5" not in pdf and b"W X Y Z 6 7 8 9" in pdf


def test_le_pdf_est_introuvable_une_fois_la_mission_livree(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    mission = MissionFactory(
        statut=StatutMission.LIVREE, vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory(), km_depart=1000, km_arrivee=1200
    )

    assert client.get(reverse("missions:codes_pdf", args=[mission.pk])).status_code == 404


def test_la_fiche_propose_le_telechargement_du_pdf(client):
    client.force_login(UserFactory(role=Role.CHARGE_CLIENTELE))
    mission = MissionFactory()

    contenu = client.get(reverse("missions:detail", args=[mission.pk])).content.decode()

    assert reverse("missions:codes_pdf", args=[mission.pk]) in contenu
