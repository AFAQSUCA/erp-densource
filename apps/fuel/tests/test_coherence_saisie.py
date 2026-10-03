"""Audit M6-09 / M5-10 : un plein est cohérent (date, volume, kilométrage) avant d'être enregistré."""

import itertools
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet import services as fleet_services
from apps.fleet.tests.factories import VehiculeFactory
from apps.fuel import services
from apps.fuel.exceptions import KilometrageInvalide, SaisieInvalide

pytestmark = pytest.mark.django_db

_tickets = itertools.count(1)


def _plein(vehicule, **surcharges):
    donnees = dict(
        vehicule=vehicule, chauffeur=ChauffeurFactory(), date_plein=timezone.localdate(), station="Total",
        quantite_litres=Decimal("100"), prix_unitaire=Decimal("655"), km_compteur=vehicule.kilometrage + 400,
        numero_ticket=f"C-{next(_tickets)}", confirmer_alerte_saisie=True,
    )
    donnees.update(surcharges)
    return services.enregistrer_plein(**donnees)


def test_un_plein_date_dans_le_futur_est_refuse():
    camion = VehiculeFactory()

    with pytest.raises(SaisieInvalide, match="dans le futur"):
        _plein(camion, date_plein=timezone.localdate() + timedelta(days=1))


def test_un_plein_du_jour_est_accepte():
    assert _plein(VehiculeFactory()).date_plein == timezone.localdate()


def test_un_volume_superieur_au_reservoir_est_refuse():
    camion = VehiculeFactory(reservoir_l=300)

    with pytest.raises(SaisieInvalide, match=r"réservoir du camion \(300 L\)"):
        _plein(camion, quantite_litres=Decimal("301"))


def test_un_volume_egal_au_reservoir_est_accepte():
    camion = VehiculeFactory(reservoir_l=300)

    assert _plein(camion, quantite_litres=Decimal("300")).quantite_litres == Decimal("300")


def test_un_km_trop_haut_par_rapport_au_plein_precedent_est_refuse_et_ne_fige_pas_le_compteur():
    camion = VehiculeFactory()
    premier = _plein(camion)

    with pytest.raises(KilometrageInvalide, match="vérifiez la saisie"):
        _plein(camion, km_compteur=premier.km_compteur + 50000)  # un zéro de trop

    camion.refresh_from_db()
    assert camion.kilometrage == premier.km_compteur  # le compteur n'a pas été gonflé


def test_un_km_trop_haut_pour_le_premier_plein_est_compare_au_compteur_du_camion():
    camion = VehiculeFactory(kilometrage=120000)

    with pytest.raises(KilometrageInvalide):
        _plein(camion, km_compteur=1200000)


def test_un_camion_au_compteur_jamais_renseigne_accepte_son_premier_plein():
    camion = VehiculeFactory(kilometrage=0)

    assert _plein(camion, km_compteur=85000).km_compteur == 85000


def test_la_distance_limite_est_acceptee():
    camion = VehiculeFactory()
    premier = _plein(camion)

    assert _plein(camion, km_compteur=premier.km_compteur + fleet_services.ECART_KM_MAX).distance_km == 5000
