from types import SimpleNamespace

import pytest

from apps.accounts.models import Role
from apps.accounts.permissions import IsAdmin, IsAdminOrDirection, IsChauffeur

from .factories import UserFactory

pytestmark = pytest.mark.django_db


def _request_for(user):
    return SimpleNamespace(user=user)


def test_is_admin_permission_grants_admin_denies_others():
    admin = UserFactory(role=Role.ADMIN)
    chauffeur = UserFactory(role=Role.CHAUFFEUR)
    perm = IsAdmin()

    assert perm.has_permission(_request_for(admin), None) is True
    assert perm.has_permission(_request_for(chauffeur), None) is False


def test_is_admin_or_direction_grants_both_roles_denies_rh():
    admin = UserFactory(role=Role.ADMIN)
    direction = UserFactory(role=Role.DIRECTION)
    rh = UserFactory(role=Role.RH)
    perm = IsAdminOrDirection()

    assert perm.has_permission(_request_for(admin), None) is True
    assert perm.has_permission(_request_for(direction), None) is True
    assert perm.has_permission(_request_for(rh), None) is False


def test_has_role_denies_unauthenticated_user():
    anonymous = SimpleNamespace(is_authenticated=False, role=None)
    perm = IsChauffeur()

    assert perm.has_permission(_request_for(anonymous), None) is False
