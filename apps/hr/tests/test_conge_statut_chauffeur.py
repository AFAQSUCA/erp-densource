"""Un congé ne doit jamais écraser un statut posé par ailleurs (audit : M3-08).

« En congé » ne se pose que depuis « Disponible » : un chauffeur suspendu, inactif ou en mission garde son
statut. Sans cela, la fin du congé le remettait « Disponible » et la suspension disparaissait sans trace."""

from datetime import timedelta

import pytest

from apps.drivers import services as drivers_services
from apps.drivers.exceptions import StatutNonModifiable
from apps.drivers.models import Chauffeur, Copilote, StatutChauffeur
from apps.hr import services

from .test_conges import DEBUT, FIN, _approuve, _hierarchie

pytestmark = pytest.mark.django_db


def _fiche_en_conge_en_cours(statut_avant=None):
    """Chauffeur dont le congé démarre ; ``statut_avant`` est posé juste avant le départ."""
    hierarchie = _hierarchie(poste="Chauffeur")
    fiche = Chauffeur.objects.get(personnel=hierarchie[0])
    _approuve(hierarchie)
    if statut_avant:
        drivers_services.changer_statut(fiche, statut_avant)
    services.synchroniser_statuts_conges(aujourd_hui=DEBUT)
    fiche.refresh_from_db()
    return fiche


def _fin_du_conge():
    services.synchroniser_statuts_conges(aujourd_hui=FIN + timedelta(days=1))


@pytest.mark.parametrize("statut", [StatutChauffeur.SUSPENDU, StatutChauffeur.INACTIF])
def test_un_conge_ne_leve_pas_une_suspension_ni_une_desactivation(statut):
    fiche = _fiche_en_conge_en_cours(statut)

    assert fiche.statut == statut  # le départ en congé ne change rien

    _fin_du_conge()
    fiche.refresh_from_db()
    assert fiche.statut == statut  # la fin du congé non plus : jamais « Disponible » par erreur


def test_un_chauffeur_disponible_passe_toujours_en_conge():
    fiche = _fiche_en_conge_en_cours()

    assert fiche.statut == StatutChauffeur.EN_CONGE


def test_un_chauffeur_en_mission_le_reste_au_depart_en_conge():
    fiche = _fiche_en_conge_en_cours(StatutChauffeur.EN_MISSION)

    assert fiche.statut == StatutChauffeur.EN_MISSION


def test_a_la_fin_de_sa_mission_un_chauffeur_en_conge_passe_en_conge_et_non_disponible():
    fiche = _fiche_en_conge_en_cours(StatutChauffeur.EN_MISSION)

    drivers_services.rappeler_de_mission(fiche)

    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.EN_CONGE  # il n'est pas affectable pendant son congé
    _fin_du_conge()
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE


def test_a_la_fin_de_sa_mission_sans_conge_un_chauffeur_redevient_disponible():
    hierarchie = _hierarchie(poste="Chauffeur")
    fiche = Chauffeur.objects.get(personnel=hierarchie[0])
    drivers_services.mettre_en_mission(fiche)

    drivers_services.rappeler_de_mission(fiche)

    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE


def test_lever_une_suspension_en_plein_conge_garde_le_chauffeur_en_conge():
    fiche = _fiche_en_conge_en_cours(StatutChauffeur.SUSPENDU)

    drivers_services.changer_statut_manuel(fiche, StatutChauffeur.DISPONIBLE)

    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.EN_CONGE
    _fin_du_conge()
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE


def test_lever_une_suspension_hors_conge_remet_disponible():
    hierarchie = _hierarchie(poste="Chauffeur")
    fiche = Chauffeur.objects.get(personnel=hierarchie[0])
    drivers_services.changer_statut(fiche, StatutChauffeur.SUSPENDU)

    drivers_services.changer_statut_manuel(fiche, StatutChauffeur.DISPONIBLE)

    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE


def test_le_statut_en_conge_reste_non_modifiable_a_la_main():
    fiche = _fiche_en_conge_en_cours()

    with pytest.raises(StatutNonModifiable):
        drivers_services.changer_statut_manuel(fiche, StatutChauffeur.SUSPENDU)


# --- copilotes : mêmes règles ---


def _copilote_en_conge_en_cours(statut_avant=None):
    hierarchie = _hierarchie(poste="Copilote")
    fiche = Copilote.objects.get(personnel=hierarchie[0])
    _approuve(hierarchie)
    if statut_avant:
        drivers_services.changer_statut_copilote(fiche, statut_avant)
    services.synchroniser_statuts_conges(aujourd_hui=DEBUT)
    fiche.refresh_from_db()
    return fiche


@pytest.mark.parametrize("statut", [StatutChauffeur.SUSPENDU, StatutChauffeur.INACTIF])
def test_un_conge_ne_leve_pas_la_suspension_d_un_copilote(statut):
    fiche = _copilote_en_conge_en_cours(statut)
    _fin_du_conge()

    fiche.refresh_from_db()
    assert fiche.statut == statut


def test_a_la_fin_de_sa_mission_un_copilote_en_conge_passe_en_conge():
    fiche = _copilote_en_conge_en_cours(StatutChauffeur.EN_MISSION)
    assert fiche.statut == StatutChauffeur.EN_MISSION

    drivers_services.rappeler_copilote_de_mission(fiche)

    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.EN_CONGE


def test_a_la_fin_de_sa_mission_sans_conge_un_copilote_redevient_disponible():
    hierarchie = _hierarchie(poste="Copilote")
    fiche = Copilote.objects.get(personnel=hierarchie[0])
    drivers_services.mettre_en_mission_copilote(fiche)

    drivers_services.rappeler_copilote_de_mission(fiche)

    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE
