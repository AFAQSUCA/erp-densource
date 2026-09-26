"""Immuabilité : une écriture validée (et ses lignes) ne se modifie ni ne se supprime."""

from datetime import date
from decimal import Decimal

import pytest

from apps.accounting import services
from apps.accounting.exceptions import EcritureVerrouillee
from apps.accounting.models import Journal, SensEcriture
from apps.accounting.services import LigneSaisie

from .factories import CompteFactory

pytestmark = pytest.mark.django_db

JOUR = date(2026, 9, 1)


def _ecriture():
    charge, tresorerie = CompteFactory(), CompteFactory()
    return services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES,
        date_ecriture=JOUR,
        libelle="Test",
        lignes=[
            LigneSaisie(compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("1000")),
            LigneSaisie(compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("1000")),
        ],
    )


def test_une_ecriture_validee_ne_se_modifie_pas():
    ecriture = _ecriture()

    ecriture.libelle = "Modifié"
    with pytest.raises(EcritureVerrouillee):
        ecriture.save()


def test_une_ecriture_validee_ne_se_supprime_pas():
    ecriture = _ecriture()

    with pytest.raises(EcritureVerrouillee):
        ecriture.delete()


def test_une_ligne_d_ecriture_ne_se_modifie_pas():
    ligne = _ecriture().lignes.first()

    ligne.montant = Decimal("1")
    with pytest.raises(ValueError):
        ligne.save()


def test_une_ligne_d_ecriture_ne_se_supprime_pas():
    ligne = _ecriture().lignes.first()

    with pytest.raises(ValueError):
        ligne.delete()
