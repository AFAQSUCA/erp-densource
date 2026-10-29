"""Exercice 2 — Un 5e document réglementaire : la carte de transport (formation/exercices/02-carte-de-transport).

À copier dans apps/fleet/tests/ puis : python -m pytest apps/fleet/tests/test_exercice_02.py -q --no-cov
"""

from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet import services
from apps.fleet.models import DocumentReglementaire, TypeDocument
from apps.fleet.tests.factories import DocumentReglementaireFactory, VehiculeEnRegleFactory, VehiculeFactory
from apps.importation import modele
from apps.missions import services as missions_services
from apps.missions.exceptions import AffectationImpossible
from apps.missions.tests.test_services import _planifiee

pytestmark = pytest.mark.django_db

ANCIENS = [TypeDocument.CARTE_GRISE, TypeDocument.ASSURANCE, TypeDocument.VISITE_TECHNIQUE, TypeDocument.PATENTE]


def _camion_avec_les_4_anciens_documents():
    camion = VehiculeFactory()
    for code in ANCIENS:
        DocumentReglementaireFactory(vehicule=camion, type_document=code, date_expiration=date(2099, 1, 1))
    return camion


def test_la_carte_de_transport_est_un_type_de_document():
    assert TypeDocument.CARTE_TRANSPORT.label == "Carte de transport"
    assert len(TypeDocument.choices) == 5


def test_sans_carte_de_transport_le_camion_n_est_pas_affectable():
    camion = _camion_avec_les_4_anciens_documents()

    with pytest.raises(AffectationImpossible, match="carte de transport non enregistrée"):
        missions_services.affecter_mission(_planifiee(), vehicule=camion, chauffeur=ChauffeurFactory())


def test_un_camion_en_regle_reste_affectable():
    missions_services.affecter_mission(_planifiee(), vehicule=VehiculeEnRegleFactory(), chauffeur=ChauffeurFactory())


def test_une_carte_de_transport_qui_expire_bientot_est_signalee():
    camion = VehiculeEnRegleFactory()
    DocumentReglementaire.objects.filter(vehicule=camion, type_document=TypeDocument.CARTE_TRANSPORT).update(
        date_expiration=timezone.localdate() + timedelta(days=10)
    )

    types = set(services.documents_a_renouveler().values_list("type_document", flat=True))

    assert TypeDocument.CARTE_TRANSPORT in types


def test_la_fiche_du_camion_et_l_import_excel_connaissent_la_carte_de_transport(client):
    client.force_login(UserFactory(role=Role.PARCAUTO))
    camion = VehiculeEnRegleFactory()

    assert "Carte de transport" in client.get(reverse("fleet:detail", args=[camion.pk])).content.decode()
    assert TypeDocument.CARTE_TRANSPORT in [code for code, _ in modele.DOCUMENTS]
