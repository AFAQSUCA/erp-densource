# Chapitre 13 — La facturation : l'app billing

> 11 fichier(s) dans ce chapitre, 1535 lignes de code.

## Ce que vous allez construire

**`billing`** : la **facturation**, les **règlements** et les **dépenses**. Une facture suit un circuit de
validation en deux mains : **FINANCES prépare, la DIRECTION valide**.

```text
Brouillon → À valider → Émise → Partiellement payée → Payée
```

| Règle | Détail |
|---|---|
| **Une facture par mission** | créée depuis une mission **livrée ou clôturée** ; elle reprend le prix convenu, la TVA et le délai de paiement du client |
| **TVA à 3 niveaux** | 18 % par défaut (système), le taux du client, puis ajustable sur la facture **tant qu'elle est en brouillon** ; à 0 %, motif obligatoire |
| **Numéro à la validation** | `FACT-<année>-0001` n'est attribué qu'à la **validation** : un brouillon abandonné ne laisse **aucun trou** dans la numérotation |
| **Montants gelés** | dès la validation : une facture émise ne se modifie ni ne se supprime |
| **Règlements** | par virement, chèque, espèces, Wave, Orange Money, MTN ; jamais plus que le **reste à recouvrer** ; un règlement erroné s'**annule** avec un motif |
| **Facture échue** | émise, non soldée, **échéance dépassée** |
| **Dépenses** | péages, entretien, frais administratifs, autre |

## Prérequis

- Chapitres 1 à 12 terminés.

## Notions Django de ce chapitre

- **Rôle strict** : `valider` exige `strict=True` : un ADMIN ou un superutilisateur ne peut **pas** valider ;
  seule la DIRECTION le peut. La règle est dans le service, **pas dans la vue**.
- **`Decimal` et arrondi au franc** : le FCFA n'a pas de centimes. `arrondir_franc` arrondit au franc entier
  (`ROUND_HALF_UP`) ; la TVA est calculée puis arrondie **une seule fois**.
- **Annotation SQL** : `_regle_annote` calcule dans la base le montant réglé de chaque facture pour trier et
  filtrer sans boucler en Python.
- **Contrainte d'unicité conditionnelle** : une seule facture par mission (hors factures supprimées).
- **`related_name="lignes"`** : `facture.lignes.all()` liste ses lignes.
- **Constantes dérivées** : `COMPTE_DU_MODE` associe chaque mode de paiement à un compte (Banque, Caisse,
  Mobile Money).
- **Signaux** : `facture_a_valider`, `facture_validee`, `facture_refusee` : `notifications` prévient les bonnes
  personnes.

## Étape 1 — Créer l'application

```bash
mkdir -p apps/billing/tests
```

#### Fichiers vides à créer

Ces fichiers n'ont aucun contenu ; ils servent à faire de leur dossier un *paquet Python* (sans eux, `import apps.xxx` échouerait). Créez d'abord les dossiers, puis les fichiers :

```bash
mkdir -p apps\billing apps\billing\tests
touch apps/billing/__init__.py
touch apps/billing/tests/__init__.py
```

> Sous PowerShell, `mkdir -p` s'écrit `New-Item -ItemType Directory -Force <dossier>` et `touch fichier` s'écrit `New-Item -ItemType File -Force fichier`. Vous pouvez aussi créer ces fichiers avec votre éditeur.

## Étape 2 — Modèles

#### `apps/billing/models.py`

*252 lignes*

```python
from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel
from apps.customers.models import MotifExoneration


class ModePaiement(models.TextChoices):
    """6 modes de règlement — cahier-des-charges.md:189-190."""

    VIREMENT = "VIREMENT", _("Virement")
    CHEQUE = "CHEQUE", _("Chèque")
    ESPECES = "ESPECES", _("Espèces")
    WAVE = "WAVE", _("Wave")
    ORANGE_MONEY = "ORANGE_MONEY", _("Orange Money")
    MTN_MONEY = "MTN_MONEY", _("MTN Mobile Money")


class CompteTresorerie(models.TextChoices):
    """Où se trouve l'argent : le mode de paiement détermine le compte."""

    BANQUE = "BANQUE", _("Banque")
    CAISSE = "CAISSE", _("Caisse")
    MOBILE_MONEY = "MOBILE_MONEY", _("Mobile Money")


COMPTE_DU_MODE = {
    ModePaiement.VIREMENT: CompteTresorerie.BANQUE,
    ModePaiement.CHEQUE: CompteTresorerie.BANQUE,
    ModePaiement.ESPECES: CompteTresorerie.CAISSE,
    ModePaiement.WAVE: CompteTresorerie.MOBILE_MONEY,
    ModePaiement.ORANGE_MONEY: CompteTresorerie.MOBILE_MONEY,
    ModePaiement.MTN_MONEY: CompteTresorerie.MOBILE_MONEY,
}


class StatutFacture(models.TextChoices):
    """Cycle de vie : le brouillon est préparé par FINANCES, validé par la DIRECTION
    (architecture.md:432), puis suivi jusqu'au paiement complet."""

    BROUILLON = "BROUILLON", _("Brouillon")
    A_VALIDER = "A_VALIDER", _("À valider")
    EMISE = "EMISE", _("Émise")
    PARTIELLEMENT_PAYEE = "PARTIELLEMENT_PAYEE", _("Partiellement payée")
    PAYEE = "PAYEE", _("Payée")


STATUTS_EMIS = (
    StatutFacture.EMISE,
    StatutFacture.PARTIELLEMENT_PAYEE,
    StatutFacture.PAYEE,
)
STATUTS_A_RECOUVRER = (StatutFacture.EMISE, StatutFacture.PARTIELLEMENT_PAYEE)


class Facture(BaseModel):
    """Facture d'une mission — cahier-des-charges.md:181-186.

    Le numéro ``FACT-AAAA-XXXX`` n'est attribué qu'à la validation : les brouillons
    abandonnés ne laissent aucun trou dans la numérotation. Une facture validée ne se
    modifie plus. Les montants sont en francs entiers (le FCFA n'a pas de centimes).
    """

    numero = models.CharField(_("numéro"), max_length=20, blank=True)
    client = models.ForeignKey(
        "customers.Client",
        verbose_name=_("client"),
        on_delete=models.PROTECT,
        related_name="factures",
    )
    mission = models.ForeignKey(
        "missions.Mission",
        verbose_name=_("mission"),
        on_delete=models.PROTECT,
        related_name="factures",
    )
    statut = models.CharField(
        _("statut"),
        max_length=20,
        choices=StatutFacture.choices,
        default=StatutFacture.BROUILLON,
    )
    taux_tva = models.DecimalField(_("taux de TVA (%)"), max_digits=5, decimal_places=2)
    motif_exoneration = models.CharField(
        _("motif d'exonération"), max_length=12, choices=MotifExoneration.choices, blank=True
    )
    delai_paiement_jours = models.PositiveSmallIntegerField(_("délai de paiement (jours)"))
    date_emission = models.DateField(_("date d'émission"), null=True, blank=True)
    date_echeance = models.DateField(_("date d'échéance"), null=True, blank=True)
    montant_ht = models.DecimalField(_("total HT (FCFA)"), max_digits=14, decimal_places=2, default=0)
    montant_tva = models.DecimalField(_("TVA (FCFA)"), max_digits=14, decimal_places=2, default=0)
    montant_ttc = models.DecimalField(_("total TTC (FCFA)"), max_digits=14, decimal_places=2, default=0)
    motif_refus = models.TextField(_("motif du dernier refus"), blank=True)
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("préparée par"),
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    validee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("validée par"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    date_validation = models.DateTimeField(_("validée le"), null=True, blank=True)

    class Meta:
        verbose_name = _("facture")
        verbose_name_plural = _("factures")
        ordering = ["-date_emission", "-created_at", "-pk"]
        indexes = [models.Index(fields=["statut", "date_echeance"])]
        constraints = [
            models.UniqueConstraint(
                fields=["numero"], condition=~Q(numero=""), name="facture_numero_unique"
            ),
            models.UniqueConstraint(
                fields=["mission"],
                condition=Q(is_deleted=False),
                name="facture_une_par_mission",
            ),
            models.CheckConstraint(
                condition=Q(taux_tva__gt=0) | ~Q(motif_exoneration=""),
                name="facture_tva_zero_requiert_motif",
            ),
            models.CheckConstraint(
                condition=Q(taux_tva__gte=0) & Q(taux_tva__lte=100),
                name="facture_taux_tva_entre_0_et_100",
            ),
            models.CheckConstraint(
                condition=Q(montant_ttc=F("montant_ht") + F("montant_tva")),
                name="facture_ttc_egal_ht_plus_tva",
            ),
            models.CheckConstraint(
                condition=Q(statut__in=["BROUILLON", "A_VALIDER"])
                | (~Q(numero="") & Q(date_emission__isnull=False) & Q(date_echeance__isnull=False)),
                name="facture_emise_a_numero_et_dates",
            ),
        ]

    def __str__(self):
        return self.numero or f"Brouillon ({self.client})"

    @property
    def est_emise(self) -> bool:
        return self.statut in STATUTS_EMIS

    @property
    def est_modifiable(self) -> bool:
        return self.statut == StatutFacture.BROUILLON


class LigneFacture(BaseModel):
    """Ligne d'une facture : la prestation de la mission, plus d'éventuelles refacturations."""

    facture = models.ForeignKey(
        Facture, verbose_name=_("facture"), on_delete=models.PROTECT, related_name="lignes"
    )
    designation = models.CharField(_("désignation"), max_length=255)
    quantite = models.DecimalField(_("quantité"), max_digits=10, decimal_places=2)
    prix_unitaire_ht = models.DecimalField(_("prix unitaire HT (FCFA)"), max_digits=12, decimal_places=2)
    montant_ht = models.DecimalField(_("montant HT (FCFA)"), max_digits=14, decimal_places=2)

    class Meta:
        verbose_name = _("ligne de facture")
        verbose_name_plural = _("lignes de facture")
        ordering = ["pk"]
        constraints = [
            models.CheckConstraint(condition=Q(quantite__gt=0), name="ligne_facture_quantite_positive"),
            models.CheckConstraint(
                condition=Q(prix_unitaire_ht__gte=0), name="ligne_facture_prix_positif"
            ),
        ]

    def __str__(self):
        return f"{self.designation} ({self.montant_ht})"


class Reglement(BaseModel):
    """Encaissement d'une facture (acompte ou solde) — cahier-des-charges.md:189-191."""

    facture = models.ForeignKey(
        Facture, verbose_name=_("facture"), on_delete=models.PROTECT, related_name="reglements"
    )
    date_reglement = models.DateField(_("date du règlement"))
    montant = models.DecimalField(_("montant (FCFA)"), max_digits=14, decimal_places=2)
    mode = models.CharField(_("mode de paiement"), max_length=14, choices=ModePaiement.choices)
    reference = models.CharField(
        _("référence"), max_length=100, blank=True, help_text=_("N° de chèque, de virement ou de transaction.")
    )
    saisi_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    motif_annulation = models.TextField(_("motif d'annulation"), blank=True)

    class Meta:
        verbose_name = _("règlement")
        verbose_name_plural = _("règlements")
        ordering = ["-date_reglement", "-pk"]
        constraints = [
            models.CheckConstraint(condition=Q(montant__gt=0), name="reglement_montant_positif"),
        ]

    def __str__(self):
        return f"{self.facture} : {self.montant} ({self.get_mode_display()})"


class CategorieDepense(models.TextChoices):
    """Catégories du CDC (cahier-des-charges.md:192) ; « Autre » pour le reste."""

    PEAGES = "PEAGES", _("Péages")
    ENTRETIEN = "ENTRETIEN", _("Entretien")
    FRAIS_ADMIN = "FRAIS_ADMIN", _("Frais administratifs")
    AUTRE = "AUTRE", _("Autre")


class Depense(BaseModel):
    """Dépense de l'entreprise, par catégorie, éventuellement rattachée à une mission."""

    categorie = models.CharField(_("catégorie"), max_length=12, choices=CategorieDepense.choices)
    date_depense = models.DateField(_("date"))
    libelle = models.CharField(_("libellé"), max_length=200)
    montant = models.DecimalField(_("montant (FCFA)"), max_digits=14, decimal_places=2)
    mode = models.CharField(_("mode de paiement"), max_length=14, choices=ModePaiement.choices)
    reference = models.CharField(_("n° de pièce"), max_length=100, blank=True)
    mission = models.ForeignKey(
        "missions.Mission",
        verbose_name=_("mission"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="depenses",
    )
    saisi_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = _("dépense")
        verbose_name_plural = _("dépenses")
        ordering = ["-date_depense", "-pk"]
        constraints = [
            models.CheckConstraint(condition=Q(montant__gt=0), name="depense_montant_positif"),
        ]

    def __str__(self):
        return f"{self.libelle} ({self.montant})"
```

Cinq modèles autour de la facture : `Facture`, `LigneFacture`, `Reglement` (avec son statut d'annulation
logique), `Depense`, et les énumérations `ModePaiement`, `CompteTresorerie`, `StatutFacture`,
`CategorieDepense`. `STATUTS_EMIS` et `STATUTS_A_RECOUVRER` regroupent les statuts pour les filtres.

## Étape 3 — Règles métier

#### `apps/billing/exceptions.py`

*22 lignes*

```python
class BillingError(Exception):
    """Erreur métier de la facturation."""


class FactureNonFacturable(BillingError):
    """La mission ne peut pas (ou plus) être facturée."""


class TransitionFactureInterdite(BillingError):
    """La facture n'est pas dans un état permettant cette action."""


class ActionFactureNonAutorisee(BillingError):
    """L'utilisateur n'a pas le droit d'effectuer cette action."""


class MontantInvalide(BillingError):
    """Montant, quantité ou taux hors des valeurs permises."""


class ReglementInvalide(BillingError):
    """Règlement refusé (facture non émise, surpaiement, date incohérente)."""
```

#### `apps/billing/permissions.py`

*15 lignes* — Qui peut consulter, préparer et valider les factures.

```python
"""Qui peut consulter, préparer et valider les factures.

Cahier-des-charges.md:44-55 : FINANCES = « validation factures, saisie dépenses/entrées,
suivi trésorerie » ; DIRECTION = « accès financier (lecture + validation) » ;
architecture.md:432 : « Rôle FINANCES + validation DIRECTION ». Décision retenue : FINANCES
prépare la facture et la soumet, la DIRECTION la valide (ce qui l'émet). L'ADMIN a accès à
tout mais ne valide pas : une facture est toujours validée par la DIRECTION. La RH, le
PARCAUTO, le chargé clientèle et le chauffeur n'ont pas accès.
"""

from apps.accounts.models import Role

CONSULTATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.FINANCES})
SAISIE = frozenset({Role.ADMIN, Role.FINANCES})  # préparer, règlements, dépenses
VALIDATION = frozenset({Role.DIRECTION})
```

Trois ensembles : `CONSULTATION` (ADMIN, DIRECTION, FINANCES), `SAISIE` (ADMIN, FINANCES : préparer, encaisser,
saisir) et `VALIDATION` (**DIRECTION seule**).

#### `apps/billing/services.py`

*520 lignes* — Logique métier de la facturation : factures, TVA, règlements, dépenses.

```python
"""Logique métier de la facturation : factures, TVA, règlements, dépenses.

Réf. cahier-des-charges.md:181-193, architecture.md:213, 224-229, 432.

Cycle : BROUILLON (préparé par FINANCES) → A_VALIDER → EMISE (validée par la DIRECTION, numéro
attribué) → PARTIELLEMENT_PAYEE → PAYEE. La DIRECTION peut renvoyer une facture en brouillon avec
un motif. Une facture émise ne se modifie plus. Les montants sont arrondis au franc (ROUND_HALF_UP).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.db.models import F, Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.core.search import filtrer_par_texte
from apps.core.services import prochain_numero
from apps.customers.models import Client
from apps.missions.models import Mission, StatutMission

from . import permissions, signals
from .exceptions import (
    ActionFactureNonAutorisee,
    FactureNonFacturable,
    MontantInvalide,
    ReglementInvalide,
    TransitionFactureInterdite,
)
from .models import (
    STATUTS_A_RECOUVRER,
    STATUTS_EMIS,
    CategorieDepense,
    Depense,
    Facture,
    LigneFacture,
    Reglement,
    StatutFacture,
)

ZERO = Decimal("0")
STATUTS_MISSION_FACTURABLES = (StatutMission.LIVREE, StatutMission.CLOTUREE)  # après la livraison


def arrondir_franc(valeur) -> Decimal:
    """Arrondit au franc entier (le FCFA n'a pas de centimes)."""
    return Decimal(valeur).quantize(Decimal(1), rounding=ROUND_HALF_UP)


def _verrouiller(objet):
    type(objet)._base_manager.select_for_update().filter(pk=objet.pk).first()
    objet.refresh_from_db()
    return objet


def _exiger_role(acteur, roles, action: str, *, strict: bool = False) -> None:
    role = acteur.role if strict else acteur.role_effectif
    if role not in roles:
        raise ActionFactureNonAutorisee(f"Vous n'avez pas le droit de {action}.")


def _exiger_statut(facture: Facture, attendus: tuple, action: str) -> None:
    if facture.statut not in attendus:
        raise TransitionFactureInterdite(
            f"Impossible de {action} : la facture est « {facture.get_statut_display()} »."
        )


# --- lecture ---


def _regle_annote(queryset):
    return queryset.annotate(
        montant_regle=Coalesce(
            Sum("reglements__montant", filter=Q(reglements__is_deleted=False)),
            Value(ZERO),
        )
    ).annotate(reste=F("montant_ttc") - F("montant_regle"))


def factures_queryset() -> QuerySet[Facture]:
    """Factures avec client, mission, montant réglé et reste à recouvrer."""
    # order_by explicite : l'agrégation (règlements) ignore l'ordre par défaut du modèle.
    return _regle_annote(
        Facture.objects.select_related("client", "mission").order_by("-created_at", "-pk")
    )


def est_echue(facture: Facture, aujourd_hui: date | None = None) -> bool:
    """Facture émise, pas soldée, dont la date d'échéance est dépassée."""
    aujourd_hui = aujourd_hui or timezone.localdate()
    return (
        facture.statut in STATUTS_A_RECOUVRER
        and facture.date_echeance is not None
        and facture.date_echeance < aujourd_hui
    )


def montant_regle(facture: Facture) -> Decimal:
    return sum((r.montant for r in facture.reglements.all()), ZERO)


def reste_a_recouvrer(facture: Facture) -> Decimal:
    """Total TTC moins les règlements enregistrés (cahier-des-charges.md:191)."""
    return facture.montant_ttc - montant_regle(facture)


def factures_echues(aujourd_hui: date | None = None) -> QuerySet[Facture]:
    aujourd_hui = aujourd_hui or timezone.localdate()
    return factures_queryset().filter(
        statut__in=STATUTS_A_RECOUVRER, date_echeance__lt=aujourd_hui
    )


def rechercher_factures(
    *,
    recherche: str = "",
    statut: str = "",
    client: Client | None = None,
    echues: bool = False,
    aujourd_hui: date | None = None,
) -> QuerySet[Facture]:
    """Factures filtrées par texte (numéro, client, mission), statut, client, échéance."""
    resultat = factures_queryset()
    if statut in StatutFacture.values:
        resultat = resultat.filter(statut=statut)
    if client is not None:
        resultat = resultat.filter(client=client)
    if echues:
        aujourd_hui = aujourd_hui or timezone.localdate()
        resultat = resultat.filter(statut__in=STATUTS_A_RECOUVRER, date_echeance__lt=aujourd_hui)
    return filtrer_par_texte(
        resultat, recherche, "numero", "client__raison_sociale", "mission__numero"
    )


def creances(aujourd_hui: date | None = None) -> dict:
    """Créances clients : reste à recouvrer total, dont échu (tableau de bord)."""
    aujourd_hui = aujourd_hui or timezone.localdate()
    total = echu = ZERO
    nombre = nombre_echues = 0
    for facture in factures_queryset().filter(statut__in=STATUTS_A_RECOUVRER):
        nombre += 1
        total += facture.reste
        if est_echue(facture, aujourd_hui):
            nombre_echues += 1
            echu += facture.reste
    return {"total": total, "nombre": nombre, "echu": echu, "nombre_echues": nombre_echues}


def missions_facturables() -> QuerySet[Mission]:
    """Missions livrées ou clôturées qui n'ont pas encore de facture (brouillon compris)."""
    return (
        Mission.objects.filter(statut__in=STATUTS_MISSION_FACTURABLES)
        .exclude(factures__is_deleted=False)
        .select_related("client")
        .order_by("-date_livraison", "-pk")
    )


def chiffre_affaires(debut: date, fin: date) -> Decimal:
    """Total HT des factures émises entre ces deux dates (bornes incluses)."""
    return Facture.objects.filter(
        statut__in=STATUTS_EMIS, date_emission__range=(debut, fin)
    ).aggregate(total=Sum("montant_ht"))["total"] or ZERO


def encaissements(debut: date, fin: date) -> Decimal:
    """Total des règlements reçus entre ces deux dates (bornes incluses)."""
    return Reglement.objects.filter(date_reglement__range=(debut, fin)).aggregate(
        total=Sum("montant")
    )["total"] or ZERO


# --- préparation d'une facture (FINANCES) ---


def _recalculer(facture: Facture) -> Facture:
    """HT = somme des lignes ; TVA arrondie au franc ; TTC = HT + TVA."""
    ht = sum((ligne.montant_ht for ligne in facture.lignes.all()), ZERO)
    tva = arrondir_franc(ht * facture.taux_tva / 100)
    facture.montant_ht, facture.montant_tva, facture.montant_ttc = ht, tva, ht + tva
    facture.save(update_fields=["montant_ht", "montant_tva", "montant_ttc", "updated_at"])
    return facture


@transaction.atomic
def creer_facture(mission: Mission, acteur) -> Facture:
    """Brouillon de facture pour une mission livrée, avec la TVA et le délai du client.

    TVA à 3 niveaux (cahier-des-charges.md:184-186) : système 18 %, puis taux du client, puis
    ajustable sur la facture tant qu'elle est en brouillon. Une ligne reprend la prestation
    au prix convenu de la mission.
    """
    _exiger_role(acteur, permissions.SAISIE, "préparer une facture")
    mission = _verrouiller(mission)
    if mission.statut not in STATUTS_MISSION_FACTURABLES:
        raise FactureNonFacturable(
            f"La mission {mission.numero} n'est pas encore livrée : elle ne peut pas être facturée."
        )
    if Facture.objects.filter(mission=mission).exists():
        raise FactureNonFacturable(f"La mission {mission.numero} a déjà une facture.")
    client = mission.client
    try:
        with transaction.atomic():
            facture = Facture.objects.create(
                client=client,
                mission=mission,
                taux_tva=client.taux_tva,
                motif_exoneration=client.motif_exoneration,
                delai_paiement_jours=client.delai_paiement_jours,
                cree_par=acteur,
            )
    except IntegrityError as erreur:  # deux préparations simultanées
        raise FactureNonFacturable(f"La mission {mission.numero} a déjà une facture.") from erreur
    LigneFacture.objects.create(
        facture=facture,
        designation=(
            f"Transport {mission.numero} : {mission.lieu_chargement} → {mission.lieu_livraison} "
            f"({mission.nature_marchandise}, {mission.poids_t} t)"
        ),
        quantite=Decimal("1"),
        prix_unitaire_ht=mission.prix_convenu,
        montant_ht=arrondir_franc(mission.prix_convenu),
    )
    return _recalculer(facture)


@transaction.atomic
def ajouter_ligne(
    facture: Facture, acteur, *, designation: str, quantite: Decimal, prix_unitaire_ht: Decimal
) -> LigneFacture:
    """Ajoute une ligne (refacturation de péages, attente...) à un brouillon."""
    _exiger_role(acteur, permissions.SAISIE, "modifier une facture")
    _verrouiller(facture)
    _exiger_statut(facture, (StatutFacture.BROUILLON,), "ajouter une ligne")
    designation = designation.strip()
    if not designation:
        raise MontantInvalide("La désignation est obligatoire.")
    quantite, prix_unitaire_ht = Decimal(quantite), Decimal(prix_unitaire_ht)
    if quantite <= 0:
        raise MontantInvalide("La quantité doit être strictement positive.")
    if prix_unitaire_ht < 0:
        raise MontantInvalide("Le prix unitaire ne peut pas être négatif.")
    ligne = LigneFacture.objects.create(
        facture=facture,
        designation=designation,
        quantite=quantite,
        prix_unitaire_ht=prix_unitaire_ht,
        montant_ht=arrondir_franc(quantite * prix_unitaire_ht),
    )
    _recalculer(facture)
    return ligne


@transaction.atomic
def supprimer_ligne(ligne: LigneFacture, acteur) -> Facture:
    _exiger_role(acteur, permissions.SAISIE, "modifier une facture")
    facture = _verrouiller(ligne.facture)
    _exiger_statut(facture, (StatutFacture.BROUILLON,), "supprimer une ligne")
    ligne.delete()
    return _recalculer(facture)


@transaction.atomic
def modifier_conditions(
    facture: Facture,
    acteur,
    *,
    taux_tva: Decimal,
    motif_exoneration: str = "",
    delai_paiement_jours: int,
) -> Facture:
    """TVA et délai de paiement de la facture (3e niveau de TVA), tant qu'elle est en brouillon."""
    _exiger_role(acteur, permissions.SAISIE, "modifier une facture")
    _verrouiller(facture)
    _exiger_statut(facture, (StatutFacture.BROUILLON,), "modifier les conditions")
    taux = Decimal(taux_tva)
    if not ZERO <= taux <= Decimal(100):
        raise MontantInvalide("Le taux de TVA doit être compris entre 0 et 100 %.")
    if taux == 0 and not motif_exoneration:
        raise MontantInvalide("Un motif d'exonération est obligatoire quand la TVA est à 0 %.")
    if not 1 <= delai_paiement_jours <= 365:
        raise MontantInvalide("Le délai de paiement doit être compris entre 1 et 365 jours.")
    facture.taux_tva = taux
    facture.motif_exoneration = motif_exoneration if taux == 0 else ""
    facture.delai_paiement_jours = delai_paiement_jours
    facture.save(
        update_fields=["taux_tva", "motif_exoneration", "delai_paiement_jours", "updated_at"]
    )
    return _recalculer(facture)


@transaction.atomic
def abandonner_brouillon(facture: Facture, acteur) -> None:
    """Supprime (logiquement) un brouillon : la mission redevient facturable.

    Comme le numéro n'est attribué qu'à la validation, aucun trou dans la numérotation.
    """
    _exiger_role(acteur, permissions.SAISIE, "abandonner une facture")
    _verrouiller(facture)
    _exiger_statut(facture, (StatutFacture.BROUILLON,), "abandonner la facture")
    facture.delete(deleted_by=acteur)


# --- validation (DIRECTION) ---


@transaction.atomic
def soumettre(facture: Facture, acteur) -> Facture:
    """Brouillon → À valider : envoie la facture à la DIRECTION."""
    _exiger_role(acteur, permissions.SAISIE, "soumettre une facture")
    _verrouiller(facture)
    _exiger_statut(facture, (StatutFacture.BROUILLON,), "soumettre la facture")
    if facture.montant_ht <= 0:
        raise MontantInvalide("Une facture à 0 FCFA ne peut pas être soumise.")
    facture.statut = StatutFacture.A_VALIDER
    facture.motif_refus = ""
    facture.save(update_fields=["statut", "motif_refus", "updated_at"])
    signals.emettre(signals.facture_a_valider, facture=facture)
    return facture


@transaction.atomic
def valider(facture: Facture, acteur, *, aujourd_hui: date | None = None) -> Facture:
    """À valider → Émise : numéro ``FACT-AAAA-XXXX``, date d'émission, échéance, créance.

    Réservé à la DIRECTION ; les montants ne bougent plus ensuite.
    """
    _exiger_role(acteur, permissions.VALIDATION, "valider une facture", strict=True)
    _verrouiller(facture)
    _exiger_statut(facture, (StatutFacture.A_VALIDER,), "valider la facture")
    aujourd_hui = aujourd_hui or timezone.localdate()
    facture.numero = prochain_numero("FACT", aujourd_hui.year)
    facture.statut = StatutFacture.EMISE
    facture.date_emission = aujourd_hui
    facture.date_echeance = aujourd_hui + timedelta(days=facture.delai_paiement_jours)
    facture.validee_par = acteur
    facture.date_validation = timezone.now()
    facture.save(
        update_fields=[
            "numero",
            "statut",
            "date_emission",
            "date_echeance",
            "validee_par",
            "date_validation",
            "updated_at",
        ]
    )
    signals.emettre(signals.facture_validee, facture=facture)
    return facture


@transaction.atomic
def refuser(facture: Facture, acteur, *, motif: str) -> Facture:
    """À valider → Brouillon avec un motif : FINANCES corrige puis soumet à nouveau."""
    _exiger_role(acteur, permissions.VALIDATION, "refuser une facture", strict=True)
    _verrouiller(facture)
    _exiger_statut(facture, (StatutFacture.A_VALIDER,), "refuser la facture")
    if not motif.strip():
        raise MontantInvalide("Le motif du refus est obligatoire.")
    facture.statut = StatutFacture.BROUILLON
    facture.motif_refus = motif.strip()
    facture.save(update_fields=["statut", "motif_refus", "updated_at"])
    signals.emettre(signals.facture_refusee, facture=facture, motif=facture.motif_refus)
    return facture


# --- règlements ---


def _statut_selon_reste(facture: Facture) -> str:
    if reste_a_recouvrer(facture) <= 0:
        return StatutFacture.PAYEE
    return (
        StatutFacture.PARTIELLEMENT_PAYEE if montant_regle(facture) > 0 else StatutFacture.EMISE
    )


@transaction.atomic
def enregistrer_reglement(
    facture: Facture,
    acteur,
    *,
    montant: Decimal,
    mode: str,
    date_reglement: date,
    reference: str = "",
) -> Reglement:
    """Acompte ou solde d'une facture émise ; le reste à recouvrer se recalcule.

    Refusé si la facture n'est pas émise, si le montant dépasse le reste à recouvrer ou si la
    date est future ou antérieure à l'émission.
    """
    _exiger_role(acteur, permissions.SAISIE, "enregistrer un règlement")
    _verrouiller(facture)
    if facture.statut not in STATUTS_A_RECOUVRER:
        raise ReglementInvalide(
            f"Impossible d'enregistrer un règlement : la facture est « {facture.get_statut_display()} »."
        )
    montant = Decimal(montant)
    if montant <= 0:
        raise ReglementInvalide("Le montant du règlement doit être strictement positif.")
    reste = reste_a_recouvrer(facture)
    if montant > reste:
        raise ReglementInvalide(
            f"Le montant dépasse le reste à recouvrer ({arrondir_franc(reste)} FCFA)."
        )
    if date_reglement > timezone.localdate():
        raise ReglementInvalide("La date du règlement ne peut pas être dans le futur.")
    if date_reglement < facture.date_emission:
        raise ReglementInvalide("Le règlement ne peut pas précéder la date d'émission de la facture.")
    reglement = Reglement.objects.create(
        facture=facture,
        date_reglement=date_reglement,
        montant=montant,
        mode=mode,
        reference=reference.strip(),
        saisi_par=acteur,
    )
    facture.statut = _statut_selon_reste(facture)
    facture.save(update_fields=["statut", "updated_at"])
    return reglement


@transaction.atomic
def annuler_reglement(reglement: Reglement, acteur, *, motif: str) -> Facture:
    """Annule (logiquement) un règlement saisi par erreur ; les jours de retard reprennent."""
    _exiger_role(acteur, permissions.SAISIE, "annuler un règlement")
    if not motif.strip():
        raise ReglementInvalide("Le motif de l'annulation est obligatoire.")
    facture = _verrouiller(reglement.facture)
    reglement.motif_annulation = motif.strip()
    reglement.save(update_fields=["motif_annulation", "updated_at"])
    reglement.delete(deleted_by=acteur)
    facture.statut = _statut_selon_reste(facture)
    facture.save(update_fields=["statut", "updated_at"])
    return facture


# --- dépenses ---


def depenses_queryset() -> QuerySet[Depense]:
    return Depense.objects.select_related("mission", "saisi_par")


def rechercher_depenses(
    *,
    recherche: str = "",
    categorie: str = "",
    date_debut: date | None = None,
    date_fin: date | None = None,
) -> QuerySet[Depense]:
    resultat = depenses_queryset()
    if categorie in CategorieDepense.values:
        resultat = resultat.filter(categorie=categorie)
    if date_debut:
        resultat = resultat.filter(date_depense__gte=date_debut)
    if date_fin:
        resultat = resultat.filter(date_depense__lte=date_fin)
    return filtrer_par_texte(resultat, recherche, "libelle", "reference", "mission__numero")


def total_depenses(debut: date, fin: date) -> Decimal:
    return Depense.objects.filter(date_depense__range=(debut, fin)).aggregate(
        total=Sum("montant")
    )["total"] or ZERO


def depenses_par_categorie(debut: date, fin: date) -> list[dict]:
    """Total par catégorie sur la période (toutes les catégories, y compris à 0)."""
    totaux = dict(
        Depense.objects.filter(date_depense__range=(debut, fin))
        .values_list("categorie")
        .annotate(total=Sum("montant"))
        .order_by()
    )
    return [
        {"code": code, "libelle": libelle, "total": totaux.get(code, ZERO)}
        for code, libelle in CategorieDepense.choices
    ]


@transaction.atomic
def enregistrer_depense(
    acteur,
    *,
    categorie: str,
    date_depense: date,
    libelle: str,
    montant: Decimal,
    mode: str,
    reference: str = "",
    mission: Mission | None = None,
) -> Depense:
    """Saisie d'une dépense (cahier-des-charges.md:192) ; la date ne peut pas être future."""
    _exiger_role(acteur, permissions.SAISIE, "saisir une dépense")
    libelle = libelle.strip()
    if not libelle:
        raise MontantInvalide("Le libellé est obligatoire.")
    montant = Decimal(montant)
    if montant <= 0:
        raise MontantInvalide("Le montant de la dépense doit être strictement positif.")
    if date_depense > timezone.localdate():
        raise MontantInvalide("La date de la dépense ne peut pas être dans le futur.")
    return Depense.objects.create(
        categorie=categorie,
        date_depense=date_depense,
        libelle=libelle,
        montant=montant,
        mode=mode,
        reference=reference.strip(),
        mission=mission,
        saisi_par=acteur,
    )
```

À lire dans cet ordre :

1. **`creer_facture`** : contrôle le rôle, verrouille la mission, refuse une mission non livrée
   (`FactureNonFacturable`), reprend prix, TVA et délai du client.
2. **`ajouter_ligne`**, **`supprimer_ligne`**, **`modifier_conditions`** : possibles **seulement en brouillon**.
   `_recalculer` refait HT, TVA arrondie, TTC.
3. **`soumettre`** : Brouillon → À valider. **`refuser`** : la Direction renvoie en brouillon **avec un motif**.
4. **`valider`** : le cœur : rôle strict, numéro `FACT-AAAA-XXXX`, date d'émission, échéance = émission + délai de
   paiement du client, montants gelés, signal `facture_validee`.
5. **`enregistrer_reglement`** / **`annuler_reglement`** : refusés si la facture n'est pas émise, si le montant
   dépasse le reste à recouvrer, ou si la date est future ou antérieure à l'émission ; le **statut** (partiellement
   payée / payée) est recalculé par `_statut_selon_reste`.
6. **Lectures** : `creances`, `factures_echues`, `chiffre_affaires`, `encaissements`, `total_depenses`,
   `depenses_par_categorie`.

#### `apps/billing/signals.py`

*27 lignes* — Événements du cycle de facturation (souscrits par ``notifications``).

```python
"""Événements du cycle de facturation (souscrits par ``notifications``).

Émis dans la transaction de l'action, avec ``send_robust`` : un récepteur en erreur ne doit
jamais empêcher une validation de facture.
"""

import logging

from django.dispatch import Signal

logger = logging.getLogger(__name__)

# La facture vient d'être soumise à la DIRECTION. Argument : ``facture``.
facture_a_valider = Signal()
# La DIRECTION vient de valider la facture (numéro attribué). Argument : ``facture``.
facture_validee = Signal()
# La DIRECTION a refusé la facture (retour en brouillon). Arguments : ``facture``, ``motif``.
facture_refusee = Signal()


def emettre(signal: Signal, **arguments) -> None:
    """Émet un signal en journalisant (sans propager) les erreurs des récepteurs."""
    from .models import Facture

    for recepteur, resultat in signal.send_robust(sender=Facture, **arguments):
        if isinstance(resultat, Exception):
            logger.error("Récepteur %r en erreur", recepteur, exc_info=resultat)
```

## Étape 4 — Démarrage et tests

#### `apps/billing/apps.py`

*29 lignes*

```python
from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.billing'
    label = 'billing'

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer
        from apps.audit.registry import audit_model

        from . import permissions
        from .models import Depense, Facture, Reglement

        audit_model(Facture, module="FINANCES")
        audit_model(Reglement, module="FINANCES")
        audit_model(Depense, module="FINANCES")
        enregistrer(
            EntreeMenu(
                "Facturation", "billing:factures", "fa-file-invoice-dollar",
                permissions.CONSULTATION, ordre=60,
            )
        )
        enregistrer(
            EntreeMenu(
                "Dépenses", "billing:depenses", "fa-receipt", permissions.CONSULTATION, ordre=61
            )
        )
```

Dans `ready()`, on branche l'audit (module `FINANCES`) sur les factures, les règlements et les dépenses, et on
déclare les entrées de menu « Facturation » et « Dépenses ».

#### `apps/billing/tests/helpers.py`

*50 lignes* — Aides de test : missions livrées, factures à tous les stades, comptes par rôle.

```python
"""Aides de test : missions livrées, factures à tous les stades, comptes par rôle."""

from datetime import date
from decimal import Decimal

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services
from apps.customers.tests.factories import ClientFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.missions.models import StatutMission
from apps.missions.tests.factories import MissionFactory

JOUR = date(2026, 9, 1)


def finances():
    return UserFactory(role=Role.FINANCES)


def direction():
    return UserFactory(role=Role.DIRECTION)


def mission_livree(*, prix="1000000", client=None, statut=StatutMission.LIVREE, **surcharges):
    return MissionFactory(
        client=client or ClientFactory(),
        statut=statut,
        prix_convenu=Decimal(prix),
        vehicule=VehiculeFactory(),
        chauffeur=ChauffeurFactory(),
        **surcharges,
    )


def brouillon(*, prix="1000000", acteur=None, **surcharges):
    return services.creer_facture(mission_livree(prix=prix, **surcharges), acteur or finances())


def a_valider(**surcharges):
    facture = brouillon(**surcharges)
    services.soumettre(facture, finances())
    return facture


def emise(*, aujourd_hui=JOUR, **surcharges):
    facture = a_valider(**surcharges)
    services.valider(facture, direction(), aujourd_hui=aujourd_hui)
    return facture
```

Ce fichier n'est pas un test : c'est une **bibliothèque d'aides** (`mission_livree`, `direction`, `finances`,
`emise`…) que réutiliseront aussi les tests de la trésorerie (chapitre 14) et des notifications.

#### `apps/billing/README.md`

*39 lignes* — billing

```markdown
# billing

Rôle : factures, TVA, règlements et dépenses — cahier-des-charges.md:181-193 ;
architecture.md:213, 224-229, 432. Interface sous `/facturation/`.

Entités : `Facture` (+ `LigneFacture`), `Reglement`, `Depense`. Audités (module `FINANCES`).

Cycle d'une facture (décision : FINANCES prépare, DIRECTION valide) :
`BROUILLON` → `A_VALIDER` → `EMISE` → `PARTIELLEMENT_PAYEE` → `PAYEE`.
- Le brouillon se crée depuis une **mission livrée ou clôturée** (une facture par mission, garantie
  en base) et reprend le prix convenu, la TVA et le délai de paiement du client. FINANCES peut
  ajouter des lignes (péages refacturés...) et ajuster la TVA et le délai tant que c'est un brouillon.
- **TVA à 3 niveaux** : système 18 %, client, facture. À 0 %, le motif d'exonération est obligatoire
  (contrainte en base). La TVA est arrondie au franc (le FCFA n'a pas de centimes).
- **Numéro `FACT-AAAA-XXXX` attribué à la validation** : un brouillon abandonné ne laisse aucun
  trou. La validation fixe aussi la date d'émission et l'échéance (émission + délai de paiement du
  client, 30 jours par défaut) et gèle les montants. Seul le rôle DIRECTION valide (un ADMIN ou un
  superutilisateur non). La DIRECTION peut renvoyer en brouillon avec un motif.
- **Règlements** (acomptes et solde) : Virement, Chèque, Espèces, Wave, Orange Money, MTN. Refusés si
  la facture n'est pas émise, si le montant dépasse le reste à recouvrer, ou si la date est future ou
  antérieure à l'émission. Un règlement erroné s'annule avec un motif (annulation logique) ; le
  reste à recouvrer et le statut se recalculent.
- **Échue** = émise, non soldée, échéance dépassée : alerte au tableau de bord et notification.
- **Dépenses** : Péages, Entretien, Frais administratifs (+ « Autre », ajout à notre initiative).

Droits (`permissions.py`) : consultation ADMIN, DIRECTION, FINANCES ; préparation, règlements et
dépenses ADMIN et FINANCES ; validation DIRECTION seulement.

Version imprimable : `/facturation/<id>/imprimer/` (Ctrl+P puis « Enregistrer au format PDF »). Les
mentions de l'émetteur viennent des variables `ENTREPRISE_NOM`, `ENTREPRISE_ADRESSE`,
`ENTREPRISE_NCC`.

Pas encore fait :
- **Écritures comptables** (critère de recette n°6 du CDC : « écriture comptable équilibrée ») :
  écarté sur décision de l'utilisateur pour cette étape.
- **Avoir / annulation d'une facture émise** : le CDC n'en parle pas ; une facture émise ne se
  modifie ni ne se supprime.
- Génération de PDF côté serveur (Celery, étape 7) ; paiement initié par Mobile Money.
- Accès du chargé clientèle aux factures de ses clients.
```

#### `apps/billing/tests/test_services.py`

*570 lignes* — Facturation : préparation, TVA à 3 niveaux, validation, numérotation, règlements.

```python
"""Facturation : préparation, TVA à 3 niveaux, validation, numérotation, règlements."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services
from apps.billing.exceptions import (
    ActionFactureNonAutorisee,
    FactureNonFacturable,
    MontantInvalide,
    ReglementInvalide,
    TransitionFactureInterdite,
)
from apps.billing.models import Facture, LigneFacture, ModePaiement, Reglement, StatutFacture
from apps.customers.tests.factories import ClientFactory
from apps.missions.models import StatutMission
from apps.missions.tests.factories import MissionFactory

from .helpers import JOUR, a_valider, brouillon, direction, emise, finances, mission_livree

pytestmark = pytest.mark.django_db


# --- missions facturables ---


def test_seules_les_missions_livrees_ou_cloturees_sans_facture_sont_facturables():
    livree = mission_livree()
    cloturee = mission_livree(statut=StatutMission.CLOTUREE)
    MissionFactory(statut=StatutMission.PLANIFIEE)
    deja = mission_livree()
    services.creer_facture(deja, finances())

    assert set(services.missions_facturables()) == {livree, cloturee}


def test_une_mission_non_livree_ne_peut_pas_etre_facturee():
    mission = MissionFactory(statut=StatutMission.PLANIFIEE)

    with pytest.raises(FactureNonFacturable, match="pas encore livrée"):
        services.creer_facture(mission, finances())


def test_une_mission_ne_peut_avoir_qu_une_facture():
    mission = mission_livree()
    services.creer_facture(mission, finances())

    with pytest.raises(FactureNonFacturable, match="déjà une facture"):
        services.creer_facture(mission, finances())


def test_seuls_finances_et_admin_preparent_une_facture():
    for role in (Role.DIRECTION, Role.RH, Role.PARCAUTO, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR):
        with pytest.raises(ActionFactureNonAutorisee):
            services.creer_facture(mission_livree(), UserFactory(role=role))
    assert services.creer_facture(mission_livree(), UserFactory(role=Role.ADMIN)).pk
    superutilisateur = UserFactory(role="", is_superuser=True)
    assert services.creer_facture(mission_livree(), superutilisateur).pk


# --- contenu du brouillon et TVA à 3 niveaux ---


def test_le_brouillon_reprend_le_client_la_prestation_et_la_tva_du_client():
    client = ClientFactory(delai_paiement_jours=45)
    mission = mission_livree(prix="1000000", client=client, lieu_chargement="Abidjan", lieu_livraison="Bouaké")

    facture = services.creer_facture(mission, finances())

    assert facture.statut == StatutFacture.BROUILLON and facture.numero == ""
    assert facture.client == client and facture.mission == mission
    assert facture.delai_paiement_jours == 45
    (ligne,) = facture.lignes.all()
    assert "Abidjan → Bouaké" in ligne.designation and mission.numero in ligne.designation
    assert (facture.montant_ht, facture.montant_tva, facture.montant_ttc) == (
        Decimal("1000000"), Decimal("180000"), Decimal("1180000"),
    )


def test_niveau_client_la_tva_du_client_s_applique_a_la_facture():
    client = ClientFactory(taux_tva=Decimal("0"), motif_exoneration="EXPORT")

    facture = services.creer_facture(mission_livree(client=client), finances())

    assert facture.taux_tva == 0 and facture.motif_exoneration == "EXPORT"
    assert facture.montant_tva == 0 and facture.montant_ttc == facture.montant_ht


def test_niveau_facture_la_tva_se_modifie_sur_le_brouillon():
    facture = brouillon()

    services.modifier_conditions(
        facture, finances(), taux_tva=Decimal("10"), delai_paiement_jours=15
    )

    facture.refresh_from_db()
    assert (facture.taux_tva, facture.montant_tva, facture.montant_ttc) == (
        Decimal("10"), Decimal("100000"), Decimal("1100000"),
    )
    assert facture.delai_paiement_jours == 15


def test_tva_zero_exige_un_motif_et_le_motif_est_efface_si_la_tva_redevient_positive():
    facture = brouillon()
    acteur = finances()

    with pytest.raises(MontantInvalide, match="motif d'exonération"):
        services.modifier_conditions(facture, acteur, taux_tva=Decimal("0"), delai_paiement_jours=30)

    services.modifier_conditions(
        facture, acteur, taux_tva=Decimal("0"), motif_exoneration="ONG", delai_paiement_jours=30
    )
    assert facture.motif_exoneration == "ONG" and facture.montant_ttc == facture.montant_ht
    services.modifier_conditions(facture, acteur, taux_tva=Decimal("18"), delai_paiement_jours=30)
    assert facture.motif_exoneration == ""


@pytest.mark.parametrize("taux", [Decimal("-1"), Decimal("101")])
def test_taux_de_tva_hors_bornes(taux):
    with pytest.raises(MontantInvalide, match="entre 0 et 100"):
        services.modifier_conditions(brouillon(), finances(), taux_tva=taux, delai_paiement_jours=30)


@pytest.mark.parametrize("delai", [0, 366])
def test_delai_de_paiement_hors_bornes(delai):
    with pytest.raises(MontantInvalide, match="entre 1 et 365"):
        services.modifier_conditions(
            brouillon(), finances(), taux_tva=Decimal("18"), delai_paiement_jours=delai
        )


def test_la_tva_est_arrondie_au_franc():
    facture = brouillon(prix="1005")  # 18 % de 1005 = 180,9

    assert facture.montant_tva == Decimal("181") and facture.montant_ttc == Decimal("1186")


def test_ajouter_et_supprimer_des_lignes_recalcule_les_totaux():
    facture = brouillon(prix="1000000")
    acteur = finances()

    peage = services.ajouter_ligne(
        facture, acteur, designation="Péages refacturés", quantite=Decimal("2"), prix_unitaire_ht=Decimal("7500.50")
    )

    facture.refresh_from_db()
    assert peage.montant_ht == Decimal("15001")  # 2 x 7500,50 arrondi au franc
    assert facture.montant_ht == Decimal("1015001") and facture.montant_tva == Decimal("182700")
    services.supprimer_ligne(peage, acteur)
    facture.refresh_from_db()
    assert facture.montant_ht == Decimal("1000000")
    assert LigneFacture.objects.filter(facture=facture).count() == 1


@pytest.mark.parametrize(
    ("designation", "quantite", "prix", "message"),
    [
        ("  ", "1", "10", "désignation"),
        ("x", "0", "10", "quantité"),
        ("x", "-1", "10", "quantité"),
        ("x", "1", "-5", "prix"),
    ],
)
def test_lignes_invalides(designation, quantite, prix, message):
    with pytest.raises(MontantInvalide, match=message):
        services.ajouter_ligne(
            brouillon(), finances(), designation=designation,
            quantite=Decimal(quantite), prix_unitaire_ht=Decimal(prix),
        )


def test_seul_un_brouillon_se_modifie():
    facture = a_valider()
    acteur = finances()

    with pytest.raises(TransitionFactureInterdite):
        services.ajouter_ligne(facture, acteur, designation="x", quantite=Decimal(1), prix_unitaire_ht=Decimal(1))
    with pytest.raises(TransitionFactureInterdite):
        services.modifier_conditions(facture, acteur, taux_tva=Decimal("18"), delai_paiement_jours=30)
    with pytest.raises(TransitionFactureInterdite):
        services.supprimer_ligne(facture.lignes.first(), acteur)
    with pytest.raises(TransitionFactureInterdite):
        services.abandonner_brouillon(facture, acteur)


def test_les_modifications_sont_reservees_a_finances_et_admin():
    facture = brouillon()
    ligne = facture.lignes.first()

    for action in (
        lambda u: services.ajouter_ligne(facture, u, designation="x", quantite=Decimal(1), prix_unitaire_ht=Decimal(1)),
        lambda u: services.supprimer_ligne(ligne, u),
        lambda u: services.modifier_conditions(facture, u, taux_tva=Decimal("18"), delai_paiement_jours=30),
        lambda u: services.soumettre(facture, u),
        lambda u: services.abandonner_brouillon(facture, u),
    ):
        with pytest.raises(ActionFactureNonAutorisee):
            action(direction())


def test_abandonner_un_brouillon_libere_la_mission_sans_trou_de_numerotation():
    mission = mission_livree()
    facture = services.creer_facture(mission, finances())

    services.abandonner_brouillon(facture, finances())

    assert not Facture.objects.filter(pk=facture.pk).exists()
    assert mission in services.missions_facturables()
    nouvelle = services.creer_facture(mission, finances())
    assert nouvelle.pk != facture.pk


# --- validation par la direction ---


def test_soumettre_envoie_le_brouillon_a_la_direction():
    facture = brouillon()

    services.soumettre(facture, finances())

    facture.refresh_from_db()
    assert facture.statut == StatutFacture.A_VALIDER and facture.numero == ""


def test_une_facture_a_zero_ne_peut_pas_etre_soumise():
    facture = brouillon(prix="0")

    with pytest.raises(MontantInvalide, match="0 FCFA"):
        services.soumettre(facture, finances())


def test_seule_la_direction_valide_et_attribue_le_numero_et_l_echeance():
    facture = a_valider()
    for role in (Role.FINANCES, Role.ADMIN, Role.RH):
        with pytest.raises(ActionFactureNonAutorisee):
            services.valider(facture, UserFactory(role=role))
    superadmin = UserFactory(role="", is_superuser=True)
    with pytest.raises(ActionFactureNonAutorisee):
        services.valider(facture, superadmin)  # un superutilisateur agit en ADMIN : pas de validation
    chef = direction()

    services.valider(facture, chef, aujourd_hui=date(2026, 9, 1))

    facture.refresh_from_db()
    assert facture.statut == StatutFacture.EMISE
    assert facture.numero == "FACT-2026-0001"
    assert facture.date_emission == date(2026, 9, 1)
    assert facture.date_echeance == date(2026, 10, 1)  # + 30 jours (délai du client)
    assert facture.validee_par == chef and facture.date_validation is not None


def test_l_echeance_suit_le_delai_de_paiement_de_la_facture():
    facture = brouillon()
    services.modifier_conditions(facture, finances(), taux_tva=Decimal("18"), delai_paiement_jours=45)
    services.soumettre(facture, finances())

    services.valider(facture, direction(), aujourd_hui=date(2026, 9, 1))

    assert facture.date_echeance == date(2026, 10, 16)


def test_la_numerotation_est_sequentielle_par_annee_et_sans_trou():
    premiere = emise(aujourd_hui=date(2026, 12, 30))
    abandonnee = brouillon()
    services.abandonner_brouillon(abandonnee, finances())
    deuxieme = emise(aujourd_hui=date(2026, 12, 31))
    nouvelle_annee = emise(aujourd_hui=date(2027, 1, 2))

    assert [premiere.numero, deuxieme.numero, nouvelle_annee.numero] == [
        "FACT-2026-0001", "FACT-2026-0002", "FACT-2027-0001",
    ]


def test_on_ne_valide_qu_une_facture_a_valider():
    for facture in (brouillon(), emise()):
        with pytest.raises(TransitionFactureInterdite):
            services.valider(facture, direction())


def test_la_direction_refuse_avec_un_motif_et_la_facture_redevient_brouillon():
    facture = a_valider()

    with pytest.raises(MontantInvalide, match="motif"):
        services.refuser(facture, direction(), motif="  ")
    services.refuser(facture, direction(), motif="Prix à revoir")

    facture.refresh_from_db()
    assert facture.statut == StatutFacture.BROUILLON and facture.motif_refus == "Prix à revoir"
    services.soumettre(facture, finances())
    facture.refresh_from_db()
    assert facture.statut == StatutFacture.A_VALIDER and facture.motif_refus == ""


def test_seule_la_direction_refuse():
    facture = a_valider()

    with pytest.raises(ActionFactureNonAutorisee):
        services.refuser(facture, finances(), motif="Non")


def test_les_contraintes_de_la_base_protegent_les_regles_essentielles():
    facture = brouillon()
    with pytest.raises(IntegrityError), transaction.atomic():
        Facture.objects.filter(pk=facture.pk).update(taux_tva=0, motif_exoneration="")
    with pytest.raises(IntegrityError), transaction.atomic():
        Facture.objects.filter(pk=facture.pk).update(montant_ttc=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        Facture.objects.filter(pk=facture.pk).update(statut=StatutFacture.EMISE)  # sans numéro ni dates
    with pytest.raises(IntegrityError), transaction.atomic():
        Facture.objects.create(
            client=facture.client, mission=facture.mission, taux_tva=18, delai_paiement_jours=30
        )


# --- règlements ---


def _regler(facture, montant, *, mode=ModePaiement.VIREMENT, jour=JOUR, acteur=None, **kw):
    return services.enregistrer_reglement(
        facture, acteur or finances(), montant=Decimal(montant), mode=mode, date_reglement=jour, **kw
    )


def test_acompte_puis_solde_mettent_a_jour_le_statut_et_le_reste_a_recouvrer():
    facture = emise(prix="1000000")  # TTC 1 180 000

    _regler(facture, "500000", reference="VIR-1")
    facture.refresh_from_db()
    assert facture.statut == StatutFacture.PARTIELLEMENT_PAYEE
    assert services.reste_a_recouvrer(facture) == Decimal("680000")
    assert services.montant_regle(facture) == Decimal("500000")

    _regler(facture, "680000", mode=ModePaiement.WAVE)
    facture.refresh_from_db()
    assert facture.statut == StatutFacture.PAYEE
    assert services.reste_a_recouvrer(facture) == 0


def test_un_reglement_ne_peut_pas_depasser_le_reste_a_recouvrer():
    facture = emise(prix="1000000")
    _regler(facture, "1000000")

    with pytest.raises(ReglementInvalide, match="dépasse le reste à recouvrer"):
        _regler(facture, "200000")
    assert Reglement.objects.count() == 1


@pytest.mark.parametrize("montant", ["0", "-10"])
def test_un_montant_de_reglement_doit_etre_positif(montant):
    with pytest.raises(ReglementInvalide, match="strictement positif"):
        _regler(emise(), montant)


def test_pas_de_reglement_avant_l_emission_ni_dans_le_futur():
    facture = emise(aujourd_hui=JOUR)

    with pytest.raises(ReglementInvalide, match="précéder"):
        _regler(facture, "1000", jour=JOUR - timedelta(days=1))
    with pytest.raises(ReglementInvalide, match="futur"):
        _regler(facture, "1000", jour=timezone.localdate() + timedelta(days=1))


def test_pas_de_reglement_sur_un_brouillon_ni_une_facture_a_valider_ni_soldee():
    for facture in (brouillon(), a_valider()):
        with pytest.raises(ReglementInvalide, match="Impossible d'enregistrer"):
            _regler(facture, "1000")
    soldee = emise(prix="1000")
    _regler(soldee, "1180")
    with pytest.raises(ReglementInvalide):
        _regler(soldee, "1")


def test_les_reglements_sont_reserves_a_finances_et_admin():
    facture = emise()

    with pytest.raises(ActionFactureNonAutorisee):
        _regler(facture, "1000", acteur=direction())
    assert _regler(facture, "1000", acteur=UserFactory(role=Role.ADMIN)).pk


def test_annuler_un_reglement_restitue_le_reste_et_le_statut():
    facture = emise(prix="1000000")
    reglement = _regler(facture, "1180000")
    assert facture.statut == StatutFacture.PAYEE

    services.annuler_reglement(reglement, finances(), motif="Chèque sans provision")

    facture.refresh_from_db()
    assert facture.statut == StatutFacture.EMISE
    assert services.reste_a_recouvrer(facture) == Decimal("1180000")
    assert not Reglement.objects.filter(pk=reglement.pk).exists()
    ancien = Reglement.all_objects.get(pk=reglement.pk)
    assert ancien.is_deleted and ancien.motif_annulation == "Chèque sans provision"


def test_annuler_un_seul_de_deux_reglements_laisse_la_facture_partiellement_payee():
    facture = emise(prix="1000000")
    premier, _ = _regler(facture, "300000"), _regler(facture, "200000")

    services.annuler_reglement(premier, finances(), motif="Erreur de saisie")

    facture.refresh_from_db()
    assert facture.statut == StatutFacture.PARTIELLEMENT_PAYEE
    assert services.reste_a_recouvrer(facture) == Decimal("980000")


def test_annulation_de_reglement_exige_un_motif_et_le_bon_role():
    reglement = _regler(emise(), "1000")

    with pytest.raises(ReglementInvalide, match="motif"):
        services.annuler_reglement(reglement, finances(), motif=" ")
    with pytest.raises(ActionFactureNonAutorisee):
        services.annuler_reglement(reglement, direction(), motif="Test")


# --- lecture et recherche ---


def test_est_echue_seulement_si_emise_non_soldee_et_apres_l_echeance():
    facture = emise(aujourd_hui=JOUR)  # échéance 2026-10-01

    assert not services.est_echue(facture, date(2026, 10, 1))  # le jour même : pas encore
    assert services.est_echue(facture, date(2026, 10, 2))
    _regler(facture, "1180000")
    assert not services.est_echue(facture, date(2026, 12, 1))  # soldée
    assert not services.est_echue(brouillon(), date(2030, 1, 1))


def test_factures_echues_et_creances():
    payee, en_retard, a_jour = emise(aujourd_hui=JOUR), emise(aujourd_hui=JOUR), emise(aujourd_hui=date(2026, 9, 25))
    _regler(payee, "1180000")
    _regler(en_retard, "180000")
    brouillon()  # pas une créance

    situation = services.creances(date(2026, 10, 5))

    assert set(services.factures_echues(date(2026, 10, 5))) == {en_retard}
    assert situation == {
        "total": Decimal("2180000"),  # 1 000 000 restant + 1 180 000 non réglé (TTC)
        "nombre": 2,
        "echu": Decimal("1000000"),
        "nombre_echues": 1,
    }
    assert a_jour.numero  # émise mais pas échue


def test_rechercher_factures_par_texte_statut_client_et_echeance():
    client = ClientFactory(raison_sociale="Cimaf Côte d'Ivoire")
    a = emise(client=client)
    b = emise()
    brouillon()

    assert list(services.rechercher_factures(recherche="cimaf")) == [a]
    assert list(services.rechercher_factures(recherche=a.numero.lower())) == [a]
    assert list(services.rechercher_factures(recherche=b.mission.numero)) == [b]
    assert list(services.rechercher_factures(client=client)) == [a]
    assert services.rechercher_factures(statut=StatutFacture.EMISE).count() == 2
    assert services.rechercher_factures(statut="INCONNU").count() == 3  # ignoré
    assert services.rechercher_factures(echues=True, aujourd_hui=date(2026, 10, 2)).count() == 2
    assert services.rechercher_factures(echues=True, aujourd_hui=date(2026, 9, 2)).count() == 0


def test_le_reste_et_le_regle_sont_calcules_en_une_requete(django_assert_num_queries):
    facture = emise()
    _regler(facture, "100000")

    with django_assert_num_queries(1):
        ligne = list(services.factures_queryset())[0]
        assert (ligne.montant_regle, ligne.reste) == (Decimal("100000"), Decimal("1080000"))


def test_chiffre_d_affaires_et_encaissements_de_la_periode():
    emise(prix="1000000", aujourd_hui=date(2026, 9, 10))
    hors_periode = emise(prix="500000", aujourd_hui=date(2026, 8, 20))
    brouillon(prix="9000000")
    _regler(hors_periode, "100000", jour=date(2026, 8, 25))
    _regler(hors_periode, "200000", jour=date(2026, 9, 3))

    assert services.chiffre_affaires(date(2026, 9, 1), date(2026, 9, 30)) == Decimal("1000000")
    assert services.encaissements(date(2026, 9, 1), date(2026, 9, 30)) == Decimal("200000")
    assert services.chiffre_affaires(date(2026, 1, 1), date(2026, 1, 31)) == 0


# --- dépenses ---


def test_enregistrer_une_depense_et_totaux_par_categorie():
    acteur = finances()
    for categorie, montant in (("PEAGES", "15000"), ("PEAGES", "5000"), ("ENTRETIEN", "80000")):
        services.enregistrer_depense(
            acteur, categorie=categorie, date_depense=date(2026, 9, 5), libelle=f"{categorie} test",
            montant=Decimal(montant), mode=ModePaiement.ESPECES,
        )

    par_categorie = {c["code"]: c["total"] for c in services.depenses_par_categorie(date(2026, 9, 1), date(2026, 9, 30))}

    assert par_categorie == {"PEAGES": 20000, "ENTRETIEN": 80000, "FRAIS_ADMIN": 0, "AUTRE": 0}
    assert services.total_depenses(date(2026, 9, 1), date(2026, 9, 30)) == Decimal("100000")
    assert services.total_depenses(date(2026, 10, 1), date(2026, 10, 31)) == 0


@pytest.mark.parametrize(
    ("libelle", "montant", "jour", "message"),
    [
        (" ", "1000", date(2026, 9, 1), "libellé"),
        ("x", "0", date(2026, 9, 1), "strictement positif"),
        ("x", "1000", date(2999, 1, 1), "futur"),
    ],
)
def test_depenses_invalides(libelle, montant, jour, message):
    with pytest.raises(MontantInvalide, match=message):
        services.enregistrer_depense(
            finances(), categorie="PEAGES", date_depense=jour, libelle=libelle,
            montant=Decimal(montant), mode=ModePaiement.ESPECES,
        )


def test_les_depenses_sont_reservees_a_finances_et_admin():
    with pytest.raises(ActionFactureNonAutorisee):
        services.enregistrer_depense(
            direction(), categorie="PEAGES", date_depense=date(2026, 9, 1), libelle="x",
            montant=Decimal("1"), mode=ModePaiement.ESPECES,
        )


def test_recherche_de_depenses_par_texte_categorie_et_periode():
    acteur = finances()
    mission = mission_livree()
    services.enregistrer_depense(acteur, categorie="PEAGES", date_depense=date(2026, 9, 5),
                                 libelle="Péage Yamoussoukro", montant=Decimal("5000"),
                                 mode=ModePaiement.ESPECES, mission=mission)
    services.enregistrer_depense(acteur, categorie="FRAIS_ADMIN", date_depense=date(2026, 8, 5),
                                 libelle="Timbres", montant=Decimal("1000"), mode=ModePaiement.ESPECES)

    assert services.rechercher_depenses(recherche="peage").count() == 1
    assert services.rechercher_depenses(recherche=mission.numero).count() == 1
    assert services.rechercher_depenses(categorie="FRAIS_ADMIN").count() == 1
    assert services.rechercher_depenses(date_debut=date(2026, 9, 1)).count() == 1
    assert services.rechercher_depenses(date_fin=date(2026, 8, 31)).count() == 1


# --- alerte de signal ---


def test_un_recepteur_en_erreur_ne_bloque_jamais_la_facturation(caplog):
    from apps.billing import signals

    def panne(sender, **kwargs):
        raise RuntimeError("panne")

    signals.facture_a_valider.connect(panne, weak=False)
    signals.facture_validee.connect(panne, weak=False)
    signals.facture_refusee.connect(panne, weak=False)
    try:
        facture = brouillon()
        services.soumettre(facture, finances())
        services.refuser(facture, direction(), motif="x")
        services.soumettre(facture, finances())
        services.valider(facture, direction(), aujourd_hui=JOUR)
    finally:
        for signal in (signals.facture_a_valider, signals.facture_validee, signals.facture_refusee):
            signal.disconnect(panne)

    assert facture.statut == StatutFacture.EMISE and "en erreur" in caplog.text
```

## Étape 5 — Déclarer l'application et migrer

#### `config/settings/base.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/settings/base.py (avant)
+++ config/settings/base.py (après)
@@ -60,4 +60,5 @@
     "apps.inventory",
     "apps.fuel",
+    "apps.billing",
 ]
 
```

```bash
python manage.py makemigrations billing
python manage.py migrate
```

**Résultat attendu :** `Create model Facture`, `Create model LigneFacture`, `Create model Reglement`,
`Create model Depense`, les contraintes, puis `Applying billing.0001_initial... OK`.

## Vérifier le chapitre

```bash
python manage.py check
```

```bash
python -m pytest apps/billing/tests/test_services.py -q --no-cov
```

**Résultat attendu :** `52 passed` (pour les 1 fichier(s) de tests présentés dans ce chapitre).

(Les tests d'écrans de `billing` sont présentés au chapitre 25.)

Essai dans le shell : l'arrondi au franc.

```bash
python manage.py shell -c "from decimal import Decimal; from apps.billing.services import arrondir_franc; print(arrondir_franc(Decimal('100530.5')), arrondir_franc(Decimal('100530.49')))"
```

**Résultat attendu :** `100531 100530`.

## Ce qu'il faut retenir

- Le **numéro attribué à la validation** évite les trous dans une numérotation légale.
- Les règles de **rôle** vivent dans les **services** : elles s'appliquent quel que soit le point d'entrée
  (interface, API, mobile).
- Après validation, **rien ne bouge plus** : la seule façon de corriger, c'est un nouveau document.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 13 : app billing (factures, TVA, règlements, dépenses)"
```

---

[← Chapitre 12](12-fuel.md) · [Sommaire](README.md) · [Chapitre 14 →](14-finance.md)
