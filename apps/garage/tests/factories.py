import factory

from apps.fleet.tests.factories import VehiculeFactory
from apps.garage.models import LieuReparation, OrdreReparation, TypeOr


class OrdreReparationFactory(factory.django.DjangoModelFactory):
    """OR créé directement (sans changer le statut du camion)."""

    class Meta:
        model = OrdreReparation

    numero = factory.Sequence(lambda n: f"OR-2026-{n + 1:04d}")
    vehicule = factory.SubFactory(VehiculeFactory)
    type_or = TypeOr.CURATIF
    lieu = LieuReparation.INTERNE
    motif = "Bruit anormal au freinage"
