"""Sortie d'un chauffeur ou d'un copilote (audit M1-22, avenant-sortie-personnel.md) : effets sur les missions,
les fiches et les notifications."""

from datetime import date, timedelta

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.drivers import services as drivers_services
from apps.drivers.models import Chauffeur, Copilote, StatutChauffeur
from apps.drivers.tests.factories import ChauffeurFactory, CopiloteFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.hr import sorties
from apps.hr.exceptions import SortieImpossible
from apps.hr.models import MotifSortie, SortiePersonnel
from apps.missions.models import Mission, StatutMission
from apps.notifications import taches
from apps.notifications.models import Notification

from .factories import MissionFactory

pytestmark = pytest.mark.django_db

AUJOURD_HUI = date(2026, 10, 12)


def _sortir(personnel, *, le=AUJOURD_HUI):
    return sorties.enregistrer_sortie(
        personnel, UserFactory(role=Role.RH), date_sortie=le, motif=MotifSortie.LICENCIEMENT, aujourd_hui=AUJOURD_HUI
    )


def _mission(statut, chauffeur, copilote=None):
    return MissionFactory(statut=statut, vehicule=VehiculeFactory(), chauffeur=chauffeur, copilote=copilote)


@pytest.mark.parametrize("statut", [StatutMission.EN_COURS_DEPART, StatutMission.EN_COURS_COLIS_RECUPERE])
def test_un_chauffeur_sur_la_route_ne_peut_pas_sortir(statut):
    chauffeur = ChauffeurFactory()
    mission = _mission(statut, chauffeur)

    with pytest.raises(SortieImpossible, match=f"sur la route \\(mission {mission.numero}\\)"):
        _sortir(chauffeur.personnel)
    assert not SortiePersonnel.objects.exists()  # rien n'est enregistré


def test_un_copilote_sur_la_route_ne_peut_pas_sortir():
    copilote = CopiloteFactory()
    _mission(StatutMission.EN_COURS_DEPART, ChauffeurFactory(), copilote)

    with pytest.raises(SortieImpossible, match="sur la route"):
        _sortir(copilote.personnel)


def test_une_sortie_a_venir_attend_la_fin_de_la_mission():
    chauffeur = ChauffeurFactory()
    mission = _mission(StatutMission.EN_COURS_DEPART, chauffeur)
    sortie, _ = _sortir(chauffeur.personnel, le=AUJOURD_HUI + timedelta(days=3))
    echeance = AUJOURD_HUI + timedelta(days=3)

    resultat = sorties.appliquer_sorties_echues(aujourd_hui=echeance)

    assert resultat["appliquees"] == 0 and resultat["reportees"][0][0] == sortie
    Mission.objects.filter(pk=mission.pk).update(statut=StatutMission.LIVREE)
    assert sorties.appliquer_sorties_echues(aujourd_hui=echeance + timedelta(days=1))["appliquees"] == 1


def test_les_fiches_chauffeur_et_copilote_du_partant_deviennent_inactives():
    chauffeur, copilote = ChauffeurFactory(), CopiloteFactory()

    _, bilan_chauffeur = _sortir(chauffeur.personnel)
    _, bilan_copilote = _sortir(copilote.personnel)

    assert Chauffeur.objects.get(pk=chauffeur.pk).statut == StatutChauffeur.INACTIF
    assert Copilote.objects.get(pk=copilote.pk).statut == StatutChauffeur.INACTIF
    assert bilan_chauffeur["fiche_chauffeur_inactive"] and bilan_copilote["fiche_copilote_inactive"]


def test_un_chauffeur_en_conge_qui_sort_devient_inactif_et_le_reste_a_la_fin_du_conge():
    chauffeur = ChauffeurFactory(statut=StatutChauffeur.EN_CONGE)

    _sortir(chauffeur.personnel)

    assert Chauffeur.objects.get(pk=chauffeur.pk).statut == StatutChauffeur.INACTIF


def test_la_mission_affectee_du_chauffeur_sortant_repasse_planifiee_et_le_parc_auto_est_prevenu():
    parc = UserFactory(role=Role.PARCAUTO)
    chauffeur = ChauffeurFactory(personnel__prenom="Issa", personnel__nom="Bamba")
    mission = _mission(StatutMission.AFFECTEE, chauffeur, CopiloteFactory())

    _, bilan = _sortir(chauffeur.personnel)

    mission.refresh_from_db()
    assert mission.statut == StatutMission.PLANIFIEE
    assert mission.vehicule is None and mission.chauffeur is None and mission.copilote is None
    assert bilan["missions_desaffectees"] == [mission.numero]
    (notification,) = Notification.objects.filter(destinataire=parc)
    assert notification.titre == f"Mission {mission.numero} à réaffecter"
    assert notification.message.startswith("Sortie de Issa Bamba le 12/10/2026")
    assert notification.url == reverse("missions:detail", args=[mission.pk])


def test_le_copilote_sortant_est_seulement_retire_de_la_mission_affectee():
    chauffeur, copilote = ChauffeurFactory(), CopiloteFactory()
    mission = _mission(StatutMission.AFFECTEE, chauffeur, copilote)

    _, bilan = _sortir(copilote.personnel)

    mission.refresh_from_db()
    assert mission.statut == StatutMission.AFFECTEE and mission.chauffeur == chauffeur and mission.copilote is None
    assert bilan["missions_sans_copilote"] == [mission.numero] and bilan["missions_desaffectees"] == []


def test_les_missions_terminees_ne_sont_pas_touchees():
    chauffeur = ChauffeurFactory()
    livree = _mission(StatutMission.LIVREE, chauffeur)
    planifiee = MissionFactory(statut=StatutMission.PLANIFIEE)

    _sortir(chauffeur.personnel)

    assert Mission.objects.get(pk=livree.pk).chauffeur == chauffeur
    assert Mission.objects.get(pk=planifiee.pk).statut == StatutMission.PLANIFIEE


def test_un_chauffeur_sorti_n_est_plus_propose():
    chauffeur = ChauffeurFactory()

    _sortir(chauffeur.personnel)

    assert chauffeur not in drivers_services.chauffeurs_actifs()
    assert chauffeur not in drivers_services.chauffeurs_disponibles()


def test_la_tache_du_jour_previent_la_rh_une_seule_fois_d_une_sortie_retenue():
    rh = UserFactory(role=Role.RH)
    chauffeur = ChauffeurFactory(personnel__prenom="Issa", personnel__nom="Bamba")
    _mission(StatutMission.EN_COURS_DEPART, chauffeur)
    _sortir(chauffeur.personnel, le=AUJOURD_HUI + timedelta(days=1))

    for jour in (1, 2):
        resultat = taches.executer_taches_quotidiennes(aujourd_hui=AUJOURD_HUI + timedelta(days=jour))

    assert resultat["sorties_appliquees"] == 0
    (notification,) = Notification.objects.filter(destinataire=rh, titre="Sortie de Issa Bamba en attente")
    assert "sur la route" in notification.message
    assert notification.url == reverse("hr:personnel_detail", args=[chauffeur.personnel_id])


def test_la_tache_du_jour_applique_une_sortie_echue():
    chauffeur = ChauffeurFactory()
    _sortir(chauffeur.personnel, le=AUJOURD_HUI + timedelta(days=1))

    resultat = taches.executer_taches_quotidiennes(aujourd_hui=AUJOURD_HUI + timedelta(days=1))

    assert resultat["sorties_appliquees"] == 1
    assert Chauffeur.objects.get(pk=chauffeur.pk).statut == StatutChauffeur.INACTIF
