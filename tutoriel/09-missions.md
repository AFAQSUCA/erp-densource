# Chapitre 9 — Les missions de transport : l'app missions

> 22 fichier(s) dans ce chapitre, 2885 lignes de code.

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

*277 lignes*

```python
from django.conf import settings
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

# Modification autorisée tant que le colis n'est pas encore récupéré : au-delà, le client a déjà le
# camion à quai / la marchandise est en route sur la base de ces informations (règle de séparation des
# tâches, avenant-separation-des-taches.md § R3).
STATUTS_MODIFIABLES = (
    StatutMission.BROUILLON,
    StatutMission.PLANIFIEE,
    StatutMission.AFFECTEE,
    StatutMission.EN_COURS_DEPART,
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
    proforma = models.OneToOneField(
        "billing.Proforma",
        verbose_name=_("devis d'origine"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="mission_creee",
        help_text=_("Devis accepté dont cette mission reprend le trajet et le prix (R6)."),
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
    copilote = models.ForeignKey(
        "drivers.Copilote",
        verbose_name=_("copilote"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="missions",
        help_text=_("Facultatif : certains voyages exigent un assistant au chauffeur."),
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


class TypeFraisMission(models.TextChoices):
    """Nature d'une ligne de prévision de trésorerie — avenant-separation-des-taches.md (R4)."""

    AVANCE_ROUTE = "AVANCE_ROUTE", _("Avance de route")
    DEPENSE_PREVUE = "DEPENSE_PREVUE", _("Dépense prévue")
    IMPREVU = "IMPREVU", _("Imprévu (panne, incident)")
    ENCAISSEMENT = "ENCAISSEMENT", _("Encaissement")


# Sorties d'argent (financent la mission) : à distinguer de l'encaissement, qui n'en est
# qu'un reflet (relié à un Règlement existant, jamais une source de mouvement à part).
TYPES_SORTIE_FRAIS = (
    TypeFraisMission.AVANCE_ROUTE,
    TypeFraisMission.DEPENSE_PREVUE,
    TypeFraisMission.IMPREVU,
)


class StatutFraisMission(models.TextChoices):
    PREVU = "PREVU", _("Prévu")
    CONFIRME = "CONFIRME", _("Confirmé")
    REJETE = "REJETE", _("Rejeté")


class FraisMission(BaseModel):
    """Ligne de prévision de trésorerie d'une mission — avenant-separation-des-taches.md (R4).

    Une avance de route ou une dépense prévue est planifiée par le Parc Auto puis validée par
    la Finance ; un imprévu est déclaré par le chauffeur (mobile, avec preuve) puis validé
    deux fois (Parc Auto, puis Finance) — jamais par celui qui l'a saisi. Un encaissement est le
    simple reflet d'un règlement déjà enregistré (``billing.Reglement``), créé automatiquement,
    directement confirmé : aucune double saisie. Seule une ligne ``CONFIRME`` représente un
    mouvement de trésorerie réel (``finance.receivers`` la transforme alors en dépense pour les
    3 premiers types, cahier-des-charges des dépenses du parc auto compris).
    """

    mission = models.ForeignKey(
        Mission, verbose_name=_("mission"), on_delete=models.PROTECT, related_name="frais"
    )
    type_frais = models.CharField(_("type"), max_length=15, choices=TypeFraisMission.choices)
    montant = models.DecimalField(_("montant (FCFA)"), max_digits=12, decimal_places=2)
    description = models.CharField(_("libellé"), max_length=255, blank=True)
    justificatif = models.FileField(
        _("justificatif"), upload_to="frais_mission/justificatifs/%Y/%m/", blank=True
    )
    statut = models.CharField(
        _("statut"), max_length=10, choices=StatutFraisMission.choices, default=StatutFraisMission.PREVU
    )
    motif_rejet = models.TextField(_("motif du rejet"), blank=True)
    chauffeur = models.ForeignKey(
        "drivers.Chauffeur",
        verbose_name=_("chauffeur"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="frais_mission_declares",
        help_text=_("Renseigné pour un imprévu déclaré depuis l'espace mobile."),
    )
    saisi_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("saisi par"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    valide_parcauto_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("validé par le parc auto"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    date_validation_parcauto = models.DateTimeField(_("validé par le parc auto le"), null=True, blank=True)
    valide_finances_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("validé par la finance"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    date_validation_finances = models.DateTimeField(_("validé par la finance le"), null=True, blank=True)

    class Meta:
        verbose_name = _("frais de mission")
        verbose_name_plural = _("frais de mission")
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["mission", "statut"])]
        constraints = [
            models.CheckConstraint(condition=Q(montant__gt=0), name="frais_mission_montant_positif"),
        ]

    def __str__(self):
        return f"{self.get_type_frais_display()} · {self.mission.numero} ({self.montant})"

    @property
    def est_sortie(self) -> bool:
        return self.type_frais in TYPES_SORTIE_FRAIS

    @property
    def attend_le_parc_auto(self) -> bool:
        """Imprévu encore prévu, pas encore validé par le Parc Auto (première validation)."""
        return (
            self.statut == StatutFraisMission.PREVU
            and self.type_frais == TypeFraisMission.IMPREVU
            and self.valide_parcauto_par_id is None
        )

    @property
    def attend_la_finance(self) -> bool:
        """Prévu, et déjà passé (ou pas concerné) par la première validation du Parc Auto."""
        return self.statut == StatutFraisMission.PREVU and not self.attend_le_parc_auto
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

*30 lignes*

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


class FraisInvalide(MissionError):
    """Montant, type ou justificatif d'un frais de mission invalide, ou ligne déjà traitée."""


class ActionFraisNonAutorisee(MissionError):
    """L'utilisateur n'a pas le droit d'effectuer cette action sur un frais de mission."""
```

#### `apps/missions/services.py`

*518 lignes* — Logique métier des missions — cycle de vie du CDC (cahier-des-charges.md:127-143).

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
from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, QuerySet, Sum
from django.utils import timezone

from apps.core.search import filtrer_par_texte, normaliser
from apps.core.services import prochain_numero, total_par_mois
from apps.customers.models import Client
from apps.drivers import services as drivers_services
from apps.drivers.models import Chauffeur, Copilote, StatutChauffeur
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
from . import signals
from .models import STATUTS_ACTIFS, STATUTS_MODIFIABLES, Mission, StatutMission
from .signals import mission_affectee, mission_demarree

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


def vehicule_a_mission_active(vehicule: Vehicule) -> bool:
    """Vrai si le camion est réservé par une mission affectée ou en cours.

    Fournit ``mission_active`` à ``fleet.services.calculer_statut`` (règle 2,
    cahier-des-charges.md:96-100). Une mission « planifiée » n'a pas encore de
    camion : seule l'affectation réserve un camion.
    """
    return Mission.objects.filter(vehicule=vehicule, statut__in=STATUTS_ACTIFS).exists()


def chauffeur_a_mission_active(chauffeur: Chauffeur) -> bool:
    return Mission.objects.filter(chauffeur=chauffeur, statut__in=STATUTS_ACTIFS).exists()


def copilote_a_mission_active(copilote: Copilote) -> bool:
    return Mission.objects.filter(copilote=copilote, statut__in=STATUTS_ACTIFS).exists()


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
        _verifier_disponibilite(vehicule, chauffeur, poids_t)
        mission.vehicule = vehicule
        mission.chauffeur = chauffeur
        champs += ["vehicule", "chauffeur"]

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


def _verifier_disponibilite(
    vehicule: Vehicule, chauffeur: Chauffeur, poids_t: Decimal, copilote: Copilote | None = None
) -> None:
    """Camion et chauffeur disponibles, non réservés par une autre mission active, et le camion
    capable d'emporter la charge (cahier-des-charges.md:130-131). Partagé par l'affectation et la
    réaffectation (modification d'une mission déjà affectée, cahier-des-charges.md « modification
    mission »). ``copilote`` facultatif : certains voyages exigent un assistant au chauffeur."""
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
    if poids_t > vehicule.capacite_charge_t:
        raise AffectationImpossible(
            f"Charge de {poids_t} t supérieure à la capacité du camion "
            f"({vehicule.capacite_charge_t} t)."
        )
    if copilote is not None:
        if copilote.statut != StatutChauffeur.DISPONIBLE:
            raise AffectationImpossible(
                f"Le copilote {copilote} n'est pas disponible ({copilote.get_statut_display()})."
            )
        if copilote_a_mission_active(copilote):
            raise AffectationImpossible(
                f"Le copilote {copilote} est déjà réservé par une autre mission."
            )


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

*36 lignes* — Événements des missions (souscrits par ``notifications`` et, pour ``frais_mission_confirme``,

```python
"""Événements des missions (souscrits par ``notifications`` et, pour ``frais_mission_confirme``,
par ``finance``).
"""

import logging

from django.dispatch import Signal

logger = logging.getLogger(__name__)

# La mission vient de démarrer : « en cours de route (départ) » (cahier-des-charges.md:136-137).
# Argument : ``mission`` (instance à jour).
mission_demarree = Signal()

# La mission vient de passer « Affectée » : mouvement de caisse probable (R4). Argument : ``mission``.
mission_affectee = Signal()

# Un imprévu vient d'être déclaré par le chauffeur, avec sa preuve. Argument : ``frais``.
frais_mission_declare = Signal()
# Le Parc Auto vient de valider un imprévu (première validation) : la Finance doit confirmer.
# Argument : ``frais``.
frais_mission_valide_parcauto = Signal()
# Une ligne vient d'être rejetée (Parc Auto ou Finance selon l'étape). Argument : ``frais``.
frais_mission_rejete = Signal()
# Une ligne vient d'être confirmée : mouvement de trésorerie réel. Argument : ``frais``. Émis en
# dehors de ``emettre`` (``send`` brut, comme ``garage.or_cloture``) : si la dépense automatique
# ne peut pas s'écrire, la confirmation est annulée plutôt que de laisser une sortie d'argent non
# comptée. Souscrit par ``finance.receivers``.
frais_mission_confirme = Signal()


def emettre(signal: Signal, **arguments) -> None:
    """Émet un signal en journalisant (sans propager) les erreurs des récepteurs."""
    for recepteur, resultat in signal.send_robust(sender=None, **arguments):
        if isinstance(resultat, Exception):
            logger.error("Récepteur %r en erreur", recepteur, exc_info=resultat)
```

#### `apps/missions/permissions.py`

*91 lignes* — Qui peut faire quoi sur une mission.

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

# Retour réunion (avenant) : c'est le Parc Auto qui affecte les missions (camion, chauffeur,
# copilote) une fois que le chargé clientèle les a créées — il doit donc aussi pouvoir les
# consulter pour savoir lesquelles affecter.
CONSULTATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.CHARGE_CLIENTELE, Role.PARCAUTO})
CREATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.CHARGE_CLIENTELE})
PLANIFICATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.CHARGE_CLIENTELE})
AFFECTATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.PARCAUTO})
# Séparation des tâches (avenant-separation-des-taches.md § R3) : modifier une mission déjà créée est
# plus restreint que la créer — le chargé clientèle crée, seules DIRECTION et ADMIN modifient ensuite.
MODIFICATION = frozenset({Role.ADMIN, Role.DIRECTION})
# Le départ peut être lancé depuis le back-office (suivi) ; le chauffeur le fait lui-même depuis le mobile.
SUIVI_TERRAIN = frozenset({Role.ADMIN, Role.DIRECTION})
# Récupération et livraison se confirment par un code secret que seul le chauffeur affecté saisit ou
# scanne (espace mobile : une mission d'un autre chauffeur y est introuvable). Depuis le back-office,
# l'ADMIN peut le faire à sa place (correction, panne du téléphone), et la DIRECTION désormais aussi
# (même largeur que l'ADMIN, retour réunion) : ni le chargé clientèle ni le Parc Auto, qui voient
# pourtant les codes pour les communiquer (VOIR_CODES) ou organiser le transport.
CODES_TERRAIN = frozenset({Role.ADMIN, Role.DIRECTION})
CLOTURE = frozenset({Role.ADMIN, Role.DIRECTION})

# Les codes sont à communiquer à l'expéditeur et au destinataire : ils ne sont visibles que des
# rôles qui gèrent la relation client — délibérément indépendant de CONSULTATION (qui inclut
# désormais le Parc Auto pour l'affectation, sans qu'il ait besoin de voir ces codes).
VOIR_CODES = frozenset({Role.ADMIN, Role.DIRECTION, Role.CHARGE_CLIENTELE})

# Prévision de trésorerie des missions (R4) : le Parc Auto planifie une avance/dépense prévue,
# la Finance valide toujours, le Parc Auto valide en plus en premier pour un imprévu (double
# validation, jamais par celui qui l'a déclaré). Écran séparé de la fiche mission : ni le
# chargé clientèle (qui ne voit déjà pas le prix convenu côté chauffeur) ni la trésorerie n'y
# figurent sur les mêmes rôles que ``CONSULTATION``.
FRAIS_CONSULTATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.PARCAUTO, Role.FINANCES})
FRAIS_SAISIE_PREVISION = frozenset({Role.ADMIN, Role.DIRECTION, Role.PARCAUTO})
FRAIS_VALIDATION_PARCAUTO = frozenset({Role.PARCAUTO})
FRAIS_VALIDATION_FINANCES = frozenset({Role.FINANCES})


def actions_disponibles(utilisateur, mission: Mission) -> dict[str, bool]:
    """Actions proposables à ``utilisateur`` sur ``mission`` (statut + rôle)."""
    role = utilisateur.role_effectif
    statut = mission.statut
    return {
        "planifier": statut == StatutMission.BROUILLON and role in PLANIFICATION,
        "affecter": statut == StatutMission.PLANIFIEE and role in AFFECTATION,
        "demarrer": statut == StatutMission.AFFECTEE and role in SUIVI_TERRAIN,
        "recuperation": statut == StatutMission.EN_COURS_DEPART
        and role in CODES_TERRAIN,
        "livraison": statut == StatutMission.EN_COURS_COLIS_RECUPERE
        and role in CODES_TERRAIN,
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

*42 lignes*

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

        from django.db.models.signals import post_save

        from . import permissions, sections, temps_reel
        from .models import FraisMission, Mission

        # Les codes secrets ne doivent jamais apparaître dans le journal.
        audit_model(
            Mission, module="MISSION", exclure=("code_expediteur", "code_destinataire")
        )
        audit_model(FraisMission, module="FINANCES")
        # Suivi en direct : tout changement d'une mission est diffusé aux écrans ouverts.
        post_save.connect(
            temps_reel.diffuser_apres_enregistrement, sender=Mission, dispatch_uid="missions.suivi_en_direct"
        )
        DETAIL_CONGE.enregistrer(sections.section_alerte_conge)
        DETAIL_CLIENT.enregistrer(sections.section_missions_client)
        enregistrer(
            EntreeMenu(
                "Missions", "missions:liste", "fa-truck-fast", permissions.CONSULTATION, ordre=10
            )
        )
        enregistrer(
            EntreeMenu(
                "Frais de mission", "missions:frais_liste", "fa-money-bill-transfer",
                permissions.FRAIS_CONSULTATION, ordre=63,
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

*137 lignes* — missions

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

### Retour d'une réunion entreprise : Parc Auto affecte, copilote facultatif

C'est le **Parc Auto** qui affecte les missions (camion, chauffeur, et éventuellement copilote) une
fois que le chargé clientèle les a créées et planifiées (`permissions.AFFECTATION` et
`permissions.CONSULTATION` incluent désormais `Role.PARCAUTO`, en plus d'ADMIN et DIRECTION). Le Parc
Auto ne voit pas pour autant les codes secrets : `permissions.VOIR_CODES` reste un ensemble
indépendant de `CONSULTATION`, réservé à ceux qui gèrent la relation client (ADMIN, DIRECTION, chargé
clientèle).

Certains voyages exigent un **copilote** (assistant du chauffeur pendant le trajet, `drivers.Copilote`
— une fiche distincte du chauffeur, jamais un chauffeur principal). Aucune règle automatique : c'est
une **décision humaine du Parc Auto au moment de l'affectation**, sur le même écran que le camion et
le chauffeur (`AffectationForm.copilote`, facultatif). `affecter_mission` vérifie sa disponibilité
comme pour le chauffeur (non déjà réservé par une autre mission active) ; `demarrer_mission` et
`livrer_mission` le mettent « En mission » / le libèrent en parallèle du chauffeur s'il est affecté.

### Saisie des codes : le chauffeur affecté (ou l'ADMIN / la DIRECTION)

Les codes de récupération et de livraison ne se confirment que par le **chauffeur affecté** (saisie ou
scan du QR depuis l'espace mobile, où une mission d'un autre chauffeur est introuvable) — ou par
l'**ADMIN** ou la **DIRECTION** (même largeur que l'ADMIN, retour réunion), en correction depuis le
back-office (`permissions.CODES_TERRAIN`). Le chargé clientèle et le Parc Auto voient (pour le
premier) ou n'ont pas accès (pour le second) aux codes, mais ne peuvent pas les saisir ; le
« départ », lui, reste ouvert à l'ADMIN et à la DIRECTION (aucun code n'est en jeu).

### Modification (`modifier_mission`, séparation des tâches — avenant-separation-des-taches.md § R3)

Tant que la mission n'a pas dépassé « Colis récupéré » (`STATUTS_MODIFIABLES`), **DIRECTION et ADMIN
seulement** (`permissions.MODIFICATION` — plus restreint que `CREATION`, qui inclut aussi le chargé
clientèle) peuvent modifier lieux, marchandise, poids, prix, date de départ prévue, et — une fois la
mission déjà **Affectée** seulement — réaffecter camion/chauffeur (revérifie leur disponibilité comme à
l'affectation, `_verifier_disponibilite` partagée avec `affecter_mission`). Changer un lieu régénère les
deux codes secrets (donc leurs QR, rendus à la volée). Le client n'est pas modifiable : c'est l'identité
de la mission. Réaffecter camion/chauffeur une fois le départ effectué (`EN_COURS_DEPART`) n'est pas pris
en charge : le camion est physiquement engagé, ça relève d'un signalement d'incident plutôt que d'une
simple modification. Tracé gratuitement par l'audit déjà branché sur `Mission`.

### PDF des codes (`documents.py`, ReportLab)

`/missions/<id>/codes.pdf` (bouton « Télécharger le PDF des codes » de la fiche, proposé dès la création) :
une page par partie, avec l'en-tête de l'entreprise et son logo (`ENTREPRISE_NOM`, `ENTREPRISE_ADRESSE`,
`ENTREPRISE_NCC`) — l'**expéditeur** (code de récupération + QR, à remettre au chauffeur au chargement) et le
**destinataire** (code de réception + QR, à transmettre à la personne qui réceptionnera la marchandise, qui
le remettra au chauffeur). Chaque page ne contient que le code de sa partie ; à envoyer à chacun
séparément. Mêmes règles que l'affichage des codes (rôles qui les voient, et seulement tant qu'ils sont
utiles) ; produit à la demande, jamais stocké ni mis en cache. L'envoi reste manuel : la mission ne
mémorise pas les coordonnées de l'expéditeur ni du destinataire.

### Suivi en direct (WebSocket : `temps_reel.py`, `consumers.py`, `routing.py`, `static/js/suivi-missions.js`)

Toute mission enregistrée (création, planification, affectation, départ, récupération, livraison, clôture —
y compris la saisie du code par le chauffeur depuis son téléphone) est diffusée, une fois la transaction
validée, aux fiches et à la liste des missions ouvertes : elles se mettent à jour seules, sans recharger la
page, avec un voyant « En direct » (et une annonce pour les lecteurs d'écran). Le message ne contient que
« quelle mission, quel statut » — jamais un code ; les données sont relues par une requête ordinaire, avec
les droits de la personne. La WebSocket exige les mêmes garanties que les pages : session, rôle qui consulte
les missions, et double authentification vérifiée (l'ADMIN et la DIRECTION), l'origine étant contrôlée
(`AllowedHostsOriginValidator`). Si Redis est indisponible, la diffusion échoue en silence (journalisée) : le
métier n'est jamais bloqué. Une saisie en cours n'est jamais écrasée : un bandeau propose d'actualiser.

Architecture : Gunicorn sert les pages ; le conteneur `realtime` (Daphne, `config/asgi.py`) tient les
WebSocket ; Redis (`channels-redis`) relie les deux. En développement, `runserver` (Daphne) fait tout, avec une
couche de messages en mémoire — un changement fait depuis un autre processus (`manage.py shell`) n'y est donc
pas diffusé, contrairement à un changement fait par le serveur lui-même.

### Suggestions de lieux

Le formulaire de création propose (liste `datalist`) les lieux de chargement et de livraison déjà saisis,
les plus fréquents d'abord, dès les premières lettres (`services.lieux_deja_utilises`) ; un lieu écrit avec
une autre casse ou sans accent ne compte qu'une fois. La saisie libre reste possible.

### Mission créée depuis un devis accepté (R6)

`Mission.proforma` (`OneToOneField` vers `billing.Proforma`, PROTECT) garantit **1 devis = 1
mission** au niveau base. `billing.services.convertir_en_mission(proforma)` (pas `missions` :
le graphe de dépendance des apps, architecture.md:95-163, interdit à `missions` de dépendre de
`billing` — l'inverse est permis, `billing` appelle donc `missions.services.creer_mission`)
recopie tel quel le trajet, la marchandise, le poids et le **prix HT** du devis (la facture
recalculera la TVA plus tard, avec le taux du client en vigueur ce jour-là) ; le devis passe à
`CONVERTIE`. Déclenché sur `POST /facturation/devis/<id>/creer-mission/`, réservé au rôle
`missions.permissions.CREATION`. Refusé si le devis n'est pas `ACCEPTEE` (y compris s'il l'a
déjà été converti).

### Prévision de trésorerie des missions (`terrain.py`, R4 — avenant-separation-des-taches.md)

Séparation des tâches : celui qui déclare ou planifie un frais n'est jamais celui qui le valide. Modèle
`FraisMission` (`mission`, `type_frais`, `montant`, `justificatif`, `statut`) :

- **Avance de route** / **dépense prévue** : planifiée par le **Parc Auto** (`planifier_frais`,
  écran `/missions/<id>/frais/`), confirmée par la seule **Finance** (`valider_finances`).
- **Imprévu** (panne, incident) : déclaré par le **chauffeur** depuis l'espace mobile (photo ou facture
  obligatoire) puis validé deux fois — le **Parc Auto** d'abord (`valider_parcauto`), la **Finance**
  ensuite (`valider_finances`) — jamais par celui qui l'a déclaré ni en une seule fois.
- **Encaissement** : reflet automatique d'un règlement déjà enregistré pour la facture de la mission
  (`billing.signals.reglement_enregistre`, souscrit par `finance`), créé directement confirmé : aucune
  double saisie.

Seule une ligne **confirmée** représente un mouvement de trésorerie réel : `finance.receivers` la
transforme alors en `billing.Depense` (catégorie « Frais de mission »), sauf l'encaissement qui n'en
crée pas (déjà compté via son règlement). `missions` ignore `billing` et `finance` — c'est `finance` qui
relie les trois signaux (`frais_mission_confirme`, `reglement_enregistre`), pour respecter le graphe de
dépendance des apps (architecture.md:95-163).

Signal `mission_affectee` (Affectée = mouvement de caisse probable) prévient la Finance. Écran séparé de
la fiche mission (`permissions.FRAIS_CONSULTATION` : ADMIN, DIRECTION, PARCAUTO, FINANCES — pas le chargé
clientèle, qui ne voit déjà pas le prix convenu côté chauffeur). Rapport de mission imprimable
(`/missions/<id>/frais/imprimer/`) : lignes et totaux (sorties confirmées, encaissé, solde).

**Limite connue** : la modification d'une mission (R3) ne verrouille pas encore son prix une fois des
frais confirmés dessus, ni une fois créée depuis un devis accepté (R6).

Reste à faire :
- Notification « en cours de route (départ) » : signal `mission_demarree`, abonné par `notifications` (fait, étape 5).
- Alerte N1 des congés « chauffeur avec mission sur la période » (via `date_depart_prevue`).

Rapport imprimable des missions (bouton « Imprimer » sur la liste, mêmes filtres) : voir `apps/core/README.md` (`ImpressionListeMixin`).
```

#### `apps/missions/terrain.py`

*196 lignes* — Prévision de trésorerie des missions (R4) : avances, dépenses prévues et imprévus.

```python
"""Prévision de trésorerie des missions (R4) : avances, dépenses prévues et imprévus.

Réf. avenant-separation-des-taches.md (R4). Séparation des tâches : celui qui déclare ou planifie
un frais n'est jamais celui qui le valide. Une avance de route ou une dépense prévue est
planifiée par le Parc Auto puis validée par la Finance seule ; un imprévu est déclaré par le
chauffeur (mobile, avec preuve) puis validé deux fois — Parc Auto d'abord, Finance ensuite. Un
encaissement est un simple reflet d'un règlement déjà enregistré, créé directement confirmé
(``finance.receivers``, aucune double saisie).
"""

from __future__ import annotations

from decimal import Decimal

from django.core.files.base import File
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from apps.drivers.models import Chauffeur

from . import permissions, signals
from .exceptions import ActionFraisNonAutorisee, FraisInvalide
from .models import FraisMission, Mission, StatutFraisMission, TypeFraisMission

TYPES_PLANIFIABLES = (TypeFraisMission.AVANCE_ROUTE, TypeFraisMission.DEPENSE_PREVUE)


def _recharger(objet):
    type(objet)._base_manager.select_for_update().filter(pk=objet.pk).first()
    objet.refresh_from_db()
    return objet


def _exiger_role(acteur, roles, action: str) -> None:
    """Contrôle strict (``acteur.role``) : ni l'ADMIN ni un superutilisateur ne valident un
    frais de mission à la place du Parc Auto ou de la Finance (même logique que la facturation)."""
    if acteur.role not in roles:
        raise ActionFraisNonAutorisee(f"Vous n'avez pas le droit de {action}.")


def frais_queryset(mission: Mission) -> QuerySet[FraisMission]:
    return mission.frais.select_related(
        "chauffeur__personnel", "saisi_par", "valide_parcauto_par", "valide_finances_par"
    )


def frais_a_traiter() -> QuerySet[FraisMission]:
    """Lignes ``PREVU`` toutes missions confondues (tableau de bord Parc Auto / Finance)."""
    return (
        FraisMission.objects.filter(statut=StatutFraisMission.PREVU)
        .select_related("mission", "chauffeur__personnel", "saisi_par")
        .order_by("created_at", "pk")
    )


def totaux(mission: Mission) -> dict:
    """Sorties et encaissement confirmés, et nombre de lignes encore en attente."""
    lignes = list(frais_queryset(mission))
    sorties = sum(
        (f.montant for f in lignes if f.est_sortie and f.statut == StatutFraisMission.CONFIRME),
        Decimal("0"),
    )
    encaisse = sum(
        (
            f.montant
            for f in lignes
            if f.type_frais == TypeFraisMission.ENCAISSEMENT and f.statut == StatutFraisMission.CONFIRME
        ),
        Decimal("0"),
    )
    en_attente = sum(1 for f in lignes if f.statut == StatutFraisMission.PREVU)
    return {"sorties": sorties, "encaisse": encaisse, "solde": encaisse - sorties, "en_attente": en_attente}


# --- déclaration (chauffeur) et planification (Parc Auto) ---


@transaction.atomic
def declarer_imprevu(
    mission: Mission, chauffeur: Chauffeur, *, montant: Decimal, justificatif: File, description: str = ""
) -> FraisMission:
    """Le chauffeur déclare un imprévu (panne, incident) sur sa mission, avec une preuve.

    Jamais validé par lui-même : Parc Auto puis Finance confirment (double validation).
    """
    if mission.chauffeur_id != chauffeur.pk:
        raise ActionFraisNonAutorisee("Cette mission n'est pas affectée à ce chauffeur.")
    montant = Decimal(montant)
    if montant <= 0:
        raise FraisInvalide("Le montant doit être strictement positif.")
    if not justificatif:
        raise FraisInvalide("Une preuve (photo, facture) est obligatoire pour un imprévu.")
    frais = FraisMission.objects.create(
        mission=mission,
        type_frais=TypeFraisMission.IMPREVU,
        montant=montant,
        description=description.strip(),
        justificatif=justificatif,
        chauffeur=chauffeur,
    )
    signals.emettre(signals.frais_mission_declare, frais=frais)
    return frais


@transaction.atomic
def planifier_frais(
    mission: Mission, acteur, *, type_frais: str, montant: Decimal, description: str = ""
) -> FraisMission:
    """Le Parc Auto planifie une avance de route ou une dépense prévue avant le départ."""
    _exiger_role(acteur, permissions.FRAIS_SAISIE_PREVISION, "planifier un frais de mission")
    if type_frais not in TYPES_PLANIFIABLES:
        raise FraisInvalide("Seules une avance de route ou une dépense prévue se planifient ainsi.")
    montant = Decimal(montant)
    if montant <= 0:
        raise FraisInvalide("Le montant doit être strictement positif.")
    return FraisMission.objects.create(
        mission=mission,
        type_frais=type_frais,
        montant=montant,
        description=description.strip(),
        saisi_par=acteur,
    )


# --- validation ---


@transaction.atomic
def valider_parcauto(frais: FraisMission, acteur) -> FraisMission:
    """Première validation d'un imprévu par le Parc Auto : la Finance confirme ensuite."""
    _exiger_role(acteur, permissions.FRAIS_VALIDATION_PARCAUTO, "valider un frais de mission")
    _recharger(frais)
    if frais.type_frais != TypeFraisMission.IMPREVU:
        raise FraisInvalide("Seul un imprévu passe par une validation du Parc Auto.")
    if frais.statut != StatutFraisMission.PREVU:
        raise FraisInvalide(f"Cette ligne est « {frais.get_statut_display()} », déjà traitée.")
    frais.valide_parcauto_par = acteur
    frais.date_validation_parcauto = timezone.now()
    frais.save(update_fields=["valide_parcauto_par", "date_validation_parcauto", "updated_at"])
    signals.emettre(signals.frais_mission_valide_parcauto, frais=frais)
    return frais


@transaction.atomic
def valider_finances(frais: FraisMission, acteur) -> FraisMission:
    """La Finance confirme la ligne : avance/dépense prévue directement, imprévu seulement une
    fois validé par le Parc Auto (seconde validation)."""
    _exiger_role(acteur, permissions.FRAIS_VALIDATION_FINANCES, "valider un frais de mission")
    _recharger(frais)
    if frais.statut != StatutFraisMission.PREVU:
        raise FraisInvalide(f"Cette ligne est « {frais.get_statut_display()} », déjà traitée.")
    if frais.type_frais == TypeFraisMission.IMPREVU and frais.valide_parcauto_par_id is None:
        raise FraisInvalide("Cet imprévu n'a pas encore été validé par le Parc Auto.")
    frais.valide_finances_par = acteur
    frais.date_validation_finances = timezone.now()
    frais.statut = StatutFraisMission.CONFIRME
    frais.save()
    # Envoi non protégé (comme garage.or_cloture) : si la dépense automatique ne peut pas
    # s'écrire, la confirmation est annulée plutôt que de laisser une sortie d'argent non comptée.
    for _recepteur, resultat in signals.frais_mission_confirme.send(sender=FraisMission, frais=frais):
        if isinstance(resultat, Exception):
            raise resultat
    return frais


@transaction.atomic
def rejeter(frais: FraisMission, acteur, *, motif: str) -> FraisMission:
    """Rejette une ligne encore ``PREVU`` : le Parc Auto pour un imprévu pas encore transmis à la
    Finance, la Finance dans tous les autres cas."""
    _recharger(frais)
    if frais.statut != StatutFraisMission.PREVU:
        raise FraisInvalide(f"Cette ligne est « {frais.get_statut_display()} », déjà traitée.")
    attend_le_parcauto = frais.type_frais == TypeFraisMission.IMPREVU and frais.valide_parcauto_par_id is None
    roles = permissions.FRAIS_VALIDATION_PARCAUTO if attend_le_parcauto else permissions.FRAIS_VALIDATION_FINANCES
    _exiger_role(acteur, roles, "rejeter un frais de mission")
    if not motif.strip():
        raise FraisInvalide("Le motif du rejet est obligatoire.")
    frais.statut = StatutFraisMission.REJETE
    frais.motif_rejet = motif.strip()
    frais.save(update_fields=["statut", "motif_rejet", "updated_at"])
    signals.emettre(signals.frais_mission_rejete, frais=frais)
    return frais


def creer_encaissement(mission: Mission, *, montant: Decimal, libelle: str, saisi_par=None) -> FraisMission:
    """Reflet automatique d'un règlement reçu pour la facture de cette mission : aucune double
    saisie, directement confirmé (appelé par ``finance.receivers``)."""
    return FraisMission.objects.create(
        mission=mission,
        type_frais=TypeFraisMission.ENCAISSEMENT,
        montant=montant,
        description=libelle,
        statut=StatutFraisMission.CONFIRME,
        saisi_par=saisi_par,
    )
```

#### `apps/missions/consumers.py`

*51 lignes* — WebSocket du suivi des missions : pousse au navigateur chaque changement d'une mission.

```python
"""WebSocket du suivi des missions : pousse au navigateur chaque changement d'une mission.

Seuls les rôles qui consultent les missions (``permissions.CONSULTATION``) peuvent se connecter, avec
les mêmes garanties que les pages HTTP : session authentifiée, compte actif, et double authentification
vérifiée pour l'ADMIN et la DIRECTION (le middleware MFA n'agit que sur les requêtes HTTP : sans ce
contrôle, une session « mot de passe seul » pourrait suivre les missions par WebSocket). Le chauffeur
n'a pas accès à ces écrans, donc pas non plus à ce flux.

L'origine de la page est contrôlée en amont (``config/asgi.py``, AllowedHostsOriginValidator).
"""

from __future__ import annotations

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.accounts import mfa

from . import permissions
from .temps_reel import GROUPE_SUIVI

CODE_REFUSE = 4403  # « interdit », dans la plage réservée aux applications


def est_autorise(scope) -> bool:
    utilisateur = scope.get("user")
    if utilisateur is None or not utilisateur.is_authenticated or not utilisateur.is_active:
        return False
    if utilisateur.role_effectif not in permissions.CONSULTATION:
        return False
    session = scope.get("session")
    if mfa.mfa_requise(utilisateur) and not (session is not None and session.get(mfa.CLE_SESSION)):
        return False
    return True


class MissionSuiviConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        if not est_autorise(self.scope):
            await self.close(code=CODE_REFUSE)  # avant accept() : la connexion est refusée (HTTP 403)
            return
        await self.channel_layer.group_add(GROUPE_SUIVI, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(GROUPE_SUIVI, self.channel_name)

    async def receive_json(self, content, **kwargs):
        """Le navigateur n'envoie rien d'utile : ce flux est en sens unique."""

    async def mission_maj(self, evenement):
        await self.send_json(evenement["donnees"])
```

#### `apps/missions/documents.py`

*184 lignes* — PDF des codes d'une mission, à transmettre à l'expéditeur et au destinataire.

```python
"""PDF des codes d'une mission, à transmettre à l'expéditeur et au destinataire.

Une page par partie (chacune ne voit que son code) : en-tête de l'entreprise avec son logo, rappel de
la mission, le code en grand et son code QR, puis la consigne à suivre. Le chauffeur saisit ou scanne
ce code pour confirmer la récupération (expéditeur) ou la livraison (destinataire) : c'est le seul
secret de la mission, le document doit donc partir vers la bonne personne.

ReportLab (cahier-des-charges.md:252 « PDF/QR : WeasyPrint / ReportLab »), choisi pour sa simplicité
de déploiement : aucune bibliothèque système à ajouter à l'image Docker, contrairement à WeasyPrint.
Le document n'est jamais stocké : il est produit à la demande, tant que les codes sont utiles.
"""

from __future__ import annotations

import io

import qrcode
from django.conf import settings
from django.contrib.staticfiles import finders
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

MARQUE = colors.HexColor("#8B0319")
ACCENT = colors.HexColor("#F28A14")
GRIS = colors.HexColor("#475569")
MARGE = 20 * mm
LARGEUR, HAUTEUR = A4

STYLE_TEXTE = ParagraphStyle("texte", fontName="Helvetica", fontSize=11, leading=16, textColor=colors.HexColor("#0f172a"))
STYLE_ALERTE = ParagraphStyle(
    "alerte", parent=STYLE_TEXTE, fontSize=10, leading=14, textColor=colors.HexColor("#78350f")
)


def _pages(mission, codes: dict[str, str | None], entreprise: str) -> list[dict]:
    """Les pages à produire : celles dont le code est encore utile (``codes`` vient de
    ``permissions.codes_visibles``)."""
    pages = []
    if codes.get("expediteur"):
        pages.append({
            "titre": "Code de récupération du colis",
            "destinataire_du_document": "À l'attention de l'expéditeur",
            "code": codes["expediteur"],
            "legende": "Code de l'expéditeur",
            "consignes": (
                f"Un camion {entreprise} viendra charger la marchandise décrite ci-dessus. Au moment "
                "du chargement, remettez le code ci-dessous au chauffeur, ou faites-lui scanner le "
                "code QR : c'est ce qui confirme que le colis a bien été récupéré."
            ),
            "alerte": "Confidentiel : ne communiquez ce code qu'au chauffeur présent au chargement. "
            "Il ne sert qu'une fois.",
        })
    if codes.get("destinataire"):
        pages.append({
            "titre": "Code de réception de la marchandise",
            "destinataire_du_document": "À l'attention du destinataire",
            "code": codes["destinataire"],
            "legende": "Code de réception",
            "consignes": (
                f"Un camion {entreprise} vous livrera la marchandise décrite ci-dessus. Merci de "
                "transmettre le code de réception ci-dessous à la personne qui réceptionnera la "
                "marchandise sur votre site (votre réceptionnaire). À l'arrivée du camion, elle le "
                "remettra au chauffeur, ou lui fera scanner le code QR : c'est ce qui confirme la livraison."
            ),
            "alerte": "Sans ce code, la livraison ne peut pas être confirmée. Ne le communiquez qu'à la "
            "personne chargée de la réception.",
        })
    return pages


def _entete(c: canvas.Canvas, entreprise: str) -> float:
    """En-tête : logo, raison sociale, adresse et NCC, filet aux couleurs de la marque. Renvoie l'ordonnée
    sous l'en-tête."""
    haut = HAUTEUR - MARGE
    logo = finders.find("img/logo-emblem.jpg")
    if logo:
        c.drawImage(logo, MARGE, haut - 22 * mm, width=22 * mm, height=22 * mm, preserveAspectRatio=True, mask="auto")
    x = MARGE + 28 * mm
    c.setFillColor(MARQUE)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(x, haut - 9 * mm, entreprise)
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 9)
    ligne = haut - 15 * mm
    for texte in (settings.ENTREPRISE_ADRESSE, f"N° CC : {settings.ENTREPRISE_NCC}" if settings.ENTREPRISE_NCC else ""):
        if texte:
            c.drawString(x, ligne, texte)
            ligne -= 4.5 * mm
    c.setStrokeColor(ACCENT)
    c.setLineWidth(2)
    c.line(MARGE, haut - 26 * mm, LARGEUR - MARGE, haut - 26 * mm)
    return haut - 34 * mm


def _paragraphe(c: canvas.Canvas, texte: str, style: ParagraphStyle, y: float) -> float:
    paragraphe = Paragraph(texte, style)
    _, hauteur = paragraphe.wrap(LARGEUR - 2 * MARGE, HAUTEUR)
    paragraphe.drawOn(c, MARGE, y - hauteur)
    return y - hauteur


def _rappel_mission(c: canvas.Canvas, mission, y: float) -> float:
    lignes = [
        ("Mission", mission.numero),
        ("Client", str(mission.client)),
        ("Marchandise", f"{mission.nature_marchandise} — {mission.poids_t.normalize():f} t"),
        ("Chargement", mission.lieu_chargement),
        ("Livraison", mission.lieu_livraison),
    ]
    if mission.date_depart_prevue:
        lignes.append(("Départ prévu", mission.date_depart_prevue.strftime("%d/%m/%Y")))
    for libelle, valeur in lignes:
        c.setFillColor(GRIS)
        c.setFont("Helvetica", 10)
        c.drawString(MARGE, y, libelle)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.setFont("Helvetica-Bold", 10)
        c.drawString(MARGE + 32 * mm, y, valeur)
        y -= 6 * mm
    return y


def _code_et_qr(c: canvas.Canvas, code: str, legende: str, y: float) -> float:
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 10)
    c.drawCentredString(LARGEUR / 2, y, legende.upper())
    y -= 4 * mm
    haut_cadre = 24 * mm
    c.setStrokeColor(MARQUE)
    c.setFillColor(colors.HexColor("#fff7ed"))
    c.setLineWidth(1.5)
    c.roundRect(MARGE + 20 * mm, y - haut_cadre, LARGEUR - 2 * MARGE - 40 * mm, haut_cadre, 4 * mm, stroke=1, fill=1)
    c.setFillColor(colors.HexColor("#0f172a"))
    c.setFont("Courier-Bold", 38)
    c.drawCentredString(LARGEUR / 2, y - 16 * mm, " ".join(code))  # espacé : se dicte plus facilement
    y -= haut_cadre + 8 * mm

    image = io.BytesIO()
    qrcode.make(code, box_size=10, border=2).save(image, format="PNG")
    image.seek(0)
    cote = 55 * mm
    c.drawImage(ImageReader(image), (LARGEUR - cote) / 2, y - cote, width=cote, height=cote)
    return y - cote - 8 * mm


def generer_pdf_codes(mission, codes: dict[str, str | None]) -> bytes:
    """PDF des codes encore utiles de ``mission`` (une page par code). Vide (aucun code) : ``ValueError``."""
    entreprise = settings.ENTREPRISE_NOM
    pages = _pages(mission, codes, entreprise)
    if not pages:
        raise ValueError("Aucun code à communiquer pour cette mission.")

    tampon = io.BytesIO()
    c = canvas.Canvas(tampon, pagesize=A4, pageCompression=0)
    c.setTitle(f"Codes de la mission {mission.numero}")
    c.setAuthor(entreprise)
    edite_le = timezone.localtime().strftime("%d/%m/%Y à %H:%M")
    for page in pages:
        y = _entete(c, entreprise)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.setFont("Helvetica-Bold", 17)
        c.drawString(MARGE, y, page["titre"])
        y -= 6 * mm
        c.setFillColor(GRIS)
        c.setFont("Helvetica-Oblique", 11)
        c.drawString(MARGE, y, page["destinataire_du_document"])
        y -= 10 * mm
        y = _rappel_mission(c, mission, y)
        y -= 4 * mm
        y = _paragraphe(c, page["consignes"], STYLE_TEXTE, y) - 8 * mm
        y = _code_et_qr(c, page["code"], page["legende"], y)
        _paragraphe(c, page["alerte"], STYLE_ALERTE, y)
        c.setFillColor(GRIS)
        c.setFont("Helvetica", 8)
        c.drawString(MARGE, 12 * mm, f"Document confidentiel — mission {mission.numero} — édité le {edite_le}")
        c.showPage()
    c.save()
    return tampon.getvalue()
```

#### `apps/missions/routing.py`

*7 lignes*

```python
from django.urls import path

from .consumers import MissionSuiviConsumer

websocket_urlpatterns = [
    path("ws/missions/suivi/", MissionSuiviConsumer.as_asgi()),
]
```

#### `apps/missions/temps_reel.py`

*51 lignes* — Suivi des missions en direct : diffusion d'un changement à tous les écrans ouverts.

```python
"""Suivi des missions en direct : diffusion d'un changement à tous les écrans ouverts.

Chaque enregistrement d'une mission (création, planification, affectation, départ, récupération,
livraison, clôture — y compris la saisie du code par le chauffeur depuis son téléphone) envoie un court
message au groupe ``GROUPE_SUIVI`` de la couche de messages (Redis en production). Les consommateurs
WebSocket (``consumers.MissionSuiviConsumer``), connectés depuis la fiche et la liste des missions, le
relaient au navigateur, qui rafraîchit l'écran (``static/js/suivi-missions.js``).

Le message ne contient jamais de code secret : seulement de quoi savoir quelle mission a changé.
La diffusion part **après** la validation de la transaction (l'écran qui se rafraîchit relit alors
l'état définitif) et ne fait jamais échouer l'opération métier : si Redis est indisponible, le chauffeur
confirme quand même sa livraison, l'écran du bureau se mettra à jour à son prochain rafraîchissement.
"""

from __future__ import annotations

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

logger = logging.getLogger(__name__)

GROUPE_SUIVI = "suivi_missions"


def message_mission(mission) -> dict:
    return {
        "id": mission.pk,
        "numero": mission.numero,
        "statut": mission.statut,
        "statut_libelle": str(mission.get_statut_display()),
    }


def diffuser(mission) -> None:
    """Prévient les écrans ouverts que ``mission`` a changé (à appeler une fois la transaction validée)."""
    try:
        couche = get_channel_layer()
        if couche is not None:
            async_to_sync(couche.group_send)(
                GROUPE_SUIVI, {"type": "mission.maj", "donnees": message_mission(mission)}
            )
    except Exception:  # noqa: BLE001 - le temps réel est un confort, jamais une condition du métier
        logger.exception("Diffusion du suivi de la mission %s impossible", getattr(mission, "pk", "?"))


def diffuser_apres_enregistrement(sender, instance, **kwargs) -> None:
    """Récepteur de ``post_save`` (branché dans ``MissionsConfig.ready``)."""
    transaction.on_commit(lambda: diffuser(instance))
```

#### `apps/missions/tests/test_frais_mission.py`

*305 lignes* — Prévision de trésorerie des missions (R4) : déclaration, planification, double validation.

```python
"""Prévision de trésorerie des missions (R4) : déclaration, planification, double validation."""

from decimal import Decimal
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.hr.tests.factories import PersonnelFactory
from apps.missions import terrain as services
from apps.missions.exceptions import ActionFraisNonAutorisee, FraisInvalide
from apps.missions.models import StatutFraisMission, StatutMission, TypeFraisMission
from apps.missions.signals import frais_mission_confirme

from .factories import MissionFactory

pytestmark = pytest.mark.django_db


def _preuve() -> SimpleUploadedFile:
    return SimpleUploadedFile("preuve.jpg", BytesIO(b"donnees").read(), content_type="image/jpeg")


def _chauffeur():
    return ChauffeurFactory(personnel=PersonnelFactory(utilisateur=UserFactory(role=Role.CHAUFFEUR)))


def _mission_affectee(chauffeur=None):
    chauffeur = chauffeur or _chauffeur()
    return MissionFactory(
        statut=StatutMission.AFFECTEE, vehicule=VehiculeFactory(), chauffeur=chauffeur
    )


def _parcauto():
    return UserFactory(role=Role.PARCAUTO)


def _finances():
    return UserFactory(role=Role.FINANCES)


# --- déclaration d'un imprévu (chauffeur) ---


def test_le_chauffeur_declare_un_imprevu_avec_preuve():
    chauffeur = _chauffeur()
    mission = _mission_affectee(chauffeur)

    frais = services.declarer_imprevu(
        mission, chauffeur, montant=Decimal("15000"), justificatif=_preuve(), description="Panne moteur"
    )

    assert frais.type_frais == TypeFraisMission.IMPREVU
    assert frais.statut == StatutFraisMission.PREVU
    assert frais.chauffeur == chauffeur
    assert frais.justificatif


def test_un_chauffeur_ne_declare_pas_sur_la_mission_d_un_autre():
    mission = _mission_affectee()
    autre_chauffeur = _chauffeur()

    with pytest.raises(ActionFraisNonAutorisee):
        services.declarer_imprevu(mission, autre_chauffeur, montant=Decimal("1000"), justificatif=_preuve())


def test_un_imprevu_sans_preuve_est_refuse():
    chauffeur = _chauffeur()
    mission = _mission_affectee(chauffeur)

    with pytest.raises(FraisInvalide, match="preuve"):
        services.declarer_imprevu(mission, chauffeur, montant=Decimal("1000"), justificatif=None)


def test_un_montant_negatif_ou_nul_est_refuse():
    chauffeur = _chauffeur()
    mission = _mission_affectee(chauffeur)

    with pytest.raises(FraisInvalide, match="positif"):
        services.declarer_imprevu(mission, chauffeur, montant=Decimal("0"), justificatif=_preuve())


# --- planification (Parc Auto) ---


def test_le_parc_auto_planifie_une_avance_de_route():
    mission = _mission_affectee()

    frais = services.planifier_frais(
        mission, _parcauto(), type_frais=TypeFraisMission.AVANCE_ROUTE, montant=Decimal("50000")
    )

    assert frais.statut == StatutFraisMission.PREVU
    assert frais.saisi_par.role == Role.PARCAUTO


def test_seul_le_parc_auto_planifie():
    mission = _mission_affectee()

    with pytest.raises(ActionFraisNonAutorisee):
        services.planifier_frais(
            mission, _finances(), type_frais=TypeFraisMission.DEPENSE_PREVUE, montant=Decimal("1000")
        )


def test_on_ne_planifie_pas_un_imprevu_ni_un_encaissement():
    mission = _mission_affectee()

    with pytest.raises(FraisInvalide):
        services.planifier_frais(
            mission, _parcauto(), type_frais=TypeFraisMission.IMPREVU, montant=Decimal("1000")
        )


# --- validation d'une avance / dépense prévue : la Finance seule ---


def test_la_finance_confirme_directement_une_avance_de_route():
    mission = _mission_affectee()
    frais = services.planifier_frais(
        mission, _parcauto(), type_frais=TypeFraisMission.AVANCE_ROUTE, montant=Decimal("50000")
    )

    services.valider_finances(frais, _finances())

    frais.refresh_from_db()
    assert frais.statut == StatutFraisMission.CONFIRME
    assert frais.valide_finances_par is not None


def test_seule_la_finance_valide_une_avance_de_route():
    mission = _mission_affectee()
    frais = services.planifier_frais(
        mission, _parcauto(), type_frais=TypeFraisMission.AVANCE_ROUTE, montant=Decimal("50000")
    )

    for acteur in (_parcauto(), UserFactory(role=Role.ADMIN)):
        with pytest.raises(ActionFraisNonAutorisee):
            services.valider_finances(frais, acteur)


# --- double validation d'un imprévu : Parc Auto puis Finance ---


def test_un_imprevu_passe_par_le_parc_auto_avant_la_finance():
    chauffeur = _chauffeur()
    mission = _mission_affectee(chauffeur)
    frais = services.declarer_imprevu(mission, chauffeur, montant=Decimal("15000"), justificatif=_preuve())

    with pytest.raises(FraisInvalide, match="Parc Auto"):
        services.valider_finances(frais, _finances())

    services.valider_parcauto(frais, _parcauto())
    frais.refresh_from_db()
    assert frais.statut == StatutFraisMission.PREVU  # toujours en attente de la finance
    assert frais.valide_parcauto_par is not None

    services.valider_finances(frais, _finances())
    frais.refresh_from_db()
    assert frais.statut == StatutFraisMission.CONFIRME
    assert frais.valide_finances_par is not None


def test_seul_le_parc_auto_valide_en_premier_un_imprevu():
    chauffeur = _chauffeur()
    mission = _mission_affectee(chauffeur)
    frais = services.declarer_imprevu(mission, chauffeur, montant=Decimal("15000"), justificatif=_preuve())

    with pytest.raises(ActionFraisNonAutorisee):
        services.valider_parcauto(frais, _finances())


def test_le_chauffeur_ne_valide_jamais_son_propre_imprevu():
    chauffeur = _chauffeur()
    mission = _mission_affectee(chauffeur)
    frais = services.declarer_imprevu(mission, chauffeur, montant=Decimal("15000"), justificatif=_preuve())

    utilisateur_chauffeur = chauffeur.personnel.utilisateur
    with pytest.raises(ActionFraisNonAutorisee):
        services.valider_parcauto(frais, utilisateur_chauffeur)


def test_une_ligne_deja_traitee_ne_se_valide_plus():
    mission = _mission_affectee()
    frais = services.planifier_frais(
        mission, _parcauto(), type_frais=TypeFraisMission.AVANCE_ROUTE, montant=Decimal("50000")
    )
    services.valider_finances(frais, _finances())

    with pytest.raises(FraisInvalide, match="déjà traitée"):
        services.valider_finances(frais, _finances())


# --- rejet ---


def test_le_parc_auto_rejette_un_imprevu_avant_la_finance():
    chauffeur = _chauffeur()
    mission = _mission_affectee(chauffeur)
    frais = services.declarer_imprevu(mission, chauffeur, montant=Decimal("15000"), justificatif=_preuve())

    services.rejeter(frais, _parcauto(), motif="Aucune preuve valable")

    frais.refresh_from_db()
    assert frais.statut == StatutFraisMission.REJETE and frais.motif_rejet == "Aucune preuve valable"


def test_la_finance_rejette_une_avance_de_route():
    mission = _mission_affectee()
    frais = services.planifier_frais(
        mission, _parcauto(), type_frais=TypeFraisMission.AVANCE_ROUTE, montant=Decimal("50000")
    )

    with pytest.raises(ActionFraisNonAutorisee):
        services.rejeter(frais, _parcauto(), motif="x")

    services.rejeter(frais, _finances(), motif="Montant excessif")
    frais.refresh_from_db()
    assert frais.statut == StatutFraisMission.REJETE


def test_le_rejet_exige_un_motif():
    mission = _mission_affectee()
    frais = services.planifier_frais(
        mission, _parcauto(), type_frais=TypeFraisMission.AVANCE_ROUTE, montant=Decimal("50000")
    )

    with pytest.raises(FraisInvalide, match="motif"):
        services.rejeter(frais, _finances(), motif="   ")


# --- encaissement automatique ---


def test_creer_encaissement_est_directement_confirme():
    mission = _mission_affectee()

    frais = services.creer_encaissement(mission, montant=Decimal("300000"), libelle="Règlement FACT-2026-0001")

    assert frais.type_frais == TypeFraisMission.ENCAISSEMENT
    assert frais.statut == StatutFraisMission.CONFIRME
    assert frais.est_sortie is False


# --- totaux ---


def test_totaux_ne_comptent_que_les_lignes_confirmees():
    mission = _mission_affectee()
    sortie_confirmee = services.planifier_frais(
        mission, _parcauto(), type_frais=TypeFraisMission.AVANCE_ROUTE, montant=Decimal("50000")
    )
    services.valider_finances(sortie_confirmee, _finances())
    services.planifier_frais(
        mission, _parcauto(), type_frais=TypeFraisMission.DEPENSE_PREVUE, montant=Decimal("99999")
    )  # encore PREVU, ignoré
    services.creer_encaissement(mission, montant=Decimal("300000"), libelle="Règlement")

    totaux = services.totaux(mission)

    assert totaux == {
        "sorties": Decimal("50000"), "encaisse": Decimal("300000"),
        "solde": Decimal("250000"), "en_attente": 1,
    }


# --- signal de confirmation (utilisé par finance.receivers) ---


def test_la_confirmation_emet_le_signal_frais_mission_confirme():
    mission = _mission_affectee()
    frais = services.planifier_frais(
        mission, _parcauto(), type_frais=TypeFraisMission.AVANCE_ROUTE, montant=Decimal("50000")
    )
    recus = []
    frais_mission_confirme.connect(lambda sender, frais, **kw: recus.append(frais.pk), weak=False)

    services.valider_finances(frais, _finances())

    assert recus == [frais.pk]


def test_une_erreur_du_recepteur_annule_la_confirmation():
    mission = _mission_affectee()
    frais = services.planifier_frais(
        mission, _parcauto(), type_frais=TypeFraisMission.AVANCE_ROUTE, montant=Decimal("50000")
    )

    def _echoue(sender, frais, **kwargs):
        raise RuntimeError("dépense impossible à écrire")

    frais_mission_confirme.connect(_echoue, weak=False, dispatch_uid="test-echec-confirmation")
    try:
        with pytest.raises(RuntimeError):
            services.valider_finances(frais, _finances())
    finally:
        frais_mission_confirme.disconnect(dispatch_uid="test-echec-confirmation")

    frais.refresh_from_db()
    assert frais.statut == StatutFraisMission.PREVU  # la transaction a été annulée
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

*60 lignes*

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
        # Retour réunion : c'est le Parc Auto qui affecte les missions après leur création.
        (StatutMission.PLANIFIEE, Role.PARCAUTO, {"affecter"}),
        (StatutMission.AFFECTEE, Role.DIRECTION, {"demarrer"}),
        (StatutMission.AFFECTEE, Role.CHARGE_CLIENTELE, set()),
        (StatutMission.AFFECTEE, Role.PARCAUTO, set()),
        (StatutMission.EN_COURS_DEPART, Role.ADMIN, {"recuperation"}),
        # Retour réunion : la DIRECTION a la même largeur que l'ADMIN, y compris ici.
        (StatutMission.EN_COURS_DEPART, Role.DIRECTION, {"recuperation"}),
        (StatutMission.EN_COURS_DEPART, Role.CHARGE_CLIENTELE, set()),
        (StatutMission.EN_COURS_COLIS_RECUPERE, Role.ADMIN, {"livraison"}),
        (StatutMission.EN_COURS_COLIS_RECUPERE, Role.DIRECTION, {"livraison"}),
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


def test_le_parc_auto_consulte_les_missions_sans_voir_les_codes():
    """Retour réunion : le Parc Auto affecte les missions, donc les consulte, mais les codes
    expéditeur/destinataire restent réservés à ceux qui gèrent la relation client (VOIR_CODES)."""
    assert Role.PARCAUTO in permissions.CONSULTATION
    assert Role.PARCAUTO not in permissions.VOIR_CODES
```

#### `apps/missions/tests/test_services.py`

*587 lignes* — Cycle de vie d'une mission — cahier-des-charges.md:127-143.

```python
"""Cycle de vie d'une mission — cahier-des-charges.md:127-143."""

import re
from decimal import Decimal

import pytest

from apps.audit.models import AuditLog
from apps.customers.tests.factories import ClientFactory
from apps.drivers.models import StatutChauffeur
from apps.drivers.tests.factories import ChauffeurFactory, CopiloteFactory
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
from apps.missions.tests.factories import MissionFactory

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


def _affectee(vehicule=None, chauffeur=None, copilote=None, **surcharges):
    vehicule = vehicule or VehiculeFactory()
    chauffeur = chauffeur or ChauffeurFactory()
    return services.affecter_mission(
        _planifiee(**surcharges), vehicule=vehicule, chauffeur=chauffeur, copilote=copilote
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


# --- copilote (retour réunion : décision humaine du Parc Auto au moment de l'affectation) ---


def test_affecter_sans_copilote_reste_possible():
    mission = _affectee()

    assert mission.copilote is None


def test_affecter_avec_un_copilote_disponible():
    copilote = CopiloteFactory()

    mission = _affectee(copilote=copilote)

    assert mission.copilote == copilote


@pytest.mark.parametrize(
    "statut",
    [
        StatutChauffeur.EN_MISSION,
        StatutChauffeur.EN_CONGE,
        StatutChauffeur.SUSPENDU,
        StatutChauffeur.INACTIF,
    ],
)
def test_affecter_refuse_un_copilote_non_disponible(statut):
    with pytest.raises(AffectationImpossible, match="copilote"):
        services.affecter_mission(
            _planifiee(),
            vehicule=VehiculeFactory(),
            chauffeur=ChauffeurFactory(),
            copilote=CopiloteFactory(statut=statut),
        )


def test_affecter_refuse_un_copilote_deja_reserve_par_une_autre_mission():
    copilote = CopiloteFactory()
    _affectee(copilote=copilote)

    with pytest.raises(AffectationImpossible, match="déjà réservé"):
        services.affecter_mission(
            _planifiee(), vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory(), copilote=copilote
        )


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


def test_demarrer_passe_le_copilote_en_mission_si_affecte():
    copilote = CopiloteFactory()
    mission = services.demarrer_mission(_affectee(copilote=copilote))

    assert mission.statut == StatutMission.EN_COURS_DEPART
    copilote.refresh_from_db()
    assert copilote.statut == StatutChauffeur.EN_MISSION


def test_demarrer_refuse_si_le_copilote_est_passe_en_conge_entre_temps():
    copilote = CopiloteFactory()
    mission = _affectee(copilote=copilote)
    copilote.statut = StatutChauffeur.EN_CONGE
    copilote.save()

    with pytest.raises(DemarrageImpossible, match="copilote"):
        services.demarrer_mission(mission)

    mission.vehicule.refresh_from_db()
    assert mission.vehicule.statut == StatutVehicule.DISPONIBLE


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


def test_livrer_libere_le_copilote_si_affecte():
    copilote = CopiloteFactory()
    mission = _affectee(copilote=copilote)
    mission = services.demarrer_mission(mission)
    mission = services.confirmer_recuperation(mission, code=mission.code_expediteur)

    services.livrer_mission(mission, code=mission.code_destinataire, km_arrivee=125000)

    copilote.refresh_from_db()
    assert copilote.statut == StatutChauffeur.DISPONIBLE


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


# --- lieux déjà utilisés (suggestions à la saisie) ---


def test_les_lieux_deja_utilises_sont_classes_par_frequence():
    MissionFactory(lieu_chargement="Abidjan", lieu_livraison="Bouaké")
    MissionFactory(lieu_chargement="Abidjan", lieu_livraison="Korhogo")
    MissionFactory(lieu_chargement="San-Pédro", lieu_livraison="Abidjan")

    assert services.lieux_deja_utilises() == ["Abidjan", "Bouaké", "Korhogo", "San-Pédro"]


def test_un_meme_lieu_ecrit_differemment_n_est_propose_qu_une_fois():
    MissionFactory(lieu_chargement="Bouaké", lieu_livraison="Abidjan")
    MissionFactory(lieu_chargement="Bouaké", lieu_livraison="Abidjan")
    MissionFactory(lieu_chargement="bouake ", lieu_livraison="ABIDJAN")

    lieux = services.lieux_deja_utilises()

    assert sorted(lieux) == ["Abidjan", "Bouaké"]  # la graphie la plus employée l'emporte


def test_aucun_lieu_sans_mission_et_la_liste_est_bornee():
    assert services.lieux_deja_utilises() == []
    for i in range(5):
        MissionFactory(lieu_chargement=f"Ville {i}", lieu_livraison=f"Ville {i}")

    assert len(services.lieux_deja_utilises(limite=3)) == 3
```

#### `apps/missions/tests/test_temps_reel.py`

*154 lignes* — Suivi des missions en direct : qui peut se connecter, ce qui est poussé, et ce qui ne casse jamais.

```python
"""Suivi des missions en direct : qui peut se connecter, ce qui est poussé, et ce qui ne casse jamais."""

import asyncio
from types import SimpleNamespace

import pytest
from asgiref.sync import sync_to_async
from channels.layers import channel_layers
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser

from apps.accounts import mfa
from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.missions import temps_reel
from apps.missions.consumers import MissionSuiviConsumer, est_autorise

from .factories import MissionFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def couche_neuve():
    """Une couche de messages vierge par test (elle est mise en mémoire, donc partagée sinon)."""
    channel_layers.backends = {}


def _communicateur(utilisateur, session=None):
    communicateur = WebsocketCommunicator(MissionSuiviConsumer.as_asgi(), "/ws/missions/suivi/")
    communicateur.scope["user"] = utilisateur
    communicateur.scope["session"] = session if session is not None else {}
    return communicateur


def _se_connecte(utilisateur, session=None) -> bool:
    async def scenario():
        communicateur = _communicateur(utilisateur, session)
        connecte, _ = await communicateur.connect()
        if connecte:
            await communicateur.disconnect()
        return connecte

    return asyncio.run(scenario())


# --- qui peut se connecter ---


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.CHARGE_CLIENTELE, Role.PARCAUTO])
def test_les_roles_qui_consultent_les_missions_se_connectent(role):
    # Retour réunion : le Parc Auto affecte les missions, donc les consulte désormais aussi.
    assert _se_connecte(UserFactory.build(role=role)) is True


@pytest.mark.parametrize("role", [Role.CHAUFFEUR, Role.RH, Role.FINANCES])
def test_les_autres_roles_sont_refuses(role):
    assert _se_connecte(UserFactory.build(role=role)) is False


def test_un_visiteur_non_connecte_est_refuse():
    assert _se_connecte(AnonymousUser()) is False


def test_un_compte_desactive_est_refuse():
    assert _se_connecte(UserFactory.build(role=Role.ADMIN, is_active=False)) is False


def test_sans_double_authentification_verifiee_un_admin_est_refuse(settings):
    """Le middleware MFA ne voit que le HTTP : la WebSocket refait ce contrôle elle-même."""
    settings.MFA_ENFORCED = True
    admin = UserFactory.build(role=Role.ADMIN)

    assert _se_connecte(admin, session={}) is False
    assert _se_connecte(admin, session={mfa.CLE_SESSION: True}) is True


def test_le_charge_clientele_n_a_pas_besoin_de_la_mfa(settings):
    settings.MFA_ENFORCED = True

    assert _se_connecte(UserFactory.build(role=Role.CHARGE_CLIENTELE), session={}) is True


def test_est_autorise_sans_session_refuse_un_role_soumis_a_la_mfa(settings):
    settings.MFA_ENFORCED = True
    scope = {"user": SimpleNamespace(is_authenticated=True, is_active=True, role_effectif=Role.DIRECTION)}

    assert est_autorise(scope) is False


# --- ce qui est poussé ---


def test_un_changement_de_mission_est_pousse_aux_ecrans_connectes():
    mission = MissionFactory(numero="MIS-2026-0077")

    async def scenario():
        communicateur = _communicateur(UserFactory.build(role=Role.DIRECTION))
        await communicateur.connect()
        await sync_to_async(temps_reel.diffuser)(mission)
        recu = await communicateur.receive_json_from()
        await communicateur.disconnect()
        return recu

    recu = asyncio.run(scenario())

    assert recu == {"id": mission.pk, "numero": "MIS-2026-0077", "statut": "BROUILLON", "statut_libelle": "Brouillon"}


def test_le_message_ne_contient_aucun_code_secret():
    mission = MissionFactory()

    contenu = str(temps_reel.message_mission(mission))

    assert mission.code_expediteur not in contenu and mission.code_destinataire not in contenu


def test_un_ecran_deconnecte_ne_recoit_plus_rien():
    async def scenario():
        communicateur = _communicateur(UserFactory.build(role=Role.ADMIN))
        await communicateur.connect()
        await communicateur.disconnect()
        await sync_to_async(temps_reel.diffuser)(MissionFactory.build(pk=1, numero="MIS-2026-0001"))
        return await communicateur.receive_nothing()

    assert asyncio.run(scenario()) is True


# --- diffusion depuis le métier ---


def test_enregistrer_une_mission_la_diffuse_apres_la_validation(monkeypatch, django_capture_on_commit_callbacks):
    diffusees = []
    monkeypatch.setattr(temps_reel, "diffuser", lambda mission: diffusees.append(mission.numero))

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        mission = MissionFactory(numero="MIS-2026-0088")

    assert diffusees == []  # rien n'est parti avant la validation de la transaction
    for callback in callbacks:
        callback()
    assert diffusees == [mission.numero]


def test_une_couche_de_messages_en_panne_ne_fait_pas_echouer_le_metier(monkeypatch, caplog):
    class CoucheCassee:
        async def group_send(self, *args, **kwargs):
            raise ConnectionError("Redis injoignable")

    monkeypatch.setattr(temps_reel, "get_channel_layer", lambda: CoucheCassee())

    temps_reel.diffuser(MissionFactory.build(pk=5, numero="MIS-2026-0005"))  # ne lève rien

    assert "Diffusion du suivi de la mission 5 impossible" in caplog.text
```

## Étape 5 — Déclarer l'application et migrer

#### `config/settings/base.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/settings/base.py (avant)
+++ config/settings/base.py (après)
@@ -59,4 +59,5 @@
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
python -m pytest apps/missions/tests/test_frais_mission.py apps/missions/tests/test_models.py apps/missions/tests/test_permissions.py apps/missions/tests/test_services.py apps/missions/tests/test_temps_reel.py -q --no-cov
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
