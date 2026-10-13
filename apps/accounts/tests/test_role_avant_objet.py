"""Le rôle est contrôlé avant de chercher l'objet de la page — audit TECH-34.

Avant, sept vues cherchaient l'objet (``get_object_or_404``) avant le contrôle du rôle : un utilisateur non autorisé
recevait 404 pour un identifiant inexistant et 403 pour un identifiant existant, et pouvait ainsi deviner les
comptes, devis, factures, pleins, congés et missions qui existent.
"""

import importlib

import pytest
from django.apps import apps as registre
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory

from apps.accounts.mixins import RoleRequiredMixin
from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

INEXISTANT = 987654321


def _toutes_les_sous_classes(classe):
    for sous_classe in classe.__subclasses__():
        yield sous_classe
        yield from _toutes_les_sous_classes(sous_classe)


def _vues_qui_chargent_un_objet():
    for config in registre.get_app_configs():
        if config.name.startswith("apps."):
            for module in ("views", "views_utilisateurs"):
                try:
                    importlib.import_module(f"{config.name}.{module}")
                except ModuleNotFoundError:
                    pass
    return sorted(
        {vue for vue in _toutes_les_sous_classes(RoleRequiredMixin) if "charger_objet" in vue.__dict__},
        key=lambda vue: vue.__qualname__,
    )


VUES = _vues_qui_chargent_un_objet()


def test_les_sept_vues_concernees_passent_par_charger_objet():
    assert len(VUES) >= 7


@pytest.mark.parametrize("vue", VUES, ids=lambda vue: f"{vue.__module__}.{vue.__qualname__}")
def test_un_role_non_autorise_recoit_403_meme_pour_un_identifiant_inexistant(vue):
    role = next(r for r in (Role.CHARGE_CLIENTELE, Role.PARCAUTO, Role.FINANCES, Role.RH, Role.CHAUFFEUR) if r not in vue.roles)
    requete = RequestFactory().get("/")
    requete.user = UserFactory(role=role)

    with pytest.raises(PermissionDenied):
        vue.as_view()(requete, pk=INEXISTANT)


@pytest.mark.parametrize("vue", VUES, ids=lambda vue: f"{vue.__module__}.{vue.__qualname__}")
def test_un_visiteur_non_connecte_est_renvoye_a_la_connexion(vue):
    requete = RequestFactory().get("/")
    requete.user = AnonymousUser()

    reponse = vue.as_view()(requete, pk=INEXISTANT)

    assert reponse.status_code == 302
