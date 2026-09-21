import pytest
from django.test import Client

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.audit.models import ActionChoices, AuditLog, StatutChoices

pytestmark = pytest.mark.django_db


def test_login_signal_creates_audit_entry():
    user = UserFactory(role=Role.FINANCES)
    client = Client()

    client.force_login(user)

    entry = AuditLog.objects.filter(action=ActionChoices.LOGIN, utilisateur=user).latest(
        "date_heure"
    )
    assert entry.role == Role.FINANCES
    assert entry.statut == StatutChoices.SUCCESS


def test_logout_signal_creates_audit_entry():
    user = UserFactory(role=Role.RH)
    client = Client()
    client.force_login(user)

    client.logout()

    assert AuditLog.objects.filter(action=ActionChoices.LOGOUT, utilisateur=user).exists()


def test_failed_login_creates_audit_entry_with_failed_status():
    client = Client()

    client.post("/connexion/", {"username": "ghost", "password": "wrong"})

    assert AuditLog.objects.filter(
        action=ActionChoices.LOGIN, statut=StatutChoices.FAILED
    ).exists()
