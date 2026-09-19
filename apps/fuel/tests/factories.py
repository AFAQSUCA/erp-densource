from datetime import date
from decimal import Decimal

import factory

from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.fuel.models import Plein


class PleinFactory(factory.django.DjangoModelFactory):
    """Plein créé directement, sans calcul ni contrôle (tests de contraintes)."""

    class Meta:
        model = Plein

    date_plein = date(2026, 9, 1)
    vehicule = factory.SubFactory(VehiculeFactory)
    chauffeur = factory.SubFactory(ChauffeurFactory)
    station = "Total Yopougon"
    quantite_litres = Decimal("120.00")
    prix_unitaire = Decimal("655")
    km_compteur = 1400
    numero_ticket = factory.Sequence(lambda n: f"TKT-{n:05d}")
