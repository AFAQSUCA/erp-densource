"""Authentification JWT : connexion, renouvellement, déconnexion, limitation, audit."""

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.audit.models import ActionChoices, AuditLog, StatutChoices
from apps.drivers.tests.factories import ChauffeurFactory

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "Test-Passw0rd!"  # défini par UserFactory


@pytest.fixture
def api():
    cache.clear()
    return APIClient()


def _connexion(api, utilisateur, mot_de_passe=MOT_DE_PASSE):
    return api.post(
        reverse("api:token"), {"username": utilisateur.username, "password": mot_de_passe}, format="json"
    )


def test_la_connexion_donne_un_acces_et_un_renouvellement(api):
    utilisateur = UserFactory(role=Role.CHAUFFEUR)

    reponse = _connexion(api, utilisateur)

    assert reponse.status_code == 200 and set(reponse.data) == {"access", "refresh"}
    utilisateur.refresh_from_db()
    assert utilisateur.last_login is not None


def test_le_jeton_d_acces_dure_15_minutes_et_le_renouvellement_7_jours(api):
    utilisateur = UserFactory()
    donnees = _connexion(api, utilisateur).data

    acces, renouvellement = AccessToken(donnees["access"]), RefreshToken(donnees["refresh"])

    assert acces["exp"] - acces["iat"] == 15 * 60
    assert renouvellement["exp"] - renouvellement["iat"] == 7 * 24 * 3600


def test_un_mauvais_mot_de_passe_ou_un_compte_inactif_est_refuse(api):
    actif, inactif = UserFactory(), UserFactory(is_active=False)

    assert _connexion(api, actif, "faux").status_code == 401
    assert _connexion(api, inactif).status_code == 401
    assert _connexion(api, UserFactory(username="inconnu"), "x").status_code == 401


def test_la_connexion_est_inscrite_au_journal_d_audit(api):
    utilisateur = UserFactory()

    _connexion(api, utilisateur)
    _connexion(api, utilisateur, "faux")

    reussie = AuditLog.objects.get(action=ActionChoices.LOGIN, statut=StatutChoices.SUCCESS)
    echouee = AuditLog.objects.get(action=ActionChoices.LOGIN, statut=StatutChoices.FAILED)
    assert reussie.entite_id == utilisateur.pk and reussie.module == "AUTH"
    assert echouee.nouvelle_valeur == {"username_tente": utilisateur.username}


def test_un_acces_valide_ouvre_le_profil_avec_le_role_et_l_id_chauffeur(api):
    fiche = ChauffeurFactory()
    compte = UserFactory(role=Role.CHAUFFEUR)
    fiche.personnel.utilisateur = compte
    fiche.personnel.save()
    acces = _connexion(api, compte).data["access"]

    reponse = api.get(reverse("api:moi"), HTTP_AUTHORIZATION=f"Bearer {acces}")

    assert reponse.status_code == 200
    assert reponse.data["role"] == Role.CHAUFFEUR and reponse.data["chauffeur_id"] == fiche.pk
    assert reponse.data["identifiant"] == compte.username


def test_le_profil_d_un_superutilisateur_sans_role_est_admin_sans_chauffeur(api):
    api.force_authenticate(UserFactory(role="", is_superuser=True))

    reponse = api.get(reverse("api:moi"))

    assert reponse.data["role"] == Role.ADMIN and reponse.data["chauffeur_id"] is None


def test_sans_jeton_ou_avec_un_jeton_invalide_ou_expire_l_acces_est_refuse(api):
    utilisateur = UserFactory()
    expire = AccessToken.for_user(utilisateur)
    expire.set_exp(lifetime=-timedelta(seconds=1))

    assert api.get(reverse("api:moi")).status_code == 401
    assert api.get(reverse("api:moi"), HTTP_AUTHORIZATION="Bearer nimportequoi").status_code == 401
    assert api.get(reverse("api:moi"), HTTP_AUTHORIZATION=f"Bearer {expire}").status_code == 401


def test_le_renouvellement_change_le_jeton_et_revoque_l_ancien(api):
    donnees = _connexion(api, UserFactory()).data

    premier = api.post(reverse("api:token_refresh"), {"refresh": donnees["refresh"]}, format="json")
    rejoue = api.post(reverse("api:token_refresh"), {"refresh": donnees["refresh"]}, format="json")

    assert premier.status_code == 200 and premier.data["refresh"] != donnees["refresh"]
    assert rejoue.status_code == 401  # l'ancien jeton de renouvellement est révoqué


def test_la_deconnexion_revoque_le_renouvellement(api):
    utilisateur = UserFactory()
    donnees = _connexion(api, utilisateur).data
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {donnees['access']}")

    sortie = api.post(reverse("api:logout"), {"refresh": donnees["refresh"]}, format="json")
    api.credentials()
    apres = api.post(reverse("api:token_refresh"), {"refresh": donnees["refresh"]}, format="json")

    assert sortie.status_code == 204 and apres.status_code == 401
    assert AuditLog.objects.filter(action=ActionChoices.LOGOUT).exists()


def test_la_deconnexion_exige_un_acces_et_un_renouvellement_valide(api):
    donnees = _connexion(api, UserFactory()).data

    assert api.post(reverse("api:logout"), {"refresh": donnees["refresh"]}, format="json").status_code == 401
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {donnees['access']}")
    assert api.post(reverse("api:logout"), {}, format="json").status_code == 400
    assert api.post(reverse("api:logout"), {"refresh": "faux"}, format="json").status_code == 401


def test_la_connexion_est_limitee_contre_la_force_brute(api, monkeypatch):
    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"connexion": "3/min"})
    utilisateur = UserFactory()

    codes = [_connexion(api, utilisateur, "faux").status_code for _ in range(5)]

    assert codes[:3] == [401, 401, 401] and codes[3:] == [429, 429]
    assert _connexion(api, utilisateur).status_code == 429  # même le bon mot de passe est bloqué
    cache.clear()
