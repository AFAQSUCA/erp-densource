from datetime import date
from decimal import Decimal

import pytest

from apps.drivers.models import Chauffeur
from apps.hr import services
from apps.hr.models import Departement, Personnel

pytestmark = pytest.mark.django_db


def _donnees(**surcharges):
    donnees = dict(
        matricule="MAT-9001",
        nom="Bamba",
        prenom="Issa",
        poste="Mécanicien",
        departement=Departement.PARC_AUTO,
        type_contrat="CDI",
        date_embauche=date(2026, 9, 1),
        salaire_base=Decimal("300000"),
    )
    donnees.update(surcharges)
    return donnees


def test_recruter_cree_la_fiche_personnel_avec_le_contrat():
    personnel = services.recruter(**_donnees())

    assert Personnel.objects.get(matricule="MAT-9001") == personnel
    assert personnel.type_contrat == "CDI"
    assert personnel.superieur is None


def test_recruter_rattache_l_employe_a_son_superieur_hierarchique():
    chef = services.recruter(**_donnees(matricule="MAT-9000", poste="Chef d'atelier"))

    employe = services.recruter(**_donnees(matricule="MAT-9003", superieur=chef))

    assert employe.superieur == chef
    assert list(chef.subordonnes.all()) == [employe]


def test_recruter_un_chauffeur_cree_automatiquement_sa_fiche_chauffeur():
    personnel = services.recruter(**_donnees(matricule="MAT-9002", poste="Chauffeur"))

    assert Chauffeur.objects.filter(personnel=personnel).exists()


def test_recruter_un_autre_poste_ne_cree_pas_de_fiche_chauffeur():
    personnel = services.recruter(**_donnees())

    assert not Chauffeur.objects.filter(personnel=personnel).exists()
