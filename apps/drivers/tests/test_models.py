import pytest
from django.core.exceptions import ValidationError

from .factories import ChauffeurFactory

pytestmark = pytest.mark.django_db


def test_matricule_nom_prenom_viennent_de_personnel():
    fiche = ChauffeurFactory(personnel__matricule="MAT-77", personnel__nom="Diallo")

    assert fiche.matricule == "MAT-77"
    assert fiche.nom == "Diallo"
    assert fiche.prenom == "Jean"


def test_categories_permis_c_et_e_acceptees():
    fiche = ChauffeurFactory(categories_permis=["C", "E"])

    fiche.clean()


def test_categorie_permis_inconnue_refusee():
    fiche = ChauffeurFactory(categories_permis=["C", "Z"])

    with pytest.raises(ValidationError):
        fiche.clean()


def test_categories_permis_doit_etre_une_liste():
    fiche = ChauffeurFactory(categories_permis="C")

    with pytest.raises(ValidationError):
        fiche.clean()
