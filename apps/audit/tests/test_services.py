import pytest
from django.test import RequestFactory

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.audit import services
from apps.audit.models import ActionChoices, StatutChoices

pytestmark = pytest.mark.django_db


def test_log_action_captures_ip_and_user_agent_from_request():
    user = UserFactory(role=Role.PARCAUTO)
    request = RequestFactory().post(
        "/x", REMOTE_ADDR="10.0.0.5", HTTP_USER_AGENT="pytest-agent"
    )

    entry = services.log_action(
        action=ActionChoices.UPDATE,
        module="FLEET",
        entite="Vehicule",
        entite_id=42,
        utilisateur=user,
        request=request,
    )

    assert entry.adresse_ip == "10.0.0.5"
    assert entry.user_agent == "pytest-agent"
    assert entry.role == Role.PARCAUTO
    assert entry.utilisateur_nom == user.get_full_name()


def test_log_action_ignore_x_forwarded_for_sans_proxy_de_confiance():
    """Sans proxy déclaré, l'en-tête écrit par le client ne doit jamais servir d'adresse."""
    request = RequestFactory().get(
        "/x", REMOTE_ADDR="10.0.0.5", HTTP_X_FORWARDED_FOR="1.2.3.4"
    )

    entry = services.log_action(
        action=ActionChoices.LOGIN, module="AUTH", entite="User", request=request
    )

    assert entry.adresse_ip == "10.0.0.5"


def test_log_action_lit_l_adresse_ajoutee_par_les_proxys_de_confiance(settings):
    settings.TRUSTED_PROXY_COUNT = 2
    request = RequestFactory().get(
        "/x",
        REMOTE_ADDR="10.0.0.5",
        HTTP_X_FORWARDED_FOR="203.0.113.9, 10.0.0.1",
    )

    entry = services.log_action(
        action=ActionChoices.LOGIN, module="AUTH", entite="User", request=request
    )

    assert entry.adresse_ip == "203.0.113.9"


def test_log_login_failed_records_failed_status_and_attempted_username():
    request = RequestFactory().post("/login")

    entry = services.log_login_failed("intrus", request)

    assert entry.statut == StatutChoices.FAILED
    assert entry.nouvelle_valeur == {"username_tente": "intrus"}
    assert entry.utilisateur is None
