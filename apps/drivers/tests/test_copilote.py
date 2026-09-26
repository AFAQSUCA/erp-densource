"""Fiche copilote : création automatique, statuts (retour réunion — avenant § R... copilotes)."""

import pytest

from apps.drivers import services
from apps.drivers.models import Copilote, StatutChauffeur
from apps.hr.tests.factories import PersonnelFactory

from .factories import CopiloteFactory

pytestmark = pytest.mark.django_db


def test_un_employe_copilote_recoit_automatiquement_une_fiche():
    personnel = PersonnelFactory(poste="Copilote")

    fiche = Copilote.objects.get(personnel=personnel)
    assert fiche.statut == StatutChauffeur.DISPONIBLE


def test_un_employe_non_copilote_ne_recoit_pas_de_fiche():
    PersonnelFactory(poste="Comptable")

    assert not Copilote.objects.exists()


def test_assurer_fiche_copilote_est_idempotent():
    personnel = PersonnelFactory(poste="Copilote")

    fiche, creee = services.assurer_fiche_copilote(personnel)

    assert creee is False
    assert Copilote.objects.filter(personnel=personnel).count() == 1


def test_copilotes_disponibles_ne_retourne_que_les_disponibles():
    libre = CopiloteFactory()
    CopiloteFactory(statut=StatutChauffeur.SUSPENDU)
    CopiloteFactory(statut=StatutChauffeur.EN_MISSION)

    assert list(services.copilotes_disponibles()) == [libre]


def test_copilotes_actifs_exclut_les_inactifs():
    actif = CopiloteFactory()
    CopiloteFactory(statut=StatutChauffeur.INACTIF)

    assert list(services.copilotes_actifs()) == [actif]


def test_mettre_en_mission_puis_rappeler_de_mission():
    fiche = CopiloteFactory()

    services.mettre_en_mission_copilote(fiche)
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.EN_MISSION

    services.rappeler_copilote_de_mission(fiche)
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE


def test_rappeler_de_mission_conserve_un_statut_change_entre_temps():
    fiche = CopiloteFactory(statut=StatutChauffeur.SUSPENDU)

    services.rappeler_copilote_de_mission(fiche)

    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.SUSPENDU


def test_mettre_en_conge_puis_rappeler_de_conge():
    fiche = CopiloteFactory()

    services.mettre_copilote_en_conge(fiche)
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.EN_CONGE

    services.rappeler_copilote_de_conge(fiche)
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE
