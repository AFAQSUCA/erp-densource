# Chapitre 10 — Le garage : l'app garage

> 17 fichier(s) dans ce chapitre, 1579 lignes de code.

## Ce que vous allez construire

**`garage`** : l'entretien et les pannes des camions.

| Élément | Règle |
|---|---|
| **Ordre de réparation (OR)** | numéro `OR-<année>-0001`, type (curatif, préventif, diagnostic, pneumatiques), lieu (garage interne ou prestataire), motif ; **ouvrir un OR met le camion « En maintenance »** |
| **Clôture d'un OR** | on saisit la main-d'œuvre ; le **statut du camion est recalculé** avec l'algorithme de `fleet` |
| **Immobiliser / hors service / remettre en service** | actions manuelles du Parc Auto (refusées si le camion est réservé par une mission) |
| **Check-list du chauffeur** | 8 points fixes (pneus, freins, feux…), OK ou KO ; un **KO exige une remarque** et **prévient** le Parc Auto sans bloquer le départ |
| **Incident** | panne, accident ou autre, avec gravité ; il prévient le Parc Auto et la Direction, **sans aucune action automatique** : le Parc Auto décide |

## Prérequis

- Chapitres 1 à 9 terminés.

## Notions Django de ce chapitre

- **Inversion de dépendance, suite** : c'est ici qu'on utilise `fleet.calculer_statut`. `garage` calcule
  « y a-t-il un OR ouvert ? » et « y a-t-il une mission active ? » (en appelant `missions`), puis passe ces
  **faits en paramètres** à `fleet`.
- **Plusieurs modèles dans un module** : un OR, une check-list, un incident.
- **Signaux métier** (`incident_signale`, `checklist_anomalie`) : `notifications` les écoutera.
- **Un registre pour recevoir des blocs** (`DETAIL_OR`) : `inventory` y ajoutera les pièces utilisées.
- **Un service qui filtre par acteur** : les incidents et check-lists d'un chauffeur ne peuvent être
  déclarés que **sur son propre camion** (`ChauffeurNonAutorise`).
- **`terrain.py`** : un second module de services pour tout ce qui vient du terrain (chauffeur mobile), pour
  ne pas mélanger avec la gestion des OR.

## Étape 1 — Créer l'application

```bash
mkdir -p apps/garage/tests
```

#### Fichiers vides à créer

Ces fichiers n'ont aucun contenu ; ils servent à faire de leur dossier un *paquet Python* (sans eux, `import apps.xxx` échouerait). Créez d'abord les dossiers, puis les fichiers :

```bash
mkdir -p apps\garage apps\garage\tests
touch apps/garage/__init__.py
touch apps/garage/tests/__init__.py
```

> Sous PowerShell, `mkdir -p` s'écrit `New-Item -ItemType Directory -Force <dossier>` et `touch fichier` s'écrit `New-Item -ItemType File -Force fichier`. Vous pouvez aussi créer ces fichiers avec votre éditeur.

## Étape 2 — Modèles

#### `apps/garage/models.py`

*212 lignes*

```python
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class TypeOr(models.TextChoices):
    """4 types d'ordre de réparation — cahier-des-charges.md:163-164."""

    CURATIF = "CURATIF", _("Curatif")
    PREVENTIF = "PREVENTIF", _("Préventif")
    DIAGNOSTIC = "DIAGNOSTIC", _("Diagnostic")
    PNEUMATIQUES = "PNEUMATIQUES", _("Pneumatiques")


class LieuReparation(models.TextChoices):
    """Lieu de la réparation — cahier-des-charges.md:164-165."""

    INTERNE = "INTERNE", _("Garage interne DEN Source")
    EXTERNE = "EXTERNE", _("Prestataire externe")


class StatutOr(models.TextChoices):
    OUVERT = "OUVERT", _("Ouvert")
    CLOTURE = "CLOTURE", _("Clôturé")


class OrdreReparation(BaseModel):
    """Ordre de réparation (OR) — cahier-des-charges.md:161-168.

    Ouvrir un OR passe le camion « En maintenance » ; le clôturer déclenche le
    recalcul automatique du statut (``services.cloturer_or``).
    """

    numero = models.CharField(_("numéro"), max_length=20, unique=True)
    vehicule = models.ForeignKey(
        "fleet.Vehicule",
        verbose_name=_("véhicule"),
        on_delete=models.PROTECT,
        related_name="ordres_reparation",
    )
    type_or = models.CharField(_("type"), max_length=15, choices=TypeOr.choices)
    lieu = models.CharField(_("lieu"), max_length=10, choices=LieuReparation.choices)
    motif = models.TextField(_("motif / symptômes"))
    statut = models.CharField(
        _("statut"), max_length=10, choices=StatutOr.choices, default=StatutOr.OUVERT
    )
    date_ouverture = models.DateTimeField(_("ouvert le"), default=timezone.now)
    date_cloture = models.DateTimeField(_("clôturé le"), null=True, blank=True)
    cout_main_oeuvre = models.DecimalField(
        _("coût de la main-d'œuvre (FCFA)"),
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    class Meta:
        verbose_name = _("ordre de réparation")
        verbose_name_plural = _("ordres de réparation")
        ordering = ["-numero"]
        indexes = [models.Index(fields=["vehicule", "statut"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(statut=StatutOr.OUVERT) | Q(date_cloture__isnull=False),
                name="or_cloture_requiert_date",
            ),
            models.CheckConstraint(
                condition=Q(cout_main_oeuvre__gte=0),
                name="or_cout_main_oeuvre_positif_ou_nul",
            ),
        ]

    def __str__(self):
        return f"{self.numero} ({self.vehicule.immatriculation})"


# --- signalements du chauffeur (espace mobile) ---

# Points de la check-list véhicule : liste fixe (le CDC ne détaille pas son contenu,
# cahier-des-charges.md:54). Un point est « OK » ou « KO » ; un KO exige une remarque.
POINTS_CHECKLIST = (
    ("PNEUS", "Pneus (état et pression)"),
    ("FREINS", "Freins"),
    ("FEUX", "Feux et clignotants"),
    ("HUILE", "Niveau d'huile moteur"),
    ("EAU", "Niveau d'eau et de refroidissement"),
    ("CARROSSERIE", "Carrosserie et rétroviseurs"),
    ("DOCUMENTS", "Documents du camion à bord"),
    ("SECURITE", "Extincteur et triangle de signalisation"),
)
CODES_CHECKLIST = tuple(code for code, _libelle in POINTS_CHECKLIST)


class ChecklistVehicule(BaseModel):
    """Check-list remplie par le chauffeur avant le départ d'une mission.

    Non bloquante : un point KO prévient le Parc Auto sans empêcher le départ.
    ``points`` : liste de ``{"code", "libelle", "ok", "remarque"}``, un élément par point.
    """

    mission = models.ForeignKey(
        "missions.Mission",
        verbose_name=_("mission"),
        on_delete=models.PROTECT,
        related_name="checklists",
    )
    vehicule = models.ForeignKey(
        "fleet.Vehicule",
        verbose_name=_("véhicule"),
        on_delete=models.PROTECT,
        related_name="checklists",
    )
    chauffeur = models.ForeignKey(
        "drivers.Chauffeur",
        verbose_name=_("chauffeur"),
        on_delete=models.PROTECT,
        related_name="checklists",
    )
    points = models.JSONField(_("points contrôlés"), default=list)
    nb_anomalies = models.PositiveSmallIntegerField(_("points KO"), default=0)
    remarque = models.TextField(_("remarque générale"), blank=True)

    class Meta:
        verbose_name = _("check-list véhicule")
        verbose_name_plural = _("check-lists véhicule")
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["mission"],
                condition=Q(is_deleted=False),
                name="checklist_une_par_mission",
            ),
        ]

    def __str__(self):
        return f"Check-list {self.mission.numero}"


class TypeIncident(models.TextChoices):
    PANNE = "PANNE", _("Panne")
    ACCIDENT = "ACCIDENT", _("Accident")
    AUTRE = "AUTRE", _("Autre")


class GraviteIncident(models.TextChoices):
    FAIBLE = "FAIBLE", _("Faible : le camion peut rouler")
    MOYENNE = "MOYENNE", _("Moyenne : intervention nécessaire")
    GRAVE = "GRAVE", _("Grave : camion immobilisé")


class StatutIncident(models.TextChoices):
    SIGNALE = "SIGNALE", _("Signalé")
    PRIS_EN_COMPTE = "PRIS_EN_COMPTE", _("Pris en compte")
    CLOS = "CLOS", _("Clos")


class Incident(BaseModel):
    """Panne ou incident signalé par le chauffeur ; le Parc Auto décide de la suite.

    Aucune action automatique sur le camion : c'est le Parc Auto qui ouvre un OR
    s'il le juge utile (décision de l'utilisateur).
    """

    vehicule = models.ForeignKey(
        "fleet.Vehicule",
        verbose_name=_("véhicule"),
        on_delete=models.PROTECT,
        related_name="incidents",
    )
    chauffeur = models.ForeignKey(
        "drivers.Chauffeur",
        verbose_name=_("chauffeur"),
        null=True,
        on_delete=models.PROTECT,
        related_name="incidents",
    )
    mission = models.ForeignKey(
        "missions.Mission",
        verbose_name=_("mission"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="incidents",
    )
    type_incident = models.CharField(_("type"), max_length=10, choices=TypeIncident.choices)
    gravite = models.CharField(_("gravité"), max_length=10, choices=GraviteIncident.choices)
    description = models.TextField(_("description"))
    lieu = models.CharField(_("lieu"), max_length=200, blank=True)
    statut = models.CharField(
        _("statut"), max_length=15, choices=StatutIncident.choices, default=StatutIncident.SIGNALE
    )
    note_traitement = models.TextField(_("suite donnée"), blank=True)
    traite_par = models.ForeignKey(
        "accounts.User",
        verbose_name=_("traité par"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    date_traitement = models.DateTimeField(_("traité le"), null=True, blank=True)

    class Meta:
        verbose_name = _("incident")
        verbose_name_plural = _("incidents")
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["statut", "gravite"])]

    def __str__(self):
        return f"{self.get_type_incident_display()} {self.vehicule.immatriculation}"
```

Trois modèles :

- **`OrdreReparation`** : le numéro, le camion (`PROTECT` : on ne supprime pas un camion qui a un
  historique), le type, le lieu, le motif, le statut (Ouvert / Clôturé) et les coûts.
- **`ChecklistVehicule`** : les résultats des 8 points (`POINTS_CHECKLIST`), rattachés à **une mission**.
- **`Incident`** : type, gravité (faible, moyenne, grave), description, lieu, statut (Signalé → Pris en
  compte → Clos).

## Étape 3 — Règles métier

#### `apps/garage/exceptions.py`

*34 lignes*

```python
class GarageError(Exception):
    """Erreur métier sur un ordre de réparation."""


class TransitionOrInterdite(GarageError):
    """L'OR n'est pas dans le statut requis (ex. déjà clôturé)."""


class CoutInvalide(GarageError):
    """Coût de main-d'œuvre négatif."""


class StatutVehiculeInvalide(GarageError):
    """Immobilisation, mise hors service ou remise en service impossible."""


class ChauffeurNonAutorise(GarageError):
    """Le chauffeur ne peut pas agir sur cette mission, ou l'utilisateur n'a pas le droit."""


class ChecklistInvalide(GarageError):
    """Check-list incomplète, point inconnu, KO sans remarque, ou mission hors avant-départ."""


class ChecklistDejaRemplie(GarageError):
    """Une seule check-list par mission."""


class IncidentInvalide(GarageError):
    """Signalement ou clôture d'incident incomplet."""


class TransitionIncidentInterdite(GarageError):
    """L'incident n'est pas dans le statut requis."""
```

#### `apps/garage/services.py`

*181 lignes* — Logique métier du garage — cahier-des-charges.md:161-168.

```python
"""Logique métier du garage — cahier-des-charges.md:161-168.

Ouverture d'un OR → camion « En maintenance ». Clôture → recalcul automatique
du statut selon l'algorithme du CDC (cahier-des-charges.md:96-100), dont
``garage`` fournit les deux faits : « d'autres OR ouverts » (lui-même) et
« mission active » (``missions``).
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from apps.core.search import filtrer_par_texte
from apps.core.services import prochain_numero
from apps.fleet import services as fleet_services
from apps.fleet.models import StatutVehicule, Vehicule
from apps.missions import services as missions_services

from .exceptions import CoutInvalide, StatutVehiculeInvalide, TransitionOrInterdite
from .models import OrdreReparation, StatutOr, TypeOr, LieuReparation
from .signals import or_cloture

PREFIXE_NUMERO = "OR"


def vehicule_a_or_ouvert(vehicule: Vehicule) -> bool:
    """Vrai si au moins un OR ouvert existe pour ce camion."""
    return OrdreReparation.objects.filter(
        vehicule=vehicule, statut=StatutOr.OUVERT
    ).exists()


def _verrouiller(objet):
    type(objet)._base_manager.select_for_update().filter(pk=objet.pk).first()
    objet.refresh_from_db()
    return objet


@transaction.atomic
def ouvrir_or(
    vehicule: Vehicule, *, type_or: str, lieu: str, motif: str
) -> OrdreReparation:
    """Ouvre un OR (numéro OR-AAAA-XXXX) et passe le camion « En maintenance ».

    Autorisé même si le camion est en mission : c'est le cas d'une panne en
    route. La mission continue ; le statut sera recalculé à la clôture.
    """
    _verrouiller(vehicule)
    ordre = OrdreReparation.objects.create(
        numero=prochain_numero(PREFIXE_NUMERO),
        vehicule=vehicule,
        type_or=type_or,
        lieu=lieu,
        motif=motif,
    )
    fleet_services.definir_statut(vehicule, StatutVehicule.EN_MAINTENANCE)
    return ordre


@transaction.atomic
def cloturer_or(
    ordre: OrdreReparation, *, cout_main_oeuvre: Decimal = Decimal("0")
) -> OrdreReparation:
    """Clôture l'OR, enregistre la main-d'œuvre et recalcule le statut du camion.

    Recalcul (cahier-des-charges.md:96-100) : d'autres OR ouverts → En
    maintenance ; sinon mission affectée/en cours → En mission ; sinon
    Immobilisé / Hors service conservé ; sinon Disponible.
    """
    if cout_main_oeuvre < 0:
        raise CoutInvalide("Le coût de la main-d'œuvre ne peut pas être négatif.")
    _verrouiller(ordre)
    if ordre.statut != StatutOr.OUVERT:
        raise TransitionOrInterdite(f"L'OR {ordre.numero} est déjà clôturé.")
    vehicule = _verrouiller(ordre.vehicule)

    ordre.statut = StatutOr.CLOTURE
    ordre.date_cloture = timezone.now()
    ordre.cout_main_oeuvre = cout_main_oeuvre
    ordre.save(
        update_fields=["statut", "date_cloture", "cout_main_oeuvre", "updated_at"]
    )

    fleet_services.recalculer_statut(
        vehicule,
        or_ouverts=vehicule_a_or_ouvert(vehicule),
        mission_active=missions_services.vehicule_a_mission_active(vehicule),
    )
    or_cloture.send(sender=OrdreReparation, ordre=ordre)
    return ordre


# --- consultation des OR ---


def ordres_queryset() -> QuerySet[OrdreReparation]:
    """OR avec leur camion chargé (évite les requêtes en boucle)."""
    return OrdreReparation.objects.select_related("vehicule")


def rechercher_ordres(
    *,
    statut: str | None = None,
    type_or: str | None = None,
    lieu: str | None = None,
    recherche: str = "",
) -> QuerySet[OrdreReparation]:
    """OR filtrés par statut, type, lieu et texte (n°, immatriculation, motif)."""
    ordres = ordres_queryset()
    if statut in StatutOr.values:
        ordres = ordres.filter(statut=statut)
    if type_or in TypeOr.values:
        ordres = ordres.filter(type_or=type_or)
    if lieu in LieuReparation.values:
        ordres = ordres.filter(lieu=lieu)
    ordres = filtrer_par_texte(ordres, recherche, "numero", "vehicule__immatriculation", "motif")
    return ordres


def ordres_du_vehicule(vehicule: Vehicule, *, limite: int = 5) -> QuerySet[OrdreReparation]:
    """Derniers OR d'un camion, du plus récent au plus ancien."""
    return OrdreReparation.objects.filter(vehicule=vehicule).order_by("-numero")[:limite]


# --- immobilisation et remise en service (cahier-des-charges.md:91-92, 96-100) ---


def _refuser_si_mission_active(vehicule: Vehicule, action: str) -> None:
    """Un camion réservé ou en route ne s'immobilise pas : sa mission serait bloquée.

    Une panne en route s'enregistre en ouvrant un OR (statut « En maintenance »)."""
    if missions_services.vehicule_a_mission_active(vehicule):
        raise StatutVehiculeInvalide(
            f"Impossible de {action} : le camion {vehicule.immatriculation} est réservé "
            "ou en route pour une mission. En cas de panne, ouvrez un OR."
        )


@transaction.atomic
def immobiliser_vehicule(vehicule: Vehicule) -> Vehicule:
    """Marque le camion « Immobilisé » (ex. accident, saisie, document expiré)."""
    _verrouiller(vehicule)
    if vehicule.statut == StatutVehicule.IMMOBILISE:
        raise StatutVehiculeInvalide("Ce camion est déjà immobilisé.")
    _refuser_si_mission_active(vehicule, "immobiliser")
    return fleet_services.definir_statut(vehicule, StatutVehicule.IMMOBILISE)


@transaction.atomic
def mettre_hors_service(vehicule: Vehicule) -> Vehicule:
    """Marque le camion « Hors service » (réforme, épave)."""
    _verrouiller(vehicule)
    if vehicule.statut == StatutVehicule.HORS_SERVICE:
        raise StatutVehiculeInvalide("Ce camion est déjà hors service.")
    _refuser_si_mission_active(vehicule, "mettre hors service")
    return fleet_services.definir_statut(vehicule, StatutVehicule.HORS_SERVICE)


@transaction.atomic
def remettre_en_service(vehicule: Vehicule) -> Vehicule:
    """Sort un camion d'« Immobilisé » ou « Hors service » et recalcule son statut.

    La règle 3 du CDC conserve ces deux statuts tant qu'on ne les lève pas : on
    repart donc de « Disponible », puis l'algorithme complet s'applique (OR
    ouvert → En maintenance, mission → En mission, sinon Disponible).
    """
    _verrouiller(vehicule)
    if vehicule.statut not in (StatutVehicule.IMMOBILISE, StatutVehicule.HORS_SERVICE):
        raise StatutVehiculeInvalide(
            "Seul un camion immobilisé ou hors service peut être remis en service."
        )
    fleet_services.definir_statut(vehicule, StatutVehicule.DISPONIBLE)
    return fleet_services.recalculer_statut(
        vehicule,
        or_ouverts=vehicule_a_or_ouvert(vehicule),
        mission_active=missions_services.vehicule_a_mission_active(vehicule),
    )
```

À lire :

1. **`ouvrir_or`** : crée l'OR, passe le camion « En maintenance » (`fleet.definir_statut`). Autorisé même
   pendant une mission : c'est une panne en route.
2. **`cloturer_or`** : enregistre la main-d'œuvre, puis **recalcule** le statut du camion avec
   `fleet.recalculer_statut`, en fournissant `or_ouverts` (y a-t-il d'autres OR ouverts ?) et `mission_active`
   (`missions.vehicule_a_mission_active`).
3. **`immobiliser_vehicule`**, **`mettre_hors_service`**, **`remettre_en_service`** : refusés si le camion est
   réservé (`_refuser_si_mission_active`). Un camion réservé qui tombe en panne s'**ouvre en OR**, on ne
   l'immobilise pas.

#### `apps/garage/terrain.py`

*225 lignes* — Services des signalements du chauffeur : check-list du véhicule et incidents.

```python
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
```

Ce que fait le chauffeur sur le terrain :

- **`enregistrer_checklist`** : refuse les points inconnus ; **exige une remarque** pour un point KO ; une
  seule check-list par mission ; **non bloquante** (elle n'empêche pas le départ).
- **`declarer_incident`** puis **`prendre_en_compte`** / **`clore_incident`** (réservés au Parc Auto) : la
  décision (ouvrir un OR ou non) reste **humaine**.

#### `apps/garage/signals.py`

*26 lignes* — Événements des signalements du chauffeur (souscrits par ``notifications``).

```python
"""Événements des signalements du chauffeur (souscrits par ``notifications``).

Émis avec ``send_robust`` : un récepteur en erreur ne doit jamais empêcher le chauffeur de
signaler une panne.
"""

import logging

from django.dispatch import Signal

logger = logging.getLogger(__name__)

# Un incident vient d'être signalé. Argument : ``incident``.
incident_signale = Signal()
# Une check-list vient d'être enregistrée avec au moins un point KO. Argument : ``checklist``.
checklist_anomalie = Signal()


def emettre(signal: Signal, **arguments) -> None:
    for recepteur, resultat in signal.send_robust(sender=None, **arguments):
        if isinstance(resultat, Exception):
            logger.error("Récepteur %r en erreur", recepteur, exc_info=resultat)

# Un OR vient d'être clôturé, dans sa transaction. Argument : ``ordre``. Souscrit par ``finance`` (dépense de
# main-d'œuvre) ; émis avec ``send`` (pas ``emettre``) pour qu'une erreur annule la clôture.
or_cloture = Signal()
```

#### `apps/garage/permissions.py`

*14 lignes* — Qui peut consulter et gérer le garage.

```python
"""Qui peut consulter et gérer le garage.

Cahier-des-charges.md:44-55 : le PARCAUTO a la « gestion technique véhicules » et
gère les « OR ». L'ADMIN a tous les droits. La DIRECTION, à l'origine en « lecture
seule sur Parc Auto », agit désormais aussi : retour d'une réunion entreprise, elle a
la même largeur que l'ADMIN sur la saisie/modification (ouvrir/clôturer un OR,
immobiliser un camion ou le remettre en service).
"""

from apps.accounts.models import Role

CONSULTATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.PARCAUTO})
# Retour réunion : la DIRECTION a la même largeur que l'ADMIN pour la saisie/modification.
MODIFICATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.PARCAUTO})
```

#### `apps/garage/sections.py`

*36 lignes* — Blocs du garage : ceux qu'il expose, et celui qu'il ajoute à la fiche d'un camion.

```python
"""Blocs du garage : ceux qu'il expose, et celui qu'il ajoute à la fiche d'un camion.

- ``DETAIL_OR`` : blocs ajoutés à la fiche d'un OR par des apps situées en dessous
  (``inventory`` y ajoute les pièces utilisées et le coût total). Fournisseurs
  appelés avec ``(ordre, utilisateur)``.
- :func:`section_maintenance` : bloc « Maintenance » de la fiche d'un camion
  (historique des OR, ouverture d'un OR, immobilisation, remise en service).
"""

from apps.core.sections import RegistreSections
from apps.fleet.models import StatutVehicule

from . import permissions, services

DETAIL_OR = RegistreSections()


def section_maintenance(vehicule, utilisateur):
    role = utilisateur.role_effectif
    if role not in permissions.CONSULTATION:
        return None
    peut_modifier = role in permissions.MODIFICATION
    statut = vehicule.statut
    return {
        "template": "garage/_maintenance_vehicule.html",
        "contexte": {
            "ordres": list(services.ordres_du_vehicule(vehicule)),
            "peut_modifier": peut_modifier,
            "peut_immobiliser": peut_modifier
            and statut != StatutVehicule.IMMOBILISE,
            "peut_mettre_hors_service": peut_modifier
            and statut != StatutVehicule.HORS_SERVICE,
            "peut_remettre_en_service": peut_modifier
            and statut in (StatutVehicule.IMMOBILISE, StatutVehicule.HORS_SERVICE),
        },
    }
```

Deux rôles : `garage` **expose** `DETAIL_OR` (où `inventory` ajoutera ses pièces) et **fournit** le bloc
« Maintenance » à la fiche d'un camion (`fleet.sections.DETAIL_VEHICULE`).

## Étape 4 — Administration, démarrage, tests

#### `apps/garage/admin.py`

*22 lignes*

```python
from django.contrib import admin

from .models import OrdreReparation


@admin.register(OrdreReparation)
class OrdreReparationAdmin(admin.ModelAdmin):
    """Lecture seule : ouverture et clôture passent par apps/garage/services.py,
    seul moyen de garder le statut du camion cohérent."""

    list_display = ("numero", "vehicule", "type_or", "lieu", "statut", "date_ouverture")
    list_filter = ("statut", "type_or", "lieu")
    search_fields = ("numero", "vehicule__immatriculation")

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in OrdreReparation._meta.fields]

    def has_add_permission(self, request):
        return False

    def get_queryset(self, request):
        return OrdreReparation.objects.select_related("vehicule")
```

#### `apps/garage/apps.py`

*30 lignes*

```python
from django.apps import AppConfig


class GarageConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.garage'
    label = 'garage'

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer
        from apps.audit.registry import audit_model
        from apps.fleet.sections import DETAIL_VEHICULE

        from . import permissions, sections
        from .models import Incident, OrdreReparation

        audit_model(OrdreReparation, module="PARC_AUTO")
        audit_model(Incident, module="PARC_AUTO")
        enregistrer(
            EntreeMenu(
                "Garage", "garage:liste", "fa-screwdriver-wrench", permissions.CONSULTATION, ordre=40
            )
        )
        enregistrer(
            EntreeMenu(
                "Incidents", "garage:incidents", "fa-triangle-exclamation",
                permissions.CONSULTATION, ordre=41,
            )
        )
        DETAIL_VEHICULE.enregistrer(sections.section_maintenance)
```

#### `apps/garage/tests/factories.py`

*17 lignes*

```python
import factory

from apps.fleet.tests.factories import VehiculeFactory
from apps.garage.models import LieuReparation, OrdreReparation, TypeOr


class OrdreReparationFactory(factory.django.DjangoModelFactory):
    """OR créé directement (sans changer le statut du camion)."""

    class Meta:
        model = OrdreReparation

    numero = factory.Sequence(lambda n: f"OR-2026-{n + 1:04d}")
    vehicule = factory.SubFactory(VehiculeFactory)
    type_or = TypeOr.CURATIF
    lieu = LieuReparation.INTERNE
    motif = "Bruit anormal au freinage"
```

#### `apps/garage/README.md`

*43 lignes* — garage

```markdown
# garage

Rôle : ordres de réparation (OR) — cahier-des-charges.md:161-168. Audité (module `PARC_AUTO`).

Entité : `OrdreReparation` (numéro `OR-AAAA-XXXX` via `core.services.prochain_numero`),
4 types (Curatif, Préventif, Diagnostic, Pneumatiques), 2 lieux (garage interne,
prestataire externe), statuts Ouvert / Clôturé.

Services :
- `ouvrir_or` : crée l'OR et passe le camion « En maintenance » (même en mission :
  panne en route).
- `cloturer_or` : enregistre la main-d'œuvre puis recalcule le statut du camion
  avec `fleet.services.recalculer_statut`, en fournissant `or_ouverts` (garage) et
  `mission_active` (`missions.services.vehicule_a_mission_active`).

Dépend de `fleet` et `missions` (jamais l'inverse).

Interface (`views.py`, `templates/garage/`) : liste des OR (filtres statut, type, lieu,
texte), fiche d'un OR, ouverture (préremplie depuis la fiche d'un camion), clôture avec
saisie de la main-d'œuvre. Accès : ADMIN, DIRECTION et PARCAUTO en consultation ; ADMIN
et PARCAUTO pour ouvrir, clôturer, immobiliser (`permissions.py`, la DIRECTION est en
lecture seule sur le parc auto).

Statut des camions (services) : `immobiliser_vehicule`, `mettre_hors_service`,
`remettre_en_service` (repart de « Disponible » puis applique l'algorithme complet :
OR ouvert, mission, sinon disponible). Un camion réservé ou en route pour une mission ne
s'immobilise pas : en cas de panne, on ouvre un OR.

Blocs enregistrables (`core/sections.py`) : `garage` ajoute un bloc « Maintenance » à la
fiche d'un camion (`fleet.sections.DETAIL_VEHICULE`) et expose `sections.DETAIL_OR` où
`inventory` ajoute les pièces utilisées. Ainsi `fleet` ne connaît pas `garage`, et
`garage` ne connaît pas `inventory`.

Signalements du chauffeur (`terrain.py`, `views_terrain.py`) :
- **Check-list du véhicule** : 8 points fixes (`POINTS_CHECKLIST` : pneus, freins, feux, huile, eau,
  carrosserie, documents, extincteur et triangle), OK ou KO, un KO exige une remarque. Une seule par
  mission, avant le départ. **Non bloquante** : un KO prévient le Parc Auto sans empêcher la mission.
- **Incident** : panne, accident ou autre, avec gravité, description et lieu. Il prévient le Parc Auto
  et la Direction ; **aucune action automatique** : le Parc Auto le prend en compte, ouvre un OR s'il le
  juge utile, puis le clôt avec la suite donnée (`/garage/incidents/`, `/garage/checklists/`).
Les signaux `incident_signale` et `checklist_anomalie` sont souscrits par `notifications`.

Rapport imprimable des OR et des incidents (bouton « Imprimer » sur la liste, mêmes filtres) : voir `apps/core/README.md` (`ImpressionListeMixin`).
```

#### `apps/garage/tests/test_models.py`

*43 lignes*

```python
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.garage.models import StatutOr

from .factories import OrdreReparationFactory

pytestmark = pytest.mark.django_db


def test_un_nouvel_or_est_ouvert_avec_une_main_d_oeuvre_nulle():
    ordre = OrdreReparationFactory()

    assert ordre.statut == StatutOr.OUVERT
    assert ordre.cout_main_oeuvre == 0
    assert ordre.date_cloture is None


def test_or_cloture_sans_date_refuse_par_la_base():
    with pytest.raises(IntegrityError), transaction.atomic():
        OrdreReparationFactory(statut=StatutOr.CLOTURE, date_cloture=None)


def test_cout_main_d_oeuvre_negatif_refuse_par_la_base():
    with pytest.raises(IntegrityError), transaction.atomic():
        OrdreReparationFactory(cout_main_oeuvre=Decimal("-1"))


def test_numero_unique():
    OrdreReparationFactory(numero="OR-2026-0001")

    with pytest.raises(IntegrityError), transaction.atomic():
        OrdreReparationFactory(numero="OR-2026-0001")


def test_un_camion_peut_avoir_plusieurs_or_ouverts():
    ordre = OrdreReparationFactory()

    OrdreReparationFactory(vehicule=ordre.vehicule)

    assert ordre.vehicule.ordres_reparation.count() == 2
```

#### `apps/garage/tests/test_services.py`

*214 lignes* — Ordres de réparation — cahier-des-charges.md:161-168 et recalcul du statut :96-100.

```python
"""Ordres de réparation — cahier-des-charges.md:161-168 et recalcul du statut :96-100."""

import re
from decimal import Decimal

import pytest

from apps.audit.models import AuditLog
from apps.fleet.models import StatutVehicule
from apps.fleet.services import definir_statut
from apps.fleet.tests.factories import VehiculeFactory
from apps.garage import services
from apps.garage.exceptions import CoutInvalide, TransitionOrInterdite
from apps.garage.models import LieuReparation, StatutOr, TypeOr
from apps.missions.tests.test_services import _affectee, _en_cours

pytestmark = pytest.mark.django_db


def _ouvrir(vehicule=None, **surcharges):
    donnees = dict(
        type_or=TypeOr.CURATIF, lieu=LieuReparation.INTERNE, motif="Fuite d'huile"
    )
    donnees.update(surcharges)
    return services.ouvrir_or(vehicule or VehiculeFactory(), **donnees)


def _statut(vehicule):
    vehicule.refresh_from_db()
    return vehicule.statut


# --- ouverture ---


def test_ouvrir_cree_un_or_ouvert_numerote_et_passe_le_camion_en_maintenance():
    camion = VehiculeFactory()

    ordre = _ouvrir(camion, type_or=TypeOr.PNEUMATIQUES, lieu=LieuReparation.EXTERNE)

    assert re.fullmatch(r"OR-\d{4}-0001", ordre.numero)
    assert ordre.statut == StatutOr.OUVERT
    assert (ordre.type_or, ordre.lieu) == (TypeOr.PNEUMATIQUES, LieuReparation.EXTERNE)
    assert _statut(camion) == StatutVehicule.EN_MAINTENANCE


def test_les_numeros_d_or_sont_consecutifs():
    assert _ouvrir().numero.endswith("-0001")
    assert _ouvrir().numero.endswith("-0002")


def test_les_or_et_les_missions_ont_des_compteurs_distincts():
    _affectee()  # consomme MIS-...-0001

    assert _ouvrir().numero.endswith("-0001")


def test_ouvrir_un_or_sur_un_camion_en_mission_signale_une_panne_en_route():
    mission = _en_cours()

    _ouvrir(mission.vehicule)

    assert _statut(mission.vehicule) == StatutVehicule.EN_MAINTENANCE


def test_l_ouverture_et_la_cloture_sont_auditees():
    ordre = _ouvrir()
    services.cloturer_or(ordre)

    entrees = AuditLog.objects.filter(entite="OrdreReparation", entite_id=ordre.pk)
    assert entrees.get(action="CREATE").module == "PARC_AUTO"
    assert entrees.get(action="UPDATE").nouvelle_valeur["statut"] == "CLOTURE"


# --- clôture : enregistrement ---


def test_cloturer_enregistre_la_main_d_oeuvre_et_la_date():
    ordre = _ouvrir()

    services.cloturer_or(ordre, cout_main_oeuvre=Decimal("45000"))

    ordre.refresh_from_db()
    assert ordre.statut == StatutOr.CLOTURE
    assert ordre.date_cloture is not None
    assert ordre.cout_main_oeuvre == Decimal("45000.00")


def test_cloturer_refuse_un_or_deja_cloture():
    ordre = _ouvrir()
    services.cloturer_or(ordre)

    with pytest.raises(TransitionOrInterdite):
        services.cloturer_or(ordre)


def test_cloturer_refuse_une_main_d_oeuvre_negative_et_laisse_l_or_ouvert():
    camion = VehiculeFactory()
    ordre = _ouvrir(camion)

    with pytest.raises(CoutInvalide):
        services.cloturer_or(ordre, cout_main_oeuvre=Decimal("-1"))

    ordre.refresh_from_db()
    assert ordre.statut == StatutOr.OUVERT
    assert _statut(camion) == StatutVehicule.EN_MAINTENANCE


# --- clôture : recalcul du statut, règle par règle ---


def test_regle_4_aucun_autre_or_ni_mission_le_camion_redevient_disponible():
    camion = VehiculeFactory()
    ordre = _ouvrir(camion)

    services.cloturer_or(ordre)

    assert _statut(camion) == StatutVehicule.DISPONIBLE


def test_regle_1_un_autre_or_ouvert_maintient_le_camion_en_maintenance():
    camion = VehiculeFactory()
    premier = _ouvrir(camion)
    second = _ouvrir(camion)

    services.cloturer_or(premier)
    assert _statut(camion) == StatutVehicule.EN_MAINTENANCE

    services.cloturer_or(second)
    assert _statut(camion) == StatutVehicule.DISPONIBLE


def test_regle_2_mission_affectee_le_camion_repasse_en_mission():
    mission = _affectee()
    ordre = _ouvrir(mission.vehicule)

    services.cloturer_or(ordre)

    assert _statut(mission.vehicule) == StatutVehicule.EN_MISSION


def test_regle_2_panne_en_cours_de_mission_le_camion_repasse_en_mission():
    mission = _en_cours()
    ordre = _ouvrir(mission.vehicule)

    services.cloturer_or(ordre)

    assert _statut(mission.vehicule) == StatutVehicule.EN_MISSION


@pytest.mark.parametrize(
    "statut", [StatutVehicule.IMMOBILISE, StatutVehicule.HORS_SERVICE]
)
def test_regle_3_immobilise_ou_hors_service_pose_pendant_l_or_est_conserve(statut):
    camion = VehiculeFactory()
    ordre = _ouvrir(camion)
    definir_statut(camion, statut)

    services.cloturer_or(ordre)

    assert _statut(camion) == statut


def test_regle_1_prime_sur_les_regles_2_et_3():
    mission = _affectee()
    camion = mission.vehicule
    premier = _ouvrir(camion)
    _ouvrir(camion)
    definir_statut(camion, StatutVehicule.IMMOBILISE)

    services.cloturer_or(premier)

    assert _statut(camion) == StatutVehicule.EN_MAINTENANCE


def test_la_cloture_d_un_or_ne_touche_pas_les_autres_camions():
    autre = VehiculeFactory()
    _ouvrir(autre)
    ordre = _ouvrir()

    services.cloturer_or(ordre)

    assert _statut(autre) == StatutVehicule.EN_MAINTENANCE


# --- consultation ---


def test_vehicule_a_or_ouvert():
    camion = VehiculeFactory()
    assert services.vehicule_a_or_ouvert(camion) is False

    ordre = _ouvrir(camion)
    assert services.vehicule_a_or_ouvert(camion) is True

    services.cloturer_or(ordre)
    assert services.vehicule_a_or_ouvert(camion) is False


# --- enchaînement avec missions ---


def test_une_mission_affectee_peut_demarrer_apres_la_reparation_de_son_camion():
    from apps.missions import services as missions_services
    from apps.missions.models import StatutMission

    mission = _affectee()
    services.cloturer_or(_ouvrir(mission.vehicule))
    assert _statut(mission.vehicule) == StatutVehicule.EN_MISSION  # règle 2 du CDC

    missions_services.demarrer_mission(mission)

    mission.refresh_from_db()
    assert mission.statut == StatutMission.EN_COURS_DEPART
```

#### `apps/garage/tests/test_statut_vehicule.py`

*180 lignes* — Immobilisation, mise hors service et remise en service — cahier-des-charges.md:91-100.

```python
"""Immobilisation, mise hors service et remise en service — cahier-des-charges.md:91-100."""

import pytest

from apps.fleet.models import StatutVehicule
from apps.fleet.services import definir_statut
from apps.fleet.tests.factories import VehiculeFactory
from apps.garage import services
from apps.garage.exceptions import StatutVehiculeInvalide
from apps.garage.models import LieuReparation, TypeOr
from apps.missions.tests.test_services import _affectee, _en_cours, _livree

pytestmark = pytest.mark.django_db


def _ouvrir(vehicule):
    return services.ouvrir_or(
        vehicule, type_or=TypeOr.CURATIF, lieu=LieuReparation.INTERNE, motif="Panne"
    )


def _statut(vehicule):
    vehicule.refresh_from_db()
    return vehicule.statut


# --- immobiliser / hors service ---


def test_immobiliser_un_camion_disponible():
    camion = VehiculeFactory()

    services.immobiliser_vehicule(camion)

    assert _statut(camion) == StatutVehicule.IMMOBILISE


def test_mettre_hors_service_un_camion_disponible():
    camion = VehiculeFactory()

    services.mettre_hors_service(camion)

    assert _statut(camion) == StatutVehicule.HORS_SERVICE


def test_un_camion_immobilise_peut_devenir_hors_service():
    camion = VehiculeFactory(statut=StatutVehicule.IMMOBILISE)

    services.mettre_hors_service(camion)

    assert _statut(camion) == StatutVehicule.HORS_SERVICE


def test_immobiliser_deux_fois_est_refuse():
    camion = VehiculeFactory(statut=StatutVehicule.IMMOBILISE)

    with pytest.raises(StatutVehiculeInvalide, match="déjà immobilisé"):
        services.immobiliser_vehicule(camion)


def test_mettre_hors_service_deux_fois_est_refuse():
    camion = VehiculeFactory(statut=StatutVehicule.HORS_SERVICE)

    with pytest.raises(StatutVehiculeInvalide, match="déjà hors service"):
        services.mettre_hors_service(camion)


@pytest.mark.parametrize("etape", [_affectee, _en_cours])
def test_un_camion_reserve_ou_en_route_ne_s_immobilise_pas(etape):
    camion = etape().vehicule

    with pytest.raises(StatutVehiculeInvalide, match="ouvrez un OR"):
        services.immobiliser_vehicule(camion)
    with pytest.raises(StatutVehiculeInvalide, match="ouvrez un OR"):
        services.mettre_hors_service(camion)

    assert _statut(camion) != StatutVehicule.IMMOBILISE


def test_un_camion_peut_etre_immobilise_apres_la_fin_de_sa_mission():
    camion = _livree().vehicule

    services.immobiliser_vehicule(camion)

    assert _statut(camion) == StatutVehicule.IMMOBILISE


def test_immobiliser_un_camion_pendant_un_or_conserve_l_immobilisation_a_la_cloture():
    camion = VehiculeFactory()
    ordre = _ouvrir(camion)

    services.immobiliser_vehicule(camion)
    services.cloturer_or(ordre)

    assert _statut(camion) == StatutVehicule.IMMOBILISE  # règle 3 du CDC


# --- remise en service ---


@pytest.mark.parametrize("statut", [StatutVehicule.IMMOBILISE, StatutVehicule.HORS_SERVICE])
def test_remettre_en_service_un_camion_sans_or_ni_mission_le_rend_disponible(statut):
    camion = VehiculeFactory(statut=statut)

    services.remettre_en_service(camion)

    assert _statut(camion) == StatutVehicule.DISPONIBLE


def test_remettre_en_service_avec_un_or_ouvert_donne_en_maintenance():
    camion = VehiculeFactory()
    _ouvrir(camion)
    services.immobiliser_vehicule(camion)

    services.remettre_en_service(camion)

    assert _statut(camion) == StatutVehicule.EN_MAINTENANCE


def test_remettre_en_service_avec_une_mission_reservee_donne_en_mission():
    camion = _affectee().vehicule
    definir_statut(camion, StatutVehicule.IMMOBILISE)  # ex. posé par un autre chemin

    services.remettre_en_service(camion)

    assert _statut(camion) == StatutVehicule.EN_MISSION


@pytest.mark.parametrize(
    "statut",
    [StatutVehicule.DISPONIBLE, StatutVehicule.EN_MISSION, StatutVehicule.EN_MAINTENANCE],
)
def test_remettre_en_service_refuse_un_camion_qui_n_est_pas_immobilise(statut):
    camion = VehiculeFactory(statut=statut)

    with pytest.raises(StatutVehiculeInvalide, match="immobilisé ou hors service"):
        services.remettre_en_service(camion)

    assert _statut(camion) == statut


# --- lecture ---


def test_rechercher_ordres_par_statut_type_lieu_et_texte():
    camion = VehiculeFactory(immatriculation="1111 AA 01")
    ouvert = services.ouvrir_or(
        camion, type_or=TypeOr.PNEUMATIQUES, lieu=LieuReparation.EXTERNE, motif="Crevaison avant droite"
    )
    cloture = _ouvrir(VehiculeFactory())
    services.cloturer_or(cloture)

    assert list(services.rechercher_ordres(statut="OUVERT")) == [ouvert]
    assert list(services.rechercher_ordres(type_or="PNEUMATIQUES")) == [ouvert]
    assert list(services.rechercher_ordres(lieu="EXTERNE")) == [ouvert]
    assert list(services.rechercher_ordres(recherche="crevaison")) == [ouvert]
    assert list(services.rechercher_ordres(recherche="1111 aa")) == [ouvert]
    assert list(services.rechercher_ordres(recherche=ouvert.numero)) == [ouvert]


def test_rechercher_ordres_ignore_les_valeurs_inconnues():
    _ouvrir(VehiculeFactory())

    assert services.rechercher_ordres(statut="?", type_or="?", lieu="?", recherche=" ").count() == 1


def test_ordres_du_vehicule_du_plus_recent_au_plus_ancien_avec_limite():
    camion = VehiculeFactory()
    ordres = [_ouvrir(camion) for _ in range(4)]

    recents = list(services.ordres_du_vehicule(camion, limite=3))

    assert recents == [ordres[3], ordres[2], ordres[1]]


def test_ordres_du_vehicule_ignore_les_autres_camions():
    _ouvrir(VehiculeFactory())
    camion = VehiculeFactory()

    assert list(services.ordres_du_vehicule(camion)) == []
```

#### `apps/garage/tests/test_terrain.py`

*285 lignes* — Check-list du véhicule et incidents signalés par le chauffeur.

```python
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
```

`test_statut_vehicule.py` teste **l'intégration** garage ↔ fleet ↔ missions : par exemple « un OR clôturé
remet le camion en mission s'il a une mission affectée ».

## Étape 5 — Déclarer l'application et migrer

#### `config/settings/base.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/settings/base.py (avant)
+++ config/settings/base.py (après)
@@ -60,4 +60,5 @@
     "apps.fleet",
     "apps.missions",
+    "apps.garage",
 ]
 
```

```bash
python manage.py makemigrations garage
python manage.py migrate
```

**Résultat attendu :** `Create model OrdreReparation`, `Create model ChecklistVehicule`,
`Create model Incident`, puis `Applying garage.0001_initial... OK`.

## Vérifier le chapitre

```bash
python manage.py check
```

```bash
python -m pytest apps/garage/tests/test_models.py apps/garage/tests/test_services.py apps/garage/tests/test_statut_vehicule.py apps/garage/tests/test_terrain.py -q --no-cov
```

**Résultat attendu :** `67 passed` (pour les 4 fichier(s) de tests présentés dans ce chapitre).

Essai dans le shell : ouvrir un OR sur le camion du chapitre 8 et regarder son statut changer, puis le clôturer.

```bash
python manage.py shell -c "from decimal import Decimal; from apps.fleet.models import Vehicule; from apps.garage import services as g; v = Vehicule.objects.get(vin='VIN00000000000001'); o = g.ouvrir_or(v, type_or='CURATIF', lieu='INTERNE', motif='Bruit au freinage'); v.refresh_from_db(); print(o.numero.startswith('OR-'), v.statut); g.cloturer_or(o, cout_main_oeuvre=Decimal('45000')); v.refresh_from_db(); print(v.statut)"
```

**Résultat attendu :** `True EN_MAINTENANCE`, puis `DISPONIBLE`.

> Si vous obtenez `DoesNotExist` ou une erreur sur `type_or` : vérifiez le VIN (`VIN00000000000001`, en
> majuscules, créé au chapitre 8) et les valeurs `CURATIF` / `INTERNE` dans `models.py`.

## Ce qu'il faut retenir

- Le statut d'un camion dépend de **plusieurs apps** (missions, garage) sans qu'elles se connaissent : chaque
  app passe des **faits** à la fonction pure de `fleet`.
- Un incident déclenche une **alerte**, pas une **décision** : les décisions restent humaines.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 10 : app garage (ordres de réparation, check-lists, incidents)"
```

---

[← Chapitre 9](09-missions.md) · [Sommaire](README.md) · [Chapitre 11 →](11-inventory.md)
