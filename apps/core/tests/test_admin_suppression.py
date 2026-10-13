"""Admin Django : plus aucune suppression physique des modèles à suppression logique — audit AUD-04, TECH-57."""

import pytest
from django.contrib import admin
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.core.admin import SansSuppressionAdmin, SuppressionLogiqueAdmin
from apps.core.models import BaseModel
from apps.customers.models import Client
from apps.customers.tests.factories import ClientFactory
from apps.fuel.models import Plein
from apps.garage.models import OrdreReparation
from apps.hr.models import AttributionConge, Conge
from apps.inventory.models import Article
from apps.missions.models import Mission

pytestmark = pytest.mark.django_db

EXPLOITATION = [Plein, Mission, OrdreReparation, Article, Conge, AttributionConge]


@pytest.fixture
def requete(rf):
    requete = rf.post("/")
    SessionMiddleware(lambda r: None).process_request(requete)
    requete.session.save()
    requete._messages = FallbackStorage(requete)
    requete.user = UserFactory(role=Role.ADMIN, is_superuser=True, is_staff=True)
    return requete


def test_aucun_admin_d_un_modele_a_suppression_logique_ne_supprime_physiquement(requete):
    """Chaque modèle ``BaseModel`` de l'admin interdit la suppression ou la rend logique : un nouvel admin qui
    l'oublierait ferait échouer ce test."""
    oublies = [
        modele._meta.label
        for modele, modele_admin in admin.site._registry.items()
        if issubclass(modele, BaseModel)
        and modele_admin.has_delete_permission(requete)
        and type(modele_admin).delete_queryset is admin.ModelAdmin.delete_queryset
    ]

    assert not oublies, oublies


@pytest.mark.parametrize("modele", EXPLOITATION, ids=lambda m: m.__name__)
def test_les_donnees_d_exploitation_ne_se_suppriment_pas_depuis_l_admin(modele, requete):
    modele_admin = admin.site._registry[modele]

    assert isinstance(modele_admin, SansSuppressionAdmin)
    assert not modele_admin.has_delete_permission(requete)
    assert "delete_selected" not in modele_admin.get_actions(requete)


def test_la_suppression_d_une_fiche_de_reference_est_logique_et_se_restaure(requete):
    modele_admin = admin.site._registry[Client]
    client = ClientFactory()
    assert isinstance(modele_admin, SuppressionLogiqueAdmin)

    modele_admin.delete_queryset(requete, Client.objects.filter(pk=client.pk))

    supprime = Client.all_objects.get(pk=client.pk)  # toujours en base
    assert supprime.is_deleted and supprime.deleted_by == requete.user
    assert supprime in modele_admin.get_queryset(requete)  # visible dans l'admin, pour être restauré

    modele_admin.restaurer(requete, Client.all_objects.filter(pk=client.pk))

    assert not Client.all_objects.get(pk=client.pk).is_deleted
    assert Client.objects.filter(pk=client.pk).exists()
