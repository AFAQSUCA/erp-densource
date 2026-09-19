"""Services de l'espace chauffeur : périmètre, cycle de la mission, plein, check-list, incident."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.fuel.exceptions import KilometrageInvalide, SaisieSuspecte
from apps.garage.exceptions import ChecklistDejaRemplie, IncidentInvalide
from apps.garage.models import GraviteIncident, TypeIncident
from apps.missions.exceptions import CodeInvalide, TransitionMissionInterdite
from apps.missions.models import StatutMission
from apps.mobile_api import services
from apps.mobile_api.exceptions import AucunCamion, MissionIntrouvable

from .helpers import CODE_DESTINATAIRE, CODE_EXPEDITEUR, checklist_ok, chauffeur_avec_compte, mission_de

pytestmark = pytest.mark.django_db


# --- périmètre ---


def test_le_chauffeur_ne_voit_que_ses_missions_a_faire_en_cours_ou_livrees_cette_semaine():
    moi, _ = chauffeur_avec_compte()
    autre = ChauffeurFactory()
    affectee = mission_de(moi)
    en_cours = mission_de(moi, StatutMission.EN_COURS_DEPART)
    livree_recente = mission_de(moi, StatutMission.LIVREE, date_livraison=timezone.now() - timedelta(days=2))
    mission_de(moi, StatutMission.LIVREE, date_livraison=timezone.now() - timedelta(days=9))  # trop ancienne
    mission_de(moi, StatutMission.PLANIFIEE)
    mission_de(moi, StatutMission.CLOTUREE, date_livraison=timezone.now() - timedelta(days=1))
    mission_de(autre)

    assert set(services.missions_du_chauffeur(moi)) == {affectee, en_cours, livree_recente}


def test_la_mission_d_un_autre_chauffeur_est_introuvable():
    moi, _ = chauffeur_avec_compte()
    mission_autre = mission_de(ChauffeurFactory())

    with pytest.raises(MissionIntrouvable):
        services.mission_du_chauffeur(moi, mission_autre.pk)
    with pytest.raises(MissionIntrouvable):
        services.mission_du_chauffeur(moi, 999999)
    with pytest.raises(MissionIntrouvable):
        services.demarrer(moi, mission_autre.pk)
    with pytest.raises(MissionIntrouvable):
        services.confirmer_recuperation(moi, mission_autre.pk, code=CODE_EXPEDITEUR)
    with pytest.raises(MissionIntrouvable):
        services.livrer(moi, mission_autre.pk, code=CODE_DESTINATAIRE, km_arrivee=999999)


def test_actions_proposees_selon_le_statut():
    moi, _ = chauffeur_avec_compte()

    affectee = mission_de(moi)
    assert services.actions_possibles(affectee) == {
        "checklist": True, "demarrer": True, "recuperation": False, "livraison": False,
    }
    services.enregistrer_checklist(moi, affectee.pk, resultats=checklist_ok())
    assert services.actions_possibles(affectee)["checklist"] is False
    assert services.actions_possibles(mission_de(moi, StatutMission.EN_COURS_DEPART))["recuperation"] is True
    assert services.actions_possibles(mission_de(moi, StatutMission.EN_COURS_COLIS_RECUPERE))["livraison"] is True
    assert not any(services.actions_possibles(mission_de(moi, StatutMission.LIVREE)).values())


# --- cycle de la mission ---


def test_cycle_complet_demarrer_recuperer_livrer():
    moi, _ = chauffeur_avec_compte()
    mission = mission_de(moi)

    assert services.demarrer(moi, mission.pk).statut == StatutMission.EN_COURS_DEPART
    assert services.confirmer_recuperation(moi, mission.pk, code=CODE_EXPEDITEUR).statut == (
        StatutMission.EN_COURS_COLIS_RECUPERE
    )
    livree = services.livrer(moi, mission.pk, code=CODE_DESTINATAIRE, km_arrivee=mission.vehicule.kilometrage + 300)

    assert livree.statut == StatutMission.LIVREE


def test_un_code_faux_ou_un_statut_incorrect_est_refuse_par_le_metier():
    moi, _ = chauffeur_avec_compte()
    mission = mission_de(moi)

    with pytest.raises(TransitionMissionInterdite):
        services.confirmer_recuperation(moi, mission.pk, code=CODE_EXPEDITEUR)  # pas encore parti
    services.demarrer(moi, mission.pk)
    with pytest.raises(CodeInvalide):
        services.confirmer_recuperation(moi, mission.pk, code="FAUX0000")
    with pytest.raises(TransitionMissionInterdite):
        services.demarrer(moi, mission.pk)  # déjà parti


# --- camion et carburant ---


def test_le_camion_courant_suit_la_mission_en_cours_puis_la_prochaine_puis_l_habituel():
    moi, _ = chauffeur_avec_compte()
    habituel = VehiculeFactory(chauffeur_habituel=moi)
    assert services.vehicule_courant(moi) == habituel

    prochaine = mission_de(moi, date_depart_prevue=date(2026, 10, 1))
    assert services.vehicule_courant(moi) == prochaine.vehicule
    en_cours = mission_de(moi, StatutMission.EN_COURS_DEPART)
    assert services.vehicule_courant(moi) == en_cours.vehicule


def test_sans_mission_ni_camion_habituel_il_n_y_a_pas_de_camion():
    moi, _ = chauffeur_avec_compte()

    assert services.vehicule_courant(moi) is None


def _plein(moi, **surcharges):
    donnees = dict(station="Total", quantite_litres=Decimal("100"), prix_unitaire=Decimal("655"),
                   km_compteur=1000, numero_ticket="T-001")
    donnees.update(surcharges)
    return services.saisir_plein(moi, **donnees)


def test_un_plein_est_saisi_sur_le_camion_courant_a_la_date_du_jour():
    moi, _ = chauffeur_avec_compte()
    mission = mission_de(moi)

    plein = _plein(moi)

    assert plein.vehicule == mission.vehicule and plein.chauffeur == moi
    assert plein.date_plein == timezone.localdate()
    assert list(services.pleins_du_chauffeur(moi)) == [plein]


def test_pas_de_plein_sans_camion_ni_sur_le_camion_d_un_autre():
    moi, _ = chauffeur_avec_compte()
    with pytest.raises(AucunCamion, match="Aucun camion"):
        _plein(moi)

    mission_de(moi)
    camion_d_un_autre = VehiculeFactory()
    with pytest.raises(AucunCamion, match="n'est pas le vôtre"):
        _plein(moi, vehicule_id=camion_d_un_autre.pk)


def test_le_chauffeur_peut_designer_son_camion_explicitement():
    moi, _ = chauffeur_avec_compte()
    mission = mission_de(moi)
    habituel = VehiculeFactory(chauffeur_habituel=moi)

    assert _plein(moi, vehicule_id=habituel.pk, numero_ticket="T-9").vehicule == habituel
    assert _plein(moi, vehicule_id=mission.vehicule.pk, numero_ticket="T-8").vehicule == mission.vehicule


def test_les_regles_du_carburant_s_appliquent_au_plein_du_chauffeur():
    moi, _ = chauffeur_avec_compte()
    mission_de(moi)
    _plein(moi, km_compteur=1000)

    with pytest.raises(KilometrageInvalide):
        _plein(moi, km_compteur=900, numero_ticket="T-002")


def test_une_saisie_suspecte_se_confirme():
    moi, _ = chauffeur_avec_compte()
    mission_de(moi)
    aujourd_hui = timezone.localdate()
    _plein(moi, km_compteur=1000, quantite_litres=Decimal("100"), numero_ticket="T-1",
           date_plein=aujourd_hui - timedelta(days=10))
    for rang, km in enumerate((1400, 1800, 2200), start=2):
        _plein(moi, km_compteur=km, quantite_litres=Decimal("120"), numero_ticket=f"T-{rang}",
               date_plein=aujourd_hui - timedelta(days=10 - rang))

    with pytest.raises(SaisieSuspecte):
        _plein(moi, km_compteur=2600, quantite_litres=Decimal("300"), numero_ticket="T-9")
    plein = _plein(moi, km_compteur=2600, quantite_litres=Decimal("300"), numero_ticket="T-9", confirmer=True)

    assert plein.alerte_saisie is True


# --- check-list et incident ---


def test_la_checklist_passe_par_la_mission_du_chauffeur():
    moi, _ = chauffeur_avec_compte()
    mission = mission_de(moi)

    checklist = services.enregistrer_checklist(
        moi, mission.pk, resultats=checklist_ok(FREINS="Spongieux"), remarque="Attention"
    )

    assert checklist.nb_anomalies == 1 and checklist.chauffeur == moi
    with pytest.raises(ChecklistDejaRemplie):
        services.enregistrer_checklist(moi, mission.pk, resultats=checklist_ok())
    with pytest.raises(MissionIntrouvable):
        services.enregistrer_checklist(moi, mission_de(ChauffeurFactory()).pk, resultats=checklist_ok())


def test_un_incident_sur_la_mission_reprend_son_camion():
    moi, _ = chauffeur_avec_compte()
    mission = mission_de(moi)

    incident = services.declarer_incident(
        moi, type_incident=TypeIncident.PANNE, gravite=GraviteIncident.GRAVE,
        description="Moteur", mission_id=mission.pk,
    )

    assert incident.vehicule == mission.vehicule and incident.mission == mission
    assert list(services.incidents_du_chauffeur(moi)) == [incident]


def test_un_incident_sans_mission_prend_le_camion_courant_et_refuse_un_camion_etranger():
    moi, _ = chauffeur_avec_compte()
    habituel = VehiculeFactory(chauffeur_habituel=moi)

    incident = services.declarer_incident(
        moi, type_incident=TypeIncident.AUTRE, gravite=GraviteIncident.FAIBLE, description="Rétro cassé"
    )
    assert incident.vehicule == habituel and incident.mission is None
    with pytest.raises(AucunCamion):
        services.declarer_incident(
            moi, type_incident=TypeIncident.AUTRE, gravite=GraviteIncident.FAIBLE,
            description="x", vehicule_id=VehiculeFactory().pk,
        )
    with pytest.raises(IncidentInvalide):
        services.declarer_incident(moi, type_incident="AUTRE", gravite="FAIBLE", description=" ")


def test_le_chauffeur_ne_voit_que_ses_incidents_et_ses_pleins():
    moi, _ = chauffeur_avec_compte()
    autre, _ = chauffeur_avec_compte()
    VehiculeFactory(chauffeur_habituel=moi)
    VehiculeFactory(chauffeur_habituel=autre)
    services.declarer_incident(moi, type_incident="AUTRE", gravite="FAIBLE", description="A")
    services.declarer_incident(autre, type_incident="AUTRE", gravite="FAIBLE", description="B")

    assert [i.description for i in services.incidents_du_chauffeur(moi)] == ["A"]


# --- tableau de bord du chauffeur ---


def test_le_tableau_reunit_course_du_jour_km_consommation_et_camion():
    moi, _ = chauffeur_avec_compte()
    livree = mission_de(moi, StatutMission.LIVREE, km_depart=1000, km_arrivee=1450,
                        date_livraison=timezone.now())
    prochaine = mission_de(moi, date_depart_prevue=date(2026, 10, 1))
    mission_de(moi, StatutMission.LIVREE, km_depart=10, km_arrivee=90,
               date_livraison=timezone.now() - timedelta(days=90))  # hors du mois

    tableau = services.tableau(moi)

    assert tableau["mission_du_jour"] == prochaine and tableau["en_cours"] is False
    assert tableau["prochaines"] == [prochaine] and tableau["km_mois"] == 450
    assert tableau["vehicule"] == prochaine.vehicule and tableau["consommation"] is None
    assert livree.pk


def test_en_cours_la_mission_du_jour_est_la_mission_demarree():
    moi, _ = chauffeur_avec_compte()
    mission_de(moi)
    en_cours = mission_de(moi, StatutMission.EN_COURS_DEPART, date_depart=timezone.now())

    tableau = services.tableau(moi)

    assert tableau["mission_du_jour"] == en_cours and tableau["en_cours"] is True
