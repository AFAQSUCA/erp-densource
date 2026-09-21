"""Double authentification sur l'émission des jetons de l'API (ADMIN et DIRECTION)."""

import pytest
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts import mfa
from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers_mfa import activer_mfa, code_frais
from apps.audit.models import AuditLog, StatutChoices

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "Test-Passw0rd!"


@pytest.fixture(autouse=True)
def mfa_imposee(settings):
    settings.MFA_ENFORCED = True
    cache.clear()


@pytest.fixture
def api():
    return APIClient()


def _connexion(api, utilisateur, **extra):
    return api.post(
        reverse("api:token"), {"username": utilisateur.username, "password": MOT_DE_PASSE, **extra}, format="json"
    )


def test_un_compte_sans_mfa_active_ne_recoit_pas_de_jeton(api):
    utilisateur = UserFactory(role=Role.DIRECTION)

    reponse = _connexion(api, utilisateur)

    assert reponse.status_code == 401 and reponse.data["code"] == "mfa_non_activee"
    assert "access" not in reponse.data


def test_sans_code_le_jeton_est_refuse(api):
    utilisateur = UserFactory(role=Role.DIRECTION)
    activer_mfa(utilisateur)

    reponse = _connexion(api, utilisateur)

    assert reponse.status_code == 401 and reponse.data["code"] == "mfa_requise"


def test_avec_un_bon_code_le_jeton_est_delivre(api):
    utilisateur = UserFactory(role=Role.ADMIN)
    activer_mfa(utilisateur)

    reponse = _connexion(api, utilisateur, otp=code_frais(utilisateur))

    assert reponse.status_code == 200 and set(reponse.data) == {"access", "refresh"}


def test_un_code_faux_est_refuse_et_inscrit_au_journal(api):
    utilisateur = UserFactory(role=Role.DIRECTION)
    activer_mfa(utilisateur)

    reponse = _connexion(api, utilisateur, otp="000000")

    assert reponse.status_code == 401 and reponse.data["code"] == "mfa_invalide"
    ligne = AuditLog.objects.get(entite="MFA", entite_id=utilisateur.pk, statut=StatutChoices.FAILED)
    assert ligne.nouvelle_valeur == {"evenement": "api_code_refuse"}


def test_un_code_ne_sert_qu_une_fois_sur_l_api(api):
    utilisateur = UserFactory(role=Role.DIRECTION)
    activer_mfa(utilisateur)
    code = code_frais(utilisateur)

    assert _connexion(api, utilisateur, otp=code).status_code == 200
    assert _connexion(api, utilisateur, otp=code).status_code == 401


def test_un_code_de_secours_fonctionne_une_seule_fois(api):
    utilisateur = UserFactory(role=Role.DIRECTION)
    _, codes = activer_mfa(utilisateur)

    assert _connexion(api, utilisateur, otp=codes[0]).status_code == 200
    assert _connexion(api, utilisateur, otp=codes[0]).status_code == 401
    assert mfa.codes_secours_restants(utilisateur) == 9


def test_apres_cinq_codes_faux_la_connexion_est_limitee(api):
    utilisateur = UserFactory(role=Role.DIRECTION)
    activer_mfa(utilisateur)
    for _ in range(5):
        _connexion(api, utilisateur, otp="000000")

    reponse = _connexion(api, utilisateur, otp=code_frais(utilisateur))

    assert reponse.status_code == 429


def test_un_mauvais_mot_de_passe_reste_refuse_avant_tout_controle_mfa(api):
    utilisateur = UserFactory(role=Role.DIRECTION)
    activer_mfa(utilisateur)

    reponse = api.post(
        reverse("api:token"),
        {"username": utilisateur.username, "password": "faux", "otp": code_frais(utilisateur)},
        format="json",
    )

    assert reponse.status_code == 401 and reponse.data.get("code") != "mfa_requise"


@pytest.mark.parametrize("role", [Role.RH, Role.CHARGE_CLIENTELE, Role.PARCAUTO, Role.FINANCES, Role.CHAUFFEUR])
def test_les_autres_roles_n_ont_pas_besoin_de_code(api, role):
    assert _connexion(api, UserFactory(role=role)).status_code == 200


def test_le_champ_otp_est_documente_dans_le_schema(api):
    admin = UserFactory(role=Role.ADMIN, is_superuser=True)
    activer_mfa(admin)
    from django.test import Client

    web = Client()
    web.force_login(admin)
    web.post(reverse("accounts:mfa_verifier"), {"code": code_frais(admin)})

    schema = web.get("/api/v1/schema/?format=json")

    assert schema.status_code == 200 and '"otp"' in schema.content.decode()
