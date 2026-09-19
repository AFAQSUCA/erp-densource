from decimal import Decimal

import factory

from apps.customers.tests.factories import ClientFactory
from apps.missions.models import Mission


class MissionFactory(factory.django.DjangoModelFactory):
    """Mission Brouillon avec des codes connus (ne passe pas par le service)."""

    class Meta:
        model = Mission

    numero = factory.Sequence(lambda n: f"MIS-2026-{n + 1:04d}")
    client = factory.SubFactory(ClientFactory)
    lieu_chargement = "Abidjan, Port"
    lieu_livraison = "Bouaké"
    nature_marchandise = "Ciment"
    poids_t = Decimal("20.00")
    prix_convenu = Decimal("850000")
    code_expediteur = "ABCD2345"
    code_destinataire = "WXYZ6789"
