import pytest

from apps.accounts.models import Role

from .factories import UserFactory

pytestmark = pytest.mark.django_db


def test_user_str_returns_full_name_when_available():
    user = UserFactory(first_name="Awa", last_name="Traore")

    assert str(user) == "Awa Traore"


def test_user_str_falls_back_to_username_without_name():
    user = UserFactory(first_name="", last_name="", username="chauffeur01")

    assert str(user) == "chauffeur01"


def test_is_admin_true_only_for_admin_role():
    admin = UserFactory(role=Role.ADMIN)
    chauffeur = UserFactory(role=Role.CHAUFFEUR)

    assert admin.is_admin is True
    assert chauffeur.is_admin is False


def test_is_direction_true_only_for_direction_role():
    direction = UserFactory(role=Role.DIRECTION)

    assert direction.is_direction is True
    assert direction.is_admin is False
