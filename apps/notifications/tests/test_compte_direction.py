"""Toute création d'un compte Direction, ou attribution de ce rôle, prévient la Direction — décision du 13/10/2026,
audit AUD-09 (l'administrateur pouvait se donner seul les pouvoirs de validation de la Direction)."""

import pytest

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.notifications.models import CategorieNotification, NiveauNotification, Notification

pytestmark = pytest.mark.django_db


def _avis(utilisateur):
    return list(Notification.objects.filter(destinataire=utilisateur, titre__startswith="Nouveau compte Direction"))


def test_la_creation_d_un_compte_direction_previent_la_direction_existante():
    directrice = UserFactory(role=Role.DIRECTION)

    nouveau = UserFactory(role=Role.DIRECTION, first_name="Koffi", last_name="Yao")

    (avis,) = _avis(directrice)
    assert avis.niveau == NiveauNotification.URGENT and avis.categorie == CategorieNotification.COMPTE
    assert "Koffi Yao" in avis.titre and "journal d'audit" in avis.message
    assert _avis(nouveau) == []  # le nouveau compte n'est pas prévenu de sa propre création


def test_la_promotion_d_un_compte_existant_previent_aussi():
    directrice = UserFactory(role=Role.DIRECTION)
    compte = UserFactory(role=Role.FINANCES)

    compte.role = Role.DIRECTION
    compte.save()

    assert len(_avis(directrice)) == 1


def test_les_autres_roles_et_changements_anodins_ne_previennent_pas():
    directrice = UserFactory(role=Role.DIRECTION)
    compte = UserFactory(role=Role.RH)

    compte.email = "nouvelle@densource.ci"
    compte.save()
    compte.role = Role.FINANCES
    compte.save()

    assert _avis(directrice) == []
