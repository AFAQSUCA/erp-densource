"""Tests de l'audit automatique (apps/audit/registry.py) sur Personnel."""

import pytest

from apps.audit.models import ActionChoices, AuditLog

from .factories import PersonnelFactory

pytestmark = pytest.mark.django_db


def _entrees(personnel):
    return AuditLog.objects.filter(entite="Personnel", entite_id=personnel.pk)


def test_creation_genere_une_entree_create_avec_les_valeurs():
    personnel = PersonnelFactory(nom="Traore")

    entree = _entrees(personnel).get()
    assert entree.action == ActionChoices.CREATE
    assert entree.module == "RH"
    assert entree.ancienne_valeur is None
    assert entree.nouvelle_valeur["nom"] == "Traore"


def test_modification_journalise_uniquement_les_champs_changes():
    personnel = PersonnelFactory(poste="Comptable")

    personnel.poste = "Chef comptable"
    personnel.save()

    entree = _entrees(personnel).get(action=ActionChoices.UPDATE)
    assert entree.ancienne_valeur == {"poste": "Comptable"}
    assert entree.nouvelle_valeur == {"poste": "Chef comptable"}


def test_save_sans_changement_ne_cree_pas_d_entree():
    personnel = PersonnelFactory()

    personnel.save()

    assert _entrees(personnel).count() == 1


def test_suppression_logique_genere_une_entree_delete():
    personnel = PersonnelFactory()

    personnel.delete()

    entree = _entrees(personnel).get(action=ActionChoices.DELETE)
    assert entree.nouvelle_valeur["is_deleted"] is True


def test_decimal_et_date_sont_serialises_en_json():
    personnel = PersonnelFactory()

    entree = _entrees(personnel).get()
    assert entree.nouvelle_valeur["date_embauche"] == "2024-01-15"
    assert entree.nouvelle_valeur["salaire_base"] == "250000.00"
