# Chapitre 8 — Les camions : l'app fleet

> 14 fichier(s) dans ce chapitre, 1189 lignes de code.

## Ce que vous allez construire

**`fleet`** : les **camions** et leurs **documents réglementaires**. Le point le plus intéressant : le
**statut d'un camion n'est jamais saisi à la main**, il est **calculé** par un algorithme.

| Statut | Quand |
|---|---|
| **En maintenance** | au moins un ordre de réparation est ouvert (règle n° 1, la plus forte) |
| **En mission** | une mission est affectée ou en cours |
| **Immobilisé** / **Hors service** | marqué à la main, et conservé tant qu'aucune règle plus forte ne s'applique |
| **Disponible** | sinon |

Et quatre **documents** par camion (carte grise, assurance, visite technique, patente), avec une **alerte 30
jours avant** l'expiration.

## Prérequis

- Chapitres 1 à 7 terminés.

## Notions Django de ce chapitre

- **Fonction pure** : une fonction dont le résultat ne dépend que de ses arguments et qui ne touche pas à la
  base : `calculer_statut(statut_actuel, or_ouverts=..., mission_active=...)`. Elle est très simple à tester.
- **Inversion de dépendance par paramètres** : `fleet` ne peut pas savoir s'il existe une mission active
  (`missions` vient après). Alors **c'est l'appelant** (missions, garage) qui calcule les faits et les
  *passe en paramètre*. `fleet` reste indépendant.
- **`UniqueConstraint(condition=Q(is_deleted=False))`** : l'unicité d'un document par type et par camion,
  **hors lignes supprimées**.
- **`select_related`** : charger le camion en même temps que ses documents (une seule requête SQL).
- **Normalisation des saisies** : « ab 123 » et « AB 123 » doivent être le même camion.
- **`update_fields`** dans `save()` : n'écrire que les colonnes modifiées.

## Étape 1 — Créer l'application

```bash
mkdir -p apps/fleet/tests
```

#### Fichiers vides à créer

Ces fichiers n'ont aucun contenu ; ils servent à faire de leur dossier un *paquet Python* (sans eux, `import apps.xxx` échouerait). Créez d'abord les dossiers, puis les fichiers :

```bash
mkdir -p apps\fleet apps\fleet\tests
touch apps/fleet/__init__.py
touch apps/fleet/tests/__init__.py
```

> Sous PowerShell, `mkdir -p` s'écrit `New-Item -ItemType Directory -Force <dossier>` et `touch fichier` s'écrit `New-Item -ItemType File -Force fichier`. Vous pouvez aussi créer ces fichiers avec votre éditeur.

## Étape 2 — Modèles

#### `apps/fleet/models.py`

*110 lignes*

```python
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class StatutVehicule(models.TextChoices):
    """5 statuts — cahier-des-charges.md:91-92."""

    DISPONIBLE = "DISPONIBLE", _("Disponible")
    EN_MISSION = "EN_MISSION", _("En mission")
    EN_MAINTENANCE = "EN_MAINTENANCE", _("En maintenance")
    IMMOBILISE = "IMMOBILISE", _("Immobilisé")
    HORS_SERVICE = "HORS_SERVICE", _("Hors service")


class Vehicule(BaseModel):
    """Fiche camion — cahier-des-charges.md:88-90."""

    immatriculation = models.CharField(_("immatriculation"), max_length=20, unique=True)
    marque = models.CharField(_("marque"), max_length=50)
    modele = models.CharField(_("modèle"), max_length=50)
    annee = models.PositiveSmallIntegerField(
        _("année"), validators=[MinValueValidator(1950)]
    )
    vin = models.CharField(_("n° de châssis (VIN)"), max_length=17, unique=True)
    kilometrage = models.PositiveIntegerField(_("kilométrage compteur"), default=0)
    capacite_charge_t = models.DecimalField(
        _("capacité de charge (t)"), max_digits=6, decimal_places=2
    )
    reservoir_l = models.PositiveIntegerField(_("réservoir (L)"))
    chauffeur_habituel = models.ForeignKey(
        "drivers.Chauffeur",
        verbose_name=_("chauffeur habituel"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="vehicules_habituels",
    )
    statut = models.CharField(
        _("statut"),
        max_length=15,
        choices=StatutVehicule.choices,
        default=StatutVehicule.DISPONIBLE,
    )

    class Meta:
        verbose_name = _("véhicule")
        verbose_name_plural = _("véhicules")
        ordering = ["immatriculation"]
        indexes = [models.Index(fields=["statut"])]

    def __str__(self):
        return f"{self.immatriculation} ({self.marque} {self.modele})"


class TypeDocument(models.TextChoices):
    """4 documents réglementaires — cahier-des-charges.md:93-94."""

    CARTE_GRISE = "CARTE_GRISE", _("Carte grise")
    ASSURANCE = "ASSURANCE", _("Assurance")
    VISITE_TECHNIQUE = "VISITE_TECHNIQUE", _("Visite technique")
    PATENTE = "PATENTE", _("Patente")


class DocumentReglementaire(BaseModel):
    """Document d'un véhicule (dates de délivrance et d'expiration).

    Un seul document actif par type et par véhicule : un renouvellement met
    à jour les dates ; l'historique des anciennes dates reste dans
    ``audit_log`` (ancienne_valeur / nouvelle_valeur).
    """

    vehicule = models.ForeignKey(
        Vehicule,
        verbose_name=_("véhicule"),
        on_delete=models.PROTECT,
        related_name="documents",
    )
    type_document = models.CharField(
        _("type"), max_length=20, choices=TypeDocument.choices
    )
    date_delivrance = models.DateField(_("date de délivrance"))
    date_expiration = models.DateField(_("date d'expiration"))

    class Meta:
        verbose_name = _("document réglementaire")
        verbose_name_plural = _("documents réglementaires")
        ordering = ["date_expiration"]
        constraints = [
            models.UniqueConstraint(
                fields=["vehicule", "type_document"],
                condition=Q(is_deleted=False),
                name="document_unique_par_type_et_vehicule",
            ),
            models.CheckConstraint(
                condition=Q(date_expiration__gte=F("date_delivrance")),
                name="document_expiration_apres_delivrance",
            ),
        ]

    def __str__(self):
        return f"{self.get_type_document_display()} - {self.vehicule.immatriculation}"

    def jours_restants(self, aujourd_hui=None) -> int:
        """Jours avant expiration (négatif si déjà expiré)."""
        return (self.date_expiration - (aujourd_hui or timezone.localdate())).days
```

- **`Vehicule`** garde la plaque et le n° de châssis (VIN) uniques, le kilométrage, la capacité de charge
  (tonnes) et la taille du réservoir.
- **`DocumentReglementaire`** porte deux contraintes en base : un seul document actif par type et par camion,
  et une date d'expiration jamais antérieure à la délivrance. `jours_restants()` donne le nombre de jours
  avant l'échéance (négatif si expiré).

## Étape 3 — Règles métier

#### `apps/fleet/exceptions.py`

*18 lignes*

```python
class FlotteError(Exception):
    """Erreur métier sur la flotte (traduite en message par les écrans / l'API)."""


class DoublonVehicule(FlotteError):
    """Immatriculation ou n° de châssis (VIN) déjà utilisé."""


class VehiculeInvalide(FlotteError):
    """Donnée de fiche véhicule invalide (capacité, réservoir, année...)."""


class KilometrageInvalide(FlotteError):
    """Le compteur d'un camion ne peut pas reculer."""


class DocumentInvalide(FlotteError):
    """Dates d'un document réglementaire incohérentes."""
```

#### `apps/fleet/services.py`

*338 lignes* — Logique métier de la flotte — conventions.md §2.

```python
"""Logique métier de la flotte — conventions.md §2."""

from __future__ import annotations

from datetime import date, timedelta

from decimal import Decimal

from django.db import transaction
from django.db.models import Count, QuerySet
from django.utils import timezone

from apps.core.constants import DELAI_ALERTE_JOURS
from apps.core.search import filtrer_par_texte
from apps.core.services import etat_echeance

from apps.drivers.models import Chauffeur

from .exceptions import (
    DocumentInvalide,
    DoublonVehicule,
    KilometrageInvalide,
    VehiculeInvalide,
)
from .models import DocumentReglementaire, StatutVehicule, TypeDocument, Vehicule


def vehicules_disponibles() -> QuerySet[Vehicule]:
    """Camions au statut « Disponible », pour l'affectation d'une mission."""
    return Vehicule.objects.filter(statut=StatutVehicule.DISPONIBLE).order_by(
        "immatriculation"
    )


def calculer_statut(
    statut_actuel: str, *, or_ouverts: bool, mission_active: bool
) -> str:
    """Statut d'un camion selon l'algorithme du CDC (cahier-des-charges.md:96-100).

    Ordre strict des règles :
      1. d'autres OR ouverts            → En maintenance
      2. mission planifiée / en cours   → En mission
      3. marqué Immobilisé / Hors service → conservé
      4. sinon                          → Disponible

    Fonction pure : ``garage`` et ``missions`` (apps situées sous ``fleet``
    dans architecture.md:161-163) calculent ``or_ouverts`` et
    ``mission_active`` et les passent en paramètre, ``fleet`` n'a donc
    jamais à les importer.
    """
    if or_ouverts:
        return StatutVehicule.EN_MAINTENANCE
    if mission_active:
        return StatutVehicule.EN_MISSION
    if statut_actuel in (StatutVehicule.IMMOBILISE, StatutVehicule.HORS_SERVICE):
        return statut_actuel
    return StatutVehicule.DISPONIBLE


def recalculer_statut(
    vehicule: Vehicule, *, or_ouverts: bool, mission_active: bool
) -> Vehicule:
    """Applique :func:`calculer_statut` et enregistre le résultat."""
    vehicule.statut = calculer_statut(
        vehicule.statut, or_ouverts=or_ouverts, mission_active=mission_active
    )
    vehicule.save(update_fields=["statut", "updated_at"])
    return vehicule


def definir_statut(vehicule: Vehicule, statut: str) -> Vehicule:
    """Change le statut manuellement (ex. Immobilisé, Hors service)."""
    if statut not in StatutVehicule.values:
        raise ValueError(f"Statut véhicule inconnu : {statut!r}")
    vehicule.statut = statut
    vehicule.save(update_fields=["statut", "updated_at"])
    return vehicule


def liberer_apres_mission(vehicule: Vehicule) -> Vehicule:
    """Fin de mission : « En mission » → « Disponible » (cahier-des-charges.md:139).

    Un camion passé entre-temps en maintenance, immobilisé ou hors service
    garde ce statut : seule la mission le libérait, pas le reste.
    """
    if vehicule.statut == StatutVehicule.EN_MISSION:
        return definir_statut(vehicule, StatutVehicule.DISPONIBLE)
    return vehicule


def enregistrer_kilometrage(vehicule: Vehicule, kilometrage: int) -> Vehicule:
    """Met à jour le compteur ; il ne peut jamais reculer (cahier-des-charges.md:139)."""
    if kilometrage < vehicule.kilometrage:
        raise ValueError("Le kilométrage ne peut pas diminuer.")
    vehicule.kilometrage = kilometrage
    vehicule.save(update_fields=["kilometrage", "updated_at"])
    return vehicule


def documents_a_renouveler(
    *, aujourd_hui: date | None = None, jours: int = DELAI_ALERTE_JOURS
) -> QuerySet[DocumentReglementaire]:
    """Documents expirant d'ici ``jours`` jours, ou déjà expirés.

    Alimente l'alerte préventive à 30 jours (cahier-des-charges.md:95) et le
    centre d'alertes du tableau de bord (cahier-des-charges.md:231-232).
    """
    limite = (aujourd_hui or timezone.localdate()) + timedelta(days=jours)
    return DocumentReglementaire.objects.select_related("vehicule").filter(
        date_expiration__lte=limite
    )


# --- fiche véhicule (cahier-des-charges.md:88-90) ---


def vehicules_queryset() -> QuerySet[Vehicule]:
    """Camions avec leur chauffeur habituel chargé (évite les requêtes en boucle)."""
    return Vehicule.objects.select_related("chauffeur_habituel__personnel")


def _normaliser(immatriculation: str, vin: str) -> tuple[str, str]:
    return " ".join(immatriculation.upper().split()), vin.strip().upper()


def _verifier_fiche(
    *,
    immatriculation: str,
    vin: str,
    capacite_charge_t: Decimal,
    reservoir_l: int,
    exclure: Vehicule | None = None,
) -> None:
    if not immatriculation:
        raise VehiculeInvalide("L'immatriculation est obligatoire.")
    if not vin:
        raise VehiculeInvalide("Le n° de châssis (VIN) est obligatoire.")
    if capacite_charge_t <= 0:
        raise VehiculeInvalide("La capacité de charge doit être strictement positive.")
    if reservoir_l <= 0:
        raise VehiculeInvalide("La capacité du réservoir doit être strictement positive.")
    # all_objects : l'unicité en base compte aussi les camions supprimés logiquement.
    autres = Vehicule.all_objects.exclude(pk=exclure.pk if exclure else None)
    if autres.filter(immatriculation=immatriculation).exists():
        raise DoublonVehicule(f"L'immatriculation {immatriculation} est déjà utilisée.")
    if autres.filter(vin=vin).exists():
        raise DoublonVehicule(f"Le n° de châssis {vin} est déjà utilisé.")


@transaction.atomic
def creer_vehicule(
    *,
    immatriculation: str,
    marque: str,
    modele: str,
    annee: int,
    vin: str,
    kilometrage: int,
    capacite_charge_t: Decimal,
    reservoir_l: int,
    chauffeur_habituel: Chauffeur | None = None,
) -> Vehicule:
    """Crée un camion « Disponible ». Immatriculation et VIN sont normalisés
    (majuscules, espaces) pour qu'« ab 123 » et « AB 123 » ne fassent pas deux camions."""
    immatriculation, vin = _normaliser(immatriculation, vin)
    _verifier_fiche(
        immatriculation=immatriculation,
        vin=vin,
        capacite_charge_t=capacite_charge_t,
        reservoir_l=reservoir_l,
    )
    return Vehicule.objects.create(
        immatriculation=immatriculation,
        marque=marque.strip(),
        modele=modele.strip(),
        annee=annee,
        vin=vin,
        kilometrage=kilometrage,
        capacite_charge_t=capacite_charge_t,
        reservoir_l=reservoir_l,
        chauffeur_habituel=chauffeur_habituel,
    )


@transaction.atomic
def modifier_vehicule(
    vehicule: Vehicule,
    *,
    immatriculation: str,
    marque: str,
    modele: str,
    annee: int,
    vin: str,
    kilometrage: int,
    capacite_charge_t: Decimal,
    reservoir_l: int,
    chauffeur_habituel: Chauffeur | None = None,
) -> Vehicule:
    """Met à jour la fiche (le statut ne se modifie pas ici : il est calculé).

    Le compteur ne peut pas reculer (cahier-des-charges.md:139)."""
    type(vehicule)._base_manager.select_for_update().filter(pk=vehicule.pk).first()
    vehicule.refresh_from_db()
    immatriculation, vin = _normaliser(immatriculation, vin)
    _verifier_fiche(
        immatriculation=immatriculation,
        vin=vin,
        capacite_charge_t=capacite_charge_t,
        reservoir_l=reservoir_l,
        exclure=vehicule,
    )
    if kilometrage < vehicule.kilometrage:
        raise KilometrageInvalide(
            f"Le compteur ({vehicule.kilometrage} km) ne peut pas diminuer."
        )
    vehicule.immatriculation = immatriculation
    vehicule.marque = marque.strip()
    vehicule.modele = modele.strip()
    vehicule.annee = annee
    vehicule.vin = vin
    vehicule.kilometrage = kilometrage
    vehicule.capacite_charge_t = capacite_charge_t
    vehicule.reservoir_l = reservoir_l
    vehicule.chauffeur_habituel = chauffeur_habituel
    vehicule.save()
    return vehicule


def rechercher_vehicules(
    *, statut: str | None = None, recherche: str = "", documents_a_renouveler: bool = False
) -> QuerySet[Vehicule]:
    """Camions filtrés par statut, texte (immatriculation, marque, modèle, VIN)
    et/ou présence d'un document à renouveler."""
    vehicules = vehicules_queryset()
    if statut in StatutVehicule.values:
        vehicules = vehicules.filter(statut=statut)
    vehicules = filtrer_par_texte(
        vehicules, recherche, "immatriculation", "marque", "modele", "vin"
    )
    if documents_a_renouveler:
        vehicules = vehicules.filter(pk__in=vehicules_avec_documents_a_renouveler())
    return vehicules


# --- documents réglementaires (cahier-des-charges.md:93-95) ---


def repartition_statuts() -> dict[str, int]:
    """Nombre de camions par statut (tous les statuts, y compris à 0) et total.

    Tableau de bord d'exploitation : disponibles / en mission / au garage
    (cahier-des-charges.md:229-230).
    """
    comptes = dict.fromkeys(StatutVehicule.values, 0)
    for statut, nombre in Vehicule.objects.values_list("statut").annotate(n=Count("pk")):
        comptes[statut] = nombre
    comptes["total"] = sum(comptes.values())
    return comptes


def vehicules_avec_documents_a_renouveler(
    *, aujourd_hui: date | None = None, jours: int = DELAI_ALERTE_JOURS
) -> set[int]:
    """Identifiants des camions ayant au moins un document expiré ou expirant."""
    return set(
        documents_a_renouveler(aujourd_hui=aujourd_hui, jours=jours).values_list(
            "vehicule_id", flat=True
        )
    )


@transaction.atomic
def enregistrer_document(
    vehicule: Vehicule,
    *,
    type_document: str,
    date_delivrance: date,
    date_expiration: date,
) -> tuple[DocumentReglementaire, bool]:
    """Enregistre un document ou le renouvelle (un seul actif par type et par camion).

    Un renouvellement met à jour les dates ; l'historique des anciennes dates
    reste dans ``audit_log``. Retourne ``(document, cree)``.
    """
    if type_document not in TypeDocument.values:
        raise DocumentInvalide(f"Type de document inconnu : {type_document!r}")
    if date_expiration < date_delivrance:
        raise DocumentInvalide(
            "La date d'expiration ne peut pas précéder la date de délivrance."
        )
    document = DocumentReglementaire.objects.filter(
        vehicule=vehicule, type_document=type_document
    ).first()
    if document is None:
        document = DocumentReglementaire.objects.create(
            vehicule=vehicule,
            type_document=type_document,
            date_delivrance=date_delivrance,
            date_expiration=date_expiration,
        )
        return document, True
    document.date_delivrance = date_delivrance
    document.date_expiration = date_expiration
    document.save()
    return document, False


def etat_documents(
    vehicule: Vehicule, *, aujourd_hui: date | None = None, jours: int = DELAI_ALERTE_JOURS
) -> list[dict]:
    """Situation des 4 documents réglementaires d'un camion, dans l'ordre du CDC.

    ``etat`` : EXPIRE (date dépassée), A_RENOUVELER (échéance dans ``jours``
    jours ou moins), VALIDE, MANQUANT (jamais enregistré).
    """
    aujourd_hui = aujourd_hui or timezone.localdate()
    existants = {
        d.type_document: d
        for d in DocumentReglementaire.objects.filter(vehicule=vehicule)
    }
    situation = []
    for code, libelle in TypeDocument.choices:
        document = existants.get(code)
        etat, restants = etat_echeance(
            document.date_expiration if document else None,
            aujourd_hui=aujourd_hui,
            jours=jours,
        )
        situation.append(
            {
                "code": code,
                "libelle": libelle,
                "document": document,
                "etat": etat,
                "jours_restants": restants,
            }
        )
    return situation
```

Lisez dans cet ordre :

1. **`calculer_statut`** : l'algorithme du cahier des charges en 4 lignes, dans l'ordre strict des règles.
2. **`recalculer_statut`** : applique l'algorithme et enregistre.
3. **`creer_vehicule` / `modifier_vehicule`** : normalisent plaque et VIN, refusent les doublons
   (`DoublonVehicule`) et un compteur qui reculerait (`KilometrageInvalide`).
4. **`enregistrer_document` / `etat_documents`** : renouvellement d'un document et état des quatre documents
   (valide, à renouveler, expiré, manquant).
5. **`documents_a_renouveler`**, **`vehicules_avec_documents_a_renouveler`**, **`repartition_statuts`** :
   des *lectures* qui alimenteront les alertes et le tableau de bord.

#### `apps/fleet/permissions.py`

*12 lignes* — Qui peut consulter et modifier la flotte.

```python
"""Qui peut consulter et modifier la flotte.

Cahier-des-charges.md:44-55 : la DIRECTION assure la « gestion flotte + chauffeurs »
et le PARCAUTO la « gestion technique véhicules, renouvellement pièces
administratives ». L'ADMIN a tous les droits. Les autres rôles n'ont pas accès au
parc auto (FINANCES : « pas d'accès parc auto » ; CHARGE_CLIENTELE et RH : idem).
"""

from apps.accounts.models import Role

CONSULTATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.PARCAUTO})
MODIFICATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.PARCAUTO})
```

#### `apps/fleet/sections.py`

*9 lignes* — Blocs affichés dans la fiche d'un camion par des apps situées en dessous.

```python
"""Blocs affichés dans la fiche d'un camion par des apps situées en dessous.

Fournisseurs appelés avec ``(vehicule, utilisateur)`` — voir ``core/sections.py``.
``garage`` y ajoute l'historique de maintenance et les actions d'immobilisation.
"""

from apps.core.sections import RegistreSections

DETAIL_VEHICULE = RegistreSections()
```

`DETAIL_VEHICULE` : le registre où `garage` ajoutera son bloc « Maintenance » (chapitre 10).

## Étape 4 — Administration, démarrage, tests

#### `apps/fleet/admin.py`

*22 lignes*

```python
from django.contrib import admin

from .models import DocumentReglementaire, Vehicule


class DocumentInline(admin.TabularInline):
    model = DocumentReglementaire
    extra = 0

    def get_queryset(self, request):
        return DocumentReglementaire.objects.all()


@admin.register(Vehicule)
class VehiculeAdmin(admin.ModelAdmin):
    list_display = ("immatriculation", "marque", "modele", "statut", "kilometrage")
    list_filter = ("statut", "marque")
    search_fields = ("immatriculation", "vin")
    inlines = [DocumentInline]

    def get_queryset(self, request):
        return Vehicule.objects.all()
```

#### `apps/fleet/apps.py`

*20 lignes*

```python
from django.apps import AppConfig


class FleetConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.fleet'
    label = 'fleet'

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer
        from apps.audit.registry import audit_model

        from . import permissions
        from .models import DocumentReglementaire, Vehicule

        audit_model(Vehicule, module="PARC_AUTO")
        audit_model(DocumentReglementaire, module="PARC_AUTO")
        enregistrer(
            EntreeMenu("Flotte", "fleet:liste", "fa-truck", permissions.CONSULTATION, ordre=20)
        )
```

#### `apps/fleet/tests/factories.py`

*30 lignes*

```python
from datetime import date
from decimal import Decimal

import factory

from apps.fleet.models import DocumentReglementaire, TypeDocument, Vehicule


class VehiculeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Vehicule

    immatriculation = factory.Sequence(lambda n: f"{1000 + n} AB 01")
    marque = "Mercedes-Benz"
    modele = "Actros"
    annee = 2020
    vin = factory.Sequence(lambda n: f"VIN{n:014d}")
    kilometrage = 120000
    capacite_charge_t = Decimal("25.00")
    reservoir_l = 600


class DocumentReglementaireFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DocumentReglementaire

    vehicule = factory.SubFactory(VehiculeFactory)
    type_document = TypeDocument.ASSURANCE
    date_delivrance = date(2026, 1, 1)
    date_expiration = date(2027, 1, 1)
```

#### `apps/fleet/README.md`

*22 lignes* — fleet

```markdown
# fleet

Rôle : camions et documents réglementaires — cahier-des-charges.md:88-100.

Entités : `Vehicule`, `DocumentReglementaire`. Services : `calculer_statut`
(algorithme du CDC en 4 règles, fonction pure appelée par `garage`/`missions`),
`recalculer_statut`, `definir_statut`, `documents_a_renouveler` (alerte 30 jours).

Interface (`views.py`, `templates/fleet/`) : liste filtrée (statut, texte, documents à
renouveler), fiche avec l'état des 4 documents, création et modification, enregistrement
et renouvellement d'un document. Accès : ADMIN, DIRECTION, PARCAUTO (`permissions.py`).
Le statut n'est jamais saisi à la main : il se calcule (missions, OR).
Services ajoutés : `creer_vehicule`, `modifier_vehicule` (immatriculation et VIN
normalisés, compteur qui ne recule pas), `rechercher_vehicules`, `enregistrer_document`,
`etat_documents`, `vehicules_avec_documents_a_renouveler`.

Reste à faire : marquer un camion Immobilisé / Hors service et le remettre en service
(demande de croiser garage et missions : à porter par l'écran du garage).

La fiche d'un camion accueille des blocs enregistrés par d'autres apps
(`sections.DETAIL_VEHICULE`) : `garage` y ajoute la maintenance et les actions
d'immobilisation / remise en service.
```

#### `apps/fleet/tests/test_fiche.py`

*336 lignes* — Fiche véhicule et documents réglementaires — cahier-des-charges.md:88-95.

```python
"""Fiche véhicule et documents réglementaires — cahier-des-charges.md:88-95."""

from datetime import date
from decimal import Decimal

import pytest

from apps.audit.models import AuditLog
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet import services
from apps.fleet.exceptions import (
    DocumentInvalide,
    DoublonVehicule,
    KilometrageInvalide,
    VehiculeInvalide,
)
from apps.fleet.models import DocumentReglementaire, StatutVehicule, TypeDocument

from .factories import DocumentReglementaireFactory, VehiculeFactory

pytestmark = pytest.mark.django_db

AUJOURDHUI = date(2026, 9, 20)


def _donnees(**surcharges):
    donnees = dict(
        immatriculation="1234 AB 01",
        marque="Mercedes-Benz",
        modele="Actros",
        annee=2021,
        vin="WDB9634031L123456",
        kilometrage=50000,
        capacite_charge_t=Decimal("25"),
        reservoir_l=600,
    )
    donnees.update(surcharges)
    return donnees


# --- création ---


def test_creer_vehicule_disponible_avec_les_donnees_saisies():
    chauffeur = ChauffeurFactory()

    camion = services.creer_vehicule(**_donnees(chauffeur_habituel=chauffeur))

    assert camion.statut == StatutVehicule.DISPONIBLE
    assert camion.chauffeur_habituel == chauffeur
    assert camion.capacite_charge_t == Decimal("25.00")


def test_creer_vehicule_normalise_immatriculation_et_vin():
    camion = services.creer_vehicule(
        **_donnees(immatriculation="  1234   ab  01 ", vin=" wdb9634031l123456 ")
    )

    assert camion.immatriculation == "1234 AB 01"
    assert camion.vin == "WDB9634031L123456"


def test_deux_saisies_qui_ne_different_que_par_la_casse_sont_un_doublon():
    services.creer_vehicule(**_donnees())

    with pytest.raises(DoublonVehicule, match="immatriculation"):
        services.creer_vehicule(**_donnees(immatriculation="1234 ab 01", vin="AUTRE0000000000001"))


def test_un_vin_deja_utilise_est_refuse():
    services.creer_vehicule(**_donnees())

    with pytest.raises(DoublonVehicule, match="châssis"):
        services.creer_vehicule(**_donnees(immatriculation="9999 ZZ 01"))


def test_l_immatriculation_d_un_camion_supprime_logiquement_reste_reservee():
    ancien = services.creer_vehicule(**_donnees())
    ancien.delete()

    with pytest.raises(DoublonVehicule):
        services.creer_vehicule(**_donnees(vin="AUTRE0000000000001"))


@pytest.mark.parametrize(
    "champ", [{"capacite_charge_t": Decimal("0")}, {"reservoir_l": 0}, {"immatriculation": "  "}, {"vin": ""}]
)
def test_creer_vehicule_refuse_les_donnees_invalides(champ):
    with pytest.raises(VehiculeInvalide):
        services.creer_vehicule(**_donnees(**champ))


def test_la_creation_est_auditee():
    camion = services.creer_vehicule(**_donnees())

    assert AuditLog.objects.filter(entite="Vehicule", entite_id=camion.pk, action="CREATE").exists()


# --- modification ---


def test_modifier_vehicule_met_a_jour_la_fiche():
    camion = VehiculeFactory(kilometrage=1000)

    services.modifier_vehicule(
        camion, **_donnees(immatriculation="5555 XY 01", marque="Volvo", kilometrage=1500)
    )

    camion.refresh_from_db()
    assert (camion.immatriculation, camion.marque, camion.kilometrage) == (
        "5555 XY 01",
        "Volvo",
        1500,
    )


def test_modifier_vehicule_conserve_son_statut():
    camion = VehiculeFactory(statut=StatutVehicule.EN_MAINTENANCE, kilometrage=0)

    services.modifier_vehicule(camion, **_donnees(kilometrage=0))

    camion.refresh_from_db()
    assert camion.statut == StatutVehicule.EN_MAINTENANCE


def test_modifier_vehicule_accepte_de_garder_sa_propre_immatriculation():
    camion = services.creer_vehicule(**_donnees())

    services.modifier_vehicule(camion, **_donnees(marque="MAN"))

    camion.refresh_from_db()
    assert camion.marque == "MAN"


def test_modifier_vehicule_refuse_l_immatriculation_d_un_autre_camion():
    services.creer_vehicule(**_donnees())
    autre = VehiculeFactory(kilometrage=0)

    with pytest.raises(DoublonVehicule):
        services.modifier_vehicule(autre, **_donnees(vin="AUTRE0000000000001", kilometrage=0))


def test_le_compteur_ne_peut_pas_reculer_lors_d_une_modification():
    camion = VehiculeFactory(kilometrage=10000)

    with pytest.raises(KilometrageInvalide):
        services.modifier_vehicule(camion, **_donnees(kilometrage=9999))

    camion.refresh_from_db()
    assert camion.kilometrage == 10000


def test_modifier_le_chauffeur_habituel_puis_le_retirer():
    camion = VehiculeFactory(kilometrage=0)
    chauffeur = ChauffeurFactory()

    services.modifier_vehicule(camion, **_donnees(kilometrage=0, chauffeur_habituel=chauffeur))
    camion.refresh_from_db()
    assert camion.chauffeur_habituel == chauffeur

    services.modifier_vehicule(camion, **_donnees(kilometrage=0, chauffeur_habituel=None))
    camion.refresh_from_db()
    assert camion.chauffeur_habituel is None


# --- recherche ---


def test_rechercher_vehicules_par_statut_et_texte():
    libre = VehiculeFactory(immatriculation="1000 AA 01", marque="Volvo")
    VehiculeFactory(immatriculation="2000 BB 01", marque="DAF", statut=StatutVehicule.EN_MISSION)

    assert list(services.rechercher_vehicules(statut=StatutVehicule.DISPONIBLE)) == [libre]
    assert list(services.rechercher_vehicules(recherche="volvo")) == [libre]
    assert list(services.rechercher_vehicules(recherche="1000")) == [libre]
    assert services.rechercher_vehicules(statut="???", recherche="  ").count() == 2


def test_rechercher_vehicules_ne_garde_que_ceux_avec_un_document_a_renouveler():
    alerte = VehiculeFactory()
    DocumentReglementaireFactory(
        vehicule=alerte, date_delivrance=date(2025, 1, 1), date_expiration=date(2026, 1, 1)
    )
    en_regle = VehiculeFactory()
    DocumentReglementaireFactory(vehicule=en_regle, date_expiration=date(2099, 1, 1))

    resultat = services.rechercher_vehicules(documents_a_renouveler=True)

    assert list(resultat) == [alerte]


# --- documents ---


def test_enregistrer_un_nouveau_document():
    camion = VehiculeFactory()

    document, cree = services.enregistrer_document(
        camion,
        type_document=TypeDocument.ASSURANCE,
        date_delivrance=date(2026, 1, 1),
        date_expiration=date(2027, 1, 1),
    )

    assert cree is True
    assert document.vehicule == camion


def test_renouveler_met_a_jour_le_meme_document_et_garde_l_historique_dans_l_audit():
    camion = VehiculeFactory()
    premier, _ = services.enregistrer_document(
        camion,
        type_document=TypeDocument.ASSURANCE,
        date_delivrance=date(2025, 1, 1),
        date_expiration=date(2026, 1, 1),
    )

    renouvele, cree = services.enregistrer_document(
        camion,
        type_document=TypeDocument.ASSURANCE,
        date_delivrance=date(2026, 1, 1),
        date_expiration=date(2027, 1, 1),
    )

    assert cree is False and renouvele.pk == premier.pk
    assert DocumentReglementaire.objects.filter(vehicule=camion).count() == 1
    modification = AuditLog.objects.get(
        entite="DocumentReglementaire", entite_id=premier.pk, action="UPDATE"
    )
    assert modification.ancienne_valeur["date_expiration"] == "2026-01-01"
    assert modification.nouvelle_valeur["date_expiration"] == "2027-01-01"


def test_l_expiration_ne_peut_pas_preceder_la_delivrance():
    with pytest.raises(DocumentInvalide):
        services.enregistrer_document(
            VehiculeFactory(),
            type_document=TypeDocument.PATENTE,
            date_delivrance=date(2026, 5, 1),
            date_expiration=date(2026, 4, 1),
        )


def test_un_type_de_document_inconnu_est_refuse():
    with pytest.raises(DocumentInvalide):
        services.enregistrer_document(
            VehiculeFactory(),
            type_document="PERMIS_DE_CONDUIRE",
            date_delivrance=date(2026, 1, 1),
            date_expiration=date(2027, 1, 1),
        )


# --- état des documents (alerte à 30 jours) ---


def _etats(camion):
    return {d["code"]: d for d in services.etat_documents(camion, aujourd_hui=AUJOURDHUI)}


def test_etat_documents_liste_les_4_types_dans_l_ordre_du_cdc():
    situation = services.etat_documents(VehiculeFactory(), aujourd_hui=AUJOURDHUI)

    assert [d["code"] for d in situation] == [
        "CARTE_GRISE",
        "ASSURANCE",
        "VISITE_TECHNIQUE",
        "PATENTE",
    ]
    assert {d["etat"] for d in situation} == {"MANQUANT"}


@pytest.mark.parametrize(
    ("expiration", "etat", "jours"),
    [
        (date(2026, 9, 19), "EXPIRE", -1),  # hier
        (date(2026, 9, 20), "A_RENOUVELER", 0),  # aujourd'hui : encore valable
        (date(2026, 10, 20), "A_RENOUVELER", 30),  # 30 jours : alerte
        (date(2026, 10, 21), "VALIDE", 31),  # 31 jours : pas encore
    ],
)
def test_etat_d_un_document_selon_les_jours_restants(expiration, etat, jours):
    camion = VehiculeFactory()
    DocumentReglementaireFactory(
        vehicule=camion,
        type_document=TypeDocument.ASSURANCE,
        date_delivrance=date(2025, 1, 1),
        date_expiration=expiration,
    )

    assurance = _etats(camion)["ASSURANCE"]

    assert (assurance["etat"], assurance["jours_restants"]) == (etat, jours)


def test_un_document_supprime_logiquement_redevient_manquant():
    camion = VehiculeFactory()
    document = DocumentReglementaireFactory(vehicule=camion, type_document=TypeDocument.PATENTE)
    document.delete()

    assert _etats(camion)["PATENTE"]["etat"] == "MANQUANT"


def test_vehicules_avec_documents_a_renouveler():
    alerte, tranquille = VehiculeFactory(), VehiculeFactory()
    DocumentReglementaireFactory(
        vehicule=alerte, date_delivrance=date(2026, 1, 1), date_expiration=date(2026, 10, 1)
    )
    DocumentReglementaireFactory(vehicule=tranquille, date_expiration=date(2099, 1, 1))

    ids = services.vehicules_avec_documents_a_renouveler(aujourd_hui=AUJOURDHUI)

    assert ids == {alerte.pk}


def test_vehicules_queryset_charge_le_chauffeur_habituel_sans_requete_supplementaire(
    django_assert_num_queries,
):
    chauffeur = ChauffeurFactory()
    VehiculeFactory(chauffeur_habituel=chauffeur)

    with django_assert_num_queries(1):
        camions = list(services.vehicules_queryset())
        assert camions[0].chauffeur_habituel.personnel.nom


def test_chauffeurs_actifs_exclut_les_inactifs_et_est_trie_par_nom():
    from apps.drivers.models import StatutChauffeur
    from apps.drivers import services as drivers_services

    b = ChauffeurFactory(personnel__nom="Zoro")
    a = ChauffeurFactory(personnel__nom="Adou")
    ChauffeurFactory(statut=StatutChauffeur.INACTIF)

    assert list(drivers_services.chauffeurs_actifs()) == [a, b]

```

#### `apps/fleet/tests/test_models.py`

*73 lignes*

```python
from datetime import date

import pytest
from django.db import IntegrityError, transaction

from apps.fleet.models import StatutVehicule, TypeDocument
from apps.drivers.tests.factories import ChauffeurFactory

from .factories import DocumentReglementaireFactory, VehiculeFactory

pytestmark = pytest.mark.django_db


def test_nouveau_vehicule_est_disponible_par_defaut():
    assert VehiculeFactory().statut == StatutVehicule.DISPONIBLE


def test_immatriculation_unique():
    VehiculeFactory(immatriculation="1234 AB 01")

    with pytest.raises(IntegrityError), transaction.atomic():
        VehiculeFactory(immatriculation="1234 AB 01")


def test_vin_unique():
    VehiculeFactory(vin="VIN00000000000001")

    with pytest.raises(IntegrityError), transaction.atomic():
        VehiculeFactory(vin="VIN00000000000001")


def test_chauffeur_habituel_devient_null_si_la_fiche_est_supprimee_physiquement():
    fiche = ChauffeurFactory()
    camion = VehiculeFactory(chauffeur_habituel=fiche)

    fiche.hard_delete()

    camion.refresh_from_db()
    assert camion.chauffeur_habituel is None


def test_un_seul_document_actif_par_type_et_par_vehicule():
    camion = VehiculeFactory()
    DocumentReglementaireFactory(vehicule=camion, type_document=TypeDocument.PATENTE)

    with pytest.raises(IntegrityError), transaction.atomic():
        DocumentReglementaireFactory(vehicule=camion, type_document=TypeDocument.PATENTE)


def test_document_supprime_logiquement_libere_le_type():
    camion = VehiculeFactory()
    ancien = DocumentReglementaireFactory(
        vehicule=camion, type_document=TypeDocument.PATENTE
    )
    ancien.delete()

    DocumentReglementaireFactory(vehicule=camion, type_document=TypeDocument.PATENTE)


def test_expiration_avant_delivrance_refusee_par_la_base():
    with pytest.raises(IntegrityError), transaction.atomic():
        DocumentReglementaireFactory(
            date_delivrance=date(2026, 5, 1), date_expiration=date(2026, 4, 1)
        )


def test_creation_vehicule_est_auditee():
    from apps.audit.models import AuditLog

    camion = VehiculeFactory()

    entree = AuditLog.objects.get(entite="Vehicule", entite_id=camion.pk)
    assert entree.module == "PARC_AUTO"
```

#### `apps/fleet/tests/test_services.py`

*185 lignes*

```python
from datetime import date

import pytest

from apps.fleet import services
from apps.fleet.models import StatutVehicule, TypeDocument

from .factories import DocumentReglementaireFactory, VehiculeFactory

pytestmark = pytest.mark.django_db


# --- algorithme de recalcul du statut (cahier-des-charges.md:96-100) ---


def test_regle_1_or_ouvert_donne_en_maintenance():
    statut = services.calculer_statut(
        StatutVehicule.DISPONIBLE, or_ouverts=True, mission_active=False
    )

    assert statut == StatutVehicule.EN_MAINTENANCE


def test_regle_2_mission_active_donne_en_mission():
    statut = services.calculer_statut(
        StatutVehicule.DISPONIBLE, or_ouverts=False, mission_active=True
    )

    assert statut == StatutVehicule.EN_MISSION


@pytest.mark.parametrize("bloque", [StatutVehicule.IMMOBILISE, StatutVehicule.HORS_SERVICE])
def test_regle_3_immobilise_et_hors_service_sont_conserves(bloque):
    statut = services.calculer_statut(bloque, or_ouverts=False, mission_active=False)

    assert statut == bloque


@pytest.mark.parametrize(
    "actuel", [StatutVehicule.EN_MAINTENANCE, StatutVehicule.EN_MISSION]
)
def test_regle_4_sinon_disponible(actuel):
    statut = services.calculer_statut(actuel, or_ouverts=False, mission_active=False)

    assert statut == StatutVehicule.DISPONIBLE


def test_or_ouvert_prime_sur_mission_et_sur_immobilise():
    statut = services.calculer_statut(
        StatutVehicule.IMMOBILISE, or_ouverts=True, mission_active=True
    )

    assert statut == StatutVehicule.EN_MAINTENANCE


def test_mission_active_prime_sur_immobilise():
    statut = services.calculer_statut(
        StatutVehicule.IMMOBILISE, or_ouverts=False, mission_active=True
    )

    assert statut == StatutVehicule.EN_MISSION


def test_recalculer_statut_enregistre_en_base():
    camion = VehiculeFactory(statut=StatutVehicule.EN_MAINTENANCE)

    services.recalculer_statut(camion, or_ouverts=False, mission_active=False)

    camion.refresh_from_db()
    assert camion.statut == StatutVehicule.DISPONIBLE


def test_definir_statut_accepte_immobilise():
    camion = VehiculeFactory()

    services.definir_statut(camion, StatutVehicule.IMMOBILISE)

    camion.refresh_from_db()
    assert camion.statut == StatutVehicule.IMMOBILISE


def test_definir_statut_refuse_un_statut_inconnu():
    camion = VehiculeFactory()

    with pytest.raises(ValueError):
        services.definir_statut(camion, "VOLANT")


# --- alerte documents à 30 jours (cahier-des-charges.md:95) ---


def test_document_expirant_dans_30_jours_est_signale():
    doc = DocumentReglementaireFactory(date_expiration=date(2026, 10, 20))

    resultat = services.documents_a_renouveler(aujourd_hui=date(2026, 9, 20))

    assert doc in resultat


def test_document_expirant_dans_31_jours_n_est_pas_signale():
    doc = DocumentReglementaireFactory(date_expiration=date(2026, 10, 21))

    resultat = services.documents_a_renouveler(aujourd_hui=date(2026, 9, 20))

    assert doc not in resultat


def test_document_deja_expire_est_signale():
    doc = DocumentReglementaireFactory(
        date_delivrance=date(2025, 1, 1), date_expiration=date(2026, 1, 1)
    )

    resultat = services.documents_a_renouveler(aujourd_hui=date(2026, 9, 20))

    assert doc in resultat


def test_jours_restants_negatif_quand_expire():
    doc = DocumentReglementaireFactory.build(
        date_delivrance=date(2025, 1, 1), date_expiration=date(2026, 9, 10)
    )

    assert doc.jours_restants(aujourd_hui=date(2026, 9, 20)) == -10


def test_documents_a_renouveler_utilise_les_types_du_cdc():
    assert set(TypeDocument.values) == {
        "CARTE_GRISE",
        "ASSURANCE",
        "VISITE_TECHNIQUE",
        "PATENTE",
    }


# --- fin de mission et compteur kilométrique ---


def test_liberer_apres_mission_remet_un_camion_en_mission_disponible():
    camion = VehiculeFactory(statut=StatutVehicule.EN_MISSION)

    services.liberer_apres_mission(camion)

    camion.refresh_from_db()
    assert camion.statut == StatutVehicule.DISPONIBLE


@pytest.mark.parametrize(
    "statut",
    [
        StatutVehicule.EN_MAINTENANCE,
        StatutVehicule.IMMOBILISE,
        StatutVehicule.HORS_SERVICE,
    ],
)
def test_liberer_apres_mission_conserve_les_autres_statuts(statut):
    camion = VehiculeFactory(statut=statut)

    services.liberer_apres_mission(camion)

    camion.refresh_from_db()
    assert camion.statut == statut


def test_enregistrer_kilometrage_met_a_jour_le_compteur():
    camion = VehiculeFactory(kilometrage=1000)

    services.enregistrer_kilometrage(camion, 1500)

    camion.refresh_from_db()
    assert camion.kilometrage == 1500


def test_enregistrer_kilometrage_refuse_de_reculer():
    camion = VehiculeFactory(kilometrage=1000)

    with pytest.raises(ValueError):
        services.enregistrer_kilometrage(camion, 999)


def test_vehicules_disponibles_exclut_les_autres_statuts():
    libre = VehiculeFactory(immatriculation="1000 AA 01")
    VehiculeFactory(statut=StatutVehicule.EN_MISSION)
    VehiculeFactory(statut=StatutVehicule.EN_MAINTENANCE)

    assert list(services.vehicules_disponibles()) == [libre]
```

`test_services.py` commence par les quatre cas de l'algorithme ; vous les lirez comme une spécification.

## Étape 5 — Déclarer l'application et migrer

#### `config/settings/base.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/settings/base.py (avant)
+++ config/settings/base.py (après)
@@ -55,4 +55,5 @@
     "apps.drivers",
     "apps.customers",
+    "apps.fleet",
 ]
 
```

```bash
python manage.py makemigrations fleet
python manage.py migrate
```

**Résultat attendu :** `Create model Vehicule`, `Create model DocumentReglementaire`, les contraintes, puis
`Applying fleet.0001_initial... OK`.

## Vérifier le chapitre

```bash
python manage.py check
```

```bash
python -m pytest apps/fleet/tests/test_fiche.py apps/fleet/tests/test_models.py apps/fleet/tests/test_services.py -q --no-cov
```

**Résultat attendu :** `62 passed` (pour les 3 fichier(s) de tests présentés dans ce chapitre).

Essai dans le shell : créer un camion, lui donner un ordre de réparation ouvert (simulé par le paramètre) et
voir son statut changer :

```bash
python manage.py shell -c "from decimal import Decimal; from apps.fleet import services as s; v = s.creer_vehicule(immatriculation='1234 ab 01', marque='Mercedes-Benz', modele='Actros', annee=2020, vin='vin00000000000001', kilometrage=120000, capacite_charge_t=Decimal('25'), reservoir_l=600); print(v.immatriculation, v.statut); print(s.calculer_statut(v.statut, or_ouverts=True, mission_active=True))"
```

**Résultat attendu :** `1234 AB 01 DISPONIBLE` (la plaque est **normalisée en majuscules**), puis
`EN_MAINTENANCE` (la maintenance l'emporte sur la mission).

## Ce qu'il faut retenir

- Une donnée **dérivée** (le statut) se **calcule**, elle ne se saisit pas : elle ne peut pas être fausse.
- Pour rester indépendant d'une app « du dessous », on lui fait passer les **faits en paramètres**.
- **Normaliser** à l'entrée évite les doublons invisibles.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 8 : app fleet (camions, documents réglementaires, statut calculé)"
```

---

[← Chapitre 7](07-customers.md) · [Sommaire](README.md) · [Chapitre 9 →](09-missions.md)
