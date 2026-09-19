import factory

from apps.customers.models import Client


class ClientFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Client

    raison_sociale = factory.Sequence(lambda n: f"Société {n}")
    ncc_nif = factory.Sequence(lambda n: f"CI-{n:07d}A")
    contact_principal = "Awa Coulibaly"
    telephone = "+2250700000000"
    adresse = "Abidjan, Plateau"
