from datetime import date

import pytest
from django.db import IntegrityError, transaction

from apps.fleet.models import StatutVehicule, TypeDocument
from apps.drivers.tests.factories import ChauffeurFactory

from .factories import DocumentReglementaireFactory, VehiculeFactory

pytestmark = pytest.mark.django_db


def test_nouveau_vehicule_est_disponible_par_defaut():
    assert VehiculeFactory().statut == StatutVehicule.DISPONIBLE


def test_immatriculation_unique():
    VehiculeFactory(immatriculation="1234 AB 01")

    with pytest.raises(IntegrityError), transaction.atomic():
        VehiculeFactory(immatriculation="1234 AB 01")


def test_vin_unique():
    VehiculeFactory(vin="VIN00000000000001")

    with pytest.raises(IntegrityError), transaction.atomic():
        VehiculeFactory(vin="VIN00000000000001")


def test_chauffeur_habituel_devient_null_si_la_fiche_est_supprimee_physiquement():
    fiche = ChauffeurFactory()
    camion = VehiculeFactory(chauffeur_habituel=fiche)

    fiche.hard_delete()

    camion.refresh_from_db()
    assert camion.chauffeur_habituel is None


def test_un_seul_document_actif_par_type_et_par_vehicule():
    camion = VehiculeFactory()
    DocumentReglementaireFactory(vehicule=camion, type_document=TypeDocument.PATENTE)

    with pytest.raises(IntegrityError), transaction.atomic():
        DocumentReglementaireFactory(vehicule=camion, type_document=TypeDocument.PATENTE)


def test_document_supprime_logiquement_libere_le_type():
    camion = VehiculeFactory()
    ancien = DocumentReglementaireFactory(
        vehicule=camion, type_document=TypeDocument.PATENTE
    )
    ancien.delete()

    DocumentReglementaireFactory(vehicule=camion, type_document=TypeDocument.PATENTE)


def test_expiration_avant_delivrance_refusee_par_la_base():
    with pytest.raises(IntegrityError), transaction.atomic():
        DocumentReglementaireFactory(
            date_delivrance=date(2026, 5, 1), date_expiration=date(2026, 4, 1)
        )


def test_creation_vehicule_est_auditee():
    from apps.audit.models import AuditLog

    camion = VehiculeFactory()

    entree = AuditLog.objects.get(entite="Vehicule", entite_id=camion.pk)
    assert entree.module == "PARC_AUTO"
