# Chapitre 9 — Les missions de transport : l'app missions

> 15 fichier(s) dans ce chapitre, 1325 lignes de code.

## Ce que vous allez construire

**`missions`** : le **cœur de l'ERP**. Une mission est un transport confié par un client : où charger, où
livrer, quelle marchandise, quel poids, à quel prix. Elle suit un **cycle de vie** strict :

```text
Brouillon → Planifiée → Affectée → En cours (départ → colis récupéré) → Livrée → Clôturée
```

| Étape | Ce que le système vérifie ou fait |
|---|---|
| **Créer** | numéro `MIS-<année>-0001`, **deux codes secrets** de 8 caractères (expéditeur et destinataire) |
| **Affecter** | le camion et le chauffeur sont **disponibles**, **non réservés** par une autre mission, et la **capacité** du camion suffit pour le poids |
| **Démarrer** | le camion et le chauffeur passent « En mission » ; le kilométrage de départ est relevé |
| **Confirmer la récupération** | il faut le **code de l'expéditeur** |
| **Livrer** | il faut le **code du destinataire** et le kilométrage d'arrivée (le compteur du camion est mis à jour ; camion et chauffeur sont libérés) |
| **Clôturer** | validation finale (la Direction) |

## Prérequis

- Chapitres 1 à 8 terminés.

## Notions Django de ce chapitre

- **Machine à états complète** : chaque transition est une fonction qui vérifie le statut de départ
  (`_exiger_statut`) et lève `TransitionMissionInterdite` sinon.
- **Verrou de ligne** (`select_for_update`) dans `_recharger` : deux personnes ne peuvent pas agir en même
  temps sur la même mission.
- **Le module `secrets`** (et non `random`) pour générer les codes : c'est le générateur prévu pour les
  secrets. **`secrets.compare_digest`** compare deux chaînes en **temps constant**, pour ne pas révéler par
  le temps de réponse combien de caractères sont justes.
- **Contrainte multi-condition** : une mission **Affectée** exige un camion **et** un chauffeur (contrainte
  `mission_affectee_requiert_camion_et_chauffeur`).
- **Signal émis avec `send_robust`** : `mission_demarree` prévient `notifications` sans dépendre d'elle.
- **Composition de services** : `demarrer_mission` appelle les services de `fleet` et `drivers` (dépendances
  descendantes autorisées).
- **Agrégation** (`Count`, `Sum`) pour les statistiques (meilleurs clients).

## Étape 1 — Créer l'application

```bash
mkdir -p apps/missions/tests
```

#### Fichiers vides à créer

Ces fichiers n'ont aucun contenu ; ils servent à faire de leur dossier un *paquet Python* (sans eux, `import apps.xxx` échouerait). Créez d'abord les dossiers, puis les fichiers :

```bash
mkdir -p apps\missions apps\missions\tests
touch apps/missions/__init__.py
touch apps/missions/tests/__init__.py
```

> Sous PowerShell, `mkdir -p` s'écrit `New-Item -ItemType Directory -Force <dossier>` et `touch fichier` s'écrit `New-Item -ItemType File -Force fichier`. Vous pouvez aussi créer ces fichiers avec votre éditeur.

## Étape 2 — Le modèle

#### `apps/missions/models.py`

*132 lignes*

```python
from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class StatutMission(models.TextChoices):
    """Cycle de vie — cahier-des-charges.md:132-134, architecture.md:239-256.

    « En cours » se décompose en deux étapes : départ, puis colis récupéré.
    """

    BROUILLON = "BROUILLON", _("Brouillon")
    PLANIFIEE = "PLANIFIEE", _("Planifiée")
    AFFECTEE = "AFFECTEE", _("Affectée")
    EN_COURS_DEPART = "EN_COURS_DEPART", _("En cours : départ")
    EN_COURS_COLIS_RECUPERE = "EN_COURS_COLIS_RECUPERE", _("En cours : colis récupéré")
    LIVREE = "LIVREE", _("Livrée")
    CLOTUREE = "CLOTUREE", _("Clôturée et validée")


# Camion et chauffeur réservés : la mission a été affectée mais n'est pas terminée.
STATUTS_ACTIFS = (
    StatutMission.AFFECTEE,
    StatutMission.EN_COURS_DEPART,
    StatutMission.EN_COURS_COLIS_RECUPERE,
)


class Mission(BaseModel):
    """Mission de transport — cahier-des-charges.md:127-143."""

    numero = models.CharField(_("numéro"), max_length=20, unique=True)
    client = models.ForeignKey(
        "customers.Client",
        verbose_name=_("client"),
        on_delete=models.PROTECT,
        related_name="missions",
    )
    vehicule = models.ForeignKey(
        "fleet.Vehicule",
        verbose_name=_("camion"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="missions",
    )
    chauffeur = models.ForeignKey(
        "drivers.Chauffeur",
        verbose_name=_("chauffeur"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="missions",
    )
    lieu_chargement = models.CharField(_("lieu de chargement"), max_length=200)
    lieu_livraison = models.CharField(_("lieu de livraison"), max_length=200)
    nature_marchandise = models.CharField(_("nature de la marchandise"), max_length=200)
    poids_t = models.DecimalField(_("poids (t)"), max_digits=8, decimal_places=2)
    prix_convenu = models.DecimalField(
        _("prix convenu (FCFA)"), max_digits=12, decimal_places=2
    )
    date_depart_prevue = models.DateField(
        _("départ prévu"),
        null=True,
        blank=True,
        help_text=_(
            "Nécessaire à l'alerte N1 « chauffeur avec mission sur la période » "
            "des congés (cahier-des-charges.md:219-221)."
        ),
    )
    statut = models.CharField(
        _("statut"),
        max_length=25,
        choices=StatutMission.choices,
        default=StatutMission.BROUILLON,
    )

    # Codes remis à l'expéditeur (récupération du colis) et au destinataire
    # (confirmation de livraison) — cahier-des-charges.md:135-137. Exclus de
    # l'audit (voir apps.py). Le QR ne fait qu'encoder ces codes.
    code_expediteur = models.CharField(_("code expéditeur"), max_length=12)
    code_destinataire = models.CharField(_("code destinataire"), max_length=12)

    km_depart = models.PositiveIntegerField(_("km au départ"), null=True, blank=True)
    km_arrivee = models.PositiveIntegerField(_("km à l'arrivée"), null=True, blank=True)
    date_depart = models.DateTimeField(_("départ effectif"), null=True, blank=True)
    date_recuperation = models.DateTimeField(_("colis récupéré le"), null=True, blank=True)
    date_livraison = models.DateTimeField(_("livrée le"), null=True, blank=True)
    date_cloture = models.DateTimeField(_("clôturée le"), null=True, blank=True)

    class Meta:
        verbose_name = _("mission")
        verbose_name_plural = _("missions")
        ordering = ["-numero"]
        indexes = [
            models.Index(fields=["statut"]),
            models.Index(fields=["vehicule", "statut"]),
            models.Index(fields=["chauffeur", "statut"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    statut__in=[StatutMission.BROUILLON, StatutMission.PLANIFIEE]
                )
                | (Q(vehicule__isnull=False) & Q(chauffeur__isnull=False)),
                name="mission_affectee_requiert_camion_et_chauffeur",
            ),
            models.CheckConstraint(
                condition=Q(poids_t__gt=0), name="mission_poids_positif"
            ),
            models.CheckConstraint(
                condition=Q(prix_convenu__gte=0), name="mission_prix_positif_ou_nul"
            ),
            models.CheckConstraint(
                condition=Q(km_arrivee__isnull=True)
                | Q(km_depart__isnull=True)
                | Q(km_arrivee__gte=F("km_depart")),
                name="mission_km_arrivee_apres_depart",
            ),
        ]

    def __str__(self):
        return f"{self.numero} ({self.client})"

    @property
    def est_en_cours(self) -> bool:
        return self.statut in (
            StatutMission.EN_COURS_DEPART,
            StatutMission.EN_COURS_COLIS_RECUPERE,
        )
```

Points clés :

- **`StatutMission`** : les 7 statuts (« En cours » se décompose en *départ* puis *colis récupéré*).
- **`STATUTS_ACTIFS`** : les statuts pendant lesquels le camion et le chauffeur sont **réservés**.
- Le **prix convenu** est un `DecimalField` ; les **codes** sont stockés en clair *mais exclus du journal
  d'audit* (voir `apps.py`).
- Trois contraintes en base : poids positif, prix positif ou nul, camion et chauffeur obligatoires dès
  « Affectée ».

## Étape 3 — Exceptions et règles métier

#### `apps/missions/exceptions.py`

*22 lignes*

```python
class MissionError(Exception):
    """Erreur métier sur une mission (traduite en 400/409 par l'API)."""


class TransitionMissionInterdite(MissionError):
    """La mission n'est pas dans le statut requis pour cette action."""


class AffectationImpossible(MissionError):
    """Camion ou chauffeur indisponible, déjà réservé, ou capacité dépassée."""


class DemarrageImpossible(MissionError):
    """Camion ou chauffeur n'est plus disponible au moment du départ."""


class CodeInvalide(MissionError):
    """Le code saisi (expéditeur ou destinataire) ne correspond pas."""


class KilometrageInvalide(MissionError):
    """Kilométrage d'arrivée incohérent avec le départ ou le compteur."""
```

#### `apps/missions/services.py`

*365 lignes* — Logique métier des missions — cycle de vie du CDC (cahier-des-charges.md:127-143).

```python
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
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, QuerySet, Sum
from django.utils import timezone

from apps.core.search import filtrer_par_texte
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
```

C'est le fichier à lire **le plus attentivement** de tout le projet. Une fonction par transition :

1. **`creer_mission`** : contrôle poids et prix, génère deux codes différents, attribue le numéro avec
   `prochain_numero` (chapitre 2).
2. **`planifier_mission`** : Brouillon → Planifiée.
3. **`affecter_mission`** : la fonction que vous avez peut-être déjà croisée. Elle recharge la mission, le
   camion et le chauffeur sous verrou, puis enchaîne les contrôles : statut « Disponible », non réservé,
   capacité suffisante.
4. **`demarrer_mission`** : camion et chauffeur passent « En mission » (via `fleet` et `drivers`), le
   kilométrage de départ est relevé, `mission_demarree` est émis.
5. **`confirmer_recuperation`** : compare le code saisi à celui de l'expéditeur avec `_verifier_code`.
6. **`livrer_mission`** : compare le code du destinataire, vérifie le kilométrage d'arrivée (jamais
   inférieur au départ ni au compteur), met à jour le compteur du camion, libère camion et chauffeur.
7. **`cloturer_mission`** : Livrée → Clôturée.
8. Les *lectures* : `rechercher_missions`, `missions_du_personnel_sur_periode` (pour l'alerte de congé de
   `hr`), `vehicule_a_mission_active` et `chauffeur_a_mission_active` (fournis à `fleet` et `drivers`),
   `meilleurs_clients`, `clients_actifs`.

#### `apps/missions/signals.py`

*7 lignes* — Événements des missions (souscrits par ``notifications``).

```python
"""Événements des missions (souscrits par ``notifications``)."""

from django.dispatch import Signal

# La mission vient de démarrer : « en cours de route (départ) » (cahier-des-charges.md:136-137).
# Argument : ``mission`` (instance à jour).
mission_demarree = Signal()
```

#### `apps/missions/permissions.py`

*69 lignes* — Qui peut faire quoi sur une mission.

```python
"""Qui peut faire quoi sur une mission.

Rôles du CDC (cahier-des-charges.md:44-55) : la DIRECTION crée, affecte et suit
les missions ; le chargé clientèle valide le passage en « Planifiée »
(architecture.md:241). L'ADMIN a tous les droits. Ces ensembles serviront aussi
aux permissions DRF de l'API (étape 6).

Le chauffeur exécute ses missions depuis l'espace mobile (étape 6) : il n'a pas
d'accès à ces écrans.
"""

from __future__ import annotations

from apps.accounts.models import Role

from .models import Mission, StatutMission

CONSULTATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.CHARGE_CLIENTELE})
CREATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.CHARGE_CLIENTELE})
PLANIFICATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.CHARGE_CLIENTELE})
AFFECTATION = frozenset({Role.ADMIN, Role.DIRECTION})
# Départ, récupération et livraison saisis depuis le back-office (suivi) ;
# le chauffeur les fera lui-même depuis le mobile.
SUIVI_TERRAIN = frozenset({Role.ADMIN, Role.DIRECTION})
CLOTURE = frozenset({Role.ADMIN, Role.DIRECTION})

# Les codes sont à communiquer à l'expéditeur et au destinataire : ils ne sont
# visibles que des rôles qui gèrent la relation client.
VOIR_CODES = CONSULTATION


def actions_disponibles(utilisateur, mission: Mission) -> dict[str, bool]:
    """Actions proposables à ``utilisateur`` sur ``mission`` (statut + rôle)."""
    role = utilisateur.role_effectif
    statut = mission.statut
    return {
        "planifier": statut == StatutMission.BROUILLON and role in PLANIFICATION,
        "affecter": statut == StatutMission.PLANIFIEE and role in AFFECTATION,
        "demarrer": statut == StatutMission.AFFECTEE and role in SUIVI_TERRAIN,
        "recuperation": statut == StatutMission.EN_COURS_DEPART
        and role in SUIVI_TERRAIN,
        "livraison": statut == StatutMission.EN_COURS_COLIS_RECUPERE
        and role in SUIVI_TERRAIN,
        "cloturer": statut == StatutMission.LIVREE and role in CLOTURE,
    }


def codes_visibles(utilisateur, mission: Mission) -> dict[str, str | None]:
    """Codes encore utiles à communiquer, ``None`` quand ils ne le sont plus.

    Le code expéditeur ne sert que jusqu'à la récupération du colis, le code
    destinataire que jusqu'à la livraison.
    """
    if utilisateur.role_effectif not in VOIR_CODES:
        return {"expediteur": None, "destinataire": None}
    avant_recuperation = mission.statut in (
        StatutMission.BROUILLON,
        StatutMission.PLANIFIEE,
        StatutMission.AFFECTEE,
        StatutMission.EN_COURS_DEPART,
    )
    avant_livraison = mission.statut not in (
        StatutMission.LIVREE,
        StatutMission.CLOTUREE,
    )
    return {
        "expediteur": mission.code_expediteur if avant_recuperation else None,
        "destinataire": mission.code_destinataire if avant_livraison else None,
    }
```

Remarquez `actions_disponibles(utilisateur, mission)` : elle indique à l'interface **quelles actions afficher**
selon le rôle *et* le statut. Et `codes_visibles` : un code n'est montré que tant qu'il sert (celui de
l'expéditeur jusqu'à la récupération, celui du destinataire jusqu'à la livraison), et **jamais** au
chauffeur.

#### `apps/missions/sections.py`

*45 lignes* — Blocs ajoutés par ``missions`` aux fiches d'autres apps.

```python
"""Blocs ajoutés par ``missions`` aux fiches d'autres apps.

- ``hr.sections.DETAIL_CONGE`` : alerte du validateur quand le chauffeur qui demande un
  congé a une mission prévue pendant la période (cahier-des-charges.md:219-221). Seules
  les missions planifiées, affectées ou en cours, dotées d'une date de départ prévue,
  peuvent être détectées.
- ``customers.sections.DETAIL_CLIENT`` : missions récentes du client.
"""

from apps.hr.models import StatutConge

from . import permissions, services
from .models import Mission


def section_alerte_conge(conge, utilisateur):
    if conge.statut not in (StatutConge.DEMANDE, StatutConge.VALIDATION_N1):
        return None
    missions = list(
        services.missions_du_personnel_sur_periode(
            conge.employe_id, conge.date_debut, conge.date_fin
        )
    )
    if not missions:
        return None
    return {
        "template": "missions/_alerte_conge.html",
        "contexte": {
            "missions": missions,
            "peut_ouvrir": utilisateur.role_effectif in permissions.CONSULTATION,
        },
    }


def section_missions_client(client, utilisateur):
    if utilisateur.role_effectif not in permissions.CONSULTATION:
        return None
    missions = Mission.objects.filter(client=client)
    return {
        "template": "missions/_missions_client.html",
        "contexte": {
            "missions": list(missions.order_by("-created_at", "-pk")[:10]),
            "total": missions.count(),
        },
    }
```

Ce fichier **ajoute des blocs à d'autres apps** : l'alerte « ce chauffeur a une mission prévue » sur la fiche
d'un congé (`hr`), et la liste des missions sur la fiche d'un client (`customers`). C'est le registre du
chapitre 2 en action.

## Étape 4 — Administration, démarrage, tests

#### `apps/missions/admin.py`

*21 lignes*

```python
from django.contrib import admin

from .models import Mission


@admin.register(Mission)
class MissionAdmin(admin.ModelAdmin):
    """Lecture seule : le cycle de vie passe par apps/missions/services.py."""

    list_display = ("numero", "client", "vehicule", "chauffeur", "statut", "prix_convenu")
    list_filter = ("statut",)
    search_fields = ("numero", "client__raison_sociale")

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in Mission._meta.fields]

    def has_add_permission(self, request):
        return False

    def get_queryset(self, request):
        return Mission.objects.select_related("client", "vehicule", "chauffeur__personnel")
```

#### `apps/missions/apps.py`

*29 lignes*

```python
from django.apps import AppConfig


class MissionsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.missions'
    label = 'missions'

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer
        from apps.audit.registry import audit_model

        from apps.customers.sections import DETAIL_CLIENT
        from apps.hr.sections import DETAIL_CONGE

        from . import permissions, sections
        from .models import Mission

        # Les codes secrets ne doivent jamais apparaître dans le journal.
        audit_model(
            Mission, module="MISSION", exclure=("code_expediteur", "code_destinataire")
        )
        DETAIL_CONGE.enregistrer(sections.section_alerte_conge)
        DETAIL_CLIENT.enregistrer(sections.section_missions_client)
        enregistrer(
            EntreeMenu(
                "Missions", "missions:liste", "fa-truck-fast", permissions.CONSULTATION, ordre=10
            )
        )
```

Ici `ready()` fait quatre choses : branche l'**audit** sur `Mission` en excluant les codes, enregistre les deux
sections, et déclare l'entrée de menu « Missions ».

#### `apps/missions/tests/factories.py`

*23 lignes*

```python
from decimal import Decimal

import factory

from apps.customers.tests.factories import ClientFactory
from apps.missions.models import Mission


class MissionFactory(factory.django.DjangoModelFactory):
    """Mission Brouillon avec des codes connus (ne passe pas par le service)."""

    class Meta:
        model = Mission

    numero = factory.Sequence(lambda n: f"MIS-2026-{n + 1:04d}")
    client = factory.SubFactory(ClientFactory)
    lieu_chargement = "Abidjan, Port"
    lieu_livraison = "Bouaké"
    nature_marchandise = "Ciment"
    poids_t = Decimal("20.00")
    prix_convenu = Decimal("850000")
    code_expediteur = "ABCD2345"
    code_destinataire = "WXYZ6789"
```

#### `apps/missions/README.md`

*26 lignes* — missions

```markdown
# missions

Rôle : missions de transport et leur cycle de vie — cahier-des-charges.md:127-143.
Audité (module `MISSION`) ; les codes secrets sont exclus du journal.

Entité : `Mission` (numéro `MIS-AAAA-XXXX` via `core.services.prochain_numero`).

Cycle : Brouillon → Planifiée → Affectée → En cours (départ → colis récupéré)
→ Livrée → Clôturée. Services : `creer_mission`, `planifier_mission`,
`affecter_mission` (camion et chauffeur disponibles, non réservés, capacité
respectée), `demarrer_mission` (camion + chauffeur « En mission »),
`confirmer_recuperation` (code expéditeur), `livrer_mission` (code destinataire,
km d'arrivée → compteur du camion, camion + chauffeur libérés),
`cloturer_mission`. `vehicule_a_mission_active` fournit `mission_active` à
`fleet.services.calculer_statut`.

Interface (`views.py`, `templates/missions/`) : liste filtrée et paginée, fiche avec
frise du cycle de vie, création, et une action POST par transition. Droits par rôle
dans `permissions.py` (direction : affectation, suivi, clôture ; chargé clientèle :
création et planification). Les codes ne s'affichent que tant qu'ils servent.

Reste à faire :
- Contrôle des rôles (chargé clientèle, direction, chauffeur) : permissions DRF, étape 6.
- Image QR des deux codes (bibliothèque `qrcode` + Pillow) : étape 6 / mobile.
- Notification « en cours de route (départ) » : signal `mission_demarree`, abonné par `notifications` (fait, étape 5).
- Alerte N1 des congés « chauffeur avec mission sur la période » (via `date_depart_prevue`).
```

#### `apps/missions/tests/test_models.py`

*48 lignes*

```python
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.missions.models import StatutMission

from .factories import MissionFactory

pytestmark = pytest.mark.django_db


def test_mission_affectee_sans_camion_ni_chauffeur_refusee_par_la_base():
    with pytest.raises(IntegrityError), transaction.atomic():
        MissionFactory(statut=StatutMission.AFFECTEE)


def test_brouillon_et_planifiee_n_exigent_pas_de_camion():
    MissionFactory(statut=StatutMission.BROUILLON)
    MissionFactory(statut=StatutMission.PLANIFIEE)


def test_poids_nul_refuse_par_la_base():
    with pytest.raises(IntegrityError), transaction.atomic():
        MissionFactory(poids_t=Decimal("0"))


def test_prix_negatif_refuse_par_la_base():
    with pytest.raises(IntegrityError), transaction.atomic():
        MissionFactory(prix_convenu=Decimal("-1"))


def test_km_arrivee_inferieur_au_depart_refuse_par_la_base():
    with pytest.raises(IntegrityError), transaction.atomic():
        MissionFactory(km_depart=1000, km_arrivee=999)


def test_numero_unique():
    MissionFactory(numero="MIS-2026-0001")

    with pytest.raises(IntegrityError), transaction.atomic():
        MissionFactory(numero="MIS-2026-0001")


def test_est_en_cours_couvre_les_deux_etapes():
    assert MissionFactory.build(statut=StatutMission.EN_COURS_DEPART).est_en_cours
    assert MissionFactory.build(statut=StatutMission.EN_COURS_COLIS_RECUPERE).est_en_cours
    assert not MissionFactory.build(statut=StatutMission.LIVREE).est_en_cours
```

#### `apps/missions/tests/test_permissions.py`

*46 lignes*

```python
from types import SimpleNamespace

import pytest

from apps.accounts.models import Role
from apps.missions import permissions
from apps.missions.models import StatutMission

from .factories import MissionFactory


def _utilisateur(role):
    return SimpleNamespace(role_effectif=role)


@pytest.mark.parametrize(
    ("statut", "role", "attendues"),
    [
        (StatutMission.BROUILLON, Role.CHARGE_CLIENTELE, {"planifier"}),
        (StatutMission.BROUILLON, Role.DIRECTION, {"planifier"}),
        (StatutMission.PLANIFIEE, Role.CHARGE_CLIENTELE, set()),
        (StatutMission.PLANIFIEE, Role.DIRECTION, {"affecter"}),
        (StatutMission.AFFECTEE, Role.DIRECTION, {"demarrer"}),
        (StatutMission.AFFECTEE, Role.CHARGE_CLIENTELE, set()),
        (StatutMission.EN_COURS_DEPART, Role.ADMIN, {"recuperation"}),
        (StatutMission.EN_COURS_COLIS_RECUPERE, Role.ADMIN, {"livraison"}),
        (StatutMission.LIVREE, Role.DIRECTION, {"cloturer"}),
        (StatutMission.LIVREE, Role.CHARGE_CLIENTELE, set()),
        (StatutMission.CLOTUREE, Role.ADMIN, set()),
        (StatutMission.BROUILLON, Role.RH, set()),
    ],
)
def test_actions_disponibles_selon_statut_et_role(statut, role, attendues):
    mission = MissionFactory.build(statut=statut)

    actions = permissions.actions_disponibles(_utilisateur(role), mission)

    assert {nom for nom, permise in actions.items() if permise} == attendues


def test_un_role_sans_droit_sur_les_codes_n_en_voit_aucun():
    mission = MissionFactory.build(statut=StatutMission.BROUILLON)

    codes = permissions.codes_visibles(_utilisateur(Role.PARCAUTO), mission)

    assert codes == {"expediteur": None, "destinataire": None}
```

#### `apps/missions/tests/test_services.py`

*477 lignes* — Cycle de vie d'une mission — cahier-des-charges.md:127-143.

```python
"""Cycle de vie d'une mission — cahier-des-charges.md:127-143."""

import re
from decimal import Decimal

import pytest

from apps.audit.models import AuditLog
from apps.customers.tests.factories import ClientFactory
from apps.drivers.models import StatutChauffeur
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.models import StatutVehicule
from apps.fleet.tests.factories import VehiculeFactory
from apps.missions import services
from apps.missions.exceptions import (
    AffectationImpossible,
    CodeInvalide,
    DemarrageImpossible,
    KilometrageInvalide,
    MissionError,
    TransitionMissionInterdite,
)
from apps.missions.models import Mission, StatutMission

pytestmark = pytest.mark.django_db


def _creer(**surcharges):
    donnees = dict(
        client=ClientFactory(),
        lieu_chargement="Abidjan",
        lieu_livraison="Bouaké",
        nature_marchandise="Ciment",
        poids_t=Decimal("20"),
        prix_convenu=Decimal("850000"),
    )
    donnees.update(surcharges)
    return services.creer_mission(**donnees)


def _planifiee(**surcharges):
    return services.planifier_mission(_creer(**surcharges))


def _affectee(vehicule=None, chauffeur=None, **surcharges):
    vehicule = vehicule or VehiculeFactory()
    chauffeur = chauffeur or ChauffeurFactory()
    return services.affecter_mission(
        _planifiee(**surcharges), vehicule=vehicule, chauffeur=chauffeur
    )


def _en_cours():
    return services.demarrer_mission(_affectee())


def _recuperee():
    mission = _en_cours()
    return services.confirmer_recuperation(mission, code=mission.code_expediteur)


def _livree(km_arrivee=125000):
    mission = _recuperee()
    return services.livrer_mission(
        mission, code=mission.code_destinataire, km_arrivee=km_arrivee
    )


# --- création ---


def test_creation_donne_un_brouillon_numerote_avec_deux_codes():
    mission = _creer()

    assert mission.statut == StatutMission.BROUILLON
    assert re.fullmatch(r"MIS-\d{4}-0001", mission.numero)
    assert mission.vehicule is None and mission.chauffeur is None
    for code in (mission.code_expediteur, mission.code_destinataire):
        assert re.fullmatch(r"[A-HJ-NP-Z2-9]{8}", code)
    assert mission.code_expediteur != mission.code_destinataire


def test_les_numeros_de_mission_sont_consecutifs():
    assert _creer().numero.endswith("-0001")
    assert _creer().numero.endswith("-0002")


def test_creation_refuse_un_poids_nul_ou_negatif():
    with pytest.raises(MissionError):
        _creer(poids_t=Decimal("0"))


def test_creation_refuse_un_prix_negatif():
    with pytest.raises(MissionError):
        _creer(prix_convenu=Decimal("-1"))


def test_les_codes_secrets_ne_sont_pas_ecrits_dans_le_journal_d_audit():
    mission = _creer()
    mission.lieu_livraison = "Korhogo"
    mission.save()

    entrees = AuditLog.objects.filter(entite="Mission", entite_id=mission.pk)
    assert entrees.count() == 2  # création + modification du lieu
    for entree in entrees:
        valeurs = {**(entree.ancienne_valeur or {}), **(entree.nouvelle_valeur or {})}
        assert "code_expediteur" not in valeurs
        assert "code_destinataire" not in valeurs


# --- planification ---


def test_planifier_passe_le_brouillon_a_planifiee():
    assert _planifiee().statut == StatutMission.PLANIFIEE


def test_planifier_refuse_hors_brouillon():
    with pytest.raises(TransitionMissionInterdite):
        services.planifier_mission(_planifiee())


# --- affectation ---


def test_affecter_reserve_camion_et_chauffeur_sans_les_passer_en_mission():
    vehicule, chauffeur = VehiculeFactory(), ChauffeurFactory()

    mission = _affectee(vehicule, chauffeur)

    assert mission.statut == StatutMission.AFFECTEE
    assert (mission.vehicule, mission.chauffeur) == (vehicule, chauffeur)
    vehicule.refresh_from_db()
    assert vehicule.statut == StatutVehicule.DISPONIBLE


def test_affecter_refuse_une_mission_non_planifiee():
    with pytest.raises(TransitionMissionInterdite):
        services.affecter_mission(
            _creer(), vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory()
        )


@pytest.mark.parametrize(
    "statut",
    [
        StatutVehicule.EN_MISSION,
        StatutVehicule.EN_MAINTENANCE,
        StatutVehicule.IMMOBILISE,
        StatutVehicule.HORS_SERVICE,
    ],
)
def test_affecter_refuse_un_camion_non_disponible(statut):
    with pytest.raises(AffectationImpossible, match="camion"):
        services.affecter_mission(
            _planifiee(),
            vehicule=VehiculeFactory(statut=statut),
            chauffeur=ChauffeurFactory(),
        )


@pytest.mark.parametrize(
    "statut",
    [
        StatutChauffeur.EN_MISSION,
        StatutChauffeur.EN_CONGE,
        StatutChauffeur.SUSPENDU,
        StatutChauffeur.INACTIF,
    ],
)
def test_affecter_refuse_un_chauffeur_non_disponible(statut):
    with pytest.raises(AffectationImpossible, match="chauffeur"):
        services.affecter_mission(
            _planifiee(),
            vehicule=VehiculeFactory(),
            chauffeur=ChauffeurFactory(statut=statut),
        )


def test_affecter_refuse_un_camion_deja_reserve_par_une_autre_mission():
    vehicule = VehiculeFactory()
    _affectee(vehicule=vehicule)

    with pytest.raises(AffectationImpossible, match="déjà réservé"):
        services.affecter_mission(
            _planifiee(), vehicule=vehicule, chauffeur=ChauffeurFactory()
        )


def test_affecter_refuse_un_chauffeur_deja_reserve_par_une_autre_mission():
    chauffeur = ChauffeurFactory()
    _affectee(chauffeur=chauffeur)

    with pytest.raises(AffectationImpossible, match="déjà réservé"):
        services.affecter_mission(
            _planifiee(), vehicule=VehiculeFactory(), chauffeur=chauffeur
        )


def test_une_mission_planifiee_ne_reserve_pas_encore_de_camion():
    _planifiee()

    assert Mission.objects.filter(vehicule__isnull=False).count() == 0


def test_affecter_refuse_une_charge_superieure_a_la_capacite_du_camion():
    with pytest.raises(AffectationImpossible, match="capacité"):
        services.affecter_mission(
            _planifiee(poids_t=Decimal("25.01")),
            vehicule=VehiculeFactory(capacite_charge_t=Decimal("25.00")),
            chauffeur=ChauffeurFactory(),
        )


def test_affecter_accepte_une_charge_egale_a_la_capacite():
    mission = _affectee(poids_t=Decimal("25.00"))

    assert mission.statut == StatutMission.AFFECTEE


# --- démarrage ---


def test_demarrer_passe_camion_et_chauffeur_en_mission_et_releve_le_km():
    vehicule = VehiculeFactory(kilometrage=120000)
    chauffeur = ChauffeurFactory()
    mission = services.demarrer_mission(_affectee(vehicule, chauffeur))

    assert mission.statut == StatutMission.EN_COURS_DEPART
    assert mission.km_depart == 120000
    assert mission.date_depart is not None
    vehicule.refresh_from_db()
    chauffeur.refresh_from_db()
    assert vehicule.statut == StatutVehicule.EN_MISSION
    assert chauffeur.statut == StatutChauffeur.EN_MISSION


def test_demarrer_refuse_si_le_camion_est_passe_en_maintenance_entre_temps():
    vehicule = VehiculeFactory()
    mission = _affectee(vehicule=vehicule)
    vehicule.statut = StatutVehicule.EN_MAINTENANCE
    vehicule.save()

    with pytest.raises(DemarrageImpossible, match="camion"):
        services.demarrer_mission(mission)

    mission.refresh_from_db()
    assert mission.statut == StatutMission.AFFECTEE


def test_demarrer_refuse_si_le_chauffeur_est_passe_en_conge_entre_temps():
    chauffeur = ChauffeurFactory()
    mission = _affectee(chauffeur=chauffeur)
    chauffeur.statut = StatutChauffeur.EN_CONGE
    chauffeur.save()

    with pytest.raises(DemarrageImpossible, match="chauffeur"):
        services.demarrer_mission(mission)

    mission.vehicule.refresh_from_db()
    assert mission.vehicule.statut == StatutVehicule.DISPONIBLE


def test_demarrer_refuse_hors_statut_affectee():
    with pytest.raises(TransitionMissionInterdite):
        services.demarrer_mission(_planifiee())


# --- récupération du colis (code expéditeur) ---


def test_confirmer_recuperation_avec_le_bon_code():
    mission = _en_cours()

    services.confirmer_recuperation(mission, code=mission.code_expediteur)

    mission.refresh_from_db()
    assert mission.statut == StatutMission.EN_COURS_COLIS_RECUPERE
    assert mission.date_recuperation is not None


def test_le_code_est_tolere_en_minuscules_et_avec_espaces():
    mission = _en_cours()

    services.confirmer_recuperation(mission, code=f" {mission.code_expediteur.lower()} ")

    assert mission.statut == StatutMission.EN_COURS_COLIS_RECUPERE


def test_confirmer_recuperation_refuse_un_mauvais_code():
    mission = _en_cours()

    with pytest.raises(CodeInvalide):
        services.confirmer_recuperation(mission, code="AAAAAAAA")

    mission.refresh_from_db()
    assert mission.statut == StatutMission.EN_COURS_DEPART


def test_le_code_destinataire_ne_permet_pas_de_recuperer_le_colis():
    mission = _en_cours()

    with pytest.raises(CodeInvalide):
        services.confirmer_recuperation(mission, code=mission.code_destinataire)


def test_confirmer_recuperation_refuse_hors_statut_depart():
    mission = _affectee()

    with pytest.raises(TransitionMissionInterdite):
        services.confirmer_recuperation(mission, code=mission.code_expediteur)


# --- livraison (code destinataire) ---


def test_livrer_libere_camion_et_chauffeur_et_met_a_jour_le_compteur():
    mission = _livree(km_arrivee=125000)

    assert mission.statut == StatutMission.LIVREE
    assert mission.km_arrivee == 125000
    assert mission.date_livraison is not None
    mission.vehicule.refresh_from_db()
    mission.chauffeur.refresh_from_db()
    assert mission.vehicule.statut == StatutVehicule.DISPONIBLE
    assert mission.vehicule.kilometrage == 125000
    assert mission.chauffeur.statut == StatutChauffeur.DISPONIBLE


def test_livrer_refuse_le_code_expediteur():
    mission = _recuperee()

    with pytest.raises(CodeInvalide):
        services.livrer_mission(mission, code=mission.code_expediteur, km_arrivee=125000)

    mission.refresh_from_db()
    assert mission.statut == StatutMission.EN_COURS_COLIS_RECUPERE


def test_livrer_refuse_un_km_arrivee_inferieur_au_km_depart_et_ne_change_rien():
    mission = _recuperee()

    with pytest.raises(KilometrageInvalide, match="départ"):
        services.livrer_mission(
            mission, code=mission.code_destinataire, km_arrivee=mission.km_depart - 1
        )

    mission.refresh_from_db()
    mission.vehicule.refresh_from_db()
    assert mission.statut == StatutMission.EN_COURS_COLIS_RECUPERE
    assert mission.vehicule.statut == StatutVehicule.EN_MISSION


def test_livrer_refuse_un_km_arrivee_inferieur_au_compteur_actuel_du_camion():
    mission = _recuperee()
    mission.vehicule.kilometrage = 200000  # ex. plein saisi entre-temps
    mission.vehicule.save()

    with pytest.raises(KilometrageInvalide, match="compteur"):
        services.livrer_mission(
            mission, code=mission.code_destinataire, km_arrivee=150000
        )


def test_livrer_conserve_le_statut_maintenance_d_un_camion_immobilise_en_route():
    mission = _recuperee()
    mission.vehicule.statut = StatutVehicule.EN_MAINTENANCE
    mission.vehicule.save()

    services.livrer_mission(mission, code=mission.code_destinataire, km_arrivee=125000)

    mission.vehicule.refresh_from_db()
    assert mission.vehicule.statut == StatutVehicule.EN_MAINTENANCE


def test_livrer_conserve_un_statut_chauffeur_suspendu():
    mission = _recuperee()
    mission.chauffeur.statut = StatutChauffeur.SUSPENDU
    mission.chauffeur.save()

    services.livrer_mission(mission, code=mission.code_destinataire, km_arrivee=125000)

    mission.chauffeur.refresh_from_db()
    assert mission.chauffeur.statut == StatutChauffeur.SUSPENDU


def test_livrer_refuse_hors_statut_colis_recupere():
    mission = _en_cours()

    with pytest.raises(TransitionMissionInterdite):
        services.livrer_mission(mission, code=mission.code_destinataire, km_arrivee=125000)


# --- clôture ---


def test_cloturer_une_mission_livree():
    mission = services.cloturer_mission(_livree())

    assert mission.statut == StatutMission.CLOTUREE
    assert mission.date_cloture is not None


def test_cloturer_refuse_une_mission_non_livree():
    with pytest.raises(TransitionMissionInterdite):
        services.cloturer_mission(_recuperee())


# --- mission active (fournit mission_active à fleet.calculer_statut) ---


@pytest.mark.parametrize(
    ("etape", "attendu"),
    [
        (_affectee, True),
        (_en_cours, True),
        (_recuperee, True),
        (_livree, False),
    ],
)
def test_vehicule_a_mission_active_selon_l_etape(etape, attendu):
    mission = etape()

    assert services.vehicule_a_mission_active(mission.vehicule) is attendu
    assert services.chauffeur_a_mission_active(mission.chauffeur) is attendu


def test_un_camion_sans_mission_n_a_pas_de_mission_active():
    _planifiee()

    assert services.vehicule_a_mission_active(VehiculeFactory()) is False


def test_le_cycle_complet_est_audite():
    mission = services.cloturer_mission(_livree())

    entrees = AuditLog.objects.filter(
        entite="Mission", entite_id=mission.pk, action="UPDATE"
    ).order_by("pk")
    statuts = [
        e.nouvelle_valeur["statut"] for e in entrees if "statut" in e.nouvelle_valeur
    ]
    assert statuts == [
        "PLANIFIEE",
        "AFFECTEE",
        "EN_COURS_DEPART",
        "EN_COURS_COLIS_RECUPERE",
        "LIVREE",
        "CLOTUREE",
    ]


# --- lecture : recherche des missions ---


def test_rechercher_missions_sans_critere_retourne_tout():
    _creer(), _planifiee()

    assert services.rechercher_missions().count() == 2


def test_rechercher_missions_combine_statut_et_texte():
    cible = _planifiee(lieu_livraison="Korhogo")
    _planifiee(lieu_livraison="Bouaké")
    _creer(lieu_livraison="Korhogo")

    resultat = services.rechercher_missions(
        statut=StatutMission.PLANIFIEE, recherche="korhogo"
    )

    assert list(resultat) == [cible]


def test_rechercher_missions_ignore_un_statut_inconnu_et_les_espaces():
    _creer()

    assert services.rechercher_missions(statut="???", recherche="   ").count() == 1
```

## Étape 5 — Déclarer l'application et migrer

#### `config/settings/base.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/settings/base.py (avant)
+++ config/settings/base.py (après)
@@ -56,4 +56,5 @@
     "apps.customers",
     "apps.fleet",
+    "apps.missions",
 ]
 
```

```bash
python manage.py makemigrations missions
python manage.py migrate
```

**Résultat attendu :** `Create model Mission`, les contraintes, puis `Applying missions.0001_initial... OK`.

## Vérifier le chapitre

```bash
python manage.py check
```

```bash
python -m pytest apps/missions/tests/test_models.py apps/missions/tests/test_permissions.py apps/missions/tests/test_services.py -q --no-cov
```

**Résultat attendu :** `69 passed` (pour les 3 fichier(s) de tests présentés dans ce chapitre).

Essais dans le shell (avec le client `Cimaf CI` créé au chapitre 7) :

```bash
python manage.py shell -c "from apps.missions.services import generer_code; print(len(generer_code()))"
python manage.py shell -c "from decimal import Decimal; from apps.customers.models import Client; from apps.missions import services as s; m = s.creer_mission(client=Client.objects.get(ncc_nif='CI-0001'), lieu_chargement='Abidjan', lieu_livraison='Bouaké', nature_marchandise='Ciment', poids_t=Decimal('22'), prix_convenu=Decimal('780000')); print(m.numero.startswith('MIS-'), m.statut, len(m.code_expediteur), m.code_expediteur != m.code_destinataire)"
```

**Résultat attendu :** `8`, puis `True BROUILLON 8 True`.

Vérifiez enfin que **le journal d'audit n'a pas gardé les codes** :

```bash
python manage.py shell -c "from apps.audit.models import AuditLog; l = AuditLog.objects.filter(entite='Mission').first(); print(l.action, 'code_expediteur' in l.nouvelle_valeur)"
```

**Résultat attendu :** `CREATE False`.

## Ce qu'il faut retenir

- Un **workflow** se code comme une suite de fonctions, chacune gardée par une vérification de statut.
- Les **secrets** se génèrent avec `secrets` et se comparent avec `compare_digest`.
- Ce qui est **réservé** (camion, chauffeur) se **verrouille** pendant l'opération.
- On peut **exclure des champs** du journal d'audit : le journal ne doit jamais contenir de secret.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 9 : app missions (cycle de vie, codes de confirmation, affectation contrôlée)"
```

---

[← Chapitre 8](08-fleet.md) · [Sommaire](README.md) · [Chapitre 10 →](10-garage.md)
