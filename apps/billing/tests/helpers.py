"""Aides de test : missions livrées, factures à tous les stades, comptes par rôle."""

from datetime import date
from decimal import Decimal

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services
from apps.customers.tests.factories import ClientFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.missions.models import StatutMission
from apps.missions.tests.factories import MissionFactory

JOUR = date(2026, 9, 1)


def finances():
    return UserFactory(role=Role.FINANCES)


def direction():
    return UserFactory(role=Role.DIRECTION)


def mission_livree(*, prix="1000000", client=None, statut=StatutMission.LIVREE, **surcharges):
    return MissionFactory(
        client=client or ClientFactory(),
        statut=statut,
        prix_convenu=Decimal(prix),
        vehicule=VehiculeFactory(),
        chauffeur=ChauffeurFactory(),
        **surcharges,
    )


def brouillon(*, prix="1000000", acteur=None, **surcharges):
    return services.creer_facture(mission_livree(prix=prix, **surcharges), acteur or finances())


def a_valider(**surcharges):
    facture = brouillon(**surcharges)
    services.soumettre(facture, finances())
    return facture


def emise(*, aujourd_hui=JOUR, **surcharges):
    facture = a_valider(**surcharges)
    services.valider(facture, direction(), aujourd_hui=aujourd_hui)
    return facture
