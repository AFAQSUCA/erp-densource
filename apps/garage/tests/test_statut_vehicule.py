"""Immobilisation, mise hors service et remise en service — cahier-des-charges.md:91-100."""

import pytest

from apps.fleet.models import StatutVehicule
from apps.fleet.services import definir_statut
from apps.fleet.tests.factories import VehiculeFactory
from apps.garage import services
from apps.garage.exceptions import StatutVehiculeInvalide
from apps.garage.models import LieuReparation, TypeOr
from apps.missions.tests.test_services import _affectee, _en_cours, _livree

pytestmark = pytest.mark.django_db


def _ouvrir(vehicule):
    return services.ouvrir_or(
        vehicule, type_or=TypeOr.CURATIF, lieu=LieuReparation.INTERNE, motif="Panne"
    )


def _statut(vehicule):
    vehicule.refresh_from_db()
    return vehicule.statut


# --- immobiliser / hors service ---


def test_immobiliser_un_camion_disponible():
    camion = VehiculeFactory()

    services.immobiliser_vehicule(camion)

    assert _statut(camion) == StatutVehicule.IMMOBILISE


def test_mettre_hors_service_un_camion_disponible():
    camion = VehiculeFactory()

    services.mettre_hors_service(camion)

    assert _statut(camion) == StatutVehicule.HORS_SERVICE


def test_un_camion_immobilise_peut_devenir_hors_service():
    camion = VehiculeFactory(statut=StatutVehicule.IMMOBILISE)

    services.mettre_hors_service(camion)

    assert _statut(camion) == StatutVehicule.HORS_SERVICE


def test_immobiliser_deux_fois_est_refuse():
    camion = VehiculeFactory(statut=StatutVehicule.IMMOBILISE)

    with pytest.raises(StatutVehiculeInvalide, match="déjà immobilisé"):
        services.immobiliser_vehicule(camion)


def test_mettre_hors_service_deux_fois_est_refuse():
    camion = VehiculeFactory(statut=StatutVehicule.HORS_SERVICE)

    with pytest.raises(StatutVehiculeInvalide, match="déjà hors service"):
        services.mettre_hors_service(camion)


@pytest.mark.parametrize("etape", [_affectee, _en_cours])
def test_un_camion_reserve_ou_en_route_ne_s_immobilise_pas(etape):
    camion = etape().vehicule

    with pytest.raises(StatutVehiculeInvalide, match="ouvrez un OR"):
        services.immobiliser_vehicule(camion)
    with pytest.raises(StatutVehiculeInvalide, match="ouvrez un OR"):
        services.mettre_hors_service(camion)

    assert _statut(camion) != StatutVehicule.IMMOBILISE


def test_un_camion_peut_etre_immobilise_apres_la_fin_de_sa_mission():
    camion = _livree().vehicule

    services.immobiliser_vehicule(camion)

    assert _statut(camion) == StatutVehicule.IMMOBILISE


def test_immobiliser_un_camion_pendant_un_or_conserve_l_immobilisation_a_la_cloture():
    camion = VehiculeFactory()
    ordre = _ouvrir(camion)

    services.immobiliser_vehicule(camion)
    services.cloturer_or(ordre)

    assert _statut(camion) == StatutVehicule.IMMOBILISE  # règle 3 du CDC


# --- remise en service ---


@pytest.mark.parametrize("statut", [StatutVehicule.IMMOBILISE, StatutVehicule.HORS_SERVICE])
def test_remettre_en_service_un_camion_sans_or_ni_mission_le_rend_disponible(statut):
    camion = VehiculeFactory(statut=statut)

    services.remettre_en_service(camion)

    assert _statut(camion) == StatutVehicule.DISPONIBLE


def test_remettre_en_service_avec_un_or_ouvert_donne_en_maintenance():
    camion = VehiculeFactory()
    _ouvrir(camion)
    services.immobiliser_vehicule(camion)

    services.remettre_en_service(camion)

    assert _statut(camion) == StatutVehicule.EN_MAINTENANCE


def test_remettre_en_service_avec_une_mission_reservee_donne_en_mission():
    camion = _affectee().vehicule
    definir_statut(camion, StatutVehicule.IMMOBILISE)  # ex. posé par un autre chemin

    services.remettre_en_service(camion)

    assert _statut(camion) == StatutVehicule.EN_MISSION


@pytest.mark.parametrize(
    "statut",
    [StatutVehicule.DISPONIBLE, StatutVehicule.EN_MISSION, StatutVehicule.EN_MAINTENANCE],
)
def test_remettre_en_service_refuse_un_camion_qui_n_est_pas_immobilise(statut):
    camion = VehiculeFactory(statut=statut)

    with pytest.raises(StatutVehiculeInvalide, match="immobilisé ou hors service"):
        services.remettre_en_service(camion)

    assert _statut(camion) == statut


# --- lecture ---


def test_rechercher_ordres_par_statut_type_lieu_et_texte():
    camion = VehiculeFactory(immatriculation="1111 AA 01")
    ouvert = services.ouvrir_or(
        camion, type_or=TypeOr.PNEUMATIQUES, lieu=LieuReparation.EXTERNE, motif="Crevaison avant droite"
    )
    cloture = _ouvrir(VehiculeFactory())
    services.cloturer_or(cloture)

    assert list(services.rechercher_ordres(statut="OUVERT")) == [ouvert]
    assert list(services.rechercher_ordres(type_or="PNEUMATIQUES")) == [ouvert]
    assert list(services.rechercher_ordres(lieu="EXTERNE")) == [ouvert]
    assert list(services.rechercher_ordres(recherche="crevaison")) == [ouvert]
    assert list(services.rechercher_ordres(recherche="1111 aa")) == [ouvert]
    assert list(services.rechercher_ordres(recherche=ouvert.numero)) == [ouvert]


def test_rechercher_ordres_ignore_les_valeurs_inconnues():
    _ouvrir(VehiculeFactory())

    assert services.rechercher_ordres(statut="?", type_or="?", lieu="?", recherche=" ").count() == 1


def test_ordres_du_vehicule_du_plus_recent_au_plus_ancien_avec_limite():
    camion = VehiculeFactory()
    ordres = [_ouvrir(camion) for _ in range(4)]

    recents = list(services.ordres_du_vehicule(camion, limite=3))

    assert recents == [ordres[3], ordres[2], ordres[1]]


def test_ordres_du_vehicule_ignore_les_autres_camions():
    _ouvrir(VehiculeFactory())
    camion = VehiculeFactory()

    assert list(services.ordres_du_vehicule(camion)) == []
