"""Logique métier des missions — cycle de vie du CDC (cahier-des-charges.md:127-143).

Brouillon → Planifiée → Affectée → En cours (départ → colis récupéré) →
Livrée → Clôturée. Chaque transition est atomique et relit la mission sous
verrou pour éviter deux actions simultanées.

Les contrôles de rôle (chargé clientèle, direction, chauffeur) relèvent des
permissions DRF de l'API (étape 6), pas de ce module.
"""

from __future__ import annotations

import secrets
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.core.services import prochain_numero
from apps.customers.models import Client
from apps.drivers import services as drivers_services
from apps.drivers.models import Chauffeur, StatutChauffeur
from apps.fleet import services as fleet_services
from apps.fleet.models import StatutVehicule, Vehicule

from .exceptions import (
    AffectationImpossible,
    CodeInvalide,
    DemarrageImpossible,
    KilometrageInvalide,
    MissionError,
    TransitionMissionInterdite,
)
from .models import STATUTS_ACTIFS, Mission, StatutMission

PREFIXE_NUMERO = "MIS"
# Sans caractères ambigus (0/O, 1/I) : les codes se dictent au téléphone.
ALPHABET_CODES = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
LONGUEUR_CODE = 8


def generer_code() -> str:
    """Code secret aléatoire (module ``secrets``, adapté aux usages sensibles)."""
    return "".join(secrets.choice(ALPHABET_CODES) for _ in range(LONGUEUR_CODE))


def _recharger(objet):
    """Verrouille la ligne puis relit l'objet (effectif sous PostgreSQL)."""
    type(objet)._base_manager.select_for_update().filter(pk=objet.pk).first()
    objet.refresh_from_db()
    return objet


def _exiger_statut(mission: Mission, attendu: str, action: str) -> None:
    if mission.statut != attendu:
        raise TransitionMissionInterdite(
            f"Impossible de {action} : la mission {mission.numero} est "
            f"« {mission.get_statut_display()} »."
        )


def _verifier_code(saisi: str, attendu: str) -> None:
    if not secrets.compare_digest(saisi.strip().upper().encode(), attendu.encode()):
        raise CodeInvalide("Code incorrect.")


# --- consultation ---


def missions_queryset() -> QuerySet[Mission]:
    """Missions avec leurs relations chargées (évite les requêtes en boucle)."""
    return Mission.objects.select_related(
        "client", "vehicule", "chauffeur__personnel"
    )


def rechercher_missions(
    *, statut: str | None = None, recherche: str = ""
) -> QuerySet[Mission]:
    """Missions filtrées par statut et/ou texte (numéro, client, lieux)."""
    missions = missions_queryset()
    if statut in StatutMission.values:
        missions = missions.filter(statut=statut)
    recherche = recherche.strip()
    if recherche:
        missions = missions.filter(
            Q(numero__icontains=recherche)
            | Q(client__raison_sociale__icontains=recherche)
            | Q(lieu_chargement__icontains=recherche)
            | Q(lieu_livraison__icontains=recherche)
        )
    return missions



def vehicule_a_mission_active(vehicule: Vehicule) -> bool:
    """Vrai si le camion est réservé par une mission affectée ou en cours.

    Fournit ``mission_active`` à ``fleet.services.calculer_statut`` (règle 2,
    cahier-des-charges.md:96-100). Une mission « planifiée » n'a pas encore de
    camion : seule l'affectation réserve un camion.
    """
    return Mission.objects.filter(vehicule=vehicule, statut__in=STATUTS_ACTIFS).exists()


def chauffeur_a_mission_active(chauffeur: Chauffeur) -> bool:
    return Mission.objects.filter(chauffeur=chauffeur, statut__in=STATUTS_ACTIFS).exists()


# --- cycle de vie ---


@transaction.atomic
def creer_mission(
    *,
    client: Client,
    lieu_chargement: str,
    lieu_livraison: str,
    nature_marchandise: str,
    poids_t: Decimal,
    prix_convenu: Decimal,
    date_depart_prevue: date | None = None,
) -> Mission:
    """Crée une mission au statut Brouillon : numéro MIS-AAAA-XXXX et deux codes."""
    if poids_t <= 0:
        raise MissionError("Le poids doit être strictement positif.")
    if prix_convenu < 0:
        raise MissionError("Le prix convenu ne peut pas être négatif.")

    code_expediteur = generer_code()
    code_destinataire = generer_code()
    while code_destinataire == code_expediteur:
        code_destinataire = generer_code()

    return Mission.objects.create(
        numero=prochain_numero(PREFIXE_NUMERO),
        client=client,
        lieu_chargement=lieu_chargement,
        lieu_livraison=lieu_livraison,
        nature_marchandise=nature_marchandise,
        poids_t=poids_t,
        prix_convenu=prix_convenu,
        date_depart_prevue=date_depart_prevue,
        code_expediteur=code_expediteur,
        code_destinataire=code_destinataire,
    )


@transaction.atomic
def planifier_mission(mission: Mission) -> Mission:
    """Brouillon → Planifiée (validation du chargé clientèle, architecture.md:241)."""
    _recharger(mission)
    _exiger_statut(mission, StatutMission.BROUILLON, "planifier la mission")
    mission.statut = StatutMission.PLANIFIEE
    mission.save(update_fields=["statut", "updated_at"])
    return mission


@transaction.atomic
def affecter_mission(mission: Mission, *, vehicule: Vehicule, chauffeur: Chauffeur) -> Mission:
    """Planifiée → Affectée : camion et chauffeur disponibles, non réservés,
    et capable d'emporter la charge (cahier-des-charges.md:130-131)."""
    _recharger(mission)
    _exiger_statut(mission, StatutMission.PLANIFIEE, "affecter la mission")
    _recharger(vehicule)
    _recharger(chauffeur)

    if vehicule.statut != StatutVehicule.DISPONIBLE:
        raise AffectationImpossible(
            f"Le camion {vehicule.immatriculation} n'est pas disponible "
            f"({vehicule.get_statut_display()})."
        )
    if chauffeur.statut != StatutChauffeur.DISPONIBLE:
        raise AffectationImpossible(
            f"Le chauffeur {chauffeur} n'est pas disponible "
            f"({chauffeur.get_statut_display()})."
        )
    if vehicule_a_mission_active(vehicule):
        raise AffectationImpossible(
            f"Le camion {vehicule.immatriculation} est déjà réservé par une autre mission."
        )
    if chauffeur_a_mission_active(chauffeur):
        raise AffectationImpossible(
            f"Le chauffeur {chauffeur} est déjà réservé par une autre mission."
        )
    if mission.poids_t > vehicule.capacite_charge_t:
        raise AffectationImpossible(
            f"Charge de {mission.poids_t} t supérieure à la capacité du camion "
            f"({vehicule.capacite_charge_t} t)."
        )

    mission.vehicule = vehicule
    mission.chauffeur = chauffeur
    mission.statut = StatutMission.AFFECTEE
    mission.save(update_fields=["vehicule", "chauffeur", "statut", "updated_at"])
    return mission


@transaction.atomic
def demarrer_mission(mission: Mission) -> Mission:
    """Affectée → En cours (départ) : camion et chauffeur passent « En mission »
    (cahier-des-charges.md:135)."""
    _recharger(mission)
    _exiger_statut(mission, StatutMission.AFFECTEE, "démarrer la mission")
    vehicule = _recharger(mission.vehicule)
    chauffeur = _recharger(mission.chauffeur)

    # « En mission » est admis : après une réparation, la règle 2 du CDC
    # (cahier-des-charges.md:98) remet « En mission » un camion réservé par
    # une mission affectée. Aucune autre mission active ne peut le détenir
    # (contrôlé à l'affectation).
    if vehicule.statut not in (StatutVehicule.DISPONIBLE, StatutVehicule.EN_MISSION):
        raise DemarrageImpossible(
            f"Le camion {vehicule.immatriculation} n'est plus disponible "
            f"({vehicule.get_statut_display()})."
        )
    if chauffeur.statut != StatutChauffeur.DISPONIBLE:
        raise DemarrageImpossible(
            f"Le chauffeur {chauffeur} n'est plus disponible "
            f"({chauffeur.get_statut_display()})."
        )

    fleet_services.definir_statut(vehicule, StatutVehicule.EN_MISSION)
    drivers_services.mettre_en_mission(chauffeur)

    mission.km_depart = vehicule.kilometrage
    mission.date_depart = timezone.now()
    mission.statut = StatutMission.EN_COURS_DEPART
    mission.save(update_fields=["km_depart", "date_depart", "statut", "updated_at"])
    return mission


@transaction.atomic
def confirmer_recuperation(mission: Mission, *, code: str) -> Mission:
    """Départ → Colis récupéré : l'expéditeur saisit ou scanne son code."""
    _recharger(mission)
    _exiger_statut(
        mission, StatutMission.EN_COURS_DEPART, "confirmer la récupération du colis"
    )
    _verifier_code(code, mission.code_expediteur)

    mission.date_recuperation = timezone.now()
    mission.statut = StatutMission.EN_COURS_COLIS_RECUPERE
    mission.save(update_fields=["date_recuperation", "statut", "updated_at"])
    return mission


@transaction.atomic
def livrer_mission(mission: Mission, *, code: str, km_arrivee: int) -> Mission:
    """Colis récupéré → Livrée : le destinataire confirme avec son code.

    Camion et chauffeur repassent « Disponible » et le compteur du camion est
    mis à jour avec le kilométrage d'arrivée (cahier-des-charges.md:139).
    """
    _recharger(mission)
    _exiger_statut(
        mission, StatutMission.EN_COURS_COLIS_RECUPERE, "livrer la mission"
    )
    _verifier_code(code, mission.code_destinataire)

    if km_arrivee < mission.km_depart:
        raise KilometrageInvalide(
            f"Le kilométrage d'arrivée ({km_arrivee}) est inférieur au départ "
            f"({mission.km_depart})."
        )
    vehicule = _recharger(mission.vehicule)
    try:
        fleet_services.enregistrer_kilometrage(vehicule, km_arrivee)
    except ValueError as erreur:
        raise KilometrageInvalide(
            f"Le kilométrage d'arrivée ({km_arrivee}) est inférieur au compteur "
            f"du camion ({vehicule.kilometrage})."
        ) from erreur
    fleet_services.liberer_apres_mission(vehicule)
    drivers_services.rappeler_de_mission(_recharger(mission.chauffeur))

    mission.km_arrivee = km_arrivee
    mission.date_livraison = timezone.now()
    mission.statut = StatutMission.LIVREE
    mission.save(update_fields=["km_arrivee", "date_livraison", "statut", "updated_at"])
    return mission


@transaction.atomic
def cloturer_mission(mission: Mission) -> Mission:
    """Livrée → Clôturée et validée (validation finale, architecture.md:247)."""
    _recharger(mission)
    _exiger_statut(mission, StatutMission.LIVREE, "clôturer la mission")
    mission.date_cloture = timezone.now()
    mission.statut = StatutMission.CLOTUREE
    mission.save(update_fields=["date_cloture", "statut", "updated_at"])
    return mission
