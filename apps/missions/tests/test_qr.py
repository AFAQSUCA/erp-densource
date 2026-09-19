"""Image QR des codes d'une mission : droits, contenu, secret."""

import io

import pytest
import qrcode
from django.test import Client
from django.urls import reverse
from PIL import Image

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.missions.models import StatutMission

from .factories import MissionFactory

pytestmark = pytest.mark.django_db


def _png(code):
    tampon = io.BytesIO()
    qrcode.make(code, box_size=8, border=2).save(tampon, format="PNG")
    return tampon.getvalue()


def _mission(statut=StatutMission.AFFECTEE):
    from apps.drivers.tests.factories import ChauffeurFactory
    from apps.fleet.tests.factories import VehiculeFactory

    return MissionFactory(
        statut=statut, vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory(),
        code_expediteur="ABCD2345", code_destinataire="WXYZ6789",
    )


def test_le_qr_est_une_image_png_qui_ne_contient_que_le_code(client):
    client.force_login(UserFactory(role=Role.DIRECTION))
    mission = _mission()

    exp = client.get(reverse("missions:qr", args=[mission.pk, "expediteur"]))
    dest = client.get(reverse("missions:qr", args=[mission.pk, "destinataire"]))

    assert exp.status_code == 200 and exp["Content-Type"] == "image/png"
    assert exp.content.startswith(b"\x89PNG") and Image.open(io.BytesIO(exp.content)).size[0] > 100
    assert exp.content == _png("ABCD2345") and dest.content == _png("WXYZ6789")  # contenu = le code seul
    assert exp.content != dest.content


def test_le_qr_n_est_jamais_mis_en_cache(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    mission = _mission()

    reponse = client.get(reverse("missions:qr", args=[mission.pk, "expediteur"]))

    assert reponse["Cache-Control"] == "no-store, private"


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.CHARGE_CLIENTELE])
def test_les_roles_qui_voient_les_codes_voient_le_qr(client, role):
    client.force_login(UserFactory(role=role))
    mission = _mission()

    assert client.get(reverse("missions:qr", args=[mission.pk, "expediteur"])).status_code == 200


@pytest.mark.parametrize("role", [Role.CHAUFFEUR, Role.PARCAUTO, Role.RH, Role.FINANCES])
def test_les_autres_roles_n_obtiennent_pas_le_qr(client, role):
    client.force_login(UserFactory(role=role))
    mission = _mission()

    assert client.get(reverse("missions:qr", args=[mission.pk, "expediteur"])).status_code == 403


def test_le_qr_exige_la_connexion(client):
    mission = _mission()

    assert client.get(reverse("missions:qr", args=[mission.pk, "expediteur"])).status_code == 302


def test_un_qr_inutile_ou_inconnu_est_un_404(client):
    client.force_login(UserFactory(role=Role.DIRECTION))
    recuperee = _mission(StatutMission.EN_COURS_COLIS_RECUPERE)
    livree = _mission(StatutMission.LIVREE)

    assert client.get(reverse("missions:qr", args=[recuperee.pk, "expediteur"])).status_code == 404  # colis déjà récupéré
    assert client.get(reverse("missions:qr", args=[recuperee.pk, "destinataire"])).status_code == 200
    assert client.get(reverse("missions:qr", args=[livree.pk, "destinataire"])).status_code == 404
    assert client.get(reverse("missions:qr", args=[recuperee.pk, "autre"])).status_code == 404
    assert client.get(reverse("missions:qr", args=[99999, "expediteur"])).status_code == 404


def test_la_fiche_de_la_mission_affiche_les_qr_pour_le_bon_role(client):
    mission = _mission()

    client.force_login(UserFactory(role=Role.DIRECTION))
    texte = client.get(reverse("missions:detail", args=[mission.pk])).content.decode()
    assert reverse("missions:qr", args=[mission.pk, "expediteur"]) in texte
    assert reverse("missions:qr", args=[mission.pk, "destinataire"]) in texte
    assert "Code QR de l&#x27;expéditeur" in texte or "Code QR de l'expéditeur" in texte


def test_le_qr_ne_fuite_pas_dans_la_fiche_des_roles_sans_droit(client):
    mission = _mission()
    client.force_login(UserFactory(role=Role.ADMIN))
    assert "/qr/" in client.get(reverse("missions:detail", args=[mission.pk])).content.decode()

    http = Client()
    http.force_login(UserFactory(role=Role.CHAUFFEUR))
    assert http.get(reverse("missions:detail", args=[mission.pk])).status_code == 403
