"""Exercice 5 — La Finance et la RH consultent les missions (formation/exercices/05-missions-finance-rh).

À copier dans apps/missions/tests/ puis : python -m pytest apps/missions/tests/test_exercice_05.py -q --no-cov
"""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.missions import permissions
from apps.missions.tests.factories import MissionFactory

pytestmark = pytest.mark.django_db

LECTEURS = [Role.FINANCES, Role.RH]  # avenant R8 : la RH a les droits de la FINANCES


@pytest.mark.parametrize("role", LECTEURS)
def test_la_finance_et_la_rh_ouvrent_la_liste_et_la_fiche_des_missions(client, role):
    mission = MissionFactory()
    client.force_login(UserFactory(role=role))

    assert client.get(reverse("missions:liste")).status_code == 200
    assert client.get(reverse("missions:detail", args=[mission.pk])).status_code == 200


@pytest.mark.parametrize("role", LECTEURS)
def test_elles_ne_voient_pas_les_codes_et_ne_creent_pas_de_mission(client, role):
    mission = MissionFactory()
    client.force_login(UserFactory(role=role))

    assert mission.code_expediteur not in client.get(reverse("missions:detail", args=[mission.pk])).content.decode()
    assert client.get(reverse("missions:creer")).status_code == 403
    assert role not in permissions.VOIR_CODES


@pytest.mark.parametrize("role", LECTEURS)
def test_l_api_suit_le_meme_droit(role):
    api = APIClient()
    api.force_authenticate(UserFactory(role=role))

    assert api.get(reverse("api:mission-list")).status_code == 200


def test_le_chauffeur_reste_sans_acces(client):
    client.force_login(UserFactory(role=Role.CHARGE_CLIENTELE))
    assert client.get(reverse("missions:liste")).status_code == 200  # inchangé
    assert Role.CHAUFFEUR not in permissions.CONSULTATION
