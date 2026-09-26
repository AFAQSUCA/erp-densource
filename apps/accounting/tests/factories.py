import factory

from apps.accounting.models import Compte, NatureCompte


class CompteFactory(factory.django.DjangoModelFactory):
    """Compte de test, indépendant du plan comptable seedé (migration 0002)."""

    class Meta:
        model = Compte

    numero = factory.Sequence(lambda n: f"9{n:05d}")
    libelle = factory.Sequence(lambda n: f"Compte de test {n}")
    nature = NatureCompte.CHARGE
