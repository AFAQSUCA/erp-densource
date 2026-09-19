"""Notifications des signalements du chauffeur, et alerte du tableau de bord."""

from datetime import date

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.dashboard import services as dashboard
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.garage import terrain
from apps.garage.models import CODES_CHECKLIST, GraviteIncident, TypeIncident
from apps.missions.models import StatutMission
from apps.missions.tests.factories import MissionFactory
from apps.notifications.models import CategorieNotification, NiveauNotification, Notification

pytestmark = pytest.mark.django_db


def _de(utilisateur):
    return list(Notification.objects.filter(destinataire=utilisateur).order_by("pk"))


def _mission():
    chauffeur = ChauffeurFactory()
    return MissionFactory(statut=StatutMission.AFFECTEE, vehicule=VehiculeFactory(), chauffeur=chauffeur)


def _declarer(gravite=GraviteIncident.MOYENNE, **surcharges):
    mission = _mission()
    donnees = dict(chauffeur=mission.chauffeur, mission=mission, type_incident=TypeIncident.PANNE,
                   gravite=gravite, description="Moteur qui chauffe", lieu="Bouaké")
    donnees.update(surcharges)
    return terrain.declarer_incident(**donnees)


def test_un_incident_previent_le_parc_auto_et_la_direction():
    parc, chef, rh = (UserFactory(role=r) for r in (Role.PARCAUTO, Role.DIRECTION, Role.RH))

    incident = _declarer()

    for compte in (parc, chef):
        (notification,) = _de(compte)
        assert notification.categorie == CategorieNotification.INCIDENT
        assert notification.niveau == NiveauNotification.ATTENTION
        assert notification.titre == f"Panne signalé : {incident.vehicule.immatriculation}"
        assert "Moteur qui chauffe" in notification.message and "(Bouaké)" in notification.message
        assert notification.url == reverse("garage:incident", args=[incident.pk])
    assert _de(rh) == []


def test_un_incident_grave_est_urgent():
    parc = UserFactory(role=Role.PARCAUTO)

    _declarer(gravite=GraviteIncident.GRAVE)

    assert _de(parc)[0].niveau == NiveauNotification.URGENT


def test_une_checklist_avec_ko_previent_le_parc_auto_seulement():
    parc, chef = UserFactory(role=Role.PARCAUTO), UserFactory(role=Role.DIRECTION)
    mission = _mission()
    resultats = [{"code": c, "ok": True, "remarque": ""} for c in CODES_CHECKLIST]
    resultats[0].update(ok=False, remarque="Pneu usé")
    resultats[1].update(ok=False, remarque="Frein mou")

    terrain.enregistrer_checklist(chauffeur=mission.chauffeur, mission=mission, resultats=resultats)

    (notification,) = _de(parc)
    assert "2 points KO" in notification.titre
    assert "Pneus" in notification.message and "Freins" in notification.message
    assert notification.url == reverse("garage:checklists")
    assert _de(chef) == []


def test_une_checklist_sans_ko_ne_notifie_personne():
    parc = UserFactory(role=Role.PARCAUTO)
    mission = _mission()

    terrain.enregistrer_checklist(
        chauffeur=mission.chauffeur, mission=mission,
        resultats=[{"code": c, "ok": True, "remarque": ""} for c in CODES_CHECKLIST],
    )

    assert _de(parc) == []


# --- tableau de bord ---


def test_les_incidents_a_traiter_apparaissent_au_centre_d_alertes():
    _declarer(gravite=GraviteIncident.GRAVE, description="Crevaison")
    traite = _declarer(description="Feu cassé")
    terrain.prendre_en_compte(traite, UserFactory(role=Role.PARCAUTO))

    for role in (Role.PARCAUTO, Role.DIRECTION, Role.ADMIN):
        groupes = {g["code"]: g for g in dashboard.centre_alertes(role, aujourd_hui=date(2026, 9, 1))}
        groupe = groupes["incidents"]
        assert groupe["nombre"] == 1 and groupe["niveau"] == "URGENT"
        assert groupe["lignes"][0]["libelle"].startswith("Panne · ")
        assert groupe["voir_tout"].endswith("?statut=SIGNALE")


def test_pas_d_alerte_d_incident_pour_les_autres_roles_ni_sans_incident():
    _declarer()

    assert "incidents" not in {g["code"] for g in dashboard.centre_alertes(Role.RH, aujourd_hui=date(2026, 9, 1))}
    assert "incidents" not in {
        g["code"] for g in dashboard.centre_alertes(Role.FINANCES, aujourd_hui=date(2026, 9, 1))
    }
