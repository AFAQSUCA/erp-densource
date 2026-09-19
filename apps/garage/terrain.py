"""Services des signalements du chauffeur : check-list du véhicule et incidents.

Réf. cahier-des-charges.md:54, 142-143 (espace mobile : check-list véhicule, signalement
d'incidents, panne). Décisions retenues : check-list à liste fixe et non bloquante ; un incident
prévient le Parc Auto et la Direction, qui décident de la suite (aucune action automatique).
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from apps.core.search import filtrer_par_texte
from apps.drivers.models import Chauffeur
from apps.fleet.models import Vehicule
from apps.missions.models import Mission, StatutMission

from . import permissions, signals
from .exceptions import (
    ChauffeurNonAutorise,
    ChecklistDejaRemplie,
    ChecklistInvalide,
    IncidentInvalide,
    TransitionIncidentInterdite,
)
from .models import (
    CODES_CHECKLIST,
    POINTS_CHECKLIST,
    ChecklistVehicule,
    GraviteIncident,
    Incident,
    StatutIncident,
    TypeIncident,
)

STATUTS_MISSION_AVANT_DEPART = (StatutMission.AFFECTEE, StatutMission.EN_COURS_DEPART)


def _exiger_mission_du_chauffeur(mission: Mission, chauffeur: Chauffeur) -> None:
    if mission.chauffeur_id != chauffeur.pk:
        raise ChauffeurNonAutorise("Cette mission n'est pas affectée à ce chauffeur.")


# --- check-list ---


@transaction.atomic
def enregistrer_checklist(
    *, chauffeur: Chauffeur, mission: Mission, resultats: list[dict], remarque: str = ""
) -> ChecklistVehicule:
    """Enregistre la check-list d'une mission affectée (une seule par mission).

    ``resultats`` : un élément ``{"code", "ok", "remarque"}`` pour chacun des points de
    ``POINTS_CHECKLIST``. Un point KO exige une remarque. Un ou plusieurs KO préviennent le
    Parc Auto ; la mission peut quand même partir.
    """
    type(mission)._base_manager.select_for_update().filter(pk=mission.pk).first()
    mission.refresh_from_db()
    _exiger_mission_du_chauffeur(mission, chauffeur)
    if mission.statut not in STATUTS_MISSION_AVANT_DEPART:
        raise ChecklistInvalide(
            f"La check-list se remplit avant le départ : la mission est « {mission.get_statut_display()} »."
        )
    if ChecklistVehicule.objects.filter(mission=mission).exists():
        raise ChecklistDejaRemplie(f"La check-list de la mission {mission.numero} est déjà remplie.")

    recus: dict[str, dict] = {}
    for element in resultats:
        code = element.get("code")
        if code not in CODES_CHECKLIST:
            raise ChecklistInvalide(f"Point de contrôle inconnu : {code}.")
        if code in recus:
            raise ChecklistInvalide(f"Le point {code} est renseigné plusieurs fois.")
        recus[code] = element
    manquants = [libelle for code, libelle in POINTS_CHECKLIST if code not in recus]
    if manquants:
        raise ChecklistInvalide("Points non renseignés : " + ", ".join(manquants) + ".")

    points, anomalies = [], 0
    for code, libelle in POINTS_CHECKLIST:
        element = recus[code]
        ok = bool(element.get("ok"))
        note = (element.get("remarque") or "").strip()
        if not ok:
            anomalies += 1
            if not note:
                raise ChecklistInvalide(f"Précisez le problème pour « {libelle} ».")
        points.append({"code": code, "libelle": libelle, "ok": ok, "remarque": note})

    checklist = ChecklistVehicule.objects.create(
        mission=mission,
        vehicule=mission.vehicule,
        chauffeur=chauffeur,
        points=points,
        nb_anomalies=anomalies,
        remarque=remarque.strip(),
    )
    if anomalies:
        signals.emettre(signals.checklist_anomalie, checklist=checklist)
    return checklist


def checklist_de(mission: Mission) -> ChecklistVehicule | None:
    return ChecklistVehicule.objects.filter(mission=mission).first()


def checklists_queryset() -> QuerySet[ChecklistVehicule]:
    return ChecklistVehicule.objects.select_related(
        "mission", "vehicule", "chauffeur__personnel"
    )


def rechercher_checklists(*, recherche: str = "", avec_anomalies: bool = False) -> QuerySet[ChecklistVehicule]:
    resultat = checklists_queryset()
    if avec_anomalies:
        resultat = resultat.filter(nb_anomalies__gt=0)
    return filtrer_par_texte(
        resultat, recherche, "mission__numero", "vehicule__immatriculation",
        "chauffeur__personnel__nom", "chauffeur__personnel__prenom",
    )


# --- incidents ---


@transaction.atomic
def declarer_incident(
    *,
    chauffeur: Chauffeur,
    type_incident: str,
    gravite: str,
    description: str,
    lieu: str = "",
    mission: Mission | None = None,
    vehicule: Vehicule | None = None,
) -> Incident:
    """Signalement d'un incident par le chauffeur ; prévient le Parc Auto et la Direction.

    Le camion est celui de la mission indiquée, ou ``vehicule`` à défaut. Aucune action
    automatique sur le camion ou la mission.
    """
    if type_incident not in TypeIncident.values:
        raise IncidentInvalide("Type d'incident inconnu.")
    if gravite not in GraviteIncident.values:
        raise IncidentInvalide("Gravité inconnue.")
    description = description.strip()
    if not description:
        raise IncidentInvalide("Décrivez l'incident.")
    if mission is not None:
        _exiger_mission_du_chauffeur(mission, chauffeur)
        vehicule = vehicule or mission.vehicule
    if vehicule is None:
        raise IncidentInvalide("Indiquez le camion concerné.")
    incident = Incident.objects.create(
        vehicule=vehicule,
        chauffeur=chauffeur,
        mission=mission,
        type_incident=type_incident,
        gravite=gravite,
        description=description,
        lieu=lieu.strip(),
    )
    signals.emettre(signals.incident_signale, incident=incident)
    return incident


def incidents_queryset() -> QuerySet[Incident]:
    return Incident.objects.select_related("vehicule", "chauffeur__personnel", "mission", "traite_par")


def rechercher_incidents(
    *, recherche: str = "", statut: str = "", gravite: str = ""
) -> QuerySet[Incident]:
    resultat = incidents_queryset()
    if statut in StatutIncident.values:
        resultat = resultat.filter(statut=statut)
    if gravite in GraviteIncident.values:
        resultat = resultat.filter(gravite=gravite)
    return filtrer_par_texte(
        resultat, recherche, "vehicule__immatriculation", "description", "lieu",
        "chauffeur__personnel__nom", "chauffeur__personnel__prenom", "mission__numero",
    )


def incidents_a_traiter() -> QuerySet[Incident]:
    """Incidents signalés que le Parc Auto n'a pas encore pris en compte (tableau de bord)."""
    return incidents_queryset().filter(statut=StatutIncident.SIGNALE)


def _exiger_parc_auto(acteur) -> None:
    if acteur.role_effectif not in permissions.MODIFICATION:
        raise ChauffeurNonAutorise("Seuls le Parc Auto et l'administrateur traitent un incident.")


@transaction.atomic
def prendre_en_compte(incident: Incident, acteur, *, note: str = "") -> Incident:
    """Signalé → Pris en compte (le Parc Auto s'en occupe)."""
    _exiger_parc_auto(acteur)
    type(incident)._base_manager.select_for_update().filter(pk=incident.pk).first()
    incident.refresh_from_db()
    if incident.statut != StatutIncident.SIGNALE:
        raise TransitionIncidentInterdite("Seul un incident signalé peut être pris en compte.")
    incident.statut = StatutIncident.PRIS_EN_COMPTE
    incident.note_traitement = note.strip()
    incident.traite_par, incident.date_traitement = acteur, timezone.now()
    incident.save()
    return incident


@transaction.atomic
def clore_incident(incident: Incident, acteur, *, note: str) -> Incident:
    """Signalé ou Pris en compte → Clos, avec la suite donnée (obligatoire)."""
    _exiger_parc_auto(acteur)
    type(incident)._base_manager.select_for_update().filter(pk=incident.pk).first()
    incident.refresh_from_db()
    if incident.statut == StatutIncident.CLOS:
        raise TransitionIncidentInterdite("Cet incident est déjà clos.")
    if not note.strip():
        raise IncidentInvalide("Indiquez la suite donnée pour clore l'incident.")
    incident.statut = StatutIncident.CLOS
    incident.note_traitement = note.strip()
    incident.traite_par, incident.date_traitement = acteur, timezone.now()
    incident.save()
    return incident
