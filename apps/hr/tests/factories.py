from datetime import date
from decimal import Decimal

import factory

from apps.hr.models import Departement, Personnel


class PersonnelFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Personnel

    matricule = factory.Sequence(lambda n: f"MAT{n:04d}")
    nom = "Kouassi"
    prenom = "Jean"
    poste = "Comptable"
    departement = Departement.COMPTABILITE
    date_embauche = date(2024, 1, 15)
    salaire_base = Decimal("250000")
