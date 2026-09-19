from datetime import date

import pytest

from apps.fleet import services
from apps.fleet.models import StatutVehicule, TypeDocument

from .factories import DocumentReglementaireFactory, VehiculeFactory

pytestmark = pytest.mark.django_db


# --- algorithme de recalcul du statut (cahier-des-charges.md:96-100) ---


def test_regle_1_or_ouvert_donne_en_maintenance():
    statut = services.calculer_statut(
        StatutVehicule.DISPONIBLE, or_ouverts=True, mission_active=False
    )

    assert statut == StatutVehicule.EN_MAINTENANCE


def test_regle_2_mission_active_donne_en_mission():
    statut = services.calculer_statut(
        StatutVehicule.DISPONIBLE, or_ouverts=False, mission_active=True
    )

    assert statut == StatutVehicule.EN_MISSION


@pytest.mark.parametrize("bloque", [StatutVehicule.IMMOBILISE, StatutVehicule.HORS_SERVICE])
def test_regle_3_immobilise_et_hors_service_sont_conserves(bloque):
    statut = services.calculer_statut(bloque, or_ouverts=False, mission_active=False)

    assert statut == bloque


@pytest.mark.parametrize(
    "actuel", [StatutVehicule.EN_MAINTENANCE, StatutVehicule.EN_MISSION]
)
def test_regle_4_sinon_disponible(actuel):
    statut = services.calculer_statut(actuel, or_ouverts=False, mission_active=False)

    assert statut == StatutVehicule.DISPONIBLE


def test_or_ouvert_prime_sur_mission_et_sur_immobilise():
    statut = services.calculer_statut(
        StatutVehicule.IMMOBILISE, or_ouverts=True, mission_active=True
    )

    assert statut == StatutVehicule.EN_MAINTENANCE


def test_mission_active_prime_sur_immobilise():
    statut = services.calculer_statut(
        StatutVehicule.IMMOBILISE, or_ouverts=False, mission_active=True
    )

    assert statut == StatutVehicule.EN_MISSION


def test_recalculer_statut_enregistre_en_base():
    camion = VehiculeFactory(statut=StatutVehicule.EN_MAINTENANCE)

    services.recalculer_statut(camion, or_ouverts=False, mission_active=False)

    camion.refresh_from_db()
    assert camion.statut == StatutVehicule.DISPONIBLE


def test_definir_statut_accepte_immobilise():
    camion = VehiculeFactory()

    services.definir_statut(camion, StatutVehicule.IMMOBILISE)

    camion.refresh_from_db()
    assert camion.statut == StatutVehicule.IMMOBILISE


def test_definir_statut_refuse_un_statut_inconnu():
    camion = VehiculeFactory()

    with pytest.raises(ValueError):
        services.definir_statut(camion, "VOLANT")


# --- alerte documents à 30 jours (cahier-des-charges.md:95) ---


def test_document_expirant_dans_30_jours_est_signale():
    doc = DocumentReglementaireFactory(date_expiration=date(2026, 10, 20))

    resultat = services.documents_a_renouveler(aujourd_hui=date(2026, 9, 20))

    assert doc in resultat


def test_document_expirant_dans_31_jours_n_est_pas_signale():
    doc = DocumentReglementaireFactory(date_expiration=date(2026, 10, 21))

    resultat = services.documents_a_renouveler(aujourd_hui=date(2026, 9, 20))

    assert doc not in resultat


def test_document_deja_expire_est_signale():
    doc = DocumentReglementaireFactory(
        date_delivrance=date(2025, 1, 1), date_expiration=date(2026, 1, 1)
    )

    resultat = services.documents_a_renouveler(aujourd_hui=date(2026, 9, 20))

    assert doc in resultat


def test_jours_restants_negatif_quand_expire():
    doc = DocumentReglementaireFactory.build(
        date_delivrance=date(2025, 1, 1), date_expiration=date(2026, 9, 10)
    )

    assert doc.jours_restants(aujourd_hui=date(2026, 9, 20)) == -10


def test_documents_a_renouveler_utilise_les_types_du_cdc():
    assert set(TypeDocument.values) == {
        "CARTE_GRISE",
        "ASSURANCE",
        "VISITE_TECHNIQUE",
        "PATENTE",
    }


# --- fin de mission et compteur kilométrique ---


def test_liberer_apres_mission_remet_un_camion_en_mission_disponible():
    camion = VehiculeFactory(statut=StatutVehicule.EN_MISSION)

    services.liberer_apres_mission(camion)

    camion.refresh_from_db()
    assert camion.statut == StatutVehicule.DISPONIBLE


@pytest.mark.parametrize(
    "statut",
    [
        StatutVehicule.EN_MAINTENANCE,
        StatutVehicule.IMMOBILISE,
        StatutVehicule.HORS_SERVICE,
    ],
)
def test_liberer_apres_mission_conserve_les_autres_statuts(statut):
    camion = VehiculeFactory(statut=statut)

    services.liberer_apres_mission(camion)

    camion.refresh_from_db()
    assert camion.statut == statut


def test_enregistrer_kilometrage_met_a_jour_le_compteur():
    camion = VehiculeFactory(kilometrage=1000)

    services.enregistrer_kilometrage(camion, 1500)

    camion.refresh_from_db()
    assert camion.kilometrage == 1500


def test_enregistrer_kilometrage_refuse_de_reculer():
    camion = VehiculeFactory(kilometrage=1000)

    with pytest.raises(ValueError):
        services.enregistrer_kilometrage(camion, 999)
