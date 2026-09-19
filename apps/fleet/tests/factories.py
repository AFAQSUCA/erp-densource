from datetime import date
from decimal import Decimal

import factory

from apps.fleet.models import DocumentReglementaire, TypeDocument, Vehicule


class VehiculeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Vehicule

    immatriculation = factory.Sequence(lambda n: f"{1000 + n} AB 01")
    marque = "Mercedes-Benz"
    modele = "Actros"
    annee = 2020
    vin = factory.Sequence(lambda n: f"VIN{n:014d}")
    kilometrage = 120000
    capacite_charge_t = Decimal("25.00")
    reservoir_l = 600


class DocumentReglementaireFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DocumentReglementaire

    vehicule = factory.SubFactory(VehiculeFactory)
    type_document = TypeDocument.ASSURANCE
    date_delivrance = date(2026, 1, 1)
    date_expiration = date(2027, 1, 1)
