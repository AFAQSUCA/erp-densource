"""Check-list du véhicule et incidents signalés par le chauffeur."""

import pytest

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.garage import signals, terrain
from apps.garage.exceptions import (
    ChauffeurNonAutorise,
    ChecklistDejaRemplie,
    ChecklistInvalide,
    IncidentInvalide,
    TransitionIncidentInterdite,
)
from apps.garage.models import (
    CODES_CHECKLIST,
    ChecklistVehicule,
    GraviteIncident,
    Incident,
    StatutIncident,
    TypeIncident,
)
from apps.missions.models import StatutMission
from apps.missions.tests.factories import MissionFactory

pytestmark = pytest.mark.django_db


def _mission(chauffeur=None, statut=StatutMission.AFFECTEE):
    chauffeur = chauffeur or ChauffeurFactory()
    return MissionFactory(statut=statut, vehicule=VehiculeFactory(), chauffeur=chauffeur)


def _tout_ok(**surcharges):
    resultats = [{"code": code, "ok": True, "remarque": ""} for code in CODES_CHECKLIST]
    for element in resultats:
        element.update(surcharges.get(element["code"], {}))
    return resultats


# --- check-list ---


def test_une_checklist_complete_est_enregistree_sans_anomalie():
    mission = _mission()

    checklist = terrain.enregistrer_checklist(
        chauffeur=mission.chauffeur, mission=mission, resultats=_tout_ok(), remarque="RAS"
    )

    assert checklist.nb_anomalies == 0 and checklist.vehicule == mission.vehicule
    assert [p["code"] for p in checklist.points] == list(CODES_CHECKLIST)  # ordre du référentiel
    assert all(p["ok"] and p["libelle"] for p in checklist.points)
    assert terrain.checklist_de(mission) == checklist


def test_un_point_ko_avec_remarque_compte_une_anomalie_et_previent_le_parc_auto():
    mission = _mission()
    recus = []
    recepteur = lambda sender, checklist, **kw: recus.append(checklist)  # noqa: E731
    signals.checklist_anomalie.connect(recepteur, weak=False)
    try:
        checklist = terrain.enregistrer_checklist(
            chauffeur=mission.chauffeur, mission=mission,
            resultats=_tout_ok(FREINS={"ok": False, "remarque": "Pédale spongieuse"}),
        )
    finally:
        signals.checklist_anomalie.disconnect(recepteur)

    assert checklist.nb_anomalies == 1 and recus == [checklist]
    frein = next(p for p in checklist.points if p["code"] == "FREINS")
    assert frein["ok"] is False and frein["remarque"] == "Pédale spongieuse"


def test_une_checklist_sans_anomalie_n_emet_aucun_signal():
    mission = _mission()
    recus = []
    recepteur = lambda sender, checklist, **kw: recus.append(checklist)  # noqa: E731
    signals.checklist_anomalie.connect(recepteur, weak=False)
    try:
        terrain.enregistrer_checklist(chauffeur=mission.chauffeur, mission=mission, resultats=_tout_ok())
    finally:
        signals.checklist_anomalie.disconnect(recepteur)

    assert recus == []


def test_un_ko_sans_remarque_est_refuse():
    mission = _mission()

    with pytest.raises(ChecklistInvalide, match="Précisez le problème pour « Freins »"):
        terrain.enregistrer_checklist(
            chauffeur=mission.chauffeur, mission=mission, resultats=_tout_ok(FREINS={"ok": False})
        )
    assert not ChecklistVehicule.objects.exists()


def test_tous_les_points_doivent_etre_renseignes_une_seule_fois():
    mission = _mission()
    incomplet = _tout_ok()[:-2]
    double = _tout_ok() + [{"code": "PNEUS", "ok": True}]
    inconnu = _tout_ok() + [{"code": "KLAXON", "ok": True}]

    with pytest.raises(ChecklistInvalide, match="Points non renseignés"):
        terrain.enregistrer_checklist(chauffeur=mission.chauffeur, mission=mission, resultats=incomplet)
    with pytest.raises(ChecklistInvalide, match="plusieurs fois"):
        terrain.enregistrer_checklist(chauffeur=mission.chauffeur, mission=mission, resultats=double)
    with pytest.raises(ChecklistInvalide, match="inconnu"):
        terrain.enregistrer_checklist(chauffeur=mission.chauffeur, mission=mission, resultats=inconnu)


def test_une_seule_checklist_par_mission():
    mission = _mission()
    terrain.enregistrer_checklist(chauffeur=mission.chauffeur, mission=mission, resultats=_tout_ok())

    with pytest.raises(ChecklistDejaRemplie):
        terrain.enregistrer_checklist(chauffeur=mission.chauffeur, mission=mission, resultats=_tout_ok())


def test_un_chauffeur_ne_remplit_que_la_checklist_de_sa_mission():
    mission = _mission()

    with pytest.raises(ChauffeurNonAutorise):
        terrain.enregistrer_checklist(chauffeur=ChauffeurFactory(), mission=mission, resultats=_tout_ok())


@pytest.mark.parametrize(
    "statut", [StatutMission.PLANIFIEE, StatutMission.EN_COURS_COLIS_RECUPERE, StatutMission.LIVREE]
)
def test_la_checklist_se_remplit_avant_le_depart(statut):
    mission = _mission(statut=statut)

    with pytest.raises(ChecklistInvalide, match="avant le départ"):
        terrain.enregistrer_checklist(chauffeur=mission.chauffeur, mission=mission, resultats=_tout_ok())


def test_la_checklist_reste_possible_juste_apres_le_demarrage():
    mission = _mission(statut=StatutMission.EN_COURS_DEPART)

    assert terrain.enregistrer_checklist(
        chauffeur=mission.chauffeur, mission=mission, resultats=_tout_ok()
    ).pk


def test_recherche_de_checklists():
    a, b = _mission(), _mission()
    terrain.enregistrer_checklist(chauffeur=a.chauffeur, mission=a, resultats=_tout_ok())
    terrain.enregistrer_checklist(
        chauffeur=b.chauffeur, mission=b, resultats=_tout_ok(FEUX={"ok": False, "remarque": "Feu arrière HS"})
    )

    assert terrain.rechercher_checklists().count() == 2
    assert [c.mission for c in terrain.rechercher_checklists(avec_anomalies=True)] == [b]
    assert [c.mission for c in terrain.rechercher_checklists(recherche=a.numero.lower())] == [a]


# --- incidents ---


def _declarer(mission=None, **surcharges):
    mission = mission or _mission()
    donnees = dict(
        chauffeur=mission.chauffeur, mission=mission, type_incident=TypeIncident.PANNE,
        gravite=GraviteIncident.MOYENNE, description="Moteur qui chauffe", lieu="Km 120, Bouaké",
    )
    donnees.update(surcharges)
    return terrain.declarer_incident(**donnees)


def test_declarer_un_incident_prend_le_camion_de_la_mission_et_previent():
    mission = _mission()
    recus = []
    recepteur = lambda sender, incident, **kw: recus.append(incident)  # noqa: E731
    signals.incident_signale.connect(recepteur, weak=False)
    try:
        incident = _declarer(mission)
    finally:
        signals.incident_signale.disconnect(recepteur)

    assert incident.vehicule == mission.vehicule and incident.mission == mission
    assert incident.statut == StatutIncident.SIGNALE and recus == [incident]
    assert incident.lieu == "Km 120, Bouaké"


def test_un_incident_peut_etre_declare_avec_un_camion_sans_mission():
    chauffeur, camion = ChauffeurFactory(), VehiculeFactory()

    incident = terrain.declarer_incident(
        chauffeur=chauffeur, vehicule=camion, type_incident=TypeIncident.AUTRE,
        gravite=GraviteIncident.FAIBLE, description="Rétroviseur cassé",
    )

    assert incident.vehicule == camion and incident.mission is None


@pytest.mark.parametrize(
    ("surcharges", "message"),
    [
        ({"description": "  "}, "Décrivez"),
        ({"type_incident": "VOL"}, "Type d'incident"),
        ({"gravite": "ENORME"}, "Gravité"),
    ],
)
def test_incident_invalide(surcharges, message):
    with pytest.raises(IncidentInvalide, match=message):
        _declarer(**surcharges)
    assert not Incident.objects.exists()


def test_un_incident_exige_un_camion():
    with pytest.raises(IncidentInvalide, match="camion"):
        terrain.declarer_incident(
            chauffeur=ChauffeurFactory(), type_incident=TypeIncident.PANNE,
            gravite=GraviteIncident.FAIBLE, description="x",
        )


def test_on_ne_declare_pas_d_incident_sur_la_mission_d_un_autre_chauffeur():
    mission = _mission()

    with pytest.raises(ChauffeurNonAutorise):
        _declarer(mission, chauffeur=ChauffeurFactory())


def test_le_parc_auto_prend_en_compte_puis_clot_avec_la_suite_donnee():
    incident, parc = _declarer(), UserFactory(role=Role.PARCAUTO)

    terrain.prendre_en_compte(incident, parc, note="Camion à ramener au garage")
    incident.refresh_from_db()
    assert incident.statut == StatutIncident.PRIS_EN_COMPTE and incident.traite_par == parc

    with pytest.raises(IncidentInvalide, match="suite donnée"):
        terrain.clore_incident(incident, parc, note=" ")
    terrain.clore_incident(incident, parc, note="OR ouvert, courroie remplacée")
    incident.refresh_from_db()
    assert incident.statut == StatutIncident.CLOS and "courroie" in incident.note_traitement


def test_un_incident_signale_peut_etre_clos_directement_mais_pas_deux_fois():
    incident, admin = _declarer(), UserFactory(role=Role.ADMIN)

    terrain.clore_incident(incident, admin, note="Fausse alerte")

    with pytest.raises(TransitionIncidentInterdite, match="déjà clos"):
        terrain.clore_incident(incident, admin, note="Encore")
    with pytest.raises(TransitionIncidentInterdite, match="signalé"):
        terrain.prendre_en_compte(incident, admin)


def test_seuls_parc_auto_admin_et_direction_traitent_un_incident():
    # Retour réunion : la DIRECTION a désormais la même largeur que l'ADMIN (MODIFICATION).
    incident = _declarer()

    for role in (Role.RH, Role.CHAUFFEUR, Role.FINANCES):
        with pytest.raises(ChauffeurNonAutorise):
            terrain.prendre_en_compte(incident, UserFactory(role=role))
    assert terrain.prendre_en_compte(incident, UserFactory(role=Role.DIRECTION)).pk
    assert terrain.clore_incident(incident, UserFactory(role=Role.DIRECTION), note="x").pk


def test_recherche_et_file_des_incidents_a_traiter():
    a = _declarer(description="Crevaison pneu avant", gravite=GraviteIncident.GRAVE)
    b = _declarer(description="Feu cassé")
    terrain.prendre_en_compte(b, UserFactory(role=Role.PARCAUTO))

    assert list(terrain.incidents_a_traiter()) == [a]
    assert [i.pk for i in terrain.rechercher_incidents(recherche="CREVAISON")] == [a.pk]
    assert [i.pk for i in terrain.rechercher_incidents(gravite="GRAVE")] == [a.pk]
    assert [i.pk for i in terrain.rechercher_incidents(statut="PRIS_EN_COMPTE")] == [b.pk]
    assert terrain.rechercher_incidents(statut="N_IMPORTE_QUOI", gravite="???").count() == 2


def test_un_recepteur_en_erreur_ne_bloque_pas_le_signalement(caplog):
    def panne(sender, **kwargs):
        raise RuntimeError("panne")

    signals.incident_signale.connect(panne, weak=False)
    try:
        incident = _declarer()
    finally:
        signals.incident_signale.disconnect(panne)

    assert incident.pk and "en erreur" in caplog.text
