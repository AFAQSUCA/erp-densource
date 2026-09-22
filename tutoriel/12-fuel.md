# Chapitre 12 — Le carburant : l'app fuel

> 14 fichier(s) dans ce chapitre, 1229 lignes de code.

## Ce que vous allez construire

**`fuel`** : les **pleins de carburant** et la **consommation**. Chaque plein est enregistré et sa
consommation est calculée, pour repérer très vite les anomalies : fuite, vol, erreur de saisie, conduite à revoir.

**La formule :** `Consommation (L/100 km) = Litres ÷ (Km actuel − Km du plein précédent) × 100`.

**Les seuils** (l'écart est mesuré par rapport à la moyenne des **3 derniers pleins du camion**) :

| Écart | Réaction |
|---|---|
| supérieur à **+20 %** | alerte **jaune** |
| supérieur à **+40 %** | alerte **rouge** |
| supérieur à **±60 %** | **saisie suspecte** : rien n'est enregistré tant que la personne n'a pas corrigé ou **confirmé** |
| consommation **> 45** ou **< 20** L/100 km | **anomalie** |

Tous les seuils sont **stricts** (« supérieur à », pas « supérieur ou égal »). Les alertes jaune/rouge et la
saisie suspecte sont indépendantes : +65 % est *à la fois* rouge et suspect.

## Prérequis

- Chapitres 1 à 11 terminés.

## Notions Django de ce chapitre

- **Champs calculés figés à la saisie** : la distance, la consommation, la moyenne de référence, l'écart et
  les alertes sont **calculés une fois** par le service et **enregistrés** avec le plein : un plein ancien
  garde l'alerte qu'il avait *à l'époque*, même si la moyenne évolue ensuite.
- **Exception « à confirmer »** : `SaisieSuspecte` est levée **sans rien enregistrer** ; l'appelant renvoie le
  même plein avec `confirmer_alerte_saisie=True`. C'est un moyen propre de demander une confirmation depuis un
  service.
- **Cohérence chronologique** : les pleins d'un camion se saisissent **dans l'ordre** (date non antérieure, km
  strictement croissant).
- **Numéro de ticket unique** : un ticket ne peut pas être saisi deux fois.
- **`Decimal.quantize`** avec `ROUND_HALF_UP` pour arrondir au centième.
- **Relever le compteur du camion** : `fuel` appelle `fleet.enregistrer_kilometrage`.
- **Signal `alerte_consommation`** : émis quand il y a quelque chose à signaler (`notifications` prévient
  le Parc Auto et la Direction).

## Étape 1 — Créer l'application

```bash
mkdir -p apps/fuel/tests
```

#### Fichiers vides à créer

Ces fichiers n'ont aucun contenu ; ils servent à faire de leur dossier un *paquet Python* (sans eux, `import apps.xxx` échouerait). Créez d'abord les dossiers, puis les fichiers :

```bash
mkdir -p apps\fuel apps\fuel\tests
touch apps/fuel/__init__.py
touch apps/fuel/tests/__init__.py
```

> Sous PowerShell, `mkdir -p` s'écrit `New-Item -ItemType Directory -Force <dossier>` et `touch fichier` s'écrit `New-Item -ItemType File -Force fichier`. Vous pouvez aussi créer ces fichiers avec votre éditeur.

## Étape 2 — Modèle et règles

#### `apps/fuel/models.py`

*112 lignes*

```python
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class NiveauAlerte(models.TextChoices):
    """Alerte de surconsommation — cahier-des-charges.md:152-155."""

    AUCUNE = "AUCUNE", _("Aucune")
    JAUNE = "JAUNE", _("Jaune (> +20 %)")
    ROUGE = "ROUGE", _("Rouge (> +40 %)")


class Plein(BaseModel):
    """Plein de carburant d'un camion — cahier-des-charges.md:148-150.

    Les champs calculés (distance, consommation, écart, alertes) sont figés à
    la saisie : ils dépendent de l'historique tel qu'il était à ce moment-là.
    Ils ne se renseignent que par ``services.enregistrer_plein``.
    """

    date_plein = models.DateField(_("date"))
    vehicule = models.ForeignKey(
        "fleet.Vehicule",
        verbose_name=_("camion"),
        on_delete=models.PROTECT,
        related_name="pleins",
    )
    chauffeur = models.ForeignKey(
        "drivers.Chauffeur",
        verbose_name=_("chauffeur"),
        on_delete=models.PROTECT,
        related_name="pleins",
    )
    station = models.CharField(_("station"), max_length=100)
    quantite_litres = models.DecimalField(
        _("quantité (L)"), max_digits=8, decimal_places=2
    )
    prix_unitaire = models.DecimalField(
        _("prix unitaire (FCFA/L)"), max_digits=10, decimal_places=2
    )
    km_compteur = models.PositiveIntegerField(_("km compteur"))
    numero_ticket = models.CharField(_("n° ticket / reçu"), max_length=50)

    km_precedent = models.PositiveIntegerField(
        _("km du plein précédent"), null=True, blank=True
    )
    distance_km = models.PositiveIntegerField(
        _("distance depuis le plein précédent"), null=True, blank=True
    )
    consommation = models.DecimalField(
        _("consommation (L/100 km)"),
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
    )
    moyenne_reference = models.DecimalField(
        _("moyenne des pleins précédents (L/100 km)"),
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
    )
    ecart_pct = models.DecimalField(
        _("écart à la moyenne (%)"),
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
    )
    niveau_alerte = models.CharField(
        _("alerte"),
        max_length=6,
        choices=NiveauAlerte.choices,
        default=NiveauAlerte.AUCUNE,
    )
    alerte_saisie = models.BooleanField(
        _("alerte de saisie (écart > ±60 %)"), default=False
    )
    anomalie = models.BooleanField(
        _("anomalie (> 45 ou < 20 L/100 km)"), default=False
    )

    class Meta:
        verbose_name = _("plein")
        verbose_name_plural = _("pleins")
        ordering = ["-date_plein", "-pk"]
        indexes = [models.Index(fields=["vehicule", "date_plein"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(quantite_litres__gt=0), name="plein_quantite_positive"
            ),
            models.CheckConstraint(
                condition=Q(prix_unitaire__gt=0), name="plein_prix_positif"
            ),
            models.UniqueConstraint(
                fields=["numero_ticket"],
                condition=Q(is_deleted=False),
                name="plein_ticket_unique",
            ),
        ]

    def __str__(self):
        return f"{self.date_plein} {self.vehicule.immatriculation} {self.quantite_litres} L"

    @property
    def montant_total(self):
        """Coût du plein en FCFA."""
        return self.quantite_litres * self.prix_unitaire
```

#### `apps/fuel/exceptions.py`

*37 lignes*

```python
from decimal import Decimal


class CarburantError(Exception):
    """Erreur métier sur la saisie d'un plein."""


class SaisieInvalide(CarburantError):
    """Quantité, prix ou n° de ticket invalide."""


class TicketDejaEnregistre(CarburantError):
    """Ce n° de ticket existe déjà : probable double saisie."""


class HorsChronologie(CarburantError):
    """Plein antérieur au dernier plein enregistré du camion."""


class KilometrageInvalide(CarburantError):
    """Le km compteur doit dépasser celui du plein précédent."""


class SaisieSuspecte(CarburantError):
    """Écart > ±60 % : à vérifier puis à confirmer (cahier-des-charges.md:155).

    Rien n'est enregistré tant que la saisie n'est pas confirmée.
    """

    def __init__(self, ecart_pct: Decimal, consommation: Decimal, moyenne: Decimal):
        self.ecart_pct = ecart_pct
        self.consommation = consommation
        self.moyenne = moyenne
        super().__init__(
            f"Consommation de {consommation} L/100 km, soit {ecart_pct:+} % par rapport "
            f"à la moyenne ({moyenne} L/100 km) : vérifiez litres et kilométrage."
        )
```

#### `apps/fuel/services.py`

*348 lignes* — Logique métier du carburant — cahier-des-charges.md:147-157.

```python
"""Logique métier du carburant — cahier-des-charges.md:147-157.

    Conso (L/100 km) = (Litres ÷ (Km actuel − Km précédent)) × 100

Alertes (écart de la conso à la moyenne des 3 derniers pleins) :
jaune > +20 %, rouge > +40 %, alerte de saisie > ±60 %. Anomalie : conso
> 45 ou < 20 L/100 km. Tous les seuils sont stricts (« > »).
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Q, QuerySet

from apps.core.search import filtrer_par_texte
from apps.drivers.models import Chauffeur
from apps.fleet import services as fleet_services
from apps.fleet.models import Vehicule

from .exceptions import (
    HorsChronologie,
    KilometrageInvalide,
    SaisieInvalide,
    SaisieSuspecte,
    TicketDejaEnregistre,
)
from .models import NiveauAlerte, Plein
from .signals import alerte_consommation

CENTIME = Decimal("0.01")
NB_PLEINS_REFERENCE = 3
SEUIL_JAUNE = Decimal("20")
SEUIL_ROUGE = Decimal("40")
SEUIL_SAISIE = Decimal("60")
CONSO_MAX = Decimal("45")
CONSO_MIN = Decimal("20")

logger = logging.getLogger(__name__)


def calculer_consommation(litres: Decimal, distance_km: int) -> Decimal:
    """Consommation en L/100 km, arrondie au centième."""
    return (Decimal(litres) / Decimal(distance_km) * 100).quantize(
        CENTIME, rounding=ROUND_HALF_UP
    )


def moyenne_reference(vehicule: Vehicule) -> Decimal | None:
    """Moyenne des consommations des 3 derniers pleins du camion.

    Moyenne arithmétique des consommations (lecture littérale du CDC). S'il y
    en a moins de 3, on utilise celles qui existent ; aucune → ``None``.
    """
    consommations = list(
        Plein.objects.filter(vehicule=vehicule, consommation__isnull=False)
        .order_by("-date_plein", "-pk")
        .values_list("consommation", flat=True)[:NB_PLEINS_REFERENCE]
    )
    if not consommations:
        return None
    return (sum(consommations) / len(consommations)).quantize(
        CENTIME, rounding=ROUND_HALF_UP
    )


def evaluer_ecart(
    consommation: Decimal, moyenne: Decimal
) -> tuple[Decimal, str, bool]:
    """Retourne ``(écart %, niveau d'alerte, alerte de saisie)``.

    Les deux alertes sont indépendantes : un écart de +65 % est à la fois
    rouge (> +40 %) et une alerte de saisie (> ±60 %).
    """
    ecart = (consommation - moyenne) / moyenne * 100
    if ecart > SEUIL_ROUGE:
        niveau = NiveauAlerte.ROUGE
    elif ecart > SEUIL_JAUNE:
        niveau = NiveauAlerte.JAUNE
    else:
        niveau = NiveauAlerte.AUCUNE
    return ecart.quantize(CENTIME, rounding=ROUND_HALF_UP), niveau, abs(ecart) > SEUIL_SAISIE


def est_anomalie(consommation: Decimal) -> bool:
    """Consommation hors de la plage plausible 20-45 L/100 km."""
    return consommation > CONSO_MAX or consommation < CONSO_MIN


@transaction.atomic
def enregistrer_plein(
    *,
    vehicule: Vehicule,
    chauffeur: Chauffeur,
    date_plein: date,
    station: str,
    quantite_litres: Decimal,
    prix_unitaire: Decimal,
    km_compteur: int,
    numero_ticket: str,
    confirmer_alerte_saisie: bool = False,
) -> Plein:
    """Enregistre un plein et calcule consommation, écart et alertes.

    - Les pleins d'un camion se saisissent dans l'ordre : date >= dernier plein
      et km strictement supérieur (sinon la formule n'a pas de sens).
    - Si l'écart dépasse ±60 %, :class:`SaisieSuspecte` est levée et rien n'est
      enregistré ; l'utilisateur vérifie puis renvoie avec
      ``confirmer_alerte_saisie=True``.
    - Le compteur du camion est relevé si ce km est supérieur.
    """
    quantite_litres, prix_unitaire = Decimal(quantite_litres), Decimal(prix_unitaire)
    if quantite_litres <= 0:
        raise SaisieInvalide("La quantité doit être strictement positive.")
    if prix_unitaire <= 0:
        raise SaisieInvalide("Le prix unitaire doit être strictement positif.")
    numero_ticket = numero_ticket.strip()
    if not numero_ticket:
        raise SaisieInvalide("Le n° de ticket est obligatoire.")
    if Plein.objects.filter(numero_ticket=numero_ticket).exists():
        raise TicketDejaEnregistre(f"Le ticket {numero_ticket} est déjà enregistré.")

    type(vehicule)._base_manager.select_for_update().filter(pk=vehicule.pk).first()
    vehicule.refresh_from_db()

    precedent = (
        Plein.objects.filter(vehicule=vehicule).order_by("-date_plein", "-pk").first()
    )
    champs_calcules: dict = {}
    if precedent is not None:
        if date_plein < precedent.date_plein:
            raise HorsChronologie(
                f"Le dernier plein de ce camion date du {precedent.date_plein} : "
                "saisissez les pleins dans l'ordre."
            )
        if km_compteur <= precedent.km_compteur:
            raise KilometrageInvalide(
                f"Le km compteur ({km_compteur}) doit dépasser celui du plein "
                f"précédent ({precedent.km_compteur})."
            )
        distance = km_compteur - precedent.km_compteur
        consommation = calculer_consommation(quantite_litres, distance)
        champs_calcules.update(
            km_precedent=precedent.km_compteur,
            distance_km=distance,
            consommation=consommation,
            anomalie=est_anomalie(consommation),
        )
        moyenne = moyenne_reference(vehicule)
        if moyenne is not None and moyenne > 0:
            ecart, niveau, saisie_suspecte = evaluer_ecart(consommation, moyenne)
            if saisie_suspecte and not confirmer_alerte_saisie:
                raise SaisieSuspecte(ecart, consommation, moyenne)
            champs_calcules.update(
                moyenne_reference=moyenne,
                ecart_pct=ecart,
                niveau_alerte=niveau,
                alerte_saisie=saisie_suspecte,
            )

    plein = Plein.objects.create(
        date_plein=date_plein,
        vehicule=vehicule,
        chauffeur=chauffeur,
        station=station,
        quantite_litres=quantite_litres,
        prix_unitaire=prix_unitaire,
        km_compteur=km_compteur,
        numero_ticket=numero_ticket,
        **champs_calcules,
    )
    if km_compteur > vehicule.kilometrage:
        fleet_services.enregistrer_kilometrage(vehicule, km_compteur)
    if (
        plein.niveau_alerte != NiveauAlerte.AUCUNE
        or plein.anomalie
        or plein.alerte_saisie
    ):
        _emettre(alerte_consommation, plein=plein)
    return plein


def _emettre(signal, **arguments) -> None:
    """Un récepteur en erreur ne doit pas faire échouer la saisie du plein."""
    for recepteur, resultat in signal.send_robust(sender=Plein, **arguments):
        if isinstance(resultat, Exception):
            logger.error("Récepteur %r en erreur", recepteur, exc_info=resultat)


# --- analyse (cahier-des-charges.md:156) ---


def consommation_moyenne(
    *, vehicule: Vehicule | None = None, chauffeur: Chauffeur | None = None
) -> Decimal | None:
    """Consommation moyenne en L/100 km : total des litres ÷ total des km x 100.

    Pondérée par la distance (un plein sur 50 km pèse moins que sur 900 km).
    Filtrable par camion et/ou par chauffeur ; sans filtre, c'est la moyenne
    globale de la flotte (tableau de bord, cahier-des-charges.md:229-230).
    ``None`` s'il n'y a encore aucune consommation calculée.
    """
    pleins = Plein.objects.filter(consommation__isnull=False)
    if vehicule is not None:
        pleins = pleins.filter(vehicule=vehicule)
    if chauffeur is not None:
        pleins = pleins.filter(chauffeur=chauffeur)
    lignes = list(pleins.values_list("quantite_litres", "distance_km"))
    distance = sum(d for _, d in lignes)
    if not distance:
        return None
    litres = sum(l for l, _ in lignes)
    return calculer_consommation(litres, distance)


def pleins_a_surveiller(*, depuis: date | None = None) -> QuerySet[Plein]:
    """Pleins en alerte (jaune/rouge), en anomalie ou à saisie suspecte confirmée.

    ``depuis`` : ne garde que les pleins de cette date ou plus récents (le centre d'alertes
    du tableau de bord n'affiche que les alertes récentes).
    """
    pleins = Plein.objects.select_related("vehicule", "chauffeur__personnel").filter(
        Q(niveau_alerte__in=[NiveauAlerte.JAUNE, NiveauAlerte.ROUGE])
        | Q(anomalie=True)
        | Q(alerte_saisie=True)
    )
    if depuis is not None:
        pleins = pleins.filter(date_plein__gte=depuis)
    return pleins


# --- lecture pour les écrans ---

ALERTES_FILTRABLES = ("JAUNE", "ROUGE", "ANOMALIE", "SAISIE", "A_SURVEILLER")


def pleins_queryset() -> QuerySet[Plein]:
    """Pleins avec camion et chauffeur chargés (évite les requêtes en boucle)."""
    return Plein.objects.select_related("vehicule", "chauffeur__personnel")


def rechercher_pleins(
    *,
    vehicule: Vehicule | None = None,
    chauffeur: Chauffeur | None = None,
    date_debut: date | None = None,
    date_fin: date | None = None,
    alerte: str = "",
    recherche: str = "",
) -> QuerySet[Plein]:
    """Pleins filtrés par camion, chauffeur, période, alerte et texte (station, ticket).

    ``alerte`` : ``JAUNE``, ``ROUGE``, ``ANOMALIE``, ``SAISIE`` (saisie suspecte
    confirmée) ou ``A_SURVEILLER`` (l'un des précédents).
    """
    pleins = pleins_queryset()
    if vehicule is not None:
        pleins = pleins.filter(vehicule=vehicule)
    if chauffeur is not None:
        pleins = pleins.filter(chauffeur=chauffeur)
    if date_debut is not None:
        pleins = pleins.filter(date_plein__gte=date_debut)
    if date_fin is not None:
        pleins = pleins.filter(date_plein__lte=date_fin)
    if alerte == "JAUNE":
        pleins = pleins.filter(niveau_alerte=NiveauAlerte.JAUNE)
    elif alerte == "ROUGE":
        pleins = pleins.filter(niveau_alerte=NiveauAlerte.ROUGE)
    elif alerte == "ANOMALIE":
        pleins = pleins.filter(anomalie=True)
    elif alerte == "SAISIE":
        pleins = pleins.filter(alerte_saisie=True)
    elif alerte == "A_SURVEILLER":
        pleins = pleins.filter(
            Q(niveau_alerte__in=[NiveauAlerte.JAUNE, NiveauAlerte.ROUGE])
            | Q(anomalie=True)
            | Q(alerte_saisie=True)
        )
    pleins = filtrer_par_texte(pleins, recherche, "station", "numero_ticket")
    return pleins


def _consommation_par_groupe(cle: str, *libelles: str) -> list[dict]:
    """Regroupe les consommations calculées par ``cle`` (camion ou chauffeur).

    Chaque groupe : litres et km cumulés, consommation moyenne pondérée par la
    distance, écart en % à la moyenne de la flotte. Trié du plus gourmand au plus
    économe. Sommes en Python : SQLite passerait par des flottants.
    """
    lignes = Plein.objects.filter(consommation__isnull=False).values_list(
        cle, *libelles, "quantite_litres", "distance_km"
    )
    groupes: dict[int, dict] = {}
    for identifiant, *noms, litres, distance in lignes:
        g = groupes.setdefault(
            identifiant,
            {
                "id": identifiant,
                "libelle": " ".join(noms),
                "litres": Decimal("0"),
                "distance": 0,
                "pleins": 0,
            },
        )
        g["litres"] += litres
        g["distance"] += distance
        g["pleins"] += 1
    moyenne_flotte = consommation_moyenne()
    resultat = []
    for g in groupes.values():
        g["consommation"] = calculer_consommation(g["litres"], g["distance"])
        g["ecart_flotte_pct"] = (
            ((g["consommation"] - moyenne_flotte) / moyenne_flotte * 100).quantize(
                CENTIME, rounding=ROUND_HALF_UP
            )
            if moyenne_flotte
            else None
        )
        g["anomalie"] = est_anomalie(g["consommation"])
        resultat.append(g)
    return sorted(resultat, key=lambda g: g["consommation"], reverse=True)


def consommation_par_vehicule() -> list[dict]:
    """Consommation moyenne de chaque camion (cahier-des-charges.md:156)."""
    return _consommation_par_groupe("vehicule_id", "vehicule__immatriculation")


def consommation_par_chauffeur() -> list[dict]:
    """Consommation moyenne de chaque chauffeur (cahier-des-charges.md:156)."""
    return _consommation_par_groupe(
        "chauffeur_id", "chauffeur__personnel__prenom", "chauffeur__personnel__nom"
    )


def cout_carburant(debut: date, fin: date) -> Decimal:
    """Valeur des pleins de la période (litres x prix unitaire), en FCFA.

    Calculée en Python : l'arithmétique décimale de SQLite passerait par des flottants.
    Alimente les charges du mois (cahier-des-charges.md:227).
    """
    lignes = Plein.objects.filter(date_plein__range=(debut, fin)).values_list(
        "quantite_litres", "prix_unitaire"
    )
    return sum((litres * prix for litres, prix in lignes), Decimal("0"))
```

Lisez les fonctions dans cet ordre, elles se lisent comme la spécification :

1. **`calculer_consommation`** : la formule, arrondie au centième.
2. **`moyenne_reference`** : moyenne des consommations des 3 derniers pleins (moins s'il y en a moins ;
   `None` s'il n'y en a aucun).
3. **`evaluer_ecart`** : renvoie `(écart en %, niveau d'alerte, saisie suspecte ?)`.
4. **`est_anomalie`** : consommation hors de la plage plausible 20-45.
5. **`enregistrer_plein`** : orchestre tout : contrôles de saisie, chronologie, calculs, saisie suspecte,
   enregistrement, relevé du compteur, signal.
6. **Lectures** : `consommation_moyenne` (globale, par camion, par chauffeur, pondérée par la distance),
   `pleins_a_surveiller`, `cout_carburant` (pour les indicateurs financiers).

#### `apps/fuel/signals.py`

*7 lignes* — Événements du carburant (souscrits par ``notifications``).

```python
"""Événements du carburant (souscrits par ``notifications``)."""

from django.dispatch import Signal

# Un plein vient d'être enregistré avec une alerte de surconsommation (jaune ou rouge), une
# anomalie ou une saisie suspecte confirmée. Argument : ``plein`` (instance enregistrée).
alerte_consommation = Signal()
```

#### `apps/fuel/permissions.py`

*12 lignes* — Qui peut consulter et saisir les pleins.

```python
"""Qui peut consulter et saisir les pleins.

Le CDC réserve la saisie du carburant au CHAUFFEUR depuis l'espace mobile
(cahier-des-charges.md:54, étape 6). Côté back-office, le suivi de la consommation
relève du parc auto : PARCAUTO et ADMIN saisissent (à partir des tickets), la
DIRECTION consulte en « lecture seule sur Parc Auto » (cahier-des-charges.md:49).
"""

from apps.accounts.models import Role

CONSULTATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.PARCAUTO})
MODIFICATION = frozenset({Role.ADMIN, Role.PARCAUTO})
```

Le CDC réserve la saisie au **chauffeur** (depuis son téléphone, chapitre 27). Côté bureau, le **Parc Auto** et
l'**ADMIN** saisissent à partir des tickets ; la **DIRECTION** consulte.

## Étape 3 — Administration, démarrage, tests

#### `apps/fuel/admin.py`

*30 lignes*

```python
from django.contrib import admin

from .models import Plein


@admin.register(Plein)
class PleinAdmin(admin.ModelAdmin):
    """Lecture seule : un plein se saisit par apps/fuel/services.py, qui calcule
    consommation et alertes à partir de l'historique."""

    list_display = (
        "date_plein",
        "vehicule",
        "chauffeur",
        "quantite_litres",
        "consommation",
        "niveau_alerte",
        "anomalie",
    )
    list_filter = ("niveau_alerte", "anomalie", "alerte_saisie")
    search_fields = ("vehicule__immatriculation", "numero_ticket", "station")

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in Plein._meta.fields]

    def has_add_permission(self, request):
        return False

    def get_queryset(self, request):
        return Plein.objects.select_related("vehicule", "chauffeur__personnel")
```

#### `apps/fuel/apps.py`

*18 lignes*

```python
from django.apps import AppConfig


class FuelConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.fuel'
    label = 'fuel'

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer

        from . import permissions

        enregistrer(
            EntreeMenu(
                "Carburant", "fuel:liste", "fa-gas-pump", permissions.CONSULTATION, ordre=45
            )
        )
```

#### `apps/fuel/tests/factories.py`

*24 lignes*

```python
from datetime import date
from decimal import Decimal

import factory

from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.fuel.models import Plein


class PleinFactory(factory.django.DjangoModelFactory):
    """Plein créé directement, sans calcul ni contrôle (tests de contraintes)."""

    class Meta:
        model = Plein

    date_plein = date(2026, 9, 1)
    vehicule = factory.SubFactory(VehiculeFactory)
    chauffeur = factory.SubFactory(ChauffeurFactory)
    station = "Total Yopougon"
    quantite_litres = Decimal("120.00")
    prix_unitaire = Decimal("655")
    km_compteur = 1400
    numero_ticket = factory.Sequence(lambda n: f"TKT-{n:05d}")
```

#### `apps/fuel/README.md`

*44 lignes* — fuel

```markdown
# fuel

Rôle : pleins de carburant et consommation — cahier-des-charges.md:147-157.

Entité : `Plein` (date, camion, chauffeur, station, litres, prix unitaire, km compteur,
n° de ticket unique). Les champs calculés (distance, consommation, moyenne de
référence, écart %, alertes) sont figés à la saisie par `services.enregistrer_plein`.

Règles (seuils stricts) :
- Conso (L/100 km) = litres ÷ (km actuel − km du plein précédent) × 100.
- Référence = moyenne arithmétique des consommations des 3 derniers pleins du camion
  (moins de 3 : ceux qui existent ; aucun : pas de comparaison).
- Jaune si écart > +20 %, rouge si > +40 %, alerte de saisie si |écart| > 60 %
  (indépendante : +65 % est rouge ET saisie suspecte).
- Anomalie si conso > 45 ou < 20 L/100 km.
- Saisie suspecte : `SaisieSuspecte` levée, rien enregistré, jusqu'à renvoi avec
  `confirmer_alerte_saisie=True`.
- Pleins dans l'ordre (date >= dernier, km strictement supérieur) ; le compteur du
  camion est relevé si le km est supérieur.

Analyse : `consommation_moyenne(vehicule=, chauffeur=)` (pondérée par la distance ;
sans filtre = moyenne globale de la flotte), `pleins_a_surveiller()`.

Reste à faire :
- Correction d'un plein saisi par erreur (aucun service de modification pour l'instant).
- Saisies hors ordre venant de la synchronisation hors-ligne du mobile (étape 6).
- Notifications : signal `alerte_consommation`, abonné par `notifications` (fait, étape 5).

Interface (`views.py`, `templates/fuel/`) : liste des pleins (filtres camion, chauffeur,
période, type d'alerte, texte) avec la consommation moyenne et le nombre de pleins à
surveiller ; saisie d'un plein ; page d'analyse par camion et par chauffeur. Accès :
ADMIN, DIRECTION (lecture) et PARCAUTO en consultation ; ADMIN et PARCAUTO saisissent
(`permissions.py`). Le chauffeur saisira lui-même depuis le mobile (étape 6).

Saisie suspecte (écart > ±60 %) : la page se réaffiche avec l'avertissement, les valeurs
saisies et un bouton « Confirmer » ; rien n'est enregistré tant que l'utilisateur n'a pas
corrigé ou confirmé. Les alertes jaune / rouge et les anomalies sont signalées par un
message après l'enregistrement.

Affichage des nombres : `core/formats.py` (`nombre`, `pourcentage_signe`) et le filtre
`pourcentage_signe` — virgule française et arrondi correct ; ne jamais écrire un nombre
dans un message avec `f"{valeur}"` (point décimal).

Recherche : `filtrer_par_texte` (core) — insensible aux accents et à la casse.
```

#### `apps/fuel/tests/test_lecture.py`

*182 lignes* — Recherche des pleins et analyse par camion / chauffeur — cahier-des-charges.md:156.

```python
"""Recherche des pleins et analyse par camion / chauffeur — cahier-des-charges.md:156."""

from datetime import date
from decimal import Decimal

import pytest

from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.fuel import services

from .test_services import _plein, _serie

pytestmark = pytest.mark.django_db


# --- recherche ---


def test_rechercher_pleins_par_camion_et_par_chauffeur():
    camion_a, camion_b = VehiculeFactory(), VehiculeFactory()
    chauffeur_a, chauffeur_b = ChauffeurFactory(), ChauffeurFactory()
    _plein(camion_a, chauffeur_a, km=1000, litres=100, jour=0)
    autre = _plein(camion_b, chauffeur_b, km=1000, litres=100, jour=0)

    assert list(services.rechercher_pleins(vehicule=camion_b)) == [autre]
    assert list(services.rechercher_pleins(chauffeur=chauffeur_b)) == [autre]


def test_rechercher_pleins_par_periode_bornes_incluses():
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    premier = _plein(camion, chauffeur, km=1000, litres=100, jour=0)  # 2026-09-01
    milieu = _plein(camion, chauffeur, km=1400, litres=120, jour=5)  # 2026-09-06
    dernier = _plein(camion, chauffeur, km=1800, litres=120, jour=10)  # 2026-09-11

    resultat = services.rechercher_pleins(date_debut=date(2026, 9, 6), date_fin=date(2026, 9, 6))

    assert list(resultat) == [milieu]
    assert set(services.rechercher_pleins(date_debut=date(2026, 9, 6))) == {milieu, dernier}
    assert set(services.rechercher_pleins(date_fin=date(2026, 9, 6))) == {premier, milieu}


def test_rechercher_pleins_par_texte_station_ou_ticket():
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    cible = _plein(
        camion, chauffeur, km=1000, litres=100, jour=0, station="Total Yopougon", numero_ticket="TKT-777"
    )
    _plein(VehiculeFactory(), chauffeur, km=1000, litres=100, jour=0)

    assert list(services.rechercher_pleins(recherche="yopougon")) == [cible]
    assert list(services.rechercher_pleins(recherche="tkt-777")) == [cible]


@pytest.mark.parametrize(
    ("alerte", "conso"),
    [
        ("JAUNE", "37"),  # +23 %
        ("ROUGE", "44"),  # +47 %
        ("ANOMALIE", "12"),  # sous 20 L/100 km (confirmé)
        ("SAISIE", "50"),  # +67 % (confirmé)
    ],
)
def test_rechercher_pleins_par_type_d_alerte(alerte, conso):
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _serie(camion, chauffeur, ["30"])
    dernier_km = 1400
    cible = _plein(
        camion, chauffeur, km=dernier_km + 400, litres=Decimal(conso) * 4, jour=5, confirmer=True
    )

    assert cible in services.rechercher_pleins(alerte=alerte)


def test_rechercher_pleins_a_surveiller_exclut_les_pleins_normaux():
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _serie(camion, chauffeur, ["30", "30"])

    assert services.rechercher_pleins(alerte="A_SURVEILLER").count() == 0
    _plein(camion, chauffeur, km=2200, litres=148, jour=5)  # 37 L/100 : jaune
    assert services.rechercher_pleins(alerte="A_SURVEILLER").count() == 1


def test_rechercher_pleins_ignore_une_alerte_inconnue_et_combine_les_criteres():
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    plein = _plein(camion, chauffeur, km=1000, litres=100, jour=0, station="Shell")
    _plein(VehiculeFactory(), chauffeur, km=1000, litres=100, jour=0, station="Shell")

    assert services.rechercher_pleins(alerte="???").count() == 2
    assert list(services.rechercher_pleins(vehicule=camion, recherche="shell")) == [plein]


def test_pleins_queryset_charge_camion_et_chauffeur_sans_requete_supplementaire(
    django_assert_num_queries,
):
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _plein(camion, chauffeur, km=1000, litres=100, jour=0)

    with django_assert_num_queries(1):
        for plein in services.pleins_queryset():
            plein.vehicule.immatriculation
            plein.chauffeur.personnel.nom


# --- analyse ---


def _deux_camions():
    camion_a, camion_b = VehiculeFactory(immatriculation="1111 AA 01"), VehiculeFactory(
        immatriculation="2222 BB 01"
    )
    chauffeur_a = ChauffeurFactory(personnel__prenom="Awa", personnel__nom="Koné")
    chauffeur_b = ChauffeurFactory(personnel__prenom="Issa", personnel__nom="Bamba")
    _serie(camion_a, chauffeur_a, ["30", "30"])  # 800 km, 240 L
    _serie(camion_b, chauffeur_b, ["40"])  # 400 km, 160 L
    return camion_a, camion_b


def test_consommation_par_vehicule_du_plus_gourmand_au_plus_econome():
    _deux_camions()

    resultat = services.consommation_par_vehicule()

    assert [g["libelle"] for g in resultat] == ["2222 BB 01", "1111 AA 01"]
    gourmand, econome = resultat
    assert (gourmand["consommation"], gourmand["pleins"], gourmand["distance"]) == (
        Decimal("40.00"),
        1,
        400,
    )
    assert (econome["consommation"], econome["pleins"], econome["distance"]) == (
        Decimal("30.00"),
        2,
        800,
    )
    assert econome["litres"] == Decimal("240.00")


def test_l_ecart_a_la_flotte_est_calcule_par_rapport_a_la_moyenne_ponderee():
    _deux_camions()  # flotte : 400 L / 1200 km = 33,33

    gourmand, econome = services.consommation_par_vehicule()

    assert gourmand["ecart_flotte_pct"] == Decimal("20.01")
    assert econome["ecart_flotte_pct"] == Decimal("-9.99")


def test_consommation_par_chauffeur_est_libellee_prenom_nom():
    _deux_camions()

    resultat = services.consommation_par_chauffeur()

    assert [g["libelle"] for g in resultat] == ["Issa Bamba", "Awa Koné"]
    assert resultat[0]["consommation"] == Decimal("40.00")


def test_deux_chauffeurs_homonymes_restent_distincts():
    camion = VehiculeFactory()
    premier = ChauffeurFactory(personnel__prenom="Awa", personnel__nom="Koné")
    second = ChauffeurFactory(personnel__prenom="Awa", personnel__nom="Koné")
    _plein(camion, premier, km=1000, litres=100, jour=0)
    _plein(camion, premier, km=1400, litres=120, jour=1)
    _plein(camion, second, km=1800, litres=160, jour=2)

    resultat = services.consommation_par_chauffeur()

    assert len(resultat) == 2
    assert {g["id"] for g in resultat} == {premier.pk, second.pk}


def test_l_analyse_signale_une_consommation_moyenne_hors_plage():
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _serie(camion, chauffeur, ["50"])  # 50 L/100 km : anomalie (confirmée)

    assert services.consommation_par_vehicule()[0]["anomalie"] is True


def test_l_analyse_est_vide_sans_consommation_calculee():
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _plein(camion, chauffeur, km=1000, litres=100, jour=0)  # premier plein : pas de conso

    assert services.consommation_par_vehicule() == []
    assert services.consommation_par_chauffeur() == []
```

#### `apps/fuel/tests/test_models.py`

*46 lignes*

```python
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from .factories import PleinFactory

pytestmark = pytest.mark.django_db


def test_montant_total_est_litres_fois_prix_unitaire():
    plein = PleinFactory.build(quantite_litres=Decimal("120.50"), prix_unitaire=Decimal("655"))

    assert plein.montant_total == Decimal("78927.500")


def test_un_plein_saisi_directement_n_a_ni_consommation_ni_alerte():
    plein = PleinFactory()

    assert plein.consommation is None
    assert plein.niveau_alerte == "AUCUNE"
    assert plein.alerte_saisie is False and plein.anomalie is False


@pytest.mark.parametrize("litres", ["0", "-5"])
def test_quantite_nulle_ou_negative_refusee_par_la_base(litres):
    with pytest.raises(IntegrityError), transaction.atomic():
        PleinFactory(quantite_litres=Decimal(litres))


def test_prix_nul_refuse_par_la_base():
    with pytest.raises(IntegrityError), transaction.atomic():
        PleinFactory(prix_unitaire=Decimal("0"))


def test_numero_de_ticket_unique():
    PleinFactory(numero_ticket="TKT-1")

    with pytest.raises(IntegrityError), transaction.atomic():
        PleinFactory(numero_ticket="TKT-1")


def test_un_ticket_d_un_plein_supprime_logiquement_peut_etre_reutilise():
    PleinFactory(numero_ticket="TKT-1").delete()

    PleinFactory(numero_ticket="TKT-1")
```

#### `apps/fuel/tests/test_services.py`

*355 lignes* — Carburant — cahier-des-charges.md:147-157.

```python
"""Carburant — cahier-des-charges.md:147-157."""

import itertools
from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.fuel import services
from apps.fuel.exceptions import (
    HorsChronologie,
    KilometrageInvalide,
    SaisieInvalide,
    SaisieSuspecte,
    TicketDejaEnregistre,
)
from apps.fuel.models import NiveauAlerte, Plein

pytestmark = pytest.mark.django_db

_tickets = itertools.count(1)
KM_INITIAL = 1000
DISTANCE = 400  # chaque plein de la série couvre 400 km : litres = conso x 4


def _plein(vehicule, chauffeur, *, km, litres, jour, confirmer=True, **surcharges):
    donnees = dict(
        vehicule=vehicule,
        chauffeur=chauffeur,
        date_plein=date(2026, 9, 1) + timedelta(days=jour),
        station="Total",
        quantite_litres=Decimal(str(litres)),
        prix_unitaire=Decimal("655"),
        km_compteur=km,
        numero_ticket=f"T-{next(_tickets)}",
        confirmer_alerte_saisie=confirmer,
    )
    donnees.update(surcharges)
    return services.enregistrer_plein(**donnees)


def _serie(vehicule, chauffeur, consommations):
    """Premier plein (sans conso) puis un plein par valeur de ``consommations``."""
    _plein(vehicule, chauffeur, km=KM_INITIAL, litres=100, jour=0)
    for rang, conso in enumerate(consommations, start=1):
        _plein(
            vehicule,
            chauffeur,
            km=KM_INITIAL + rang * DISTANCE,
            litres=Decimal(str(conso)) * 4,
            jour=rang,
        )
    return KM_INITIAL + len(consommations) * DISTANCE


def _suivant(vehicule, chauffeur, consommations, conso, confirmer=True):
    """Ajoute un plein de consommation ``conso`` après la série."""
    dernier_km = _serie(vehicule, chauffeur, consommations)
    return _plein(
        vehicule,
        chauffeur,
        km=dernier_km + DISTANCE,
        litres=Decimal(str(conso)) * 4,
        jour=len(consommations) + 1,
        confirmer=confirmer,
    )


@pytest.fixture
def camion():
    return VehiculeFactory()


@pytest.fixture
def chauffeur():
    return ChauffeurFactory()


# --- formule ---


def test_formule_litres_sur_distance_fois_100():
    assert services.calculer_consommation(Decimal("120"), 400) == Decimal("30.00")


def test_la_consommation_est_arrondie_au_centieme():
    assert services.calculer_consommation(Decimal("100"), 300) == Decimal("33.33")


def test_premier_plein_sans_consommation_ni_alerte(camion, chauffeur):
    plein = _plein(camion, chauffeur, km=KM_INITIAL, litres=100, jour=0)

    assert plein.consommation is None
    assert plein.km_precedent is None and plein.distance_km is None
    assert plein.niveau_alerte == NiveauAlerte.AUCUNE
    assert not plein.anomalie and not plein.alerte_saisie


def test_deuxieme_plein_calcule_la_consommation_sans_comparaison(camion, chauffeur):
    _plein(camion, chauffeur, km=1000, litres=100, jour=0)

    plein = _plein(camion, chauffeur, km=1400, litres=120, jour=1)

    assert plein.km_precedent == 1000
    assert plein.distance_km == 400
    assert plein.consommation == Decimal("30.00")
    assert plein.moyenne_reference is None and plein.ecart_pct is None
    assert plein.niveau_alerte == NiveauAlerte.AUCUNE


# --- alertes : seuils stricts, moyenne de référence 30 L/100 km ---


@pytest.mark.parametrize(
    ("conso", "niveau", "saisie", "anomalie"),
    [
        ("30", NiveauAlerte.AUCUNE, False, False),  # écart 0 %
        ("24", NiveauAlerte.AUCUNE, False, False),  # -20 %
        ("36", NiveauAlerte.AUCUNE, False, False),  # +20 % exactement : pas > 20
        ("36.04", NiveauAlerte.JAUNE, False, False),  # juste au-dessus
        ("37", NiveauAlerte.JAUNE, False, False),  # +23,33 %
        ("42", NiveauAlerte.JAUNE, False, False),  # +40 % exactement : pas > 40
        ("42.04", NiveauAlerte.ROUGE, False, False),
        ("44", NiveauAlerte.ROUGE, False, False),  # +46,67 %
        ("45", NiveauAlerte.ROUGE, False, False),  # 45 exactement : pas > 45
        ("45.01", NiveauAlerte.ROUGE, False, True),  # anomalie haute
        ("48", NiveauAlerte.ROUGE, False, True),  # +60 % exactement : pas > 60
        ("48.04", NiveauAlerte.ROUGE, True, True),  # +60,13 %
        ("50", NiveauAlerte.ROUGE, True, True),  # +66,67 %
        ("20", NiveauAlerte.AUCUNE, False, False),  # 20 exactement : pas < 20
        ("19.99", NiveauAlerte.AUCUNE, False, True),  # anomalie basse
        ("12", NiveauAlerte.AUCUNE, False, True),  # -60 % exactement : pas > 60
        ("11.96", NiveauAlerte.AUCUNE, True, True),  # -60,13 %
    ],
)
def test_alertes_selon_l_ecart_a_la_moyenne(camion, chauffeur, conso, niveau, saisie, anomalie):
    plein = _suivant(camion, chauffeur, ["30"], conso)

    assert plein.moyenne_reference == Decimal("30.00")
    assert plein.niveau_alerte == niveau
    assert plein.alerte_saisie is saisie
    assert plein.anomalie is anomalie


def test_l_ecart_est_enregistre_en_pourcentage(camion, chauffeur):
    plein = _suivant(camion, chauffeur, ["30"], "37")

    assert plein.ecart_pct == Decimal("23.33")


def test_une_consommation_inferieure_a_la_moyenne_ne_declenche_pas_de_surconsommation(
    camion, chauffeur
):
    plein = _suivant(camion, chauffeur, ["30"], "22")  # -26,67 %

    assert plein.niveau_alerte == NiveauAlerte.AUCUNE
    assert plein.ecart_pct == Decimal("-26.67")


# --- moyenne de référence ---


def test_la_reference_est_la_moyenne_des_3_derniers_pleins_seulement(camion, chauffeur):
    plein = _suivant(camion, chauffeur, ["20", "30", "40", "30"], "30")

    # 3 derniers avant celui-ci : 30, 40, 30 ; le plein à 20 est exclu.
    assert plein.moyenne_reference == Decimal("33.33")


def test_la_reference_utilise_les_pleins_disponibles_s_il_y_en_a_moins_de_3(camion, chauffeur):
    plein = _suivant(camion, chauffeur, ["20", "30"], "40")

    assert plein.moyenne_reference == Decimal("25.00")
    assert plein.ecart_pct == Decimal("60.00")
    assert plein.niveau_alerte == NiveauAlerte.ROUGE
    assert plein.alerte_saisie is False  # 60 % exactement


def test_la_reference_ignore_les_pleins_des_autres_camions(camion, chauffeur):
    _serie(VehiculeFactory(), chauffeur, ["50", "50"])

    plein = _suivant(camion, chauffeur, ["30"], "30")

    assert plein.moyenne_reference == Decimal("30.00")


# --- saisie suspecte (alerte de saisie, cahier-des-charges.md:155) ---


def test_saisie_suspecte_est_refusee_tant_qu_elle_n_est_pas_confirmee(camion, chauffeur):
    with pytest.raises(SaisieSuspecte) as erreur:
        _suivant(camion, chauffeur, ["30"], "50", confirmer=False)

    assert erreur.value.ecart_pct == Decimal("66.67")
    assert erreur.value.consommation == Decimal("50.00")
    assert erreur.value.moyenne == Decimal("30.00")
    assert Plein.objects.count() == 2  # premier plein + plein de la série


def test_saisie_suspecte_confirmee_est_enregistree_avec_son_alerte(camion, chauffeur):
    plein = _suivant(camion, chauffeur, ["30"], "50", confirmer=True)

    assert plein.alerte_saisie is True
    assert Plein.objects.count() == 3


def test_une_sous_consommation_suspecte_demande_aussi_confirmation(camion, chauffeur):
    with pytest.raises(SaisieSuspecte):
        _suivant(camion, chauffeur, ["30"], "10", confirmer=False)


def test_un_ecart_de_60_pourcent_pile_ne_demande_pas_confirmation(camion, chauffeur):
    plein = _suivant(camion, chauffeur, ["30"], "48", confirmer=False)

    assert plein.alerte_saisie is False


# --- contrôles de saisie ---


def test_km_inferieur_ou_egal_au_plein_precedent_refuse(camion, chauffeur):
    _plein(camion, chauffeur, km=2000, litres=100, jour=0)

    for km in (2000, 1999):
        with pytest.raises(KilometrageInvalide):
            _plein(camion, chauffeur, km=km, litres=100, jour=1)

    assert Plein.objects.count() == 1


def test_date_anterieure_au_dernier_plein_refusee(camion, chauffeur):
    _plein(camion, chauffeur, km=2000, litres=100, jour=5)

    with pytest.raises(HorsChronologie):
        _plein(camion, chauffeur, km=2500, litres=100, jour=4)


def test_deux_pleins_le_meme_jour_sont_acceptes_dans_l_ordre_des_km(camion, chauffeur):
    _plein(camion, chauffeur, km=2000, litres=100, jour=1)

    plein = _plein(camion, chauffeur, km=2300, litres=90, jour=1)

    assert plein.distance_km == 300


def test_le_chronometrage_est_propre_a_chaque_camion(camion, chauffeur):
    _plein(camion, chauffeur, km=5000, litres=100, jour=5)

    _plein(VehiculeFactory(), chauffeur, km=100, litres=100, jour=1)


@pytest.mark.parametrize("litres", ["0", "-10"])
def test_quantite_nulle_ou_negative_refusee(camion, chauffeur, litres):
    with pytest.raises(SaisieInvalide):
        _plein(camion, chauffeur, km=1000, litres=litres, jour=0)


def test_prix_nul_refuse(camion, chauffeur):
    with pytest.raises(SaisieInvalide):
        _plein(camion, chauffeur, km=1000, litres=100, jour=0, prix_unitaire=Decimal("0"))


@pytest.mark.parametrize("ticket", ["", "   "])
def test_numero_de_ticket_obligatoire(camion, chauffeur, ticket):
    with pytest.raises(SaisieInvalide):
        _plein(camion, chauffeur, km=1000, litres=100, jour=0, numero_ticket=ticket)


def test_ticket_deja_enregistre_refuse_comme_double_saisie(camion, chauffeur):
    _plein(camion, chauffeur, km=1000, litres=100, jour=0, numero_ticket="TKT-9")

    with pytest.raises(TicketDejaEnregistre):
        _plein(camion, chauffeur, km=1400, litres=100, jour=1, numero_ticket=" TKT-9 ")


# --- compteur du camion ---


def test_le_plein_releve_le_compteur_du_camion_s_il_est_superieur(chauffeur):
    camion = VehiculeFactory(kilometrage=120000)

    _plein(camion, chauffeur, km=120500, litres=100, jour=0)

    camion.refresh_from_db()
    assert camion.kilometrage == 120500


def test_le_plein_ne_fait_jamais_reculer_le_compteur(chauffeur):
    camion = VehiculeFactory(kilometrage=130000)

    _plein(camion, chauffeur, km=125000, litres=100, jour=0)

    camion.refresh_from_db()
    assert camion.kilometrage == 130000


# --- analyse par camion, par chauffeur, globale (cahier-des-charges.md:156) ---


def test_consommation_moyenne_ponderee_par_la_distance(camion, chauffeur):
    _plein(camion, chauffeur, km=1000, litres=100, jour=0)
    _plein(camion, chauffeur, km=1400, litres=120, jour=1)  # 400 km, 30 L/100
    _plein(camion, chauffeur, km=1500, litres=45, jour=2)  # 100 km, 45 L/100

    # (120 + 45) / (400 + 100) x 100 = 33,00 ; la moyenne simple donnerait 37,5.
    assert services.consommation_moyenne(vehicule=camion) == Decimal("33.00")


def test_consommation_moyenne_par_chauffeur(camion):
    econome, gourmand = ChauffeurFactory(), ChauffeurFactory()
    _plein(camion, econome, km=1000, litres=100, jour=0)
    _plein(camion, econome, km=1400, litres=100, jour=1)  # 25 L/100
    _plein(camion, gourmand, km=1800, litres=160, jour=2)  # 40 L/100

    assert services.consommation_moyenne(chauffeur=econome) == Decimal("25.00")
    assert services.consommation_moyenne(chauffeur=gourmand) == Decimal("40.00")


def test_consommation_moyenne_globale_de_la_flotte(chauffeur):
    premier, second = VehiculeFactory(), VehiculeFactory()
    _plein(premier, chauffeur, km=1000, litres=100, jour=0)
    _plein(premier, chauffeur, km=1400, litres=100, jour=1)  # 400 km, 100 L
    _plein(second, chauffeur, km=1000, litres=100, jour=0)
    _plein(second, chauffeur, km=1200, litres=100, jour=1)  # 200 km, 100 L

    assert services.consommation_moyenne() == Decimal("33.33")  # 200 L / 600 km


def test_consommation_moyenne_ignore_le_premier_plein_sans_distance(camion, chauffeur):
    _plein(camion, chauffeur, km=1000, litres=500, jour=0)  # sans conso : exclu
    _plein(camion, chauffeur, km=1400, litres=120, jour=1)

    assert services.consommation_moyenne(vehicule=camion) == Decimal("30.00")


def test_consommation_moyenne_est_none_sans_donnees(camion):
    assert services.consommation_moyenne(vehicule=camion) is None
    assert services.consommation_moyenne() is None


# --- pleins à surveiller ---


def test_pleins_a_surveiller_liste_alertes_anomalies_et_saisies_suspectes(camion, chauffeur):
    _serie(camion, chauffeur, ["30", "30"])
    normal = Plein.objects.get(km_compteur=KM_INITIAL + 2 * DISTANCE)
    jaune = _plein(camion, chauffeur, km=2200, litres=148, jour=9)  # 37 L/100
    anomalie = _plein(camion, chauffeur, km=2600, litres=72, jour=10)  # 18 L/100

    surveilles = list(services.pleins_a_surveiller())

    assert jaune in surveilles and anomalie in surveilles
    assert normal not in surveilles
```

## Étape 4 — Déclarer l'application et migrer

#### `config/settings/base.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/settings/base.py (avant)
+++ config/settings/base.py (après)
@@ -59,4 +59,5 @@
     "apps.garage",
     "apps.inventory",
+    "apps.fuel",
 ]
 
```

```bash
python manage.py makemigrations fuel
python manage.py migrate
```

**Résultat attendu :** `Create model Plein`, puis `Applying fuel.0001_initial... OK`.

## Vérifier le chapitre

```bash
python manage.py check
```

```bash
python -m pytest apps/fuel/tests/test_lecture.py apps/fuel/tests/test_models.py apps/fuel/tests/test_services.py -q --no-cov
```

**Résultat attendu :** `71 passed` (pour les 3 fichier(s) de tests présentés dans ce chapitre).

Essais dans le shell : les seuils.

```bash
python manage.py shell -c "from decimal import Decimal; from apps.fuel import services as s; c = s.calculer_consommation(Decimal('180'), 600); print(c); print(s.evaluer_ecart(Decimal('42'), Decimal('30'))); print(s.est_anomalie(Decimal('46')), s.est_anomalie(Decimal('45')))"
```

**Résultat attendu :** `30.00`, puis `(Decimal('40.00'), NiveauAlerte.JAUNE, False)` (l'écart est exactement +40 % : le seuil
rouge est **strict**, donc jaune seulement), puis `True False` (45 n'est **pas** une anomalie).

## Ce qu'il faut retenir

- Quand une règle demande une **confirmation**, une **exception qui n'enregistre rien** est plus sûre qu'un
  booléen oublié.
- **Figer** un résultat calculé au moment où il a un sens évite de le voir changer rétroactivement.
- Les seuils sont des **constantes nommées** en tête du module (`SEUIL_JAUNE`…) : faciles à lire et à ajuster.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 12 : app fuel (pleins, consommation, alertes de surconsommation)"
```

---

[← Chapitre 11](11-inventory.md) · [Sommaire](README.md) · [Chapitre 13 →](13-billing.md)
