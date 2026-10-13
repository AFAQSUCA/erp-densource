"""Anti force brute étendu à l'API et à « mot de passe oublié » — audit TECH-46."""

from pathlib import Path

import pytest
from django.core import mail
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import Role

from .factories import UserFactory

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "Test-Passw0rd!"


@pytest.fixture(autouse=True)
def cache_vide():
    cache.clear()


def _api_connexion(api, identifiant, mot_de_passe="faux"):
    return api.post(reverse("api:token"), {"username": identifiant, "password": mot_de_passe}, format="json")


def test_l_api_applique_le_verrou_de_compte_meme_avec_le_bon_mot_de_passe():
    """Avant, l'API vérifiait encore le mot de passe d'un identifiant bloqué sur le site : la force brute passait par
    là."""
    UserFactory(username="awa", role=Role.CHAUFFEUR)
    api = APIClient()
    for _ in range(5):
        assert _api_connexion(api, "awa").status_code == 401

    reponse = _api_connexion(api, "awa", MOT_DE_PASSE)

    assert reponse.status_code == 429
    assert "Trop de tentatives" in str(reponse.data)


def test_les_echecs_de_l_api_comptent_aussi_pour_le_site(client):
    UserFactory(username="awa", role=Role.RH)
    api = APIClient()
    for _ in range(5):
        _api_connexion(api, "awa")

    reponse = client.post(reverse("accounts:login"), {"username": "awa", "password": MOT_DE_PASSE})

    assert reponse.status_code == 429


def test_une_connexion_api_reussie_efface_les_echecs_du_compte():
    UserFactory(username="awa", role=Role.CHAUFFEUR)
    api = APIClient()
    for _ in range(4):
        _api_connexion(api, "awa")
    assert _api_connexion(api, "awa", MOT_DE_PASSE).status_code == 200

    for _ in range(4):
        assert _api_connexion(api, "awa").status_code == 401  # le compteur est reparti de zéro


def _demande(client, email):
    return client.post(reverse("accounts:password_reset"), {"email": email})


def test_mot_de_passe_oublie_est_limite_par_adresse_e_mail(client):
    UserFactory(email="awa@densource.ci")
    for _ in range(3):
        assert _demande(client, "awa@densource.ci").status_code == 302

    reponse = _demande(client, "awa@densource.ci")

    assert reponse.status_code == 429 and "Trop de demandes" in reponse.content.decode()
    assert len(mail.outbox) == 3  # pas de quatrième e-mail


def test_mot_de_passe_oublie_est_limite_par_adresse_ip(client):
    for numero in range(5):
        assert _demande(client, f"inconnu{numero}@exemple.ci").status_code == 302

    assert _demande(client, "encore@exemple.ci").status_code == 429


def test_nginx_limite_le_debit_des_pages_d_authentification():
    conf = (Path(__file__).resolve().parents[3] / "nginx" / "nginx.conf").read_text(encoding="utf-8")

    assert "limit_req_zone" in conf and "zone=authentification" in conf
    for chemin in ("connexion", "mot-de-passe", "api/v1/auth"):
        assert chemin in conf
