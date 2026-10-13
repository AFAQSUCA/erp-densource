"""Redis en panne : le tableau de bord et la connexion continuent de fonctionner — audit TECH-65."""

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse

from apps.accounts import throttle
from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "Test-Passw0rd!"


@pytest.fixture
def cache_en_panne(monkeypatch):
    def panne(*args, **kwargs):
        raise ConnectionError("Redis injoignable")

    for methode in ("get", "set", "delete", "get_or_set"):
        monkeypatch.setattr(cache, methode, panne)


@override_settings(DASHBOARD_CACHE_SECONDS=60)
def test_le_tableau_de_bord_s_affiche_sans_cache(client, cache_en_panne):
    client.force_login(UserFactory(role=Role.RH))

    assert client.get(reverse("home")).status_code == 200


def test_la_connexion_reste_possible_et_les_compteurs_ne_plantent_pas(client, cache_en_panne, rf):
    UserFactory(username="awa", role=Role.RH)
    requete = rf.post("/")

    throttle.connexion_enregistrer_echec(requete, "awa")
    assert throttle.connexion_secondes_restantes(requete, "awa") == 0
    reponse = client.post(reverse("accounts:login"), {"username": "awa", "password": MOT_DE_PASSE})

    assert reponse.status_code == 302 and "_auth_user_id" in client.session
