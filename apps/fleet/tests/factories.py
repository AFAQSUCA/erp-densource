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
    kilometrage = 0  # compteur jamais renseigné : aucun plancher pour un premier plein de test (audit M6-07)
    capacite_charge_t = Decimal("25.00")
    reservoir_l = 600


class DocumentReglementaireFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DocumentReglementaire

    vehicule = factory.SubFactory(VehiculeFactory)
    type_document = TypeDocument.ASSURANCE
    date_delivrance = date(2026, 1, 1)
    date_expiration = date(2027, 1, 1)


class VehiculeEnRegleFactory(VehiculeFactory):
    """Camion avec ses 4 documents réglementaires valides : sans eux, l'affectation et le départ d'une mission
    sont refusés (audit AUD-12). Les tests qui portent sur un document précis gardent ``VehiculeFactory``."""

    @factory.post_generation
    def documents(obj, create, extracted, **kwargs):
        if create:
            completer_documents(obj)


def completer_documents(vehicule, *, expiration=date(2099, 1, 1)):
    """Ajoute les documents réglementaires qui manquent au camion, valides longtemps : un test qui porte sur un
    seul document n'est pas parasité par l'alerte « document manquant » des trois autres (audit M2-22)."""
    for code in TypeDocument.values:
        if not DocumentReglementaire.objects.filter(vehicule=vehicule, type_document=code).exists():
            DocumentReglementaireFactory(vehicule=vehicule, type_document=code, date_expiration=expiration)
    return vehicule
