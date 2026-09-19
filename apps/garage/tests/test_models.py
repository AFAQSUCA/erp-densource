from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.garage.models import StatutOr

from .factories import OrdreReparationFactory

pytestmark = pytest.mark.django_db


def test_un_nouvel_or_est_ouvert_avec_une_main_d_oeuvre_nulle():
    ordre = OrdreReparationFactory()

    assert ordre.statut == StatutOr.OUVERT
    assert ordre.cout_main_oeuvre == 0
    assert ordre.date_cloture is None


def test_or_cloture_sans_date_refuse_par_la_base():
    with pytest.raises(IntegrityError), transaction.atomic():
        OrdreReparationFactory(statut=StatutOr.CLOTURE, date_cloture=None)


def test_cout_main_d_oeuvre_negatif_refuse_par_la_base():
    with pytest.raises(IntegrityError), transaction.atomic():
        OrdreReparationFactory(cout_main_oeuvre=Decimal("-1"))


def test_numero_unique():
    OrdreReparationFactory(numero="OR-2026-0001")

    with pytest.raises(IntegrityError), transaction.atomic():
        OrdreReparationFactory(numero="OR-2026-0001")


def test_un_camion_peut_avoir_plusieurs_or_ouverts():
    ordre = OrdreReparationFactory()

    OrdreReparationFactory(vehicule=ordre.vehicule)

    assert ordre.vehicule.ordres_reparation.count() == 2
