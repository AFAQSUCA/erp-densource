"""Qui est prévenu de quoi pour la prévision de trésorerie des missions (R4)."""

from decimal import Decimal
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.missions import services as missions_services
from apps.missions import terrain as missions_terrain
from apps.missions.models import TypeFraisMission
from apps.missions.tests.test_frais_mission import _chauffeur, _finances, _mission_affectee, _parcauto
from apps.notifications.models import CategorieNotification, Notification

pytestmark = pytest.mark.django_db


def _de(utilisateur):
    return list(Notification.objects.filter(destinataire=utilisateur).order_by("pk"))


def _preuve():
    return SimpleUploadedFile("p.jpg", BytesIO(b"x").read(), content_type="image/jpeg")


def test_la_finance_est_prevenue_d_une_affectation():
    finance = UserFactory(role=Role.FINANCES)
    from apps.drivers.tests.factories import ChauffeurFactory
    from apps.fleet.tests.factories import VehiculeFactory
    from apps.missions.models import StatutMission
    from apps.missions.tests.factories import MissionFactory

    mission = MissionFactory(statut=StatutMission.PLANIFIEE)

    missions_services.affecter_mission(mission, vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory())

    (notification,) = _de(finance)
    assert notification.categorie == CategorieNotification.FRAIS_MISSION


def test_le_parc_auto_est_prevenu_d_un_imprevu_declare():
    parcauto = UserFactory(role=Role.PARCAUTO)
    chauffeur = _chauffeur()
    mission = _mission_affectee(chauffeur)

    missions_terrain.declarer_imprevu(mission, chauffeur, montant=Decimal("9000"), justificatif=_preuve())

    (notification,) = _de(parcauto)
    assert notification.categorie == CategorieNotification.FRAIS_MISSION
    assert mission.numero in notification.titre


def test_la_finance_est_prevenue_apres_la_validation_du_parc_auto():
    finance = UserFactory(role=Role.FINANCES)
    chauffeur = _chauffeur()
    mission = _mission_affectee(chauffeur)
    frais = missions_terrain.declarer_imprevu(mission, chauffeur, montant=Decimal("9000"), justificatif=_preuve())

    missions_terrain.valider_parcauto(frais, _parcauto())

    (notification,) = _de(finance)
    assert notification.categorie == CategorieNotification.FRAIS_MISSION
    assert "Parc Auto" in notification.message


def test_l_auteur_est_prevenu_du_rejet_d_une_avance():
    mission = _mission_affectee()
    parcauto = _parcauto()
    frais = missions_terrain.planifier_frais(
        mission, parcauto, type_frais=TypeFraisMission.AVANCE_ROUTE, montant=Decimal("50000")
    )

    missions_terrain.rejeter(frais, _finances(), motif="Montant excessif")

    (notification,) = _de(parcauto)
    assert "Montant excessif" in notification.message


def test_le_chauffeur_est_prevenu_du_rejet_de_son_imprevu():
    chauffeur = _chauffeur()
    mission = _mission_affectee(chauffeur)
    frais = missions_terrain.declarer_imprevu(mission, chauffeur, montant=Decimal("9000"), justificatif=_preuve())

    missions_terrain.rejeter(frais, _parcauto(), motif="Aucune preuve valable")

    utilisateur_chauffeur = chauffeur.personnel.utilisateur
    (notification,) = _de(utilisateur_chauffeur)
    assert "Aucune preuve valable" in notification.message
