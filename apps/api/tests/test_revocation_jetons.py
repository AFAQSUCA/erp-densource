"""Jetons de l'API mobile : révoqués quand le compte change, et session plafonnée — audit TECH-43."""

from datetime import timedelta

import pytest
from django.conf import settings
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "Test-Passw0rd!"  # défini par UserFactory


@pytest.fixture
def api():
    cache.clear()
    return APIClient()


def _connecte(api, utilisateur):
    reponse = api.post(
        reverse("api:token"), {"username": utilisateur.username, "password": MOT_DE_PASSE}, format="json"
    )
    assert reponse.status_code == 200
    return reponse.data["refresh"]


def _renouveler(api, refresh):
    return api.post(reverse("api:token_refresh"), {"refresh": refresh}, format="json")


@pytest.mark.parametrize(
    "changement",
    [
        lambda u: u.set_password("Nouveau-Secret-2027"),
        lambda u: setattr(u, "role", Role.CHARGE_CLIENTELE),
        lambda u: setattr(u, "is_active", False),
    ],
    ids=["mot de passe", "rôle", "désactivation"],
)
def test_un_changement_sensible_du_compte_revoque_ses_jetons(api, changement):
    """Téléphone volé, rôle retiré, départ : la session mobile ne doit pas survivre au changement."""
    utilisateur = UserFactory(role=Role.CHAUFFEUR)
    refresh = _connecte(api, utilisateur)

    changement(utilisateur)
    utilisateur.save()

    assert _renouveler(api, refresh).status_code == 401


def test_un_changement_anodin_ne_deconnecte_pas(api):
    utilisateur = UserFactory(role=Role.CHAUFFEUR)
    refresh = _connecte(api, utilisateur)

    utilisateur.email = "nouvelle@adresse.ci"
    utilisateur.save()

    assert _renouveler(api, refresh).status_code == 200


def test_le_changement_de_mot_de_passe_par_l_ecran_revoque_aussi_les_jetons(api, client):
    utilisateur = UserFactory(role=Role.RH)
    refresh = _connecte(api, utilisateur)
    client.force_login(utilisateur)

    client.post(
        reverse("accounts:password_change"),
        {"old_password": MOT_DE_PASSE, "new_password1": "Nouveau-Secret-2027", "new_password2": "Nouveau-Secret-2027"},
    )

    assert _renouveler(api, refresh).status_code == 401


def test_une_session_trop_ancienne_ne_se_renouvelle_plus(api):
    """Le renouvellement glisse de 7 jours à chaque usage : sans plafond, une session ne finissait jamais."""
    utilisateur = UserFactory(role=Role.CHAUFFEUR)
    jeton = RefreshToken.for_user(utilisateur)
    jeton["auth_time"] = int((timezone.now() - settings.JWT_SESSION_MAX - timedelta(minutes=1)).timestamp())

    reponse = _renouveler(api, str(jeton))

    assert reponse.status_code == 401
    assert "reconnectez-vous" in str(reponse.data).lower()


def test_la_connexion_note_son_heure_et_le_renouvellement_la_conserve(api):
    utilisateur = UserFactory(role=Role.CHAUFFEUR)
    refresh = _connecte(api, utilisateur)
    heure = RefreshToken(refresh)["auth_time"]

    nouveau = _renouveler(api, refresh).data["refresh"]

    assert RefreshToken(nouveau)["auth_time"] == heure
