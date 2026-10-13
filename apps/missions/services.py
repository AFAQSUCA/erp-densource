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
from django.db.models import Count, Q, QuerySet, Sum
from django.utils import timezone

from apps.core.montants import exiger_montant_entier
from apps.core.search import filtrer_par_texte, normaliser
from apps.core.services import etat_echeance, prochain_numero, total_par_mois
from apps.customers.models import Client
from apps.drivers import services as drivers_services
from apps.drivers.models import Chauffeur, Copilote, StatutChauffeur
from apps.fleet import services as fleet_services
from apps.fleet.models import DocumentReglementaire, StatutVehicule, TypeDocument, Vehicule
from apps.parametres import services as parametres_services

from .exceptions import (
    AffectationImpossible,
    CodeInvalide,
    DemarrageImpossible,
    KilometrageInvalide,
    MissionError,
    TransitionMissionInterdite,
)
from . import permissions, signals
from .models import (
    STATUTS_ACTIFS,
    STATUTS_ANNULABLES,
    STATUTS_EN_ROUTE_TRANSFERABLES,
    STATUTS_MODIFIABLES,
    FraisMission,
    Mission,
    StatutFraisMission,
    StatutMission,
    TransfertMission,
)
from .signals import mission_affectee, mission_annulee, mission_demarree, mission_desaffectee, mission_transferee

PREFIXE_NUMERO = "MIS"
# Sans caractères ambigus (0/O, 1/I) : les codes se dictent au téléphone.
ALPHABET_CODES = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
LONGUEUR_CODE = 8

logger = logging.getLogger(__name__)


def generer_code() -> str:
    """Code secret aléatoire (module ``secrets``, adapté aux usages sensibles)."""
    return "".join(secrets.choice(ALPHABET_CODES) for _ in range(LONGUEUR_CODE))


def _deux_codes() -> tuple[str, str]:
    """Codes expéditeur et destinataire, garantis différents l'un de l'autre."""
    expediteur = generer_code()
    destinataire = generer_code()
    while destinataire == expediteur:
        destinataire = generer_code()
    return expediteur, destinataire


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
    """Missions planifiées, affectées ou en cours d'un employé (identifié par sa fiche du personnel), en
    tant que chauffeur ou copilote, qui touchent la période.

    Alimente l'alerte N1 des congés (cahier-des-charges.md:219-221). Deux cas : le départ prévu tombe dans la
    période, ou la mission est déjà en cours (partie avant ou pendant la période, pas encore livrée : elle
    déborde sur le congé). Une mission non commencée et sans date de départ prévue ne peut pas être détectée.
    """
    en_cours = Q(
        statut__in=(StatutMission.EN_COURS_DEPART, StatutMission.EN_COURS_COLIS_RECUPERE),
        date_depart__date__lte=fin,
    )
    return (
        Mission.objects.filter(
            Q(chauffeur__personnel_id=personnel_id) | Q(copilote__personnel_id=personnel_id),
            statut__in=STATUTS_A_SURVEILLER,
        )
        .filter(Q(date_depart_prevue__range=(debut, fin)) | en_cours)
        .select_related("client")
        .order_by("date_depart_prevue", "pk")
    )


def repartition_par_statut() -> dict[str, int]:
    """Nombre de missions par statut (tous les statuts, y compris à 0)."""
    comptes = dict.fromkeys(StatutMission.values, 0)
    for statut, nombre in Mission.objects.values_list("statut").annotate(n=Count("pk")):
        comptes[statut] = nombre
    return comptes


def missions_par_mois(debut: date, fin: date) -> dict[str, dict[tuple[int, int], int]]:
    """Missions créées et missions livrées (livrées ou clôturées) par mois, sur la période.

    ``{"creees": {(année, mois): n}, "livrees": {...}}`` : deux requêtes.
    """
    return {
        "creees": total_par_mois(Mission.objects.filter(created_at__date__range=(debut, fin)), "created_at", None),
        "livrees": total_par_mois(
            Mission.objects.filter(
                statut__in=[StatutMission.LIVREE, StatutMission.CLOTUREE], date_livraison__date__range=(debut, fin)
            ),
            "date_livraison",
            None,
        ),
    }


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


def _missions_actives(sauf: Mission | None = None):
    """Missions affectées ou en cours, hors ``sauf`` : la mission qu'on est en train de modifier ne compte pas
    comme « une autre mission » qui réserverait déjà son propre camion ou son propre chauffeur."""
    missions = Mission.objects.filter(statut__in=STATUTS_ACTIFS)
    return missions.exclude(pk=sauf.pk) if sauf is not None else missions


def vehicule_a_mission_active(vehicule: Vehicule, *, sauf: Mission | None = None) -> bool:
    """Vrai si le camion est réservé par une mission affectée ou en cours.

    Fournit ``mission_active`` à ``fleet.services.calculer_statut`` (règle 2,
    cahier-des-charges.md:96-100). Une mission « planifiée » n'a pas encore de
    camion : seule l'affectation réserve un camion.
    """
    return _missions_actives(sauf).filter(vehicule=vehicule).exists()


def chauffeur_a_mission_active(chauffeur: Chauffeur, *, sauf: Mission | None = None) -> bool:
    return _missions_actives(sauf).filter(chauffeur=chauffeur).exists()


def copilote_a_mission_active(copilote: Copilote, *, sauf: Mission | None = None) -> bool:
    return _missions_actives(sauf).filter(copilote=copilote).exists()


# --- sortie du personnel (hr.sorties, avenant-sortie-personnel.md) ---

STATUTS_EN_ROUTE = (StatutMission.EN_COURS_DEPART, StatutMission.EN_COURS_COLIS_RECUPERE)


def missions_en_route_du_personnel(personnel_id: int) -> QuerySet[Mission]:
    """Missions parties que cet employé conduit ou accompagne : elles bloquent sa sortie."""
    return Mission.objects.filter(statut__in=STATUTS_EN_ROUTE).filter(
        Q(chauffeur__personnel_id=personnel_id) | Q(copilote__personnel_id=personnel_id)
    )


@transaction.atomic
def liberer_missions_du_partant(personnel_id: int, *, motif: str) -> dict:
    """Missions « Affectées » (pas encore parties) d'un employé qui sort : s'il en est le chauffeur, la mission
    repasse « Planifiée » sans camion, chauffeur ni copilote (camion libéré) et le Parc Auto est prévenu pour la
    réaffecter ; s'il en est le copilote, il en est seulement retiré."""
    desaffectees, sans_copilote = [], []
    for mission in Mission.objects.select_for_update().filter(
        statut=StatutMission.AFFECTEE, chauffeur__personnel_id=personnel_id
    ):
        mission.vehicule = mission.chauffeur = mission.copilote = None
        mission.statut = StatutMission.PLANIFIEE
        mission.save(update_fields=["vehicule", "chauffeur", "copilote", "statut", "updated_at"])
        signals.emettre(mission_desaffectee, mission=mission, motif=motif)
        desaffectees.append(mission.numero)
    for mission in Mission.objects.select_for_update().filter(
        statut=StatutMission.AFFECTEE, copilote__personnel_id=personnel_id
    ):
        mission.copilote = None
        mission.save(update_fields=["copilote", "updated_at"])
        sans_copilote.append(mission.numero)
    return {"missions_desaffectees": desaffectees, "missions_sans_copilote": sans_copilote}


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
    exiger_montant_entier(prix_convenu, libelle="Le prix convenu", erreur=MissionError)

    code_expediteur, code_destinataire = _deux_codes()

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
def modifier_mission(
    mission: Mission,
    *,
    lieu_chargement: str,
    lieu_livraison: str,
    nature_marchandise: str,
    poids_t: Decimal,
    prix_convenu: Decimal,
    date_depart_prevue: date | None,
    vehicule: Vehicule | None = None,
    chauffeur: Chauffeur | None = None,
) -> Mission:
    """Modifie une mission tant que le colis n'est pas encore récupéré (``STATUTS_MODIFIABLES`` :
    Brouillon, Planifiée, Affectée, En cours de départ) — règle de séparation des tâches, réservée à
    DIRECTION et ADMIN (``permissions.MODIFICATION``), tracée dans l'audit comme toute mission.

    Le client n'est pas modifiable : c'est l'identité de la mission. Un changement de lieu régénère les
    deux codes secrets (donc leurs QR, rendus à la volée depuis le code — ``CodeQrView``) : l'ancien code
    ne doit plus servir une fois le lieu changé. Un changement de camion ou de chauffeur (uniquement
    possible une fois la mission Affectée : avant, il n'y en a pas encore) revérifie leur disponibilité
    comme à l'affectation (:func:`_verifier_disponibilite`) ; réaffecter en cours de route
    (``EN_COURS_DEPART``) n'est pas pris en charge ici (le camion est physiquement engagé : ça relève
    d'un signalement d'incident et d'une nouvelle mission, pas d'une simple modification).
    """
    _recharger(mission)
    if mission.statut not in STATUTS_MODIFIABLES:
        raise TransitionMissionInterdite(
            f"Impossible de modifier la mission {mission.numero} : elle est déjà "
            f"« {mission.get_statut_display()} »."
        )
    if poids_t <= 0:
        raise MissionError("Le poids doit être strictement positif.")
    if prix_convenu < 0:
        raise MissionError("Le prix convenu ne peut pas être négatif.")
    exiger_montant_entier(prix_convenu, libelle="Le prix convenu", erreur=MissionError)

    champs = [
        "lieu_chargement", "lieu_livraison", "nature_marchandise",
        "poids_t", "prix_convenu", "date_depart_prevue", "updated_at",
    ]
    if lieu_chargement != mission.lieu_chargement or lieu_livraison != mission.lieu_livraison:
        mission.code_expediteur, mission.code_destinataire = _deux_codes()
        champs += ["code_expediteur", "code_destinataire"]

    mission.lieu_chargement = lieu_chargement
    mission.lieu_livraison = lieu_livraison
    mission.nature_marchandise = nature_marchandise
    mission.poids_t = poids_t
    mission.prix_convenu = prix_convenu
    mission.date_depart_prevue = date_depart_prevue

    if (vehicule is not None or chauffeur is not None) and (
        vehicule is None or chauffeur is None
    ):
        raise MissionError("Le camion et le chauffeur se changent ensemble.")
    if vehicule is not None and (vehicule.pk != mission.vehicule_id or chauffeur.pk != mission.chauffeur_id):
        if mission.statut != StatutMission.AFFECTEE:
            raise TransitionMissionInterdite(
                "Le camion et le chauffeur ne se réaffectent qu'avant le départ (mission Affectée)."
            )
        _recharger(vehicule)
        _recharger(chauffeur)
        # Seul ce qui change est revérifié : le camion ou le chauffeur conservé est déjà réservé par cette
        # mission (elle ne compte pas comme « une autre mission ») et son statut n'a pas à être « Disponible ».
        if vehicule.pk != mission.vehicule_id:
            _verifier_vehicule(vehicule, poids_t, sauf=mission)
        if chauffeur.pk != mission.chauffeur_id:
            _verifier_chauffeur(chauffeur, sauf=mission)
        mission.vehicule = vehicule
        mission.chauffeur = chauffeur
        champs += ["vehicule", "chauffeur"]
    if mission.vehicule_id and (vehicule is None or vehicule.pk == mission.vehicule_id):
        # Camion inchangé : une hausse du poids doit quand même rester dans sa capacité.
        _verifier_capacite(mission.vehicule, poids_t)

    mission.save(update_fields=champs)
    return mission


@transaction.atomic
def planifier_mission(mission: Mission) -> Mission:
    """Brouillon → Planifiée (validation du chargé clientèle, architecture.md:241)."""
    _recharger(mission)
    _exiger_statut(mission, StatutMission.BROUILLON, "planifier la mission")
    mission.statut = StatutMission.PLANIFIEE
    mission.save(update_fields=["statut", "updated_at"])
    return mission


def _verifier_vehicule(vehicule: Vehicule, poids_t: Decimal, sauf: Mission | None = None) -> None:
    """Camion disponible, non réservé par une autre mission, et capable d'emporter la charge."""
    if vehicule.statut != StatutVehicule.DISPONIBLE:
        raise AffectationImpossible(
            f"Le camion {vehicule.immatriculation} n'est pas disponible "
            f"({vehicule.get_statut_display()})."
        )
    if vehicule_a_mission_active(vehicule, sauf=sauf):
        raise AffectationImpossible(
            f"Le camion {vehicule.immatriculation} est déjà réservé par une autre mission."
        )
    _exiger_vehicule_en_regle(vehicule, AffectationImpossible)
    _verifier_capacite(vehicule, poids_t)


def _verifier_capacite(vehicule: Vehicule, poids_t: Decimal) -> None:
    if poids_t > vehicule.capacite_charge_t:
        raise AffectationImpossible(
            f"Charge de {poids_t} t supérieure à la capacité du camion "
            f"({vehicule.capacite_charge_t} t)."
        )


def documents_expires_du_chauffeur(chauffeur: Chauffeur, *, aujourd_hui: date | None = None) -> list[str]:
    """Libellés (« permis », « visite médicale ») des documents du chauffeur dont la date est dépassée. Une date
    non renseignée n'est pas une expiration : elle est traitée par :func:`documents_manquants_du_chauffeur`."""
    expires = []
    for libelle, echeance in (
        ("permis de conduire", chauffeur.date_expiration_permis),
        ("visite médicale", chauffeur.date_expiration_visite_medicale),
    ):
        etat, _ = etat_echeance(echeance, aujourd_hui=aujourd_hui)
        if etat == "EXPIRE":
            expires.append(f"{libelle} (expiré le {echeance:%d/%m/%Y})")
    return expires


# La règle appartient aux chauffeurs (``drivers``) : le tableau de bord et la liste des chauffeurs l'appliquent
# aussi (audit M12-10). Noms gardés ici pour les appelants existants.
CATEGORIES_POIDS_LOURD = drivers_services.CATEGORIES_POIDS_LOURD
documents_manquants_du_chauffeur = drivers_services.documents_manquants_du_chauffeur


def _exiger_documents_valides(chauffeur: Chauffeur, erreur: type[MissionError]) -> None:
    """Un chauffeur au permis ou à la visite médicale expiré ou non renseigné, ou sans catégorie poids lourd, ne
    peut pas conduire, donc pas être affecté ni partir (audit M5-04)."""
    problemes = documents_expires_du_chauffeur(chauffeur) + documents_manquants_du_chauffeur(chauffeur)
    if problemes:
        raise erreur(f"Le chauffeur {chauffeur} ne peut pas conduire : {' ; '.join(problemes)}.")


def documents_non_valides_du_vehicule(vehicule: Vehicule, *, aujourd_hui: date | None = None) -> list[str]:
    """Documents réglementaires du camion expirés ou jamais enregistrés (décision du 12/10/2026, audit AUD-12 :
    bloquant à l'affectation et au départ)."""
    aujourd_hui = aujourd_hui or timezone.localdate()
    documents = {d.type_document: d for d in DocumentReglementaire.objects.filter(vehicule=vehicule)}
    problemes = []
    for code, libelle in TypeDocument.choices:
        document = documents.get(code)
        if document is None:
            problemes.append(f"{libelle.lower()} non enregistrée")  # les 4 documents sont féminins
        elif document.date_expiration < aujourd_hui:
            problemes.append(f"{libelle.lower()} expirée le {document.date_expiration:%d/%m/%Y}")
    return problemes


def _exiger_vehicule_en_regle(vehicule: Vehicule, erreur: type[MissionError]) -> None:
    problemes = documents_non_valides_du_vehicule(vehicule)
    if problemes:
        raise erreur(f"Le camion {vehicule.immatriculation} ne peut pas rouler : {' ; '.join(problemes)}.")


def _verifier_chauffeur(chauffeur: Chauffeur, sauf: Mission | None = None) -> None:
    """Chauffeur disponible, non réservé par une autre mission, aux documents en règle."""
    if chauffeur.statut != StatutChauffeur.DISPONIBLE:
        raise AffectationImpossible(
            f"Le chauffeur {chauffeur} n'est pas disponible "
            f"({chauffeur.get_statut_display()})."
        )
    if chauffeur_a_mission_active(chauffeur, sauf=sauf):
        raise AffectationImpossible(
            f"Le chauffeur {chauffeur} est déjà réservé par une autre mission."
        )
    _exiger_documents_valides(chauffeur, AffectationImpossible)


def _verifier_copilote(copilote: Copilote, sauf: Mission | None = None) -> None:
    if copilote.statut != StatutChauffeur.DISPONIBLE:
        raise AffectationImpossible(
            f"Le copilote {copilote} n'est pas disponible ({copilote.get_statut_display()})."
        )
    if copilote_a_mission_active(copilote, sauf=sauf):
        raise AffectationImpossible(
            f"Le copilote {copilote} est déjà réservé par une autre mission."
        )


def _verifier_disponibilite(
    vehicule: Vehicule,
    chauffeur: Chauffeur,
    poids_t: Decimal,
    copilote: Copilote | None = None,
    *,
    sauf: Mission | None = None,
) -> None:
    """Camion et chauffeur disponibles, non réservés par une autre mission active, chauffeur aux documents en
    règle, et camion capable d'emporter la charge (cahier-des-charges.md:130-131). Utilisé par l'affectation ;
    la réaffectation (modification d'une mission déjà affectée) revérifie, elle, seulement ce qui change.
    ``copilote`` facultatif : certains voyages exigent un assistant au chauffeur. ``sauf`` : la mission en
    cours de modification, qui ne compte pas comme « une autre mission »."""
    _verifier_vehicule(vehicule, poids_t, sauf)
    _verifier_chauffeur(chauffeur, sauf)
    if copilote is not None:
        _verifier_copilote(copilote, sauf)


@transaction.atomic
def affecter_mission(
    mission: Mission, *, vehicule: Vehicule, chauffeur: Chauffeur, copilote: Copilote | None = None
) -> Mission:
    """Planifiée → Affectée : camion et chauffeur disponibles, non réservés,
    et capable d'emporter la charge (cahier-des-charges.md:130-131). ``copilote`` facultatif,
    pour les voyages qui l'exigent (décision du Parc Auto au moment de l'affectation)."""
    _recharger(mission)
    _exiger_statut(mission, StatutMission.PLANIFIEE, "affecter la mission")
    _recharger(vehicule)
    _recharger(chauffeur)
    if copilote is not None:
        _recharger(copilote)
    _verifier_disponibilite(vehicule, chauffeur, mission.poids_t, copilote)

    mission.vehicule = vehicule
    mission.chauffeur = chauffeur
    mission.copilote = copilote
    mission.statut = StatutMission.AFFECTEE
    mission.save(update_fields=["vehicule", "chauffeur", "copilote", "statut", "updated_at"])
    signals.emettre(mission_affectee, mission=mission)
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
    _exiger_documents_valides(chauffeur, DemarrageImpossible)  # un document a pu expirer depuis l'affectation
    _exiger_vehicule_en_regle(vehicule, DemarrageImpossible)
    copilote = _recharger(mission.copilote) if mission.copilote_id else None
    if copilote is not None and copilote.statut != StatutChauffeur.DISPONIBLE:
        raise DemarrageImpossible(
            f"Le copilote {copilote} n'est plus disponible ({copilote.get_statut_display()})."
        )

    fleet_services.definir_statut(vehicule, StatutVehicule.EN_MISSION)
    drivers_services.mettre_en_mission(chauffeur)
    if copilote is not None:
        drivers_services.mettre_en_mission_copilote(copilote)

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
    ecart_max = parametres_services.parametres().ecart_km_max
    if not fleet_services.distance_plausible(mission.km_depart, km_arrivee, ecart_max=ecart_max):
        raise KilometrageInvalide(
            f"Le kilométrage d'arrivée ({km_arrivee}) est {km_arrivee - mission.km_depart} km au-dessus du "
            f"départ ({mission.km_depart}) : plus de {ecart_max} km sur une mission, "
            "vérifiez la saisie (le compteur du camion ne peut plus reculer ensuite)."
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
    if mission.copilote_id:
        drivers_services.rappeler_copilote_de_mission(_recharger(mission.copilote))

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


# --- annulation avant le départ et transfert en route (décision du 13/10/2026, audit AUD-02) ---


def _exiger_role(acteur, roles, action: str) -> None:
    if acteur.role_effectif not in roles:
        raise TransitionMissionInterdite(f"Vous n'avez pas le droit de {action}.")


@transaction.atomic
def annuler_mission(mission: Mission, acteur, *, motif: str) -> Mission:
    """Annule une mission pas encore partie (Brouillon, Planifiée, Affectée), avec un motif. Le camion et le
    chauffeur ne sont plus réservés (une mission annulée n'est plus active) ; les frais encore prévus sont rejetés
    (une avance déjà versée reste comptée : l'argent est sorti) ; le devis d'origine est annulé (``billing``)."""
    _exiger_role(acteur, permissions.ANNULATION, "annuler une mission")
    _recharger(mission)
    if mission.statut not in STATUTS_ANNULABLES:
        raise TransitionMissionInterdite(
            f"La mission {mission.numero} est « {mission.get_statut_display()} » : seule une mission pas encore "
            "partie s'annule ; en route, elle se transfère vers un autre camion ou chauffeur."
        )
    motif = motif.strip()
    if not motif:
        raise MissionError("Le motif de l'annulation est obligatoire.")
    for frais in FraisMission.objects.select_for_update().filter(mission=mission, statut=StatutFraisMission.PREVU):
        frais.statut = StatutFraisMission.REJETE
        frais.motif_rejet = f"Mission annulée : {motif}"
        frais.save(update_fields=["statut", "motif_rejet", "updated_at"])
    mission.statut = StatutMission.ANNULEE
    mission.motif_annulation = motif
    mission.date_annulation = timezone.now()
    mission.annulee_par = acteur
    mission.save(update_fields=["statut", "motif_annulation", "date_annulation", "annulee_par", "updated_at"])
    mission_annulee.send(sender=Mission, mission=mission)
    return mission


STATUTS_ANCIEN_CAMION = (StatutVehicule.EN_MAINTENANCE, StatutVehicule.IMMOBILISE, StatutVehicule.DISPONIBLE)


@transaction.atomic
def transferer_mission(
    mission: Mission,
    acteur,
    *,
    vehicule: Vehicule,
    chauffeur: Chauffeur,
    copilote: Copilote | None = None,
    km_ancien_vehicule: int,
    statut_ancien_vehicule: str,
    motif: str,
) -> TransfertMission:
    """Transfère une mission en route vers un autre camion et/ou chauffeur (panne définitive, chauffeur
    indisponible). Mêmes contrôles qu'à l'affectation pour ce qui change ; l'ancien camion reçoit son kilométrage
    et le statut choisi (en maintenance, immobilisé ou disponible), l'ancien équipage est libéré, le nouveau part
    « En mission ». La mission continue avec ses codes ; le nouveau tronçon part du compteur du nouveau camion."""
    _exiger_role(acteur, permissions.TRANSFERT, "transférer une mission")
    _recharger(mission)
    if mission.statut not in STATUTS_EN_ROUTE_TRANSFERABLES:
        raise TransitionMissionInterdite(
            f"La mission {mission.numero} est « {mission.get_statut_display()} » : seule une mission en route se "
            "transfère (avant le départ, on modifie son affectation)."
        )
    motif = motif.strip()
    if not motif:
        raise MissionError("Le motif du transfert est obligatoire.")
    if statut_ancien_vehicule not in STATUTS_ANCIEN_CAMION:
        raise MissionError("Statut de l'ancien camion inconnu.")
    if vehicule.pk == mission.vehicule_id and chauffeur.pk == mission.chauffeur_id and (
        (copilote.pk if copilote else None) == mission.copilote_id
    ):
        raise MissionError("Rien ne change : choisissez un autre camion, un autre chauffeur ou un autre copilote.")
    ancien_vehicule = _recharger(mission.vehicule)
    ancien_chauffeur = _recharger(mission.chauffeur)
    ancien_copilote = _recharger(mission.copilote) if mission.copilote_id else None
    nouveau_vehicule, nouveau_chauffeur = _recharger(vehicule), _recharger(chauffeur)
    nouveau_copilote = _recharger(copilote) if copilote is not None else None

    # Contrôles comme à l'affectation, pour ce qui change (le conservé est déjà engagé sur cette mission).
    if nouveau_vehicule.pk != ancien_vehicule.pk:
        _verifier_vehicule(nouveau_vehicule, mission.poids_t, sauf=mission)
        if km_ancien_vehicule < ancien_vehicule.kilometrage:
            raise KilometrageInvalide(
                f"Le kilométrage de l'ancien camion ({km_ancien_vehicule}) est inférieur à son compteur "
                f"({ancien_vehicule.kilometrage})."
            )
    if nouveau_chauffeur.pk != ancien_chauffeur.pk:
        _verifier_chauffeur(nouveau_chauffeur, sauf=mission)
    if nouveau_copilote is not None and (ancien_copilote is None or nouveau_copilote.pk != ancien_copilote.pk):
        _verifier_copilote(nouveau_copilote, sauf=mission)

    # L'ancien équipage descend, le nouveau monte.
    if nouveau_vehicule.pk != ancien_vehicule.pk:
        fleet_services.enregistrer_kilometrage(ancien_vehicule, km_ancien_vehicule)
        fleet_services.definir_statut(ancien_vehicule, statut_ancien_vehicule)
        _exiger_vehicule_en_regle(nouveau_vehicule, AffectationImpossible)
        fleet_services.definir_statut(nouveau_vehicule, StatutVehicule.EN_MISSION)
        mission.km_depart = nouveau_vehicule.kilometrage
    if nouveau_chauffeur.pk != ancien_chauffeur.pk:
        drivers_services.rappeler_de_mission(ancien_chauffeur)
        drivers_services.mettre_en_mission(nouveau_chauffeur)
    if ancien_copilote is not None and (nouveau_copilote is None or nouveau_copilote.pk != ancien_copilote.pk):
        drivers_services.rappeler_copilote_de_mission(ancien_copilote)
    if nouveau_copilote is not None and (ancien_copilote is None or nouveau_copilote.pk != ancien_copilote.pk):
        drivers_services.mettre_en_mission_copilote(nouveau_copilote)

    transfert = TransfertMission.objects.create(
        mission=mission, ancien_vehicule=ancien_vehicule, nouveau_vehicule=nouveau_vehicule,
        ancien_chauffeur=ancien_chauffeur, nouveau_chauffeur=nouveau_chauffeur,
        km_ancien_vehicule=km_ancien_vehicule if nouveau_vehicule.pk != ancien_vehicule.pk else ancien_vehicule.kilometrage,
        km_depart_nouveau=nouveau_vehicule.kilometrage,
        statut_ancien_vehicule=statut_ancien_vehicule if nouveau_vehicule.pk != ancien_vehicule.pk else "",
        motif=motif, transfere_par=acteur,
    )
    mission.vehicule, mission.chauffeur, mission.copilote = nouveau_vehicule, nouveau_chauffeur, nouveau_copilote
    mission.save(update_fields=["vehicule", "chauffeur", "copilote", "km_depart", "updated_at"])
    signals.emettre(mission_transferee, transfert=transfert)
    return transfert
