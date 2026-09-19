"""Ordres de réparation — cahier-des-charges.md:161-168 et recalcul du statut :96-100."""

import re
from decimal import Decimal

import pytest

from apps.audit.models import AuditLog
from apps.fleet.models import StatutVehicule
from apps.fleet.services import definir_statut
from apps.fleet.tests.factories import VehiculeFactory
from apps.garage import services
from apps.garage.exceptions import CoutInvalide, TransitionOrInterdite
from apps.garage.models import LieuReparation, StatutOr, TypeOr
from apps.missions.tests.test_services import _affectee, _en_cours

pytestmark = pytest.mark.django_db


def _ouvrir(vehicule=None, **surcharges):
    donnees = dict(
        type_or=TypeOr.CURATIF, lieu=LieuReparation.INTERNE, motif="Fuite d'huile"
    )
    donnees.update(surcharges)
    return services.ouvrir_or(vehicule or VehiculeFactory(), **donnees)


def _statut(vehicule):
    vehicule.refresh_from_db()
    return vehicule.statut


# --- ouverture ---


def test_ouvrir_cree_un_or_ouvert_numerote_et_passe_le_camion_en_maintenance():
    camion = VehiculeFactory()

    ordre = _ouvrir(camion, type_or=TypeOr.PNEUMATIQUES, lieu=LieuReparation.EXTERNE)

    assert re.fullmatch(r"OR-\d{4}-0001", ordre.numero)
    assert ordre.statut == StatutOr.OUVERT
    assert (ordre.type_or, ordre.lieu) == (TypeOr.PNEUMATIQUES, LieuReparation.EXTERNE)
    assert _statut(camion) == StatutVehicule.EN_MAINTENANCE


def test_les_numeros_d_or_sont_consecutifs():
    assert _ouvrir().numero.endswith("-0001")
    assert _ouvrir().numero.endswith("-0002")


def test_les_or_et_les_missions_ont_des_compteurs_distincts():
    _affectee()  # consomme MIS-...-0001

    assert _ouvrir().numero.endswith("-0001")


def test_ouvrir_un_or_sur_un_camion_en_mission_signale_une_panne_en_route():
    mission = _en_cours()

    _ouvrir(mission.vehicule)

    assert _statut(mission.vehicule) == StatutVehicule.EN_MAINTENANCE


def test_l_ouverture_et_la_cloture_sont_auditees():
    ordre = _ouvrir()
    services.cloturer_or(ordre)

    entrees = AuditLog.objects.filter(entite="OrdreReparation", entite_id=ordre.pk)
    assert entrees.get(action="CREATE").module == "PARC_AUTO"
    assert entrees.get(action="UPDATE").nouvelle_valeur["statut"] == "CLOTURE"


# --- clôture : enregistrement ---


def test_cloturer_enregistre_la_main_d_oeuvre_et_la_date():
    ordre = _ouvrir()

    services.cloturer_or(ordre, cout_main_oeuvre=Decimal("45000"))

    ordre.refresh_from_db()
    assert ordre.statut == StatutOr.CLOTURE
    assert ordre.date_cloture is not None
    assert ordre.cout_main_oeuvre == Decimal("45000.00")


def test_cloturer_refuse_un_or_deja_cloture():
    ordre = _ouvrir()
    services.cloturer_or(ordre)

    with pytest.raises(TransitionOrInterdite):
        services.cloturer_or(ordre)


def test_cloturer_refuse_une_main_d_oeuvre_negative_et_laisse_l_or_ouvert():
    camion = VehiculeFactory()
    ordre = _ouvrir(camion)

    with pytest.raises(CoutInvalide):
        services.cloturer_or(ordre, cout_main_oeuvre=Decimal("-1"))

    ordre.refresh_from_db()
    assert ordre.statut == StatutOr.OUVERT
    assert _statut(camion) == StatutVehicule.EN_MAINTENANCE


# --- clôture : recalcul du statut, règle par règle ---


def test_regle_4_aucun_autre_or_ni_mission_le_camion_redevient_disponible():
    camion = VehiculeFactory()
    ordre = _ouvrir(camion)

    services.cloturer_or(ordre)

    assert _statut(camion) == StatutVehicule.DISPONIBLE


def test_regle_1_un_autre_or_ouvert_maintient_le_camion_en_maintenance():
    camion = VehiculeFactory()
    premier = _ouvrir(camion)
    second = _ouvrir(camion)

    services.cloturer_or(premier)
    assert _statut(camion) == StatutVehicule.EN_MAINTENANCE

    services.cloturer_or(second)
    assert _statut(camion) == StatutVehicule.DISPONIBLE


def test_regle_2_mission_affectee_le_camion_repasse_en_mission():
    mission = _affectee()
    ordre = _ouvrir(mission.vehicule)

    services.cloturer_or(ordre)

    assert _statut(mission.vehicule) == StatutVehicule.EN_MISSION


def test_regle_2_panne_en_cours_de_mission_le_camion_repasse_en_mission():
    mission = _en_cours()
    ordre = _ouvrir(mission.vehicule)

    services.cloturer_or(ordre)

    assert _statut(mission.vehicule) == StatutVehicule.EN_MISSION


@pytest.mark.parametrize(
    "statut", [StatutVehicule.IMMOBILISE, StatutVehicule.HORS_SERVICE]
)
def test_regle_3_immobilise_ou_hors_service_pose_pendant_l_or_est_conserve(statut):
    camion = VehiculeFactory()
    ordre = _ouvrir(camion)
    definir_statut(camion, statut)

    services.cloturer_or(ordre)

    assert _statut(camion) == statut


def test_regle_1_prime_sur_les_regles_2_et_3():
    mission = _affectee()
    camion = mission.vehicule
    premier = _ouvrir(camion)
    _ouvrir(camion)
    definir_statut(camion, StatutVehicule.IMMOBILISE)

    services.cloturer_or(premier)

    assert _statut(camion) == StatutVehicule.EN_MAINTENANCE


def test_la_cloture_d_un_or_ne_touche_pas_les_autres_camions():
    autre = VehiculeFactory()
    _ouvrir(autre)
    ordre = _ouvrir()

    services.cloturer_or(ordre)

    assert _statut(autre) == StatutVehicule.EN_MAINTENANCE


# --- consultation ---


def test_vehicule_a_or_ouvert():
    camion = VehiculeFactory()
    assert services.vehicule_a_or_ouvert(camion) is False

    ordre = _ouvrir(camion)
    assert services.vehicule_a_or_ouvert(camion) is True

    services.cloturer_or(ordre)
    assert services.vehicule_a_or_ouvert(camion) is False


# --- enchaînement avec missions ---


def test_une_mission_affectee_peut_demarrer_apres_la_reparation_de_son_camion():
    from apps.missions import services as missions_services
    from apps.missions.models import StatutMission

    mission = _affectee()
    services.cloturer_or(_ouvrir(mission.vehicule))
    assert _statut(mission.vehicule) == StatutVehicule.EN_MISSION  # règle 2 du CDC

    missions_services.demarrer_mission(mission)

    mission.refresh_from_db()
    assert mission.statut == StatutMission.EN_COURS_DEPART
