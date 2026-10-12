"""Audit M5-10 : le kilométrage d'arrivée d'une mission est borné (il fige ensuite le compteur du camion)."""

import pytest

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.missions import services
from apps.missions.exceptions import KilometrageInvalide
from apps.parametres import services as parametres_services
from apps.parametres.models import ECART_KM_MAX

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
        mission, code=mission.code_destinataire, km_arrivee=mission.km_depart + ECART_KM_MAX
    )

    assert livree.km_arrivee == mission.km_depart + 5000


def test_l_ecart_maximal_des_parametres_s_applique_a_l_arrivee_d_une_mission():
    parametres_services.modifier_parametres(UserFactory(role=Role.ADMIN), ecart_km_max=1000)
    mission = _recuperee()

    with pytest.raises(KilometrageInvalide, match="plus de 1000 km sur une mission"):
        services.livrer_mission(mission, code=mission.code_destinataire, km_arrivee=mission.km_depart + 1500)
