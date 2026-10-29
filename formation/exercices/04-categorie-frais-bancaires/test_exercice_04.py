"""Exercice 4 — Une catégorie de dépense « Frais bancaires » (formation/exercices/04-categorie-frais-bancaires).

À copier dans apps/billing/tests/ puis : python -m pytest apps/billing/tests/test_exercice_04.py -q --no-cov
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.accounting.models import EcritureComptable, SensEcriture
from apps.billing import services
from apps.billing.forms import DepenseForm
from apps.billing.models import CategorieDepense, ModePaiement
from apps.billing.tests.helpers import finances

pytestmark = pytest.mark.django_db


def test_la_categorie_existe_et_se_propose_a_la_saisie():
    assert CategorieDepense.FRAIS_BANCAIRES.label == "Frais bancaires"
    assert CategorieDepense.FRAIS_BANCAIRES in [code for code, _ in DepenseForm().fields["categorie"].choices]


def test_une_depense_de_frais_bancaires_est_comptee_au_compte_631000():
    depense = services.enregistrer_depense(
        finances(), categorie=CategorieDepense.FRAIS_BANCAIRES, date_depense=date(2026, 9, 1),
        libelle="Frais de tenue de compte", montant=Decimal("7500"), mode=ModePaiement.VIREMENT,
    )

    ecriture = EcritureComptable.objects.get(origine="DEPENSE", origine_id=depense.pk)
    debit = ecriture.lignes.get(sens=SensEcriture.DEBIT)
    assert (debit.compte.numero, debit.montant) == ("631000", Decimal("7500"))
