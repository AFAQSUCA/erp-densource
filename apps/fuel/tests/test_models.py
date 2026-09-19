from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from .factories import PleinFactory

pytestmark = pytest.mark.django_db


def test_montant_total_est_litres_fois_prix_unitaire():
    plein = PleinFactory.build(quantite_litres=Decimal("120.50"), prix_unitaire=Decimal("655"))

    assert plein.montant_total == Decimal("78927.500")


def test_un_plein_saisi_directement_n_a_ni_consommation_ni_alerte():
    plein = PleinFactory()

    assert plein.consommation is None
    assert plein.niveau_alerte == "AUCUNE"
    assert plein.alerte_saisie is False and plein.anomalie is False


@pytest.mark.parametrize("litres", ["0", "-5"])
def test_quantite_nulle_ou_negative_refusee_par_la_base(litres):
    with pytest.raises(IntegrityError), transaction.atomic():
        PleinFactory(quantite_litres=Decimal(litres))


def test_prix_nul_refuse_par_la_base():
    with pytest.raises(IntegrityError), transaction.atomic():
        PleinFactory(prix_unitaire=Decimal("0"))


def test_numero_de_ticket_unique():
    PleinFactory(numero_ticket="TKT-1")

    with pytest.raises(IntegrityError), transaction.atomic():
        PleinFactory(numero_ticket="TKT-1")


def test_un_ticket_d_un_plein_supprime_logiquement_peut_etre_reutilise():
    PleinFactory(numero_ticket="TKT-1").delete()

    PleinFactory(numero_ticket="TKT-1")
