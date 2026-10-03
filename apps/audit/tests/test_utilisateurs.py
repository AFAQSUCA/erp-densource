"""Les comptes utilisateurs sont audités : rôle, droits et activation, jamais le mot de passe en clair."""

import pytest
from django.test import Client

from apps.accounts.models import Role, User
from apps.accounts.tests.factories import UserFactory
from apps.audit.models import ActionChoices, AuditLog

pytestmark = pytest.mark.django_db


def _entrees(user, action=None):
    qs = AuditLog.objects.filter(module="UTILISATEURS", entite="User", entite_id=user.pk)
    return qs.filter(action=action) if action else qs


def test_la_creation_d_un_compte_est_journalisee_sans_le_mot_de_passe():
    user = User.objects.create_user(username="nouveau", password="Secret-12345!", role=Role.FINANCES)

    entree = _entrees(user, ActionChoices.CREATE).get()

    assert entree.nouvelle_valeur["role"] == Role.FINANCES
    assert entree.nouvelle_valeur["password"].startswith("masqué:")
    assert user.password not in str(entree.nouvelle_valeur)
    assert "Secret-12345!" not in str(entree.nouvelle_valeur)


def test_un_changement_de_role_est_journalise_avec_l_ancienne_valeur():
    user = UserFactory(role=Role.RH)

    user.role = Role.DIRECTION
    user.save()

    entree = _entrees(user, ActionChoices.UPDATE).filter(nouvelle_valeur__role=Role.DIRECTION).get()
    assert entree.ancienne_valeur == {"role": Role.RH}


def test_la_desactivation_et_les_droits_d_administration_sont_journalises():
    user = UserFactory(role=Role.ADMIN)

    user.is_active = False
    user.is_superuser = True
    user.save()

    entree = _entrees(user, ActionChoices.UPDATE).filter(nouvelle_valeur__is_active=False).get()
    assert entree.nouvelle_valeur == {"is_active": False, "is_superuser": True}
    assert entree.ancienne_valeur == {"is_active": True, "is_superuser": False}


def test_un_changement_de_mot_de_passe_est_visible_sans_ecrire_le_hash():
    user = UserFactory(role=Role.RH)
    ancien_hash = user.password

    user.set_password("Autre-mot-de-passe-9876!")
    user.save()

    entree = _entrees(user, ActionChoices.UPDATE).filter(nouvelle_valeur__has_key="password").latest("pk")
    assert entree.ancienne_valeur["password"].startswith("masqué:")
    assert entree.nouvelle_valeur["password"].startswith("masqué:")
    assert entree.ancienne_valeur["password"] != entree.nouvelle_valeur["password"]
    assert ancien_hash not in str(entree.ancienne_valeur)
    assert user.password not in str(entree.nouvelle_valeur)


def test_la_connexion_ne_produit_pas_de_modification_de_compte():
    user = UserFactory(role=Role.FINANCES)
    avant = _entrees(user, ActionChoices.UPDATE).count()

    Client().force_login(user)

    assert _entrees(user, ActionChoices.UPDATE).count() == avant
