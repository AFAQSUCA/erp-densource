"""Audit M5-10 : le kilométrage d'arrivée d'une mission est borné (il fige ensuite le compteur du camion)."""

import pytest

from apps.fleet import services as fleet_services
from apps.missions import services
from apps.missions.exceptions import KilometrageInvalide

from .test_services import _recuperee

pytestmark = pytest.mark.django_db


def test_une_faute_de_frappe_sur_le_km_d_arrivee_est_refusee_et_le_compteur_reste_intact():
    mission = _recuperee()
    compteur = mission.vehicule.kilometrage

    with pytest.raises(KilometrageInvalide, match="vérifiez la saisie"):
        services.livrer_mission(
            mission, code=mission.code_destinataire, km_arrivee=mission.km_depart + 100000
        )

    mission.vehicule.refresh_from_db()
    assert mission.vehicule.kilometrage == compteur


def test_la_distance_maximale_d_une_mission_est_acceptee():
    mission = _recuperee()

    livree = services.livrer_mission(
        mission, code=mission.code_destinataire, km_arrivee=mission.km_depart + fleet_services.ECART_KM_MAX
    )

    assert livree.km_arrivee == mission.km_depart + 5000
