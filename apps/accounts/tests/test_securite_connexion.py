"""Anti force brute sur la connexion, hachage Argon2 et longueur des mots de passe."""

import pytest
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts import throttle
from apps.accounts.models import Role, User
from apps.audit.models import ActionChoices, AuditLog, StatutChoices

from .factories import UserFactory

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "Test-Passw0rd!"


@pytest.fixture(autouse=True)
def cache_vide():
    cache.clear()


def _essai(client, identifiant, mot_de_passe="faux", **extra):
    return client.post(reverse("accounts:login"), {"username": identifiant, "password": mot_de_passe}, **extra)


# --- limitation par couple (adresse, identifiant) ---


def test_apres_cinq_echecs_meme_le_bon_mot_de_passe_est_refuse(client):
    UserFactory(username="awa", role=Role.RH)
    for _ in range(5):
        assert _essai(client, "awa").status_code == 200

    reponse = _essai(client, "awa", MOT_DE_PASSE)

    assert reponse.status_code == 429
    assert "Trop de tentatives" in reponse.content.decode()
    assert "_auth_user_id" not in client.session


def test_le_blocage_ne_verifie_meme_pas_le_mot_de_passe(client):
    """Pas de nouvelle ligne d'audit « échec » pendant le blocage : rien n'a été tenté."""
    for _ in range(5):
        _essai(client, "awa")
    avant = AuditLog.objects.filter(action=ActionChoices.LOGIN, statut=StatutChoices.FAILED).count()

    _essai(client, "awa")

    assert AuditLog.objects.filter(action=ActionChoices.LOGIN, statut=StatutChoices.FAILED).count() == avant


def test_un_autre_identifiant_depuis_la_meme_adresse_n_est_pas_bloque(client):
    UserFactory(username="moussa", role=Role.RH)
    for _ in range(5):
        _essai(client, "awa")

    assert _essai(client, "moussa", MOT_DE_PASSE).status_code == 302


def test_un_autre_client_n_est_pas_bloque_par_les_echecs_d_une_adresse(client):
    UserFactory(username="awa", role=Role.RH)
    for _ in range(5):
        _essai(client, "awa", REMOTE_ADDR="198.51.100.7")

    assert _essai(Client(), "awa", MOT_DE_PASSE, REMOTE_ADDR="198.51.100.8").status_code == 302


def test_la_casse_et_les_espaces_ne_contournent_pas_la_limite(client):
    UserFactory(username="awa", role=Role.RH)
    for variante in ("awa", "AWA", " Awa ", "aWa", "awa"):
        _essai(client, variante)

    assert _essai(client, "awa", MOT_DE_PASSE).status_code == 429


def test_un_en_tete_x_forwarded_for_forge_ne_contourne_pas_la_limite(client):
    UserFactory(username="awa", role=Role.RH)
    for i in range(5):
        _essai(client, "awa", HTTP_X_FORWARDED_FOR=f"203.0.113.{i}")

    assert _essai(client, "awa", MOT_DE_PASSE, HTTP_X_FORWARDED_FOR="203.0.113.99").status_code == 429


def test_une_connexion_reussie_remet_le_compteur_a_zero(client):
    UserFactory(username="awa", role=Role.RH)
    for _ in range(4):
        _essai(client, "awa")
    assert _essai(client, "awa", MOT_DE_PASSE).status_code == 302
    client.post(reverse("accounts:logout"))

    for _ in range(4):
        _essai(client, "awa")

    assert _essai(client, "awa", MOT_DE_PASSE).status_code == 302  # 4 + 4 échecs, mais remis à zéro entre


def test_le_blocage_prend_fin_avec_la_fenetre(client, monkeypatch):
    UserFactory(username="awa", role=Role.RH)
    for _ in range(5):
        _essai(client, "awa")
    assert _essai(client, "awa", MOT_DE_PASSE).status_code == 429

    instant = throttle.time.time()
    monkeypatch.setattr(throttle.time, "time", lambda: instant + 15 * 60 + 1)

    assert _essai(client, "awa", MOT_DE_PASSE).status_code == 302


# --- limitation par adresse ---


def test_vingt_echecs_depuis_une_adresse_la_bloquent_quel_que_soit_l_identifiant(client):
    UserFactory(username="awa", role=Role.RH)
    for i in range(20):
        _essai(client, f"inconnu{i}")

    assert _essai(client, "awa", MOT_DE_PASSE).status_code == 429


def test_la_phrase_d_attente_est_en_minutes_arrondies_vers_le_haut():
    assert throttle.phrase_attente(1) == "1 minute"
    assert throttle.phrase_attente(61) == "2 minutes"
    assert throttle.phrase_attente(15 * 60) == "15 minutes"


def test_le_message_ne_revele_pas_si_le_compte_existe(client):
    UserFactory(username="reel", role=Role.RH)
    for _ in range(5):
        _essai(client, "reel")
        _essai(client, "fantome")

    reel = _essai(client, "reel").content.decode()
    fantome = _essai(client, "fantome").content.decode()

    assert "Trop de tentatives" in reel and "Trop de tentatives" in fantome


def test_les_echecs_de_l_api_comptent_aussi(client):
    from rest_framework.test import APIClient

    UserFactory(username="awa", role=Role.RH)
    api = APIClient()
    for _ in range(5):
        api.post(reverse("api:token"), {"username": "awa", "password": "faux"}, format="json")

    assert _essai(client, "awa", MOT_DE_PASSE).status_code == 429


# --- Argon2 et mots de passe ---


def test_argon2_est_le_premier_hacheur_de_la_configuration_de_production():
    from config.settings import base

    assert base.PASSWORD_HASHERS[0] == "django.contrib.auth.hashers.Argon2PasswordHasher"
    assert "django.contrib.auth.hashers.PBKDF2PasswordHasher" in base.PASSWORD_HASHERS


ARGON2_PUIS_PBKDF2 = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]


@override_settings(PASSWORD_HASHERS=ARGON2_PUIS_PBKDF2)
def test_un_ancien_hachage_pbkdf2_est_converti_en_argon2_a_la_connexion():
    ancien = make_password(MOT_DE_PASSE, hasher="pbkdf2_sha256")
    utilisateur = UserFactory(username="awa", role=Role.RH)
    User.objects.filter(pk=utilisateur.pk).update(password=ancien)
    assert User.objects.get(pk=utilisateur.pk).password.startswith("pbkdf2_sha256$")

    assert authenticate(username="awa", password=MOT_DE_PASSE) is not None

    assert User.objects.get(pk=utilisateur.pk).password.startswith("argon2$")


@override_settings(PASSWORD_HASHERS=ARGON2_PUIS_PBKDF2)
def test_un_nouveau_mot_de_passe_est_hache_en_argon2():
    utilisateur = UserFactory(role=Role.RH)
    utilisateur.set_password("Nouveau-Mot-de-passe-9")

    assert utilisateur.password.startswith("argon2$")
    assert utilisateur.check_password("Nouveau-Mot-de-passe-9")


def test_un_mot_de_passe_de_moins_de_dix_caracteres_est_refuse():
    with pytest.raises(ValidationError):
        validate_password("Court-1aB")  # 9 caractères
    validate_password("Assez-long-42x")  # 14 : accepté


# --- administration ---


def test_l_echec_sur_l_admin_django_passe_par_la_page_du_site(client):
    reponse = client.post("/admin/login/", {"username": "awa", "password": "faux"})

    assert reponse.status_code == 302 and reponse["Location"].startswith(reverse("accounts:login"))
