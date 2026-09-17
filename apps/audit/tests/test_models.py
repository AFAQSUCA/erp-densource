import pytest

from apps.audit.models import ActionChoices, AuditLog, StatutChoices

pytestmark = pytest.mark.django_db


def test_audit_log_created_with_success_status_by_default():
    entry = AuditLog.objects.create(
        action=ActionChoices.CREATE,
        module="FLEET",
        entite="Vehicule",
        entite_id=1,
    )

    assert entry.statut == StatutChoices.SUCCESS
    assert entry.date_heure is not None


def test_audit_log_save_raises_on_update_of_existing_entry():
    entry = AuditLog.objects.create(action=ActionChoices.CREATE, module="FLEET", entite="Vehicule")
    entry.statut = StatutChoices.FAILED

    with pytest.raises(ValueError):
        entry.save()


def test_audit_log_delete_is_forbidden():
    entry = AuditLog.objects.create(action=ActionChoices.CREATE, module="FLEET", entite="Vehicule")

    with pytest.raises(ValueError):
        entry.delete()
