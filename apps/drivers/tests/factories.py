import factory

from apps.drivers.models import Chauffeur
from apps.hr.tests.factories import PersonnelFactory


class ChauffeurFactory(factory.django.DjangoModelFactory):
    """Crée un Personnel « Chauffeur » puis récupère la fiche.

    Le signal de ``drivers`` crée déjà la fiche à la création du Personnel ;
    la factory la récupère et lui applique les attributs demandés.
    """

    class Meta:
        model = Chauffeur

    personnel = factory.SubFactory(PersonnelFactory, poste="Chauffeur")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        personnel = kwargs.pop("personnel")
        fiche, _ = model_class.all_objects.get_or_create(personnel=personnel)
        for champ, valeur in kwargs.items():
            setattr(fiche, champ, valeur)
        fiche.save()
        return fiche
