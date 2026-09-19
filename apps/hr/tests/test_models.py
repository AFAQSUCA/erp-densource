from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from .factories import PersonnelFactory

pytestmark = pytest.mark.django_db


def test_est_chauffeur_true_quand_poste_chauffeur_sans_tenir_compte_de_la_casse():
    assert PersonnelFactory.build(poste="  chauffeur ").est_chauffeur is True


def test_est_chauffeur_false_pour_un_autre_poste():
    assert PersonnelFactory.build(poste="Mécanicien").est_chauffeur is False


def test_matricule_doit_etre_unique_meme_apres_suppression_logique():
    supprime = PersonnelFactory(matricule="MAT-X")
    supprime.delete()

    with pytest.raises(IntegrityError):
        PersonnelFactory(matricule="MAT-X")


def test_salaire_negatif_refuse_par_la_validation():
    personnel = PersonnelFactory.build(salaire_base=Decimal("-1"))

    with pytest.raises(ValidationError):
        personnel.full_clean()


def test_personnel_supprime_logiquement_absent_du_manager_par_defaut():
    from apps.hr.models import Personnel

    personnel = PersonnelFactory()
    personnel.delete()

    assert not Personnel.objects.filter(pk=personnel.pk).exists()
    assert Personnel.all_objects.filter(pk=personnel.pk).exists()


def test_un_employe_ne_peut_pas_etre_son_propre_superieur():
    personnel = PersonnelFactory()
    personnel.superieur = personnel

    with pytest.raises(ValidationError):
        personnel.clean()
