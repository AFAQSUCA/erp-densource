"""Logique métier des missions — cycle de vie du CDC (cahier-des-charges.md:127-143).

Brouillon → Planifiée → Affectée → En cours (départ → colis récupéré) →
Livrée → Clôturée. Chaque transition est atomique et relit la mission sous
verrou pour éviter deux actions simultanées.

Les contrôles de rôle (chargé clientèle, direction, chauffeur) relèvent des
permissions DRF de l'API (étape 6), pas de ce module.
"""

from __future__ import annotations

import logging
import secrets
from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, QuerySet, Sum
from django.utils import timezone

from apps.core.search import filtrer_par_texte, normaliser
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
from .signals import mission_demarree

PREFIXE_NUMERO = "MIS"
# Sans caractères ambigus (0/O, 1/I) : les codes se dictent au téléphone.
ALPHABET_CODES = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
LONGUEUR_CODE = 8

logger = logging.getLogger(__name__)


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


def lieux_deja_utilises(*, limite: int = 200) -> list[str]:
    """Lieux de chargement et de livraison déjà saisis, les plus fréquents d'abord.

    Sert de liste de suggestions à la saisie d'une nouvelle mission : un même lieu, écrit avec une
    autre casse ou sans accent (« Bouake », « bouaké »), ne compte qu'une fois — on garde la graphie
    la plus employée.
    """
    par_lieu: dict[str, Counter[str]] = {}
    for champ in ("lieu_chargement", "lieu_livraison"):
        for lieu, nombre in Mission.objects.values_list(champ).annotate(n=Count("pk")):
            lieu = (lieu or "").strip()
            if lieu:
                par_lieu.setdefault(normaliser(lieu), Counter())[lieu] += nombre
    classes = sorted(
        par_lieu.values(), key=lambda graphies: (-sum(graphies.values()), graphies.most_common(1)[0][0].casefold())
    )
    return [graphies.most_common(1)[0][0] for graphies in classes[:limite]]


def rechercher_missions(
    *, statut: str | None = None, recherche: str = ""
) -> QuerySet[Mission]:
    """Missions filtrées par statut et/ou texte (numéro, client, lieux)."""
    missions = missions_queryset()
    if statut in StatutMission.values:
        missions = missions.filter(statut=statut)
    missions = filtrer_par_texte(
        missions, recherche, "numero", "client__raison_sociale", "lieu_chargement", "lieu_livraison"
    )
    return missions



STATUTS_A_SURVEILLER = (
    StatutMission.PLANIFIEE,
    StatutMission.AFFECTEE,
    StatutMission.EN_COURS_DEPART,
    StatutMission.EN_COURS_COLIS_RECUPERE,
)


def missions_du_personnel_sur_periode(personnel_id: int, debut, fin) -> QuerySet[Mission]:
    """Missions planifiées, affectées ou en cours d'un chauffeur (identifié par sa fiche du
    personnel) dont le départ prévu tombe dans la période.

    Alimente l'alerte N1 des congés (cahier-des-charges.md:219-221). Une mission sans date
    de départ prévue ne peut pas être détectée.
    """
    return (
        Mission.objects.filter(
            chauffeur__personnel_id=personnel_id,
            statut__in=STATUTS_A_SURVEILLER,
            date_depart_prevue__range=(debut, fin),
        )
        .select_related("client")
        .order_by("date_depart_prevue")
    )


def repartition_par_statut() -> dict[str, int]:
    """Nombre de missions par statut (tous les statuts, y compris à 0)."""
    comptes = dict.fromkeys(StatutMission.values, 0)
    for statut, nombre in Mission.objects.values_list("statut").annotate(n=Count("pk")):
        comptes[statut] = nombre
    return comptes


def clients_actifs(*, jours: int = 90, maintenant: datetime | None = None) -> int:
    """Clients ayant au moins une mission créée sur les ``jours`` derniers jours."""
    depuis = (maintenant or timezone.now()) - timedelta(days=jours)
    return Mission.objects.filter(created_at__gte=depuis).values("client").distinct().count()


def meilleurs_clients(
    *, limite: int = 3, mois: int = 12, maintenant: datetime | None = None
) -> list[dict]:
    """Clients classés par montant des missions livrées ou clôturées sur ``mois`` mois.

    Le montant est le prix convenu des missions (l'écran de facturation viendra avec
    l'étape 4). Chaque ligne : ``client``, ``montant``, ``missions``.
    """
    depuis = (maintenant or timezone.now()) - timedelta(days=30 * mois)
    lignes = (
        Mission.objects.filter(
            statut__in=[StatutMission.LIVREE, StatutMission.CLOTUREE], date_livraison__gte=depuis
        )
        .values("client_id", "client__raison_sociale")
        .annotate(montant=Sum("prix_convenu"), missions=Count("pk"))
        .order_by("-montant", "client__raison_sociale")[:limite]
    )
    return [
        {
            "client_id": ligne["client_id"],
            "client": ligne["client__raison_sociale"],
            "montant": ligne["montant"],
            "missions": ligne["missions"],
        }
        for ligne in lignes
    ]


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
    for recepteur, resultat in mission_demarree.send_robust(sender=Mission, mission=mission):
        if isinstance(resultat, Exception):
            logger.error("Récepteur %r en erreur", recepteur, exc_info=resultat)
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
