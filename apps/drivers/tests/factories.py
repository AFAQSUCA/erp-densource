from datetime import date

import factory

from apps.drivers.models import Chauffeur, Copilote
from apps.hr.tests.factories import PersonnelFactory


class ChauffeurFactory(factory.django.DjangoModelFactory):
    """Crée un Personnel « Chauffeur » puis récupère la fiche.

    Le signal de ``drivers`` crée déjà la fiche à la création du Personnel ;
    la factory la récupère et lui applique les attributs demandés.
    """

    class Meta:
        model = Chauffeur

    personnel = factory.SubFactory(PersonnelFactory, poste="Chauffeur")
    # Permis poids lourd complet par défaut : sans lui, l'affectation est refusée (audit M5-04). Un test sur un
    # permis manquant ou expiré passe explicitement ``numero_permis=""``, une date passée, etc.
    numero_permis = factory.Sequence(lambda n: f"PERMIS-{n:05d}")
    categories_permis = factory.LazyFunction(lambda: ["C", "E"])
    date_expiration_permis = date(2099, 1, 1)
    date_expiration_visite_medicale = date(2099, 1, 1)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        personnel = kwargs.pop("personnel")
        fiche, _ = model_class.all_objects.get_or_create(personnel=personnel)
        for champ, valeur in kwargs.items():
            setattr(fiche, champ, valeur)
        fiche.save()
        return fiche



def chauffeur_sans_permis(**champs):
    """Chauffeur dont la fiche permis n'est pas encore remplie (n°, catégories, dates vides)."""
    return ChauffeurFactory(
        **{"numero_permis": "", "categories_permis": [], "date_expiration_permis": None,
           "date_expiration_visite_medicale": None, **champs}
    )


class CopiloteFactory(factory.django.DjangoModelFactory):
    """Crée un Personnel « Copilote » puis récupère la fiche (même principe que ChauffeurFactory)."""

    class Meta:
        model = Copilote

    personnel = factory.SubFactory(PersonnelFactory, poste="Copilote")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        personnel = kwargs.pop("personnel")
        fiche, _ = model_class.all_objects.get_or_create(personnel=personnel)
        for champ, valeur in kwargs.items():
            setattr(fiche, champ, valeur)
        fiche.save()
        return fiche
