"""Services de l'espace chauffeur : ce qu'un chauffeur voit et fait, sur SES données seulement.

Partagés par l'API mobile (JWT) et par les écrans mobiles (session) : la règle n'est écrite
qu'une fois. Chaque fonction reçoit le ``chauffeur`` et n'agit que sur ses missions ; une
mission d'un autre chauffeur est traitée comme inexistante (404), sans rien révéler.

Les règles métier restent dans ``missions``, ``fuel`` et ``garage`` ; ce module ne fait que
vérifier l'appartenance et orchestrer (cahier-des-charges.md:54, 132-143).
"""

from __future__ import annotations

from datetime import date, timedelta

from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.drivers.models import Chauffeur
from apps.fleet.models import Vehicule
from apps.fuel import services as fuel_services
from apps.fuel.models import Plein
from apps.garage import terrain as garage_terrain
from apps.garage.models import ChecklistVehicule, Incident
from apps.missions import services as missions_services
from apps.missions.models import Mission, StatutMission

from .exceptions import AucunCamion, MissionIntrouvable

STATUTS_EN_COURS = (StatutMission.EN_COURS_DEPART, StatutMission.EN_COURS_COLIS_RECUPERE)
JOURS_MISSIONS_LIVREES = 7  # une mission livrée reste visible une semaine


# --- missions ---


def missions_du_chauffeur(chauffeur: Chauffeur, *, aujourd_hui: date | None = None) -> QuerySet[Mission]:
    """Missions à faire, en cours, ou livrées depuis moins d'une semaine (les plus récentes d'abord)."""
    aujourd_hui = aujourd_hui or timezone.localdate()
    limite = timezone.now() - timedelta(days=JOURS_MISSIONS_LIVREES)
    return (
        missions_services.missions_queryset()
        .filter(chauffeur=chauffeur)
        .filter(
            Q(statut=StatutMission.AFFECTEE)
            | Q(statut__in=STATUTS_EN_COURS)
            | Q(statut=StatutMission.LIVREE, date_livraison__gte=limite)
        )
        .order_by("-date_depart_prevue", "-pk")
    )


def mission_du_chauffeur(chauffeur: Chauffeur, pk: int) -> Mission:
    """Une mission de ce chauffeur, quel que soit son statut ; sinon ``MissionIntrouvable``."""
    mission = missions_services.missions_queryset().filter(pk=pk, chauffeur=chauffeur).first()
    if mission is None:
        raise MissionIntrouvable("Mission introuvable.")
    return mission


def checklist_faite(mission: Mission) -> bool:
    return ChecklistVehicule.objects.filter(mission=mission).exists()


def actions_possibles(mission: Mission) -> dict[str, bool]:
    """Boutons proposés selon le statut : démarrer, confirmer la récupération, livrer."""
    return {
        "checklist": mission.statut == StatutMission.AFFECTEE and not checklist_faite(mission),
        "demarrer": mission.statut == StatutMission.AFFECTEE,
        "recuperation": mission.statut == StatutMission.EN_COURS_DEPART,
        "livraison": mission.statut == StatutMission.EN_COURS_COLIS_RECUPERE,
    }


def demarrer(chauffeur: Chauffeur, pk: int) -> Mission:
    mission = mission_du_chauffeur(chauffeur, pk)
    return missions_services.demarrer_mission(mission)


def confirmer_recuperation(chauffeur: Chauffeur, pk: int, *, code: str) -> Mission:
    """Colis récupéré : le code de l'expéditeur est saisi ou scanné sur le téléphone du chauffeur."""
    mission = mission_du_chauffeur(chauffeur, pk)
    return missions_services.confirmer_recuperation(mission, code=code)


def livrer(chauffeur: Chauffeur, pk: int, *, code: str, km_arrivee: int) -> Mission:
    """Livraison : code du destinataire et compteur à l'arrivée."""
    mission = mission_du_chauffeur(chauffeur, pk)
    return missions_services.livrer_mission(mission, code=code, km_arrivee=km_arrivee)


# --- camion et carburant ---


def vehicule_courant(chauffeur: Chauffeur) -> Vehicule | None:
    """Camion de la mission en cours, sinon de la prochaine mission, sinon son camion habituel."""
    missions = missions_services.missions_queryset().filter(chauffeur=chauffeur)
    mission = (
        missions.filter(statut__in=STATUTS_EN_COURS).order_by("-date_depart", "-pk").first()
        or missions.filter(statut=StatutMission.AFFECTEE).order_by("date_depart_prevue", "pk").first()
    )
    if mission is not None and mission.vehicule is not None:
        return mission.vehicule
    return Vehicule.objects.filter(chauffeur_habituel=chauffeur).order_by("immatriculation").first()


def _vehicules_autorises(chauffeur: Chauffeur) -> set[int]:
    """Camions sur lesquels ce chauffeur peut déclarer un plein ou un incident."""
    de_ses_missions = (
        Mission.objects.filter(chauffeur=chauffeur, statut__in=(StatutMission.AFFECTEE, *STATUTS_EN_COURS))
        .exclude(vehicule=None)
        .values_list("vehicule_id", flat=True)
    )
    habituels = Vehicule.objects.filter(chauffeur_habituel=chauffeur).values_list("pk", flat=True)
    return set(de_ses_missions) | set(habituels)


def _resoudre_vehicule(chauffeur: Chauffeur, vehicule_id: int | None) -> Vehicule:
    if vehicule_id is None:
        vehicule = vehicule_courant(chauffeur)
        if vehicule is None:
            raise AucunCamion("Aucun camion ne vous est affecté : contactez le Parc Auto.")
        return vehicule
    if vehicule_id not in _vehicules_autorises(chauffeur):
        raise AucunCamion("Ce camion n'est pas le vôtre.")
    return Vehicule.objects.get(pk=vehicule_id)


def saisir_plein(
    chauffeur: Chauffeur,
    *,
    station: str,
    quantite_litres,
    prix_unitaire,
    km_compteur: int,
    numero_ticket: str,
    date_plein: date | None = None,
    vehicule_id: int | None = None,
    confirmer: bool = False,
) -> Plein:
    """Saisie d'un plein par le chauffeur (cahier-des-charges.md:142-143, 148-155).

    Sans ``vehicule_id``, c'est le camion courant. Un écart de plus de 60 % lève
    ``SaisieSuspecte`` : le chauffeur vérifie puis renvoie avec ``confirmer=True``.
    """
    vehicule = _resoudre_vehicule(chauffeur, vehicule_id)
    return fuel_services.enregistrer_plein(
        vehicule=vehicule,
        chauffeur=chauffeur,
        date_plein=date_plein or timezone.localdate(),
        station=station,
        quantite_litres=quantite_litres,
        prix_unitaire=prix_unitaire,
        km_compteur=km_compteur,
        numero_ticket=numero_ticket,
        confirmer_alerte_saisie=confirmer,
    )


def pleins_du_chauffeur(chauffeur: Chauffeur, *, limite: int = 20) -> QuerySet[Plein]:
    return (
        Plein.objects.filter(chauffeur=chauffeur)
        .select_related("vehicule")
        .order_by("-date_plein", "-pk")[:limite]
    )


# --- check-list et incidents ---


def enregistrer_checklist(chauffeur: Chauffeur, pk: int, *, resultats: list[dict], remarque: str = ""):
    mission = mission_du_chauffeur(chauffeur, pk)
    return garage_terrain.enregistrer_checklist(
        chauffeur=chauffeur, mission=mission, resultats=resultats, remarque=remarque
    )


def declarer_incident(
    chauffeur: Chauffeur,
    *,
    type_incident: str,
    gravite: str,
    description: str,
    lieu: str = "",
    mission_id: int | None = None,
    vehicule_id: int | None = None,
) -> Incident:
    """Signale une panne ou un incident ; sans mission, sur le camion courant du chauffeur."""
    mission = mission_du_chauffeur(chauffeur, mission_id) if mission_id else None
    vehicule = None if mission else _resoudre_vehicule(chauffeur, vehicule_id)
    return garage_terrain.declarer_incident(
        chauffeur=chauffeur,
        type_incident=type_incident,
        gravite=gravite,
        description=description,
        lieu=lieu,
        mission=mission,
        vehicule=vehicule,
    )


def incidents_du_chauffeur(chauffeur: Chauffeur, *, limite: int = 20) -> QuerySet[Incident]:
    return Incident.objects.filter(chauffeur=chauffeur).select_related("vehicule").order_by("-created_at", "-pk")[:limite]


# --- tableau de bord du chauffeur (cahier-des-charges.md:238-239) ---


def tableau(chauffeur: Chauffeur, *, aujourd_hui: date | None = None) -> dict:
    """Course du jour, km parcourus, consommation, état du véhicule, prochaine mission."""
    aujourd_hui = aujourd_hui or timezone.localdate()
    missions = missions_services.missions_queryset().filter(chauffeur=chauffeur)
    en_cours = missions.filter(statut__in=STATUTS_EN_COURS).order_by("-date_depart", "-pk").first()
    a_venir = list(
        missions.filter(statut=StatutMission.AFFECTEE).order_by("date_depart_prevue", "pk")[:5]
    )
    debut_mois = aujourd_hui.replace(day=1)
    livrees = missions.filter(
        statut__in=(StatutMission.LIVREE, StatutMission.CLOTUREE),
        date_livraison__date__gte=debut_mois,
        km_depart__isnull=False,
        km_arrivee__isnull=False,
    ).values_list("km_depart", "km_arrivee")
    km_mois = sum(arrivee - depart for depart, arrivee in livrees if arrivee > depart)
    vehicule = vehicule_courant(chauffeur)
    return {
        "chauffeur": chauffeur,
        "mission_du_jour": en_cours or (a_venir[0] if a_venir else None),
        "en_cours": en_cours is not None,
        "prochaines": a_venir,
        "vehicule": vehicule,
        "km_mois": km_mois,
        "consommation": fuel_services.consommation_moyenne(chauffeur=chauffeur),
    }
