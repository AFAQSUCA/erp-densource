# Chapitre 15 — La comptabilité en partie double : l'app accounting

> 26 fichier(s) dans ce chapitre, 4020 lignes de code.

## Ce que vous allez construire

**`accounting`** : la **comptabilité en partie double**, au référentiel **SYSCOHADA révisé**
(cahier-des-charges.md:340). Comme `finance`, c'est une **couche au-dessus** des autres apps : elle ne
saisit rien elle-même, elle **écoute** ce que `billing` et `finance` ont déjà validé et en tire des
**écritures toujours équilibrées**.

| Événement | Écriture générée |
|---|---|
| Facture **validée** (`billing`) | débit Client (TTC), crédit Ventes (HT) et TVA collectée |
| Règlement **encaissé** (`billing`) | débit Trésorerie (banque/caisse/mobile money selon le mode), crédit Client |
| Dépense **automatique** (plein, pièces, main-d'œuvre d'OR, frais de mission…) | débit Charge (+ TVA déductible), crédit Trésorerie |
| Mode de paiement d'une dépense **corrigé après coup** | contre-passe l'ancien compte de trésorerie, impute le nouveau |
| Mouvement manuel de trésorerie (`finance`) | débit ou crédit Trésorerie, contrepartie selon sa nature |
| Saisie manuelle (« opérations diverses ») | brouillon → lignes → **validation par la DIRECTION** |

**Le principe central : personne n'écrit d'écriture à la main dans le code.** Une seule fonction,
`services.passer_ecriture`, crée une `EcritureComptable` — elle garantit elle-même l'**équilibre**
(débit == crédit), l'**idempotence** (rejouer le même événement ne recrée rien) et que l'**exercice**
concerné n'est pas clôturé. Chaque événement a sa fonction dédiée qui prépare les lignes puis appelle
`passer_ecriture` ; si l'écriture ne peut pas s'équilibrer, **l'opération d'origine est annulée** plutôt
que de laisser un grand livre incomplet.

Une fois validée, une écriture ne se modifie ni ne se supprime : seule une **contre-passation**
(non livrée dans ce lot) la corrige. Un **exercice comptable** (année civile) s'ouvre tout seul à la
première écriture qui le concerne ; la DIRECTION peut le **clôturer**, ce qui verrouille définitivement
toute nouvelle écriture datée dans sa période.

Ce chapitre présente aussi les **rapports en lecture seule** (grand livre, balance, bilan, compte de
résultat, déclaration TVA) : uniquement des agrégations sur les écritures déjà posées, aucun nouveau
modèle. Leurs **écrans** viennent au chapitre 27, une fois le tableau de bord et les autres écrans en
place.

> Le **plan comptable de départ** est une liste de travail, à valider par un expert-comptable avant mise
> en production (aucun cabinet externe consulté à ce stade). Il est chargé par une **migration de
> données** que vous écrivez à la main dans ce chapitre (Étape 7) — la seule migration de tout ce
> tutoriel à ne pas être générée par `makemigrations` : les autres, purement schéma, sont reproductibles
> depuis les modèles et ne sont donc jamais recopiées (voir la couverture en fin de tutoriel).

**Clôture d'un exercice et bilan.** `cloturer_exercice` pose une **écriture de clôture** (`ecriture_de_cloture`, journal OD, datée du
31/12) : chaque compte de charge ou de produit est soldé et le résultat est **viré au compte 120000** (crédit si bénéfice, débit si
perte). Sans elle, le résultat de l'année N disparaissait du bilan de l'année N+1 (cumulé depuis l'origine), qui ne s'équilibrait
plus. Le compte de résultat et la balance **ignorent** cette écriture (un exercice clôturé garde son activité visible) ; le bilan
l'inclut. La commande `ecrire_clotures_historiques` reprend les exercices clôturés avant ce lot.

**Corriger sans effacer.** Une écriture validée ne se modifie jamais : `contre_passer` pose l'écriture inverse (même journal, même
pièce, datée du jour). Annuler un règlement ou un mouvement manuel contre-passe automatiquement son écriture ; la commande
`contre_passer_historique_annulations` reprend l'existant. Le grand livre est en **lecture seule** dans l'administration Django, et
un sens autre que débit/crédit est refusé par `passer_ecriture`.

## Prérequis

- Chapitres 1 à 14 terminés.

## Notions Django de ce chapitre

- **Un seul point d'entrée pour écrire** : `passer_ecriture` est la **seule** fonction qui crée une
  `EcritureComptable` ; elle vérifie l'équilibre elle-même, **jamais l'appelant** — à l'image de
  `_exiger_role`/`_exiger_statut` dans `apps.billing.services`.
- **Idempotence par `(origine, origine_id)`** : une contrainte d'unicité **et** une vérification en
  amont dans `passer_ecriture` garantissent que rejouer le même événement (ou relancer une commande de
  reprise d'historique) ne double jamais une écriture.
- **Verrouillage en Python, pas seulement par une règle métier** : `EcritureComptable.save()` et
  `.delete()`, `LigneEcriture.save()` et `.delete()` lèvent une exception dès qu'on touche à une écriture
  déjà `VALIDEE` — impossible à contourner en passant par un autre chemin que les services.
- **Rattachement générique optionnel** (`tiers_type`/`tiers_id`) : `LigneEcriture` peut pointer vers un
  client sans **aucune** dépendance au niveau du modèle envers `customers` — le découplage entre apps se
  paie ici en indirection, pas en `ForeignKey`.
- **`send()` brut, pas `send_robust`** : contrairement aux signaux que `notifications` consomme
  (chapitre 16), ceux que `accounting` consomme sont envoyés **bruts** — une écriture qui échoue à
  s'équilibrer doit annuler l'opération d'origine, jamais être silencieusement absente du grand livre.
- **`Sum` avec `filter=Q(...)`, `Coalesce`** : `_agreger_par_compte` calcule en une seule requête le
  total débit **et** crédit de chaque compte mouvementé — la base fait le travail, pas une boucle Python.
- **Commandes de reprise d'historique, volontairement pas une migration** : `comptabiliser_historique_*`
  rejoue les événements déjà enregistrés **avant** la mise en service de la comptabilisation automatique
  — à lancer une fois, à la main, jamais dans une migration (le choix d'inclure ou non l'historique avant
  un solde d'ouverture appartient à qui déploie, pas au code).
- **Migration de données (`RunPython`)** : contrairement à une migration de schéma (déduite de
  `models.py` par `makemigrations`), une migration de données est écrite à la main — ici pour peupler le
  plan comptable de départ. `apps.get_model("accounting", "Compte")` (et non un `import` direct du
  modèle) fige la version du modèle **au moment de cette migration** : le code continue de fonctionner
  même si `Compte` change de forme plus tard. `update_or_create` la rend **idempotente** (rejouable sans
  doublon), et son second argument (`retirer`) permet de la défaire avec `migrate accounting 0001`.

## Étape 1 — Créer l'application

```bash
mkdir -p apps/accounting/tests apps/accounting/management/commands
```

#### Fichiers vides à créer

Ces fichiers n'ont aucun contenu ; ils servent à faire de leur dossier un *paquet Python* (sans eux, `import apps.xxx` échouerait). Créez d'abord les dossiers, puis les fichiers :

```bash
mkdir -p apps\accounting apps\accounting\management apps\accounting\management\commands apps\accounting\tests
touch apps/accounting/__init__.py
touch apps/accounting/management/__init__.py
touch apps/accounting/management/commands/__init__.py
touch apps/accounting/tests/__init__.py
```

> Sous PowerShell, `mkdir -p` s'écrit `New-Item -ItemType Directory -Force <dossier>` et `touch fichier` s'écrit `New-Item -ItemType File -Force fichier`. Vous pouvez aussi créer ces fichiers avec votre éditeur.

## Étape 2 — Le plan comptable et le moteur d'écritures

#### `apps/accounting/models.py`

*222 lignes*

```python
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel

from .exceptions import EcritureVerrouillee


class NatureCompte(models.TextChoices):
    """Sens naturel d'un compte du plan comptable — détermine son solde normal."""

    ACTIF = "ACTIF", _("Actif")
    PASSIF = "PASSIF", _("Passif")
    CHARGE = "CHARGE", _("Charge")
    PRODUIT = "PRODUIT", _("Produit")


class Compte(models.Model):
    """Un compte du plan comptable SYSCOHADA révisé.

    Table de référence technique (comme ``core.CompteurNumero``) : jamais soft-supprimée,
    seulement désactivée (``actif=False``) si elle ne doit plus servir à de nouvelles écritures.
    """

    numero = models.CharField(_("numéro"), max_length=10, unique=True)
    libelle = models.CharField(_("libellé"), max_length=150)
    nature = models.CharField(_("nature"), max_length=10, choices=NatureCompte.choices)
    actif = models.BooleanField(_("actif"), default=True)

    class Meta:
        verbose_name = _("compte")
        verbose_name_plural = _("plan comptable")
        ordering = ["numero"]

    def __str__(self):
        return f"{self.numero} — {self.libelle}"


class Journal(models.TextChoices):
    """5 journaux auxiliaires SYSCOHADA — chaque écriture appartient à l'un d'eux."""

    ACHATS = "ACH", _("Achats")
    VENTES = "VTE", _("Ventes")
    BANQUE = "BQ", _("Banque")
    CAISSE = "CAI", _("Caisse")
    OPERATIONS_DIVERSES = "OD", _("Opérations diverses")


class SensEcriture(models.TextChoices):
    DEBIT = "DEBIT", _("Débit")
    CREDIT = "CREDIT", _("Crédit")


class StatutEcriture(models.TextChoices):
    """Une écriture automatique naît toujours ``VALIDEE`` (elle découle d'un événement déjà
    validé ailleurs, cahier-des-charges.md:340). ``BROUILLON`` sert à la saisie manuelle
    (opérations diverses), pas encore livrée à ce stade."""

    BROUILLON = "BROUILLON", _("Brouillon")
    VALIDEE = "VALIDEE", _("Validée")


class EcritureComptable(BaseModel):
    """En-tête d'une écriture comptable — cahier-des-charges.md:340 (« écriture comptable
    équilibrée »). Une fois ``VALIDEE``, elle ne se modifie ni ne se supprime : seule une
    contre-passation (nouvelle écriture inverse) corrige une erreur.
    """

    numero = models.CharField(_("numéro"), max_length=20, blank=True)
    journal = models.CharField(_("journal"), max_length=3, choices=Journal.choices)
    date_ecriture = models.DateField(_("date"))
    libelle = models.CharField(_("libellé"), max_length=255)
    piece_reference = models.CharField(_("pièce justificative"), max_length=30, blank=True)
    origine = models.CharField(_("origine"), max_length=30, blank=True)
    origine_id = models.PositiveIntegerField(_("ID origine"), null=True, blank=True)
    statut = models.CharField(
        _("statut"), max_length=10, choices=StatutEcriture.choices, default=StatutEcriture.VALIDEE
    )
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("créée par"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("validée par"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    date_validation = models.DateTimeField(_("validée le"), null=True, blank=True)

    class Meta:
        verbose_name = _("écriture comptable")
        verbose_name_plural = _("écritures comptables")
        ordering = ["-date_ecriture", "-pk"]
        indexes = [models.Index(fields=["journal", "date_ecriture"])]
        constraints = [
            models.UniqueConstraint(
                fields=["numero"], condition=~Q(numero=""), name="ecriture_numero_unique"
            ),
            models.UniqueConstraint(
                fields=["origine", "origine_id"],
                condition=~Q(origine=""),
                name="ecriture_une_par_origine",
            ),
        ]

    def __str__(self):
        return self.numero or f"{self.journal} — {self.libelle}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            statut_en_base = (
                type(self).all_objects.filter(pk=self.pk).values_list("statut", flat=True).first()
            )
            if statut_en_base == StatutEcriture.VALIDEE:
                raise EcritureVerrouillee(
                    "Une écriture validée ne se modifie pas : contre-passez-la."
                )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Une écriture encore en brouillon peut être abandonnée (soft delete, ``BaseModel``) ;
        une écriture validée ne se supprime jamais, seule une contre-passation la corrige."""
        if self.statut == StatutEcriture.VALIDEE:
            raise EcritureVerrouillee("Une écriture validée ne se supprime jamais : contre-passez-la.")
        super().delete(*args, **kwargs)


class LigneEcriture(models.Model):
    """Ligne débit ou crédit d'une écriture — append-only, comme ``inventory.MouvementStock``."""

    ecriture = models.ForeignKey(
        EcritureComptable, verbose_name=_("écriture"), on_delete=models.CASCADE, related_name="lignes"
    )
    compte = models.ForeignKey(
        Compte, verbose_name=_("compte"), on_delete=models.PROTECT, related_name="lignes"
    )
    sens = models.CharField(_("sens"), max_length=6, choices=SensEcriture.choices)
    montant = models.DecimalField(_("montant (FCFA)"), max_digits=14, decimal_places=2)
    libelle = models.CharField(_("libellé"), max_length=255, blank=True)
    # Rattachement générique optionnel (ex. tiers_type="CLIENT", tiers_id=client.pk) : sert au
    # suivi par tiers (compte 411 par client) sans dépendre de ``customers`` au niveau du modèle.
    tiers_type = models.CharField(_("type de tiers"), max_length=20, blank=True)
    tiers_id = models.PositiveIntegerField(_("ID tiers"), null=True, blank=True)

    class Meta:
        verbose_name = _("ligne d'écriture")
        verbose_name_plural = _("lignes d'écriture")
        ordering = ["ecriture", "pk"]
        indexes = [models.Index(fields=["compte"]), models.Index(fields=["tiers_type", "tiers_id"])]
        constraints = [
            models.CheckConstraint(condition=Q(montant__gt=0), name="ligne_ecriture_montant_positif"),
        ]

    def __str__(self):
        return f"{self.compte.numero} {self.get_sens_display()} {self.montant}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("LigneEcriture est append-only : contre-passez plutôt que modifier.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Une ligne d'une écriture encore en brouillon (saisie manuelle) peut être retirée ; une
        fois l'écriture validée, plus aucune ligne ne se supprime."""
        if self.ecriture.statut == StatutEcriture.VALIDEE:
            raise EcritureVerrouillee(
                "Une ligne d'une écriture validée ne se supprime pas : contre-passez plutôt."
            )
        super().delete(*args, **kwargs)


class StatutExercice(models.TextChoices):
    OUVERT = "OUVERT", _("Ouvert")
    CLOTURE = "CLOTURE", _("Clôturé")


class ExerciceComptable(BaseModel):
    """Exercice comptable — année civile (hypothèse par défaut alignée sur
    ``core.CompteurNumero`` ; le cahier des charges ne précise pas de date de clôture fiscale
    propre à l'entreprise, à confirmer avec l'expert-comptable avant mise en production).

    Auto-créé ``OUVERT`` au passage de la première écriture de son année (même principe que
    ``core.services.prochain_numero``) : aucun geste explicite n'est requis pour « ouvrir »
    une nouvelle année. Une fois ``CLOTURE``, aucune écriture ne peut plus être datée dans sa
    période — jamais rouvert (une correction après clôture attend une phase de contre-passation).
    """

    annee = models.PositiveSmallIntegerField(_("année"), unique=True)
    date_debut = models.DateField(_("début"))
    date_fin = models.DateField(_("fin"))
    statut = models.CharField(
        _("statut"), max_length=10, choices=StatutExercice.choices, default=StatutExercice.OUVERT
    )
    cloture_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("clôturé par"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    date_cloture = models.DateTimeField(_("clôturé le"), null=True, blank=True)

    class Meta:
        verbose_name = _("exercice comptable")
        verbose_name_plural = _("exercices comptables")
        ordering = ["-annee"]

    def __str__(self):
        return f"Exercice {self.annee}"

    def delete(self, *args, **kwargs):
        raise ValueError("ExerciceComptable ne se supprime jamais.")
```

Quatre modèles : `Compte` (plan comptable, table de référence — jamais supprimée, seulement désactivée),
`EcritureComptable` (en-tête, `BROUILLON` ou `VALIDEE`), `LigneEcriture` (ligne débit/crédit,
append-only une fois l'écriture validée) et `ExerciceComptable` (année, statut `OUVERT`/`CLOTURE`).
Repérez les `save()`/`delete()` redéfinis : c'est là que vit le verrouillage.

#### `apps/accounting/exceptions.py`

*39 lignes*

```python
from apps.core.exceptions import ErreurMetier


class AccountingError(ErreurMetier):
    """Erreur métier de la comptabilité."""


class EcritureNonEquilibree(AccountingError):
    """Le total des débits ne correspond pas au total des crédits."""


class CompteInconnu(AccountingError):
    """Le compte demandé n'existe pas dans le plan comptable, ou n'est plus actif."""


class CompteDejaExistant(AccountingError):
    """Un compte porte déjà ce numéro dans le plan comptable."""


class EcritureVerrouillee(AccountingError):
    """Une écriture déjà validée ne se modifie ni ne se supprime."""


class ActionComptableNonAutorisee(AccountingError):
    """L'utilisateur n'a pas le droit d'effectuer cette action."""


class ExerciceCloture(AccountingError):
    """L'exercice comptable concerné est déjà clôturé : aucune écriture ne peut plus y être
    datée, ni y être clôturé une seconde fois."""


class ContrePassationImpossible(AccountingError):
    """Cette écriture ne peut pas être contre-passée (brouillon, ou déjà une contre-passation)."""


class ClotureImpossible(AccountingError):
    """L'exercice ne peut pas être clôturé : brouillons non résolus (saisie manuelle) ou année pas
    encore terminée."""
```

#### `apps/accounting/constants.py`

*59 lignes* — Numéros de comptes utilisés par le code (ancrages internes, pas de saisie utilisateur).

```python
"""Numéros de comptes utilisés par le code (ancrages internes, pas de saisie utilisateur).

Le plan comptable complet (``migrations/0002_plan_comptable_seed.py``) est une liste de travail
à valider par un expert-comptable avant mise en production (aucun cabinet externe consulté à ce
stade) ; seuls les comptes ci-dessous sont mobilisés par la Phase 1.
"""

from apps.billing.models import CategorieDepense, CompteTresorerie
from apps.finance.models import NatureMouvement

from .models import Journal

COMPTE_CLIENTS = "411000"
COMPTE_VENTES_TRANSPORT = "706100"
COMPTE_TVA_COLLECTEE = "443300"
COMPTE_TVA_DEDUCTIBLE = "445200"
COMPTE_RESULTAT = "120000"  # résultat de l'exercice : reçoit le solde des comptes 6/7 à la clôture

# billing.models.CategorieDepense -> Compte.numero — les 4 catégories automatiques
# (billing.models.CATEGORIES_AUTOMATIQUES) et les 4 catégories de saisie manuelle sont toutes
# mobilisées (avenant-comptabilite-autonomie.md § Lot C). Péages rattachés aux frais de mission
# (comptes de déplacement) ; Entretien au même compte que la main-d'œuvre des OR (prestataires
# extérieurs) ; Frais administratifs et Autre au compte générique de charges diverses — mapping
# de départ, à valider par un expert-comptable comme le reste du plan comptable.
CATEGORIE_DEPENSE_VERS_COMPTE = {
    CategorieDepense.CARBURANT: "605100",
    CategorieDepense.PIECES: "605800",
    CategorieDepense.MAINTENANCE: "624100",
    CategorieDepense.FRAIS_MISSION: "628100",
    CategorieDepense.PEAGES: "628100",
    CategorieDepense.ENTRETIEN: "624100",
    CategorieDepense.FRAIS_ADMIN: "658000",
    CategorieDepense.AUTRE: "658000",
}

# finance.models.NatureMouvement -> Compte.numero (contrepartie du mouvement manuel de trésorerie).
NATURE_MOUVEMENT_VERS_COMPTE = {
    NatureMouvement.SOLDE_OUVERTURE: "101000",
    NatureMouvement.APPORT: "101000",
    NatureMouvement.RETRAIT: "108000",
    NatureMouvement.FRAIS_BANCAIRE: "631000",
    NatureMouvement.AUTRE: "658000",
}

# apps.billing.models.CompteTresorerie -> Compte.numero (Mobile Money reste fusionné pour les
# 3 opérateurs, cf. avenant-comptabilite-syscohada.md).
COMPTE_TRESORERIE_VERS_COMPTE = {
    CompteTresorerie.BANQUE: "521000",
    CompteTresorerie.CAISSE: "571000",
    CompteTresorerie.MOBILE_MONEY: "521900",
}

# apps.billing.models.CompteTresorerie -> Journal : le Mobile Money, dématérialisé, n'a pas de
# journal auxiliaire dédié dans les 5 journaux SYSCOHADA standards — rattaché à la Banque.
COMPTE_TRESORERIE_VERS_JOURNAL = {
    CompteTresorerie.BANQUE: Journal.BANQUE,
    CompteTresorerie.CAISSE: Journal.CAISSE,
    CompteTresorerie.MOBILE_MONEY: Journal.BANQUE,
}
```

Numéros de comptes **mobilisés par le code** (pas de saisie utilisateur) : `COMPTE_CLIENTS`,
`COMPTE_VENTES_TRANSPORT`, la TVA collectée/déductible, et trois tables de correspondance —
catégorie de dépense, nature de mouvement manuel, mode de paiement — vers un numéro de compte. Ce
mapping est le même genre de choix qu'un `COMPTE_DU_MODE` dans `billing` : un dictionnaire, pas une
suite de `if`.

#### `apps/accounting/permissions.py`

*24 lignes* — Qui peut consulter, saisir, valider et clôturer la comptabilité.

```python
"""Qui peut consulter, saisir, valider et clôturer la comptabilité.

Cohérent avec ``billing.permissions`` : la RH fait tout ce que fait la FINANCES, la DIRECTION a
la même largeur que l'ADMIN — sauf sur la validation d'une écriture manuelle et la clôture d'un
exercice, strictement réservées à la DIRECTION (comme la validation d'une facture, jamais
l'ADMIN/un superutilisateur à sa place : ce sont les deux seuls contrôles comptables a posteriori
sur une saisie humaine).
"""

from apps.accounts.models import Role

CONSULTATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.FINANCES, Role.RH})

# Saisie d'une écriture manuelle (opérations diverses, P4) : créer le brouillon, y ajouter/retirer
# des lignes, l'abandonner.
SAISIE_OD = frozenset({Role.ADMIN, Role.DIRECTION, Role.FINANCES, Role.RH})
# Validation d'une écriture manuelle : DIRECTION seule, contrôle strict.
VALIDATION_OD = frozenset({Role.DIRECTION})
# Clôture d'un exercice comptable (P5) : DIRECTION seule, contrôle strict.
CLOTURE_EXERCICE = frozenset({Role.DIRECTION})
# Gestion du plan comptable (créer/modifier un compte, Lot F autonomie comptable) : même largeur
# que la saisie d'une écriture manuelle, pas de contrôle Direction a posteriori (ce n'est pas une
# transaction financière, seulement le paramétrage du référentiel).
GESTION_PLAN_COMPTABLE = frozenset({Role.ADMIN, Role.DIRECTION, Role.FINANCES, Role.RH})
```

Cinq ensembles : `CONSULTATION` (ADMIN, DIRECTION, FINANCES, RH), `SAISIE_OD` et
`GESTION_PLAN_COMPTABLE` (même largeur), puis deux contrôles **stricts**, réservés à la seule
DIRECTION : `VALIDATION_OD` (valider une écriture manuelle) et `CLOTURE_EXERCICE` — les deux seuls
contrôles comptables *a posteriori* sur une saisie humaine, sur le même principe que `Facture.valider`
dans `billing`.

## Étape 3 — Le service central : passer une écriture équilibrée

#### `apps/accounting/services.py`

*818 lignes* — Moteur d'écritures comptables — conventions.md §2.

```python
"""Moteur d'écritures comptables — conventions.md §2.

``passer_ecriture`` est le seul point d'entrée qui écrit une ``EcritureComptable`` : il garantit
lui-même l'équilibre (jamais l'appelant), à l'image de ``_exiger_role``/``_exiger_statut`` dans
``apps.billing.services``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Sequence

from django.db import transaction
from django.db.models import Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.billing.models import COMPTE_DU_MODE
from apps.core.services import prochain_numero

from .constants import (
    CATEGORIE_DEPENSE_VERS_COMPTE,
    COMPTE_CLIENTS,
    COMPTE_RESULTAT,
    COMPTE_TRESORERIE_VERS_COMPTE,
    COMPTE_TRESORERIE_VERS_JOURNAL,
    COMPTE_TVA_COLLECTEE,
    COMPTE_TVA_DEDUCTIBLE,
    COMPTE_VENTES_TRANSPORT,
    NATURE_MOUVEMENT_VERS_COMPTE,
)
from . import permissions
from .exceptions import (
    ActionComptableNonAutorisee,
    ClotureImpossible,
    CompteDejaExistant,
    ContrePassationImpossible,
    CompteInconnu,
    EcritureNonEquilibree,
    EcritureVerrouillee,
    ExerciceCloture,
)
from .models import (
    Compte,
    EcritureComptable,
    ExerciceComptable,
    Journal,
    LigneEcriture,
    NatureCompte,
    SensEcriture,
    StatutEcriture,
    StatutExercice,
)

ZERO = Decimal("0")


@dataclass(frozen=True)
class LigneSaisie:
    """Une ligne débit ou crédit à passer, avant résolution du ``Compte``."""

    compte: str
    sens: str
    montant: Decimal
    libelle: str = ""
    tiers_type: str = ""
    tiers_id: int | None = None


def _exiger_role(acteur, roles, action: str, *, strict: bool = False) -> None:
    role = acteur.role if strict else acteur.role_effectif
    if role not in roles:
        raise ActionComptableNonAutorisee(f"Vous n'avez pas le droit de {action}.")


def _exiger_brouillon(ecriture: EcritureComptable, action: str) -> None:
    if ecriture.statut != StatutEcriture.BROUILLON:
        raise EcritureVerrouillee(f"Impossible de {action} : l'écriture est « {ecriture.get_statut_display()} ».")


def creer_compte(acteur, *, numero: str, libelle: str, nature: str) -> Compte:
    """Ajoute un compte au plan comptable (avenant-comptabilite-autonomie.md § Lot F). Le numéro
    et la nature ne se modifient plus ensuite (:func:`modifier_compte`) : seuls le libellé et
    l'activation le peuvent, pour ne jamais reclasser silencieusement des écritures déjà
    posées."""
    _exiger_role(acteur, permissions.GESTION_PLAN_COMPTABLE, "créer un compte")
    numero = numero.strip()
    if not numero:
        raise CompteInconnu("Le numéro de compte est obligatoire.")
    if Compte.objects.filter(numero=numero).exists():
        raise CompteDejaExistant(f"Le compte {numero} existe déjà.")
    libelle = libelle.strip()
    if not libelle:
        raise CompteInconnu("Le libellé est obligatoire.")
    if nature not in NatureCompte.values:
        raise CompteInconnu("Nature de compte inconnue.")
    return Compte.objects.create(numero=numero, libelle=libelle, nature=nature)


def modifier_compte(compte: Compte, acteur, *, libelle: str, actif: bool) -> Compte:
    """Corrige le libellé d'un compte et/ou le désactive (jamais supprimé, voir
    ``Compte.__doc__``) : un compte désactivé ne peut plus être utilisé dans une nouvelle
    écriture, mais son historique reste lisible dans le grand livre."""
    _exiger_role(acteur, permissions.GESTION_PLAN_COMPTABLE, "modifier un compte")
    libelle = libelle.strip()
    if not libelle:
        raise CompteInconnu("Le libellé est obligatoire.")
    compte.libelle, compte.actif = libelle, actif
    compte.save(update_fields=["libelle", "actif"])
    return compte


def exercice_pour(date_ecriture: date) -> ExerciceComptable:
    """Renvoie l'exercice comptable (année civile) de cette date, le crée ``OUVERT`` s'il
    n'existe pas encore — même principe que ``core.services.prochain_numero`` : aucun geste
    explicite n'est requis pour « ouvrir » une nouvelle année."""
    exercice, _ = ExerciceComptable.objects.get_or_create(
        annee=date_ecriture.year,
        defaults={
            "date_debut": date(date_ecriture.year, 1, 1),
            "date_fin": date(date_ecriture.year, 12, 31),
        },
    )
    return exercice


def _exiger_exercice_ouvert(date_ecriture: date) -> None:
    exercice = exercice_pour(date_ecriture)
    if exercice.statut == StatutExercice.CLOTURE:
        raise ExerciceCloture(
            f"L'exercice {exercice.annee} est clôturé : aucune écriture ne peut plus y être datée."
        )


@transaction.atomic
def cloturer_exercice(exercice: ExerciceComptable, acteur) -> ExerciceComptable:
    """Clôture un exercice : verrouille toute nouvelle écriture datée dans sa période. Refusé s'il
    reste des brouillons (saisie manuelle non validée) dans la période — à valider ou abandonner
    avant de clôturer, pour ne jamais clôturer une année à l'insu d'une saisie en attente. Refusé aussi
    tant que l'année n'est pas terminée : toute opération datée d'ici là (règlement, dépense, plein...)
    serait alors refusée.
    Pose l'**écriture de clôture** (:func:`ecriture_de_cloture`) : le résultat de l'exercice est
    viré au compte 120000 pour que le bilan de l'exercice suivant l'y retrouve.
    Contrôle **strict** (``acteur.role``) : réservé à la DIRECTION, comme ``Facture.valider`` —
    jamais l'ADMIN ni un superutilisateur à sa place. Jamais rouvert ensuite."""
    _exiger_role(acteur, permissions.CLOTURE_EXERCICE, "clôturer un exercice", strict=True)
    if exercice.statut == StatutExercice.CLOTURE:
        raise ExerciceCloture(f"L'exercice {exercice.annee} est déjà clôturé.")
    if timezone.localdate() <= exercice.date_fin:
        raise ClotureImpossible(
            f"L'exercice {exercice.annee} ne peut être clôturé qu'après le {exercice.date_fin:%d/%m/%Y} : "
            "clôturé avant, il bloquerait toutes les opérations datées d'ici là (règlements, dépenses, pleins...)."
        )
    brouillons = EcritureComptable.objects.filter(
        statut=StatutEcriture.BROUILLON,
        date_ecriture__gte=exercice.date_debut,
        date_ecriture__lte=exercice.date_fin,
    ).count()
    if brouillons:
        raise ClotureImpossible(
            f"{brouillons} écriture(s) en brouillon reste(nt) dans cette période : "
            "validez-les ou abandonnez-les avant de clôturer."
        )
    ecriture_de_cloture(exercice)
    exercice.statut = StatutExercice.CLOTURE
    exercice.cloture_par = acteur
    exercice.date_cloture = timezone.now()
    exercice.save(update_fields=["statut", "cloture_par", "date_cloture", "updated_at"])
    return exercice


ORIGINE_CLOTURE = "CLOTURE"


def _lignes_de_resultat(exercice: ExerciceComptable) -> QuerySet[LigneEcriture]:
    """Lignes validées des comptes de charge/produit de la période, écriture de clôture exclue."""
    return LigneEcriture.objects.filter(
        ecriture__statut=StatutEcriture.VALIDEE,
        ecriture__date_ecriture__gte=exercice.date_debut,
        ecriture__date_ecriture__lte=exercice.date_fin,
        compte__nature__in=[NatureCompte.CHARGE, NatureCompte.PRODUIT],
    ).exclude(ecriture__origine=ORIGINE_CLOTURE)


@transaction.atomic
def ecriture_de_cloture(exercice: ExerciceComptable) -> EcritureComptable | None:
    """Vire le résultat de l'exercice au compte 120000 : chaque compte de charge ou de produit est
    soldé (sens inverse de son solde), la différence est portée au crédit (bénéfice) ou au débit
    (perte) du 120000. Sans cela le résultat de l'année N disparaîtrait du bilan de l'année N+1
    (cumulé depuis l'origine, il ne verrait que ses propres charges et produits).

    Datée du dernier jour de l'exercice, journal des opérations diverses, validée d'office.
    Idempotente (``origine`` = ``CLOTURE``, ``origine_id`` = exercice) ; ``None`` si l'exercice n'a
    mouvementé aucun compte de charge ou de produit. Le compte de résultat et la balance l'ignorent
    pour continuer d'afficher l'activité de l'année."""
    lignes = []
    total_debit = total_credit = ZERO
    for compte in _agreger_par_compte(_lignes_de_resultat(exercice)):
        solde = compte["total_debit"] - compte["total_credit"]
        if solde == 0:
            continue
        sens = SensEcriture.CREDIT if solde > 0 else SensEcriture.DEBIT
        lignes.append(LigneSaisie(compte=compte["compte__numero"], sens=sens, montant=abs(solde)))
        if sens == SensEcriture.DEBIT:
            total_debit += abs(solde)
        else:
            total_credit += abs(solde)
    if not lignes:
        return None
    ecart = total_debit - total_credit  # > 0 : produits > charges, bénéfice
    if ecart != 0:
        lignes.append(
            LigneSaisie(
                compte=COMPTE_RESULTAT,
                sens=SensEcriture.CREDIT if ecart > 0 else SensEcriture.DEBIT,
                montant=abs(ecart),
            )
        )
    return passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES,
        date_ecriture=exercice.date_fin,
        libelle=f"Clôture de l'exercice {exercice.annee} — virement du résultat",
        lignes=lignes,
        origine=ORIGINE_CLOTURE,
        origine_id=exercice.pk,
        piece_reference=f"CLOTURE-{exercice.annee}",
        ignorer_cloture=True,
    )


def _comptes_actifs(numeros: set[str]) -> dict[str, Compte]:
    comptes = {c.numero: c for c in Compte.objects.filter(numero__in=numeros, actif=True)}
    manquants = numeros - comptes.keys()
    if manquants:
        raise CompteInconnu(
            f"Compte(s) inconnu(s) ou inactif(s) dans le plan comptable : {', '.join(sorted(manquants))}."
        )
    return comptes


@transaction.atomic
def passer_ecriture(
    *,
    journal: str,
    date_ecriture: date,
    libelle: str,
    lignes: Sequence[LigneSaisie],
    origine: str = "",
    origine_id: int | None = None,
    piece_reference: str = "",
    ignorer_cloture: bool = False,
) -> EcritureComptable:
    """Crée une écriture équilibrée (débit == crédit) et ses lignes.

    Idempotente par ``(origine, origine_id)`` : rejouer le même événement source renvoie
    l'écriture déjà comptabilisée, sans en recréer une seconde. Tout est vérifié avant la
    moindre écriture en base : au moins 2 lignes, montants strictement positifs, comptes
    existants et actifs, total débit égal au total crédit.
    """
    if origine:
        existante = EcritureComptable.objects.filter(origine=origine, origine_id=origine_id).first()
        if existante is not None:
            return existante

    if not ignorer_cloture:  # seule l'écriture de clôture elle-même s'écrit dans un exercice clôturé
        _exiger_exercice_ouvert(date_ecriture)

    if len(lignes) < 2:
        raise EcritureNonEquilibree("Une écriture comptable a au moins 2 lignes.")
    for ligne in lignes:
        if ligne.montant <= 0:
            raise EcritureNonEquilibree("Chaque montant doit être strictement positif.")
        if ligne.sens not in SensEcriture.values:
            # Un sens inconnu serait stocké sans compter dans aucun des deux totaux : l'écriture paraîtrait équilibrée.
            raise EcritureNonEquilibree(f"Sens inconnu « {ligne.sens} » : débit ou crédit attendu.")

    comptes = _comptes_actifs({ligne.compte for ligne in lignes})

    total_debit = sum((l.montant for l in lignes if l.sens == SensEcriture.DEBIT), Decimal("0"))
    total_credit = sum((l.montant for l in lignes if l.sens == SensEcriture.CREDIT), Decimal("0"))
    if total_debit != total_credit:
        raise EcritureNonEquilibree(
            f"Écriture déséquilibrée : débit {total_debit} FCFA, crédit {total_credit} FCFA."
        )

    ecriture = EcritureComptable.objects.create(
        numero=prochain_numero(journal, date_ecriture.year),
        journal=journal,
        date_ecriture=date_ecriture,
        libelle=libelle,
        piece_reference=piece_reference,
        origine=origine,
        origine_id=origine_id,
        statut=StatutEcriture.VALIDEE,
    )
    LigneEcriture.objects.bulk_create(
        LigneEcriture(
            ecriture=ecriture,
            compte=comptes[ligne.compte],
            sens=ligne.sens,
            montant=ligne.montant,
            libelle=ligne.libelle,
            tiers_type=ligne.tiers_type,
            tiers_id=ligne.tiers_id,
        )
        for ligne in lignes
    )
    return ecriture


def comptabiliser_facture_validee(facture) -> EcritureComptable:
    """Écriture d'une facture validée : débite le client (TTC), crédite les ventes (HT) et la
    TVA collectée (si le taux n'est pas nul) — cahier-des-charges.md:340. Idempotent (voir
    :func:`passer_ecriture`) : reprendre une facture déjà comptabilisée ne recrée rien."""
    lignes = [
        LigneSaisie(
            compte=COMPTE_CLIENTS,
            sens=SensEcriture.DEBIT,
            montant=facture.montant_ttc,
            tiers_type="CLIENT",
            tiers_id=facture.client_id,
        ),
        LigneSaisie(
            compte=COMPTE_VENTES_TRANSPORT, sens=SensEcriture.CREDIT, montant=facture.montant_ht
        ),
    ]
    if facture.montant_tva > 0:
        lignes.append(
            LigneSaisie(
                compte=COMPTE_TVA_COLLECTEE, sens=SensEcriture.CREDIT, montant=facture.montant_tva
            )
        )
    return passer_ecriture(
        journal=Journal.VENTES,
        date_ecriture=facture.date_emission,
        libelle=f"Facture {facture.numero} — {facture.client}",
        lignes=lignes,
        origine="FACTURE",
        origine_id=facture.pk,
        piece_reference=facture.numero,
    )


def comptabiliser_un_reglement(reglement) -> EcritureComptable:
    """Écriture d'un règlement encaissé : débite la trésorerie (banque/caisse/mobile money selon
    le mode de paiement), crédite le client (411) — solde la créance. Idempotent (voir
    :func:`passer_ecriture`)."""
    compte_tresorerie = COMPTE_DU_MODE[reglement.mode]
    lignes = [
        LigneSaisie(
            compte=COMPTE_TRESORERIE_VERS_COMPTE[compte_tresorerie],
            sens=SensEcriture.DEBIT,
            montant=reglement.montant,
        ),
        LigneSaisie(
            compte=COMPTE_CLIENTS,
            sens=SensEcriture.CREDIT,
            montant=reglement.montant,
            tiers_type="CLIENT",
            tiers_id=reglement.facture.client_id,
        ),
    ]
    return passer_ecriture(
        journal=COMPTE_TRESORERIE_VERS_JOURNAL[compte_tresorerie],
        date_ecriture=reglement.date_reglement,
        libelle=f"Règlement {reglement.facture.numero} — {reglement.facture.client}",
        lignes=lignes,
        origine="REGLEMENT",
        origine_id=reglement.pk,
        piece_reference=reglement.facture.numero,
    )


def comptabiliser_une_depense_automatique(depense) -> EcritureComptable:
    """Écriture d'une dépense, automatique (plein, achat de pièces, main-d'œuvre d'OR, frais de
    mission, ordre de décaissement) ou manuelle (péages, entretien, frais administratifs, autre —
    avenant-comptabilite-autonomie.md § Lot C) : débite la charge (montant HT) selon la catégorie,
    débite la TVA déductible si ``depense.montant_tva`` est renseignée (§ Lot D), crédite la
    trésorerie au montant TTC selon le mode de paiement. Pour une dépense automatique, le mode est
    provisoire (Caisse par défaut) sauf pour un ordre de décaissement, dont le mode réel est connu
    dès l'exécution — voir :func:`reclasser_mode_depense` pour la correction ultérieure ; une
    dépense saisie à la main connaît déjà son mode réel. Idempotent (voir :func:`passer_ecriture`)."""
    compte_tresorerie = COMPTE_DU_MODE[depense.mode]
    lignes = [
        LigneSaisie(
            compte=CATEGORIE_DEPENSE_VERS_COMPTE[depense.categorie],
            sens=SensEcriture.DEBIT,
            montant=depense.montant_ht,
        ),
    ]
    if depense.montant_tva > 0:
        lignes.append(
            LigneSaisie(compte=COMPTE_TVA_DEDUCTIBLE, sens=SensEcriture.DEBIT, montant=depense.montant_tva)
        )
    lignes.append(
        LigneSaisie(
            compte=COMPTE_TRESORERIE_VERS_COMPTE[compte_tresorerie],
            sens=SensEcriture.CREDIT,
            montant=depense.montant,
        )
    )
    return passer_ecriture(
        journal=COMPTE_TRESORERIE_VERS_JOURNAL[compte_tresorerie],
        date_ecriture=depense.date_depense,
        libelle=depense.libelle,
        lignes=lignes,
        origine="DEPENSE",
        origine_id=depense.pk,
        piece_reference=depense.reference,
    )


def reclasser_mode_depense(depense, ancien_mode: str) -> EcritureComptable | None:
    """Corrige le compte de trésorerie d'une dépense automatique après coup (Finance corrige le
    mode réel via ``billing.services.changer_mode_depense``) : contre-passe l'ancien compte,
    impute le nouveau, plutôt que de modifier l'écriture d'origine (append-only). Ne crée rien si
    l'ancien et le nouveau mode partagent le même compte de trésorerie (ex. virement → chèque,
    tous deux Banque).

    Non idempotente (pas d'``origine``/``origine_id``) : une correction manuelle rejouée deux fois
    créerait deux reclassements — cas rare, accepté pour cette phase (voir « Limite connue »,
    avenant-comptabilite-syscohada.md)."""
    ancien_compte_tresorerie = COMPTE_DU_MODE[ancien_mode]
    nouveau_compte_tresorerie = COMPTE_DU_MODE[depense.mode]
    if ancien_compte_tresorerie == nouveau_compte_tresorerie:
        return None
    lignes = [
        LigneSaisie(
            compte=COMPTE_TRESORERIE_VERS_COMPTE[nouveau_compte_tresorerie],
            sens=SensEcriture.DEBIT,
            montant=depense.montant,
        ),
        LigneSaisie(
            compte=COMPTE_TRESORERIE_VERS_COMPTE[ancien_compte_tresorerie],
            sens=SensEcriture.CREDIT,
            montant=depense.montant,
        ),
    ]
    return passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES,
        date_ecriture=timezone.localdate(),
        libelle=f"Reclassement du mode de paiement — {depense.libelle}",
        lignes=lignes,
    )


def comptabiliser_un_mouvement_manuel(mouvement) -> EcritureComptable:
    """Écriture d'un mouvement manuel de trésorerie (solde d'ouverture, apport, retrait, frais
    bancaires…) : la contrepartie se déduit de sa nature (``finance.models.NatureMouvement``).
    Une entrée débite la trésorerie et crédite la contrepartie ; une sortie fait l'inverse.
    Idempotent (voir :func:`passer_ecriture`)."""
    from apps.finance.models import SensMouvement

    compte_tresorerie = COMPTE_DU_MODE[mouvement.mode]
    compte_contrepartie = NATURE_MOUVEMENT_VERS_COMPTE[mouvement.nature]
    if mouvement.sens == SensMouvement.ENTREE:
        lignes = [
            LigneSaisie(compte=COMPTE_TRESORERIE_VERS_COMPTE[compte_tresorerie], sens=SensEcriture.DEBIT, montant=mouvement.montant),
            LigneSaisie(compte=compte_contrepartie, sens=SensEcriture.CREDIT, montant=mouvement.montant),
        ]
    else:
        lignes = [
            LigneSaisie(compte=compte_contrepartie, sens=SensEcriture.DEBIT, montant=mouvement.montant),
            LigneSaisie(compte=COMPTE_TRESORERIE_VERS_COMPTE[compte_tresorerie], sens=SensEcriture.CREDIT, montant=mouvement.montant),
        ]
    return passer_ecriture(
        journal=COMPTE_TRESORERIE_VERS_JOURNAL[compte_tresorerie],
        date_ecriture=mouvement.date_mouvement,
        libelle=mouvement.libelle,
        lignes=lignes,
        origine="MOUVEMENT",
        origine_id=mouvement.pk,
        piece_reference=mouvement.reference,
    )


# --- contre-passation ---

ORIGINE_CONTRE_PASSATION = "CONTRE_PASSATION"


@transaction.atomic
def contre_passer(
    ecriture: EcritureComptable, *, date_ecriture: date | None = None, motif: str = ""
) -> EcritureComptable:
    """Annule une écriture **validée** par une écriture inverse (mêmes comptes, sens opposés, même
    journal et même pièce), datée du jour par défaut : l'écriture d'origine reste intacte
    (append-only) et le grand livre garde la trace des deux. Une écriture dans un exercice
    déjà clôturé se corrige ainsi dans l'exercice ouvert.

    Idempotente : une écriture n'est contre-passée qu'une fois (``origine`` = ``CONTRE_PASSATION``,
    ``origine_id`` = identifiant de l'écriture d'origine). Refusée pour un brouillon (il
    s'abandonne) et pour une contre-passation (pas de chaîne). Si un compte de l'écriture a été
    désactivé depuis, ``passer_ecriture`` refuse : le réactiver d'abord."""
    if ecriture.statut != StatutEcriture.VALIDEE:
        raise ContrePassationImpossible(
            "Seule une écriture validée se contre-passe : un brouillon s'abandonne."
        )
    if ecriture.origine == ORIGINE_CONTRE_PASSATION:
        raise ContrePassationImpossible("Une contre-passation ne se contre-passe pas.")
    if ecriture.origine == ORIGINE_CLOTURE:
        raise ContrePassationImpossible(
            "L'écriture de clôture ne se contre-passe pas : un exercice clôturé ne se rouvre jamais."
        )
    inverse = {SensEcriture.DEBIT: SensEcriture.CREDIT, SensEcriture.CREDIT: SensEcriture.DEBIT}
    lignes = [
        LigneSaisie(
            compte=ligne.compte.numero,
            sens=inverse[ligne.sens],
            montant=ligne.montant,
            libelle=ligne.libelle,
            tiers_type=ligne.tiers_type,
            tiers_id=ligne.tiers_id,
        )
        for ligne in ecriture.lignes.select_related("compte")
    ]
    libelle = f"Contre-passation {ecriture.numero} — {ecriture.libelle}"
    if motif.strip():
        libelle = f"{libelle} ({motif.strip()})"
    return passer_ecriture(
        journal=ecriture.journal,
        date_ecriture=date_ecriture or timezone.localdate(),
        libelle=libelle[:255],
        lignes=lignes,
        origine=ORIGINE_CONTRE_PASSATION,
        origine_id=ecriture.pk,
        piece_reference=ecriture.piece_reference,
    )


def contre_passation_de(ecriture: EcritureComptable) -> EcritureComptable | None:
    """L'écriture qui contre-passe celle-ci, s'il y en a une."""
    return EcritureComptable.objects.filter(
        origine=ORIGINE_CONTRE_PASSATION, origine_id=ecriture.pk
    ).first()


@transaction.atomic
def contre_passer_ecriture_manuelle(ecriture: EcritureComptable, acteur, *, motif: str) -> EcritureComptable:
    """Corrige une opération diverse **validée** saisie à la main : écriture inverse datée du jour, motif
    obligatoire. Réservé à la DIRECTION (contrôle strict, comme la validation d'une écriture manuelle : défaire
    une écriture engage autant que la poser). Les écritures automatiques (facture, règlement, dépense...) se
    corrigent à la source — annulation du règlement, du mouvement — et la clôture ne se défait pas."""
    _exiger_role(acteur, permissions.VALIDATION_OD, "contre-passer une écriture", strict=True)
    if ecriture.origine:
        raise ContrePassationImpossible(
            "Seule une opération diverse saisie à la main se contre-passe ici : une écriture automatique se "
            "corrige à la source (annulation du règlement, du mouvement…)."
        )
    if not motif.strip():
        raise ContrePassationImpossible("Le motif de la contre-passation est obligatoire.")
    if contre_passation_de(ecriture) is not None:
        raise ContrePassationImpossible(f"L'écriture {ecriture.numero} est déjà contre-passée.")
    return contre_passer(ecriture, motif=motif)


def contre_passer_origine(
    origine: str, origine_id: int, *, date_ecriture: date | None = None, motif: str = ""
) -> EcritureComptable | None:
    """Contre-passe l'écriture générée par un événement source (règlement, mouvement manuel...) quand
    celui-ci est annulé. Ne fait rien (``None``) si cet événement n'a jamais été comptabilisé (saisi
    avant la mise en service de la comptabilité) : il n'y a rien à annuler."""
    ecriture = EcritureComptable.objects.filter(origine=origine, origine_id=origine_id).first()
    if ecriture is None:
        return None
    return contre_passer(ecriture, date_ecriture=date_ecriture, motif=motif)


# --- saisie manuelle (opérations diverses) ---


@transaction.atomic
def creer_ecriture_manuelle(acteur, *, date_ecriture: date, libelle: str) -> EcritureComptable:
    """Ouvre un brouillon d'écriture manuelle (journal Opérations diverses) : pas de numéro tant
    qu'elle n'est pas validée (comme ``Facture``, pour ne pas laisser de trou de numérotation si
    elle est abandonnée), pas de ligne encore."""
    _exiger_role(acteur, permissions.SAISIE_OD, "saisir une écriture")
    if not libelle.strip():
        raise EcritureNonEquilibree("Le libellé est obligatoire.")
    _exiger_exercice_ouvert(date_ecriture)
    return EcritureComptable.objects.create(
        journal=Journal.OPERATIONS_DIVERSES,
        date_ecriture=date_ecriture,
        libelle=libelle.strip(),
        statut=StatutEcriture.BROUILLON,
        cree_par=acteur,
    )


@transaction.atomic
def ajouter_ligne_manuelle(
    ecriture: EcritureComptable, acteur, *, compte: str, sens: str, montant: Decimal, libelle: str = ""
) -> LigneEcriture:
    """Ajoute une ligne à un brouillon d'écriture manuelle."""
    _exiger_role(acteur, permissions.SAISIE_OD, "saisir une écriture")
    _exiger_brouillon(ecriture, "ajouter une ligne")
    montant = Decimal(montant)
    if montant <= 0:
        raise EcritureNonEquilibree("Le montant doit être strictement positif.")
    comptes = _comptes_actifs({compte})
    return LigneEcriture.objects.create(
        ecriture=ecriture, compte=comptes[compte], sens=sens, montant=montant, libelle=libelle.strip()
    )


def supprimer_ligne_manuelle(ligne: LigneEcriture, acteur) -> None:
    """Retire une ligne d'un brouillon d'écriture manuelle."""
    _exiger_role(acteur, permissions.SAISIE_OD, "modifier une écriture")
    _exiger_brouillon(ligne.ecriture, "retirer une ligne")
    ligne.delete()


@transaction.atomic
def abandonner_ecriture_manuelle(ecriture: EcritureComptable, acteur) -> None:
    """Abandonne un brouillon d'écriture manuelle (soft delete) : aucun numéro n'a encore été
    attribué, rien à contre-passer."""
    _exiger_role(acteur, permissions.SAISIE_OD, "abandonner une écriture")
    _exiger_brouillon(ecriture, "abandonner l'écriture")
    ecriture.delete(deleted_by=acteur)


@transaction.atomic
def valider_ecriture_manuelle(ecriture: EcritureComptable, acteur) -> EcritureComptable:
    """Verrouille un brouillon d'écriture manuelle : vérifie l'équilibre (au moins 2 lignes,
    débit == crédit), attribue son numéro, la statut passe à ``VALIDEE`` — définitif, réservé à la
    DIRECTION (contrôle strict, comme ``Facture.valider`` : jamais l'ADMIN ni un superutilisateur
    à sa place)."""
    _exiger_role(acteur, permissions.VALIDATION_OD, "valider une écriture", strict=True)
    _exiger_brouillon(ecriture, "valider l'écriture")
    _exiger_exercice_ouvert(ecriture.date_ecriture)
    lignes = list(ecriture.lignes.all())
    if len(lignes) < 2:
        raise EcritureNonEquilibree("Une écriture comptable a au moins 2 lignes.")
    total_debit = sum((l.montant for l in lignes if l.sens == SensEcriture.DEBIT), Decimal("0"))
    total_credit = sum((l.montant for l in lignes if l.sens == SensEcriture.CREDIT), Decimal("0"))
    if total_debit != total_credit:
        raise EcritureNonEquilibree(
            f"Écriture déséquilibrée : débit {total_debit} FCFA, crédit {total_credit} FCFA."
        )
    ecriture.numero = prochain_numero(ecriture.journal, ecriture.date_ecriture.year)
    ecriture.statut = StatutEcriture.VALIDEE
    ecriture.valide_par = acteur
    ecriture.date_validation = timezone.now()
    ecriture.save(update_fields=["numero", "statut", "valide_par", "date_validation", "updated_at"])
    return ecriture


def grand_livre(
    compte: Compte, *, debut: date | None = None, fin: date | None = None
) -> QuerySet[LigneEcriture]:
    """Lignes d'un compte, triées par date d'écriture. Un brouillon d'opération diverse n'est pas
    encore approuvé par la DIRECTION (services.valider_ecriture_manuelle) : il ne doit jamais
    apparaître dans un rapport officiel, donc seules les écritures VALIDEE sont incluses."""
    lignes = LigneEcriture.objects.filter(
        compte=compte, ecriture__statut=StatutEcriture.VALIDEE
    ).select_related("ecriture", "compte")
    if debut is not None:
        lignes = lignes.filter(ecriture__date_ecriture__gte=debut)
    if fin is not None:
        lignes = lignes.filter(ecriture__date_ecriture__lte=fin)
    return lignes.order_by("ecriture__date_ecriture", "pk")


def grand_livre_avec_solde(
    compte: Compte, *, debut: date | None = None, fin: date | None = None
) -> list[dict]:
    """Lignes du compte avec leur solde cumulé (débit augmente le solde, crédit le diminue —
    convention SYSCOHADA, valable pour un compte d'actif/charge ; un compte de passif/produit se
    lit alors en négatif, ce qui reste correct pour vérifier l'équilibre ligne à ligne)."""
    solde = ZERO
    resultat = []
    for ligne in grand_livre(compte, debut=debut, fin=fin):
        solde += ligne.montant if ligne.sens == SensEcriture.DEBIT else -ligne.montant
        resultat.append({"ligne": ligne, "solde_cumule": solde})
    return resultat


def _agreger_par_compte(lignes: QuerySet[LigneEcriture]) -> list[dict]:
    """Total débit/crédit par compte mouvementé dans ``lignes``."""
    return list(
        lignes.values("compte__id", "compte__numero", "compte__libelle", "compte__nature")
        .annotate(
            total_debit=Coalesce(Sum("montant", filter=Q(sens=SensEcriture.DEBIT)), Value(ZERO)),
            total_credit=Coalesce(Sum("montant", filter=Q(sens=SensEcriture.CREDIT)), Value(ZERO)),
        )
        .order_by("compte__numero")
    )


def balance(
    *, debut: date | None = None, fin: date | None = None, avec_cloture: bool = False
) -> list[dict]:
    """Balance générale : total débit/crédit et solde de chaque compte mouvementé sur la période
    (tous comptes confondus, toutes dates si ``debut``/``fin`` omis). Seules les écritures
    VALIDEE comptent — un brouillon d'opération diverse ne doit jamais fausser la balance
    officielle avant l'approbation de la DIRECTION. Les écritures de clôture sont écartées par
    défaut (balance avant clôture : les charges et produits d'un exercice clôturé restent
    lisibles) ; elles sont équilibrées, le total débit = total crédit tient dans les deux cas."""
    lignes = LigneEcriture.objects.filter(ecriture__statut=StatutEcriture.VALIDEE)
    if not avec_cloture:
        lignes = lignes.exclude(ecriture__origine=ORIGINE_CLOTURE)
    if debut is not None:
        lignes = lignes.filter(ecriture__date_ecriture__gte=debut)
    if fin is not None:
        lignes = lignes.filter(ecriture__date_ecriture__lte=fin)
    resultat = []
    for ligne in _agreger_par_compte(lignes):
        solde = ligne["total_debit"] - ligne["total_credit"]
        resultat.append(
            {
                **ligne,
                "solde_debiteur": solde if solde > 0 else ZERO,
                "solde_crediteur": -solde if solde < 0 else ZERO,
            }
        )
    return resultat


def declaration_tva(*, debut: date, fin: date) -> dict:
    """TVA collectée (443300, sur les ventes) moins TVA déductible (445200, sur les dépenses) sur
    la période = TVA nette à payer (positive) ou crédit de TVA reportable (négative), comme une
    déclaration périodique réelle (avenant-comptabilite-autonomie.md § Lot E). Seules les
    écritures VALIDEE comptent."""
    lignes = LigneEcriture.objects.filter(
        ecriture__statut=StatutEcriture.VALIDEE,
        ecriture__date_ecriture__gte=debut,
        ecriture__date_ecriture__lte=fin,
        compte__numero__in=[COMPTE_TVA_COLLECTEE, COMPTE_TVA_DEDUCTIBLE],
    )
    agrege = {ligne["compte__numero"]: ligne for ligne in _agreger_par_compte(lignes)}
    collectee = agrege.get(COMPTE_TVA_COLLECTEE)
    deductible = agrege.get(COMPTE_TVA_DEDUCTIBLE)
    tva_collectee = (collectee["total_credit"] - collectee["total_debit"]) if collectee else ZERO
    tva_deductible = (deductible["total_debit"] - deductible["total_credit"]) if deductible else ZERO
    return {
        "debut": debut,
        "fin": fin,
        "tva_collectee": tva_collectee,
        "tva_deductible": tva_deductible,
        "tva_nette": tva_collectee - tva_deductible,
    }


def compte_de_resultat(exercice: ExerciceComptable) -> dict:
    """Produits moins charges de l'exercice = résultat net (bénéfice ou perte), calculé à la demande
    sur les lignes de la période. L'écriture de clôture (:func:`ecriture_de_cloture`) est ignorée :
    elle solde ces comptes pour le bilan, mais le compte de résultat d'un exercice clôturé doit
    continuer d'afficher son activité. Seules les écritures VALIDEE comptent, jamais un brouillon
    d'opération diverse non encore approuvé par la DIRECTION."""
    lignes = _lignes_de_resultat(exercice)
    charges, produits = [], []
    total_charges = total_produits = ZERO
    for ligne in _agreger_par_compte(lignes):
        if ligne["compte__nature"] == NatureCompte.CHARGE:
            montant = ligne["total_debit"] - ligne["total_credit"]
            charges.append({**ligne, "montant": montant})
            total_charges += montant
        else:
            montant = ligne["total_credit"] - ligne["total_debit"]
            produits.append({**ligne, "montant": montant})
            total_produits += montant
    return {
        "charges": charges,
        "produits": produits,
        "total_charges": total_charges,
        "total_produits": total_produits,
        "resultat_net": total_produits - total_charges,
    }


def bilan(exercice: ExerciceComptable) -> dict:
    """Actif et passif cumulés depuis l'origine jusqu'à la fin de l'exercice (un bilan est une
    photo à une date, pas une période — contrairement au compte de résultat). Le résultat des
    exercices clôturés est déjà au compte 120000 (:func:`ecriture_de_cloture`). Reste à ajouter au
    passif le résultat **non encore viré** : celui de l'exercice en cours, et celui d'un exercice
    antérieur qui ne serait pas encore clôturé. C'est la somme, depuis l'origine, des charges et
    produits écriture de clôture comprise (elle annule le résultat qu'elle a viré) : le bilan
    s'équilibre donc à tout moment, quel que soit le nombre d'exercices. Seules les écritures
    VALIDEE comptent, jamais un brouillon d'opération diverse non encore approuvé par la DIRECTION."""
    lignes = LigneEcriture.objects.filter(
        ecriture__statut=StatutEcriture.VALIDEE,
        ecriture__date_ecriture__lte=exercice.date_fin,
        compte__nature__in=[NatureCompte.ACTIF, NatureCompte.PASSIF],
    )
    actif, passif = [], []
    total_actif = total_passif = ZERO
    for ligne in _agreger_par_compte(lignes):
        if ligne["compte__nature"] == NatureCompte.ACTIF:
            montant = ligne["total_debit"] - ligne["total_credit"]
            actif.append({**ligne, "montant": montant})
            total_actif += montant
        else:
            montant = ligne["total_credit"] - ligne["total_debit"]
            passif.append({**ligne, "montant": montant})
            total_passif += montant
    resultat_net = sum(
        (
            ligne["total_credit"] - ligne["total_debit"]
            for ligne in _agreger_par_compte(
                LigneEcriture.objects.filter(
                    ecriture__statut=StatutEcriture.VALIDEE,
                    ecriture__date_ecriture__lte=exercice.date_fin,
                    compte__nature__in=[NatureCompte.CHARGE, NatureCompte.PRODUIT],
                )
            )
        ),
        ZERO,
    )
    return {
        "actif": actif,
        "passif": passif,
        "total_actif": total_actif,
        "total_passif": total_passif,
        "resultat_net": resultat_net,
        "total_passif_avec_resultat": total_passif + resultat_net,
    }
```

À lire dans cet ordre :

1. **`passer_ecriture`** : le cœur. Rejoue l'idempotence (`origine`/`origine_id`), vérifie l'exercice
   ouvert, qu'il y a au moins 2 lignes, que chaque montant est strictement positif, que les comptes
   existent et sont actifs, puis que le total débit égale le total crédit — **avant** la moindre écriture
   en base.
2. **`comptabiliser_facture_validee`**, **`comptabiliser_un_reglement`**,
   **`comptabiliser_une_depense_automatique`**, **`reclasser_mode_depense`**,
   **`comptabiliser_un_mouvement_manuel`** : une fonction par événement automatique, qui construit les
   `LigneSaisie` puis appelle `passer_ecriture`. Chacune est idempotente, sauf `reclasser_mode_depense`
   (pas d'`origine`/`origine_id`, limite connue et assumée pour ce lot).
3. **Cycle de la saisie manuelle** : `creer_ecriture_manuelle` (brouillon, pas encore de numéro) →
   `ajouter_ligne_manuelle`/`supprimer_ligne_manuelle` (librement, tant que `BROUILLON`) →
   `valider_ecriture_manuelle` (rôle **strict**, vérifie l'équilibre, attribue le numéro) ou
   `abandonner_ecriture_manuelle` (soft delete du brouillon).
4. **`exercice_pour`** / **`cloturer_exercice`** : un exercice s'ouvre tout seul à la première écriture
   qui le concerne (même principe que `core.services.prochain_numero`) ; la clôture est refusée s'il
   reste des brouillons non résolus dans la période.
5. **Rapports en lecture seule** : `grand_livre_avec_solde` (lignes d'un compte + solde cumulé),
   `balance` (tous les comptes mouvementés), `declaration_tva` (TVA collectée − déductible sur une
   période), `compte_de_resultat` (produits − charges, borné à l'exercice) et `bilan` (actif/passif
   cumulés depuis l'origine). Toujours filtrés sur `statut=VALIDEE` : un brouillon d'opération diverse ne
   doit jamais fausser un rapport officiel avant l'approbation de la DIRECTION.

## Étape 4 — Les abonnements automatiques

#### `apps/accounting/receivers.py`

*58 lignes* — Génération automatique des écritures comptables depuis les événements de facturation et de

```python
"""Génération automatique des écritures comptables depuis les événements de facturation et de
trésorerie.

Souscrit aux signaux **bloquants** de ``billing`` et ``finance`` (``facture_a_comptabiliser``,
``reglement_a_comptabiliser``, ``depense_a_comptabiliser``, ``depense_mode_a_reclasser``,
``mouvement_a_comptabiliser``, envoyés en ``send()`` brut, pas ``emettre()``/``send_robust``) :
si l'écriture ne peut pas s'équilibrer, l'opération d'origine (validation de la facture,
enregistrement du règlement ou du mouvement, dépense automatique, correction du mode) est
annulée plutôt que de laisser un grand livre incomplet — cahier-des-charges.md:340.
"""

from django.dispatch import receiver

from apps.billing.signals import (
    depense_a_comptabiliser,
    depense_mode_a_reclasser,
    facture_a_comptabiliser,
    reglement_a_comptabiliser,
    reglement_annule,
)
from apps.finance.signals import mouvement_a_comptabiliser, mouvement_annule

from . import services


@receiver(facture_a_comptabiliser)
def comptabiliser_une_facture_validee(sender, facture, **kwargs) -> None:
    services.comptabiliser_facture_validee(facture)


@receiver(reglement_a_comptabiliser)
def comptabiliser_un_reglement_recu(sender, reglement, **kwargs) -> None:
    services.comptabiliser_un_reglement(reglement)


@receiver(depense_a_comptabiliser)
def comptabiliser_une_depense(sender, depense, **kwargs) -> None:
    services.comptabiliser_une_depense_automatique(depense)


@receiver(depense_mode_a_reclasser)
def reclasser_le_mode_d_une_depense(sender, depense, ancien_mode, **kwargs) -> None:
    services.reclasser_mode_depense(depense, ancien_mode)


@receiver(mouvement_a_comptabiliser)
def comptabiliser_un_mouvement(sender, mouvement, **kwargs) -> None:
    services.comptabiliser_un_mouvement_manuel(mouvement)


@receiver(reglement_annule)
def contre_passer_un_reglement_annule(sender, reglement, **kwargs) -> None:
    services.contre_passer_origine("REGLEMENT", reglement.pk, motif=reglement.motif_annulation)


@receiver(mouvement_annule)
def contre_passer_un_mouvement_annule(sender, mouvement, **kwargs) -> None:
    services.contre_passer_origine("MOUVEMENT", mouvement.pk, motif=mouvement.motif_annulation)
```

`accounting` ne connaît de `billing` et `finance` que leurs **signaux** — jamais l'inverse. Comparez
avec `notifications` (chapitre 16) : même mécanisme d'abonnement par `@receiver`, mais ici les signaux
sont envoyés en `send()` **brut** (voir plus haut) : un récepteur qui échoue doit remonter l'erreur et
annuler l'opération d'origine, pas seulement la journaliser.

## Étape 5 — Reprise de l'historique

Trois commandes indépendantes, une par type d'événement, pour comptabiliser ce qui a été enregistré
**avant** la mise en service de ce lot :

#### `apps/accounting/management/commands/comptabiliser_historique_factures.py`

*76 lignes* — Reprise, à la demande, des factures déjà validées avant la mise en service de la

```python
"""Reprise, à la demande, des factures déjà validées avant la mise en service de la
comptabilisation automatique (``accounting.receivers``) : sans cette commande, ces factures
n'auraient jamais leur écriture, alors qu'elles ont bien généré une créance client réelle.

Volontairement **pas une migration automatique**, sur le même principe que
``finance.comptabiliser_historique_parc_auto`` : sur une base qui a déjà un solde d'ouverture
saisi en comptabilité, reprendre l'historique complet compterait deux fois les créances
antérieures à ce solde. À exécuter une fois, après avoir vérifié la date du solde d'ouverture
(s'il y en a un) :
- pas de solde d'ouverture (ou aucune facture antérieure à sa date) → lancer sans ``--depuis`` ;
- un solde d'ouverture à une date donnée → lancer avec ``--depuis`` fixé au lendemain de cette date.

Rejouable sans double compte (une écriture par facture, comme le mécanisme normal) : relancer la
commande après un ``--depuis`` mal choisi, corrigé, ne recrée pas ce qui a déjà été comptabilisé.
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounting import services
from apps.accounting.models import EcritureComptable
from apps.billing.models import STATUTS_EMIS, Facture


class Command(BaseCommand):
    help = (
        "Comptabilise les factures déjà validées avant ce lot (voir --dry-run pour prévisualiser, "
        "--depuis pour ignorer ce qui précède un solde d'ouverture)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--depuis", metavar="AAAA-MM-JJ",
            help="Ne reprend que les factures émises à partir de cette date (bornes incluses).",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Affiche ce qui serait comptabilisé sans rien écrire.",
        )

    def handle(self, *args, depuis=None, dry_run=False, **options):
        date_depuis = None
        if depuis:
            try:
                date_depuis = date.fromisoformat(depuis)
            except ValueError:
                raise CommandError(f"Date invalide pour --depuis : {depuis!r} (attendu AAAA-MM-JJ).")

        factures = Facture.objects.filter(statut__in=STATUTS_EMIS)
        if date_depuis is not None:
            factures = factures.filter(date_emission__gte=date_depuis)

        deja = set(
            EcritureComptable.objects.filter(
                origine="FACTURE", origine_id__in=factures.values_list("pk", flat=True)
            ).values_list("origine_id", flat=True)
        )
        comptabilisees = 0
        deja_presentes = 0
        with transaction.atomic():
            for facture in factures:
                services.comptabiliser_facture_validee(facture)
                if facture.pk in deja:
                    deja_presentes += 1
                else:
                    comptabilisees += 1
            if dry_run:
                transaction.set_rollback(True)

        prefixe = "[Simulation, rien n'a été écrit] " if dry_run else ""
        self.stdout.write(
            f"{prefixe}{comptabilisees} facture(s) comptabilisée(s) "
            f"({deja_presentes} déjà présentes, inchangées)."
        )
```

#### `apps/accounting/management/commands/comptabiliser_historique_reglements.py`

*72 lignes* — Reprise, à la demande, des règlements déjà enregistrés avant la mise en service de la

```python
"""Reprise, à la demande, des règlements déjà enregistrés avant la mise en service de la
comptabilisation automatique des encaissements (``accounting.receivers``) — même principe que
``comptabiliser_historique_factures`` et ``finance.comptabiliser_historique_parc_auto`` : sur une
base qui a déjà un solde d'ouverture saisi en comptabilité, reprendre l'historique complet
compterait deux fois les encaissements antérieurs à ce solde.

- pas de solde d'ouverture (ou aucun règlement antérieur à sa date) → lancer sans ``--depuis`` ;
- un solde d'ouverture à une date donnée → lancer avec ``--depuis`` fixé au lendemain de cette date.

Rejouable sans double compte (une écriture par règlement, comme le mécanisme normal).
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounting import services
from apps.accounting.models import EcritureComptable
from apps.billing.models import Reglement


class Command(BaseCommand):
    help = (
        "Comptabilise les règlements déjà enregistrés avant ce lot (voir --dry-run pour "
        "prévisualiser, --depuis pour ignorer ce qui précède un solde d'ouverture)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--depuis", metavar="AAAA-MM-JJ",
            help="Ne reprend que les règlements enregistrés à partir de cette date (bornes incluses).",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Affiche ce qui serait comptabilisé sans rien écrire.",
        )

    def handle(self, *args, depuis=None, dry_run=False, **options):
        date_depuis = None
        if depuis:
            try:
                date_depuis = date.fromisoformat(depuis)
            except ValueError:
                raise CommandError(f"Date invalide pour --depuis : {depuis!r} (attendu AAAA-MM-JJ).")

        reglements = Reglement.objects.select_related("facture", "facture__client")
        if date_depuis is not None:
            reglements = reglements.filter(date_reglement__gte=date_depuis)

        deja = set(
            EcritureComptable.objects.filter(
                origine="REGLEMENT", origine_id__in=reglements.values_list("pk", flat=True)
            ).values_list("origine_id", flat=True)
        )
        comptabilises = 0
        deja_presents = 0
        with transaction.atomic():
            for reglement in reglements:
                services.comptabiliser_un_reglement(reglement)
                if reglement.pk in deja:
                    deja_presents += 1
                else:
                    comptabilises += 1
            if dry_run:
                transaction.set_rollback(True)

        prefixe = "[Simulation, rien n'a été écrit] " if dry_run else ""
        self.stdout.write(
            f"{prefixe}{comptabilises} règlement(s) comptabilisé(s) "
            f"({deja_presents} déjà présents, inchangés)."
        )
```

#### `apps/accounting/management/commands/comptabiliser_historique_depenses.py`

*73 lignes* — Reprise, à la demande, des dépenses déjà enregistrées avant la mise en service de la

```python
"""Reprise, à la demande, des dépenses déjà enregistrées avant la mise en service de la
comptabilisation automatique (``accounting.receivers``) — même principe que
``comptabiliser_historique_factures``/``comptabiliser_historique_reglements``. Reprend toutes les
dépenses, automatiques (catégories CARBURANT, PIECES, MAINTENANCE, FRAIS_MISSION) et de saisie
manuelle (péages, entretien, frais administratifs, autre — comptabilisées depuis
avenant-comptabilite-autonomie.md § Lot C).

- pas de solde d'ouverture (ou aucune dépense antérieure à sa date) → lancer sans ``--depuis`` ;
- un solde d'ouverture à une date donnée → lancer avec ``--depuis`` fixé au lendemain de cette date.

Rejouable sans double compte (une écriture par dépense, comme le mécanisme normal).
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounting import services
from apps.accounting.models import EcritureComptable
from apps.billing.models import Depense


class Command(BaseCommand):
    help = (
        "Comptabilise les dépenses déjà enregistrées avant ce lot (voir --dry-run pour "
        "prévisualiser, --depuis pour ignorer ce qui précède un solde d'ouverture)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--depuis", metavar="AAAA-MM-JJ",
            help="Ne reprend que les dépenses enregistrées à partir de cette date (bornes incluses).",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Affiche ce qui serait comptabilisé sans rien écrire.",
        )

    def handle(self, *args, depuis=None, dry_run=False, **options):
        date_depuis = None
        if depuis:
            try:
                date_depuis = date.fromisoformat(depuis)
            except ValueError:
                raise CommandError(f"Date invalide pour --depuis : {depuis!r} (attendu AAAA-MM-JJ).")

        depenses = Depense.objects.all()
        if date_depuis is not None:
            depenses = depenses.filter(date_depense__gte=date_depuis)

        deja = set(
            EcritureComptable.objects.filter(
                origine="DEPENSE", origine_id__in=depenses.values_list("pk", flat=True)
            ).values_list("origine_id", flat=True)
        )
        comptabilisees = 0
        deja_presentes = 0
        with transaction.atomic():
            for depense in depenses:
                services.comptabiliser_une_depense_automatique(depense)
                if depense.pk in deja:
                    deja_presentes += 1
                else:
                    comptabilisees += 1
            if dry_run:
                transaction.set_rollback(True)

        prefixe = "[Simulation, rien n'a été écrit] " if dry_run else ""
        self.stdout.write(
            f"{prefixe}{comptabilisees} dépense(s) comptabilisée(s) "
            f"({deja_presentes} déjà présentes, inchangées)."
        )
```

Chacune accepte `--depuis AAAA-MM-JJ` (ignorer ce qui précède un solde d'ouverture déjà saisi, pour ne
pas compter deux fois les créances antérieures) et `--dry-run` (prévisualiser sans rien écrire). Toutes
trois sont **rejouables sans double compte** : relancer après un `--depuis` mal choisi ne recrée pas ce
qui a déjà été comptabilisé.

## Étape 6 — Administration, démarrage et tests

#### `apps/accounting/admin.py`

*65 lignes*

```python
from django.contrib import admin

from .models import Compte, EcritureComptable, ExerciceComptable, LigneEcriture

# Le grand livre est en lecture seule dans l'admin : une écriture ne se crée, ne se valide et ne se corrige que
# par ``accounting.services`` (équilibre, numéro, rôle DIRECTION, exercice ouvert, contre-passation). Passer par
# l'admin contournerait ces contrôles (audit ACC-01 : un brouillon pouvait être validé sans équilibre, ni
# numéro, ni DIRECTION ; une ligne ajoutée à une écriture validée).


class LectureSeuleAdmin(admin.ModelAdmin):
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Compte)
class CompteAdmin(admin.ModelAdmin):
    list_display = ("numero", "libelle", "nature", "actif")
    list_filter = ("nature", "actif")
    search_fields = ("numero", "libelle")

    def get_readonly_fields(self, request, obj=None):
        # Comme ``services.modifier_compte`` : le numéro et la nature ne changent plus une fois le compte créé,
        # pour ne jamais reclasser silencieusement des écritures déjà posées.
        return ("numero", "nature") if obj is not None else ()


class LigneEcritureInline(admin.TabularInline):
    model = LigneEcriture
    extra = 0
    fields = ("compte", "sens", "montant", "libelle", "tiers_type", "tiers_id")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EcritureComptable)
class EcritureComptableAdmin(LectureSeuleAdmin):
    list_display = ("numero", "journal", "date_ecriture", "libelle", "statut", "piece_reference")
    list_filter = ("journal", "statut")
    search_fields = ("numero", "libelle", "piece_reference")
    inlines = [LigneEcritureInline]

    def get_queryset(self, request):
        return EcritureComptable.objects.select_related("cree_par", "valide_par")


@admin.register(ExerciceComptable)
class ExerciceComptableAdmin(LectureSeuleAdmin):
    # La clôture passe par ``services.cloturer_exercice`` (DIRECTION, après la fin de l'année, sans brouillon,
    # avec l'écriture de clôture) ; un exercice clôturé ne se rouvre jamais.
    list_display = ("annee", "date_debut", "date_fin", "statut", "cloture_par")
    list_filter = ("statut",)
```

#### `apps/accounting/apps.py`

*49 lignes*

```python
from django.apps import AppConfig


class AccountingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounting"
    label = "accounting"
    verbose_name = "Comptabilité"

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer
        from apps.audit.registry import audit_model

        from . import permissions, receivers  # noqa: F401  (connecte les récepteurs)
        from .models import Compte, EcritureComptable, ExerciceComptable, LigneEcriture

        audit_model(Compte, module="COMPTABILITE")
        audit_model(
            EcritureComptable,
            module="COMPTABILITE",
            validation=("statut", ("VALIDEE",)),
            auto_validation=("cree_par", ("valide_par",)),
        )
        audit_model(LigneEcriture, module="COMPTABILITE")
        audit_model(ExerciceComptable, module="COMPTABILITE")
        enregistrer(
            EntreeMenu(
                "Plan comptable", "accounting:plan_comptable", "fa-list-check",
                permissions.CONSULTATION, ordre=63,
            )
        )
        enregistrer(
            EntreeMenu(
                "Opérations diverses", "accounting:ecritures_manuelles", "fa-scale-balanced",
                permissions.CONSULTATION, ordre=64,
            )
        )
        enregistrer(
            EntreeMenu(
                "Exercices comptables", "accounting:exercices", "fa-calendar-days",
                permissions.CONSULTATION, ordre=65,
            )
        )
        enregistrer(
            EntreeMenu(
                "Rapports comptables", "accounting:balance", "fa-chart-column",
                permissions.CONSULTATION, ordre=66,
            )
        )
```

Dans `ready()`, on branche l'audit (module `COMPTABILITE`) sur les quatre modèles, et on déclare quatre
entrées de menu : « Plan comptable », « Opérations diverses », « Exercices comptables » et « Rapports
comptables » — ces écrans n'existent pas encore, l'entrée reste simplement inactive jusqu'au chapitre 27.

La migration de données du plan comptable de départ — la seule migration de tout ce tutoriel à être
montrée : les autres, purement schéma, sont reproduites par `makemigrations` (voir l'Étape 7) :

#### `apps/accounting/migrations/0002_plan_comptable_seed.py`

*52 lignes* — Plan comptable de départ (SYSCOHADA révisé) — liste de travail, à valider par un

```python
"""Plan comptable de départ (SYSCOHADA révisé) — liste de travail, à valider par un
expert-comptable avant mise en production (voir apps/accounting/README.md et
avenant-comptabilite-syscohada.md). Seuls 411000, 706100, 443300 et les 3 comptes de trésorerie
sont mobilisés par le code de la Phase 1 ; le reste est seedé pour ne pas fragmenter la migration
de données quand les lots suivants (dépenses automatiques, saisie manuelle) arriveront.

``RunPython`` idempotent (``update_or_create``) : rejouable sans effet si déjà appliquée.
"""

from django.db import migrations

PLAN_COMPTABLE = [
    ("101000", "Capital social", "PASSIF"),
    ("108000", "Compte de l'exploitant", "PASSIF"),
    ("120000", "Résultat de l'exercice", "PASSIF"),
    ("401000", "Fournisseurs", "PASSIF"),
    ("411000", "Clients", "ACTIF"),
    ("443300", "État, TVA facturée sur ventes", "PASSIF"),
    ("445200", "État, TVA déductible", "ACTIF"),
    ("521000", "Banque", "ACTIF"),
    ("521900", "Mobile Money", "ACTIF"),
    ("571000", "Caisse", "ACTIF"),
    ("605100", "Carburants et lubrifiants", "CHARGE"),
    ("605800", "Pièces détachées et fournitures véhicules", "CHARGE"),
    ("624100", "Entretien, réparations (prestataires extérieurs)", "CHARGE"),
    ("628100", "Frais de mission et déplacements", "CHARGE"),
    ("631000", "Frais bancaires", "CHARGE"),
    ("658000", "Charges diverses de gestion courante", "CHARGE"),
    ("706100", "Prestations de transport", "PRODUIT"),
]


def seeder(apps, schema_editor):
    Compte = apps.get_model("accounting", "Compte")
    for numero, libelle, nature in PLAN_COMPTABLE:
        Compte.objects.update_or_create(numero=numero, defaults={"libelle": libelle, "nature": nature})


def retirer(apps, schema_editor):
    Compte = apps.get_model("accounting", "Compte")
    Compte.objects.filter(numero__in=[numero for numero, _, _ in PLAN_COMPTABLE]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seeder, retirer),
    ]
```

Seuls `411000`, `706100`, `443300` et les 3 comptes de trésorerie sont mobilisés par ce chapitre ; le
reste est seedé maintenant pour ne pas fragmenter cette migration quand les dépenses automatiques et la
saisie manuelle (déjà couvertes par `services.py`) s'en serviront.

#### `apps/accounting/README.md`

*117 lignes* — accounting

```markdown
# accounting

Rôle : comptabilité en partie double (SYSCOHADA révisé) — cahier-des-charges.md:340. Dépend de
`billing` et `finance` (architecture.md). Nouveau chantier (avenant-comptabilite-syscohada.md),
livré par lot indépendant comme R1-R8 (`avenant-separation-des-taches.md`).

**Phase 1** : fondations — plan comptable, moteur d'écritures toujours équilibrées, écriture
générée automatiquement à la validation d'une facture (« une facture émise génère la créance
client et l'écriture comptable équilibrée », cahier-des-charges.md:340).

**Phase 2** : encaissements — écriture générée automatiquement à l'enregistrement d'un règlement
(débit trésorerie selon le mode de paiement, crédit client).

**Phase 3** : dépenses automatiques du parc auto/missions — écriture générée automatiquement pour
un plein, un achat de pièces, une main-d'œuvre d'OR, un frais de mission confirmé ou un ordre de
décaissement exécuté ; reclassement de trésorerie quand la Finance corrige après coup le mode
d'une dépense provisoire.

**Phase 4** : saisie manuelle — écriture générée automatiquement pour un mouvement manuel de
trésorerie (`finance.MouvementManuel`, champ `nature` pour déduire le compte de contrepartie) ;
écran de saisie manuelle d'opérations diverses (brouillon → ajout/retrait de lignes → validation
par la DIRECTION, cycle calqué sur `Facture`).

**Phase 5** : exercice comptable et clôture — un exercice (année civile) s'ouvre tout
seul à la première écriture qui le concerne ; la DIRECTION peut le clôturer (contrôle strict),
ce qui verrouille définitivement toute nouvelle écriture datée dans sa période. Refusé s'il reste
des brouillons non résolus dans la période, et tant que l'année n'est pas terminée (clôturée avant, elle
refuserait toutes les opérations datées d'ici là : règlements, dépenses, pleins...). La clôture pose
l'**écriture de clôture** (`services.ecriture_de_cloture`, journal OD, datée du 31/12) : chaque compte de
charge ou de produit est soldé et le résultat est viré au compte 120000 (crédit si bénéfice, débit si perte),
pour que le bilan de l'exercice suivant le retrouve. Reprise des exercices clôturés avant ce lot :
`manage.py ecrire_clotures_historiques [--dry-run]`.

**Phase 6 (ce lot, dernière de la feuille de route)** : rapports en lecture seule — grand livre
d'un compte avec solde cumulé, balance générale de tous les comptes mouvementés, bilan (cumulé
depuis l'origine) et compte de résultat (strictement borné à l'exercice choisi). Aucun nouveau
modèle ni signal : uniquement des agrégations sur les écritures déjà posées par les Phases 1-5.

Entités : `Compte` (plan comptable, table de référence), `EcritureComptable` (en-tête, numérotée
par journal via `core.services.prochain_numero` — vide tant qu'elle est en `BROUILLON`),
`LigneEcriture` (ligne débit/crédit, append-only une fois l'écriture validée, modifiable tant
qu'elle est en brouillon), `ExerciceComptable` (année, période, statut `OUVERT`/`CLOTURE`).
Une écriture validée ne se modifie ni ne se supprime : seule une contre-passation la corrige
(`services.contre_passer` : écriture inverse, même journal et même pièce, datée du jour — donc dans
l'exercice ouvert même si l'original est dans un exercice clos ; idempotente ; refusée pour un brouillon
et pour une contre-passation). Annuler un règlement (`billing.annuler_reglement`) ou un mouvement manuel
(`finance.annuler_mouvement`) contre-passe automatiquement son écriture (signaux `reglement_annule` et
`mouvement_annule`, `send()` brut : si la contre-passation est impossible — exercice du jour clos, compte
désactivé — l'annulation est refusée avec son message) et défait le pointage bancaire éventuel. Reprise des
annulations antérieures : `python manage.py contre_passer_historique_annulations [--dry-run]`. Un exercice
clôturé ne se rouvre jamais.

Service central : `services.passer_ecriture(...)` — garantit lui-même l'équilibre (débit ==
crédit), l'idempotence par `(origine, origine_id)` et que l'exercice de la date n'est pas
clôturé, jamais l'appelant ; toujours `VALIDEE` directement (usage automatique). Chaque événement
automatique a sa fonction dédiée qui construit les lignes puis appelle `passer_ecriture` :
`comptabiliser_facture_validee`, `comptabiliser_un_reglement`,
`comptabiliser_une_depense_automatique` (dépenses automatiques *et* manuelles, les 8 catégories
de `billing.CategorieDepense` — `avenant-comptabilite-autonomie.md` § Lot C), `reclasser_mode_depense`
(sans `origine`/`origine_id`, voir « Limite connue » P3), `comptabiliser_un_mouvement_manuel`.

La saisie manuelle passe par un cycle brouillon/validation distinct :
`creer_ecriture_manuelle` → `ajouter_ligne_manuelle`/`supprimer_ligne_manuelle` (librement, tant
que `BROUILLON`) → `valider_ecriture_manuelle` (DIRECTION, contrôle **strict**, vérifie
l'équilibre et attribue le numéro) ou `abandonner_ecriture_manuelle` (soft delete du brouillon).

`services.exercice_pour(date)` renvoie (et crée si besoin, `OUVERT`) l'exercice d'une date —
même principe que `core.services.prochain_numero`. `services.cloturer_exercice(exercice, acteur)`
verrouille la période (DIRECTION, strict), refusé s'il reste des brouillons dans la période.

Rapports (Phase 6, lecture seule) : `services.grand_livre_avec_solde(compte, debut=, fin=)`
(lignes d'un compte + solde cumulé), `services.balance(debut=, fin=)` (tous les comptes
mouvementés, total débit/crédit et solde par compte), `services.compte_de_resultat(exercice)`
(produits/charges strictement dans l'exercice, écriture de clôture ignorée), `services.bilan(exercice)`
(actif/passif cumulés depuis l'origine jusqu'à la fin de l'exercice ; le résultat des exercices clôturés est
au compte 120000, le résultat pas encore viré est ajouté au passif — le bilan s'équilibre à tout moment).
`balance()` écarte les écritures de clôture par défaut (`avec_cloture=True` pour les inclure).

Déclenchement (automatique) : signaux `billing.signals.facture_a_comptabiliser`,
`reglement_a_comptabiliser`, `depense_a_comptabiliser`, `depense_mode_a_reclasser`, et
`finance.signals.mouvement_a_comptabiliser` — tous émis en `send()` **brut** (pas
`emettre()`/`send_robust`) : une écriture qui échoue à s'équilibrer (ou tombe dans un exercice
clôturé) annule l'opération d'origine plutôt que de laisser un grand livre incomplet. Les erreurs
comptables héritent de `core.ErreurMetier` : un écran qui ne les attrape pas affiche leur message (retour à
la page d'origine, `core.middleware.ErreurMetierMiddleware`) et l'API répond 400 (403 pour un droit refusé),
jamais une erreur 500.

Reprise de l'historique (événements déjà enregistrés avant la mise en service de chaque lot) :
`python manage.py comptabiliser_historique_factures`, `comptabiliser_historique_reglements`,
`comptabiliser_historique_depenses` (chacune avec `[--depuis AAAA-MM-JJ] [--dry-run]`).

Accès : `permissions.CONSULTATION` (ADMIN, DIRECTION, FINANCES, RH, lecture) ; `SAISIE_OD` (mêmes
rôles, opérations diverses) ; `VALIDATION_OD` (DIRECTION seule, strict) ; `CLOTURE_EXERCICE`
(DIRECTION seule, strict) ; `GESTION_PLAN_COMPTABLE` (mêmes rôles que `SAISIE_OD` — créer/modifier
un compte, `avenant-comptabilite-autonomie.md` § Lot F). Écrans :
`/comptabilite/plan-comptable/` (liste, création, modification — numéro et nature fixés à la
création, un compte ne se supprime jamais, seulement désactivé),
`/comptabilite/operations-diverses/` (liste, création, fiche avec ajout/retrait de ligne,
validation, abandon), `/comptabilite/exercices/` (liste, clôture),
`/comptabilite/grand-livre/` (formulaire compte + période), `/comptabilite/balance/` (formulaire
période), `/comptabilite/bilan/` et `/comptabilite/compte-de-resultat/` (sélecteur d'exercice,
le plus récent par défaut), `/comptabilite/declaration-tva/` (TVA collectée 443300 − TVA
déductible 445200 sur une période, le mois en cours par défaut —
`services.declaration_tva`, `avenant-comptabilite-autonomie.md` § Lot E) — ces 5 derniers
accessibles depuis le menu « Rapports comptables », chacun avec une version imprimable
(`.../imprimer/`, même mécanisme que `finance.tresorerie` — voir
`avenant-comptabilite-autonomie.md` § Lot B).

**Plan comptable de départ** (`migrations/0002_plan_comptable_seed.py`) : liste de travail, à
valider par un expert-comptable avant mise en production — aucun plan comptable existant côté
cabinet externe n'a été fourni à ce stade.

**Admin Django en lecture seule** pour les écritures et les exercices (aucune création, validation ou réouverture hors des
services : équilibre, numéro, DIRECTION, exercice ouvert) ; numéro et nature d'un compte ne se modifient plus. `passer_ecriture`
refuse un sens autre que débit/crédit. **Contre-passation d'une opération diverse validée** depuis son écran
(`contre_passer_ecriture_manuelle`, DIRECTION en contrôle strict, motif obligatoire, une seule fois). **Export Excel** du grand
livre, de la balance, du bilan, du compte de résultat et de la déclaration TVA (bouton « Excel » à côté de « Imprimer »).
```

#### `apps/accounting/management/commands/contre_passer_historique_annulations.py`

*64 lignes* — Reprise, à la demande, des règlements et mouvements manuels **annulés avant** la mise en service de la

```python
"""Reprise, à la demande, des règlements et mouvements manuels **annulés avant** la mise en service de la
contre-passation automatique (``accounting.receivers``) : leur écriture est restée au grand livre alors
que la trésorerie ne les compte plus. Chaque annulation reçoit son écriture inverse, datée du jour de
l'annulation (jamais d'un exercice clôturé : ceux-là sont signalés, à traiter à la main).

Rejouable sans double contre-passation (une par écriture d'origine, comme le mécanisme normal).
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounting import services
from apps.accounting.exceptions import AccountingError
from apps.accounting.models import EcritureComptable
from apps.billing.models import Reglement
from apps.finance.models import MouvementManuel


class Command(BaseCommand):
    help = (
        "Contre-passe les règlements et mouvements manuels déjà annulés avant ce lot "
        "(voir --dry-run pour prévisualiser)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Affiche ce qui serait contre-passé sans rien écrire."
        )

    def handle(self, *args, dry_run=False, **options):
        faites = deja = sans_ecriture = impossibles = 0
        sources = (("REGLEMENT", Reglement), ("MOUVEMENT", MouvementManuel))
        with transaction.atomic():
            for origine, modele in sources:
                for annule in modele.all_objects.filter(is_deleted=True):
                    if not EcritureComptable.objects.filter(origine=origine, origine_id=annule.pk).exists():
                        sans_ecriture += 1
                        continue
                    if EcritureComptable.objects.filter(
                        origine=services.ORIGINE_CONTRE_PASSATION,
                        origine_id=EcritureComptable.objects.get(origine=origine, origine_id=annule.pk).pk,
                    ).exists():
                        deja += 1
                        continue
                    jour = timezone.localdate(annule.deleted_at) if annule.deleted_at else None
                    try:
                        with transaction.atomic():
                            services.contre_passer_origine(
                                origine, annule.pk, date_ecriture=jour, motif=annule.motif_annulation
                            )
                    except AccountingError as erreur:
                        impossibles += 1
                        self.stderr.write(f"{origine} #{annule.pk} non contre-passé : {erreur}")
                    else:
                        faites += 1
            if dry_run:
                transaction.set_rollback(True)

        prefixe = "[Simulation, rien n'a été écrit] " if dry_run else ""
        self.stdout.write(
            f"{prefixe}{faites} annulation(s) contre-passée(s) ({deja} déjà faites, {sans_ecriture} jamais "
            f"comptabilisées, {impossibles} impossible(s))."
        )
```

#### `apps/accounting/management/commands/ecrire_clotures_historiques.py`

*52 lignes* — Reprise, à la demande, des exercices **déjà clôturés avant** l'écriture de clôture : leur résultat n'a jamais

```python
"""Reprise, à la demande, des exercices **déjà clôturés avant** l'écriture de clôture : leur résultat n'a jamais
été viré au compte 120000, et le bilan de l'exercice suivant ne le retrouve pas. Chaque exercice clôturé sans
écriture de clôture reçoit la sienne, datée de son dernier jour (le seul cas où l'on écrit dans un exercice
clôturé, pour la clôture elle-même).

Rejouable sans doublon (une écriture de clôture par exercice).
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounting import services
from apps.accounting.exceptions import AccountingError
from apps.accounting.models import EcritureComptable, ExerciceComptable, StatutExercice


class Command(BaseCommand):
    help = "Pose l'écriture de clôture des exercices déjà clôturés (voir --dry-run pour prévisualiser)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Affiche ce qui serait écrit sans rien écrire."
        )

    def handle(self, *args, dry_run=False, **options):
        faites = deja = sans_resultat = impossibles = 0
        with transaction.atomic():
            for exercice in ExerciceComptable.objects.filter(statut=StatutExercice.CLOTURE).order_by("annee"):
                if EcritureComptable.objects.filter(
                    origine=services.ORIGINE_CLOTURE, origine_id=exercice.pk
                ).exists():
                    deja += 1
                    continue
                try:
                    with transaction.atomic():
                        ecriture = services.ecriture_de_cloture(exercice)
                except AccountingError as erreur:
                    impossibles += 1
                    self.stderr.write(f"Exercice {exercice.annee} sans écriture de clôture : {erreur}")
                    continue
                if ecriture is None:
                    sans_resultat += 1
                else:
                    faites += 1
            if dry_run:
                transaction.set_rollback(True)

        prefixe = "[Simulation, rien n'a été écrit] " if dry_run else ""
        self.stdout.write(
            f"{prefixe}{faites} écriture(s) de clôture posée(s) ({deja} déjà faites, {sans_resultat} exercice(s) "
            f"sans charge ni produit, {impossibles} impossible(s))."
        )
```

#### `apps/accounting/tests/factories.py`

*14 lignes*

```python
import factory

from apps.accounting.models import Compte, NatureCompte


class CompteFactory(factory.django.DjangoModelFactory):
    """Compte de test, indépendant du plan comptable seedé (migration 0002)."""

    class Meta:
        model = Compte

    numero = factory.Sequence(lambda n: f"9{n:05d}")
    libelle = factory.Sequence(lambda n: f"Compte de test {n}")
    nature = NatureCompte.CHARGE
```

#### `apps/accounting/tests/test_cloture_resultat.py`

*224 lignes* — Écriture de clôture : le résultat d'un exercice est viré au compte 120000, le bilan du 2e exercice reste

```python
"""Écriture de clôture : le résultat d'un exercice est viré au compte 120000, le bilan du 2e exercice reste
équilibré (audit : bilan déséquilibré dès le 2e exercice)."""

from datetime import date
from decimal import Decimal

import pytest

from apps.accounting import services
from apps.accounting.exceptions import CompteInconnu, ContrePassationImpossible
from apps.accounting.models import Compte, EcritureComptable, Journal, SensEcriture, StatutExercice
from apps.accounting.services import LigneSaisie
from apps.billing.tests.helpers import direction

pytestmark = pytest.mark.django_db

JOUR_2025 = date(2025, 6, 1)
JOUR_2026 = date(2026, 6, 1)


def _vente(jour, montant):
    services.passer_ecriture(
        journal=Journal.VENTES, date_ecriture=jour, libelle="Vente",
        lignes=[
            LigneSaisie(compte="411000", sens=SensEcriture.DEBIT, montant=Decimal(montant)),
            LigneSaisie(compte="706100", sens=SensEcriture.CREDIT, montant=Decimal(montant)),
        ],
    )


def _charge(jour, montant):
    services.passer_ecriture(
        journal=Journal.CAISSE, date_ecriture=jour, libelle="Carburant",
        lignes=[
            LigneSaisie(compte="605100", sens=SensEcriture.DEBIT, montant=Decimal(montant)),
            LigneSaisie(compte="571000", sens=SensEcriture.CREDIT, montant=Decimal(montant)),
        ],
    )


def _cloturer(jour):
    exercice = services.exercice_pour(jour)
    services.cloturer_exercice(exercice, direction())
    exercice.refresh_from_db()
    return exercice


def _ecriture_de_cloture(exercice):
    return EcritureComptable.objects.get(origine=services.ORIGINE_CLOTURE, origine_id=exercice.pk)


def _lignes(ecriture):
    return {(l.compte.numero, l.sens): l.montant for l in ecriture.lignes.select_related("compte")}


def test_la_cloture_vire_un_benefice_au_credit_du_120000():
    _vente(JOUR_2025, "1000")
    _charge(JOUR_2025, "300")

    exercice = _cloturer(JOUR_2025)

    ecriture = _ecriture_de_cloture(exercice)
    assert exercice.statut == StatutExercice.CLOTURE
    assert ecriture.date_ecriture == date(2025, 12, 31)
    assert ecriture.journal == Journal.OPERATIONS_DIVERSES
    assert _lignes(ecriture) == {
        ("706100", SensEcriture.DEBIT): Decimal("1000"),
        ("605100", SensEcriture.CREDIT): Decimal("300"),
        ("120000", SensEcriture.CREDIT): Decimal("700"),
    }


def test_la_cloture_vire_une_perte_au_debit_du_120000():
    _vente(JOUR_2025, "200")
    _charge(JOUR_2025, "500")

    ecriture = _ecriture_de_cloture(_cloturer(JOUR_2025))

    assert _lignes(ecriture)[("120000", SensEcriture.DEBIT)] == Decimal("300")


def test_un_exercice_sans_charge_ni_produit_ne_pose_aucune_ecriture_de_cloture():
    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=JOUR_2025, libelle="Apport",
        lignes=[
            LigneSaisie(compte="571000", sens=SensEcriture.DEBIT, montant=Decimal("900")),
            LigneSaisie(compte="101000", sens=SensEcriture.CREDIT, montant=Decimal("900")),
        ],
    )

    _cloturer(JOUR_2025)

    assert not EcritureComptable.objects.filter(origine=services.ORIGINE_CLOTURE).exists()


def test_le_bilan_du_2e_exercice_reste_equilibre():
    """Le défaut d'origine : le résultat 2025 disparaissait du passif du bilan 2026."""
    _vente(JOUR_2025, "1000")
    _charge(JOUR_2025, "300")
    _cloturer(JOUR_2025)
    _vente(JOUR_2026, "400")
    _charge(JOUR_2026, "100")

    rapport = services.bilan(services.exercice_pour(JOUR_2026))

    passif = {l["compte__numero"]: l["montant"] for l in rapport["passif"]}
    assert passif["120000"] == Decimal("700")  # résultat 2025 reporté
    assert rapport["resultat_net"] == Decimal("300")  # résultat 2026, pas encore viré
    assert rapport["total_actif"] == rapport["total_passif_avec_resultat"] == Decimal("1000")


def test_le_bilan_de_l_exercice_cloture_ne_compte_pas_deux_fois_son_resultat():
    _vente(JOUR_2025, "1000")
    _charge(JOUR_2025, "300")
    exercice = _cloturer(JOUR_2025)

    rapport = services.bilan(exercice)

    assert rapport["resultat_net"] == Decimal("0")
    assert rapport["total_actif"] == rapport["total_passif_avec_resultat"] == Decimal("700")


def test_le_bilan_s_equilibre_aussi_sans_cloture_des_exercices_precedents():
    _vente(JOUR_2025, "1000")
    _vente(JOUR_2026, "400")  # 2025 jamais clôturé

    rapport = services.bilan(services.exercice_pour(JOUR_2026))

    assert rapport["total_actif"] == rapport["total_passif_avec_resultat"] == Decimal("1400")


def test_le_compte_de_resultat_d_un_exercice_cloture_garde_son_activite():
    _vente(JOUR_2025, "1000")
    _charge(JOUR_2025, "300")
    exercice = _cloturer(JOUR_2025)

    rapport = services.compte_de_resultat(exercice)

    assert rapport["total_produits"] == Decimal("1000")
    assert rapport["total_charges"] == Decimal("300")
    assert rapport["resultat_net"] == Decimal("700")


def test_la_balance_ignore_la_cloture_par_defaut_et_reste_equilibree():
    _vente(JOUR_2025, "1000")
    _cloturer(JOUR_2025)

    sans = {l["compte__numero"]: l for l in services.balance()}
    avec = {l["compte__numero"]: l for l in services.balance(avec_cloture=True)}

    assert sans["706100"]["total_credit"] == Decimal("1000") and sans["706100"]["total_debit"] == 0
    assert "120000" not in sans
    assert avec["706100"]["solde_debiteur"] == avec["706100"]["solde_crediteur"] == 0
    assert avec["120000"]["solde_crediteur"] == Decimal("1000")
    for balance in (sans.values(), avec.values()):
        assert sum(l["total_debit"] for l in balance) == sum(l["total_credit"] for l in balance)


def test_l_ecriture_de_cloture_ne_se_contre_passe_pas():
    _vente(JOUR_2025, "1000")
    ecriture = _ecriture_de_cloture(_cloturer(JOUR_2025))

    with pytest.raises(ContrePassationImpossible, match="ne se rouvre jamais"):
        services.contre_passer(ecriture)


def test_ecriture_de_cloture_est_idempotente():
    _vente(JOUR_2025, "1000")
    exercice = _cloturer(JOUR_2025)

    de_nouveau = services.ecriture_de_cloture(exercice)

    assert de_nouveau == _ecriture_de_cloture(exercice)
    assert EcritureComptable.objects.filter(origine=services.ORIGINE_CLOTURE).count() == 1


def test_une_cloture_impossible_faute_de_compte_120000_ne_clot_rien():
    _vente(JOUR_2025, "1000")
    Compte.objects.filter(numero="120000").update(actif=False)
    exercice = services.exercice_pour(JOUR_2025)

    with pytest.raises(CompteInconnu, match="120000"):
        services.cloturer_exercice(exercice, direction())

    exercice.refresh_from_db()
    assert exercice.statut == StatutExercice.OUVERT
    assert not EcritureComptable.objects.filter(origine=services.ORIGINE_CLOTURE).exists()


# --- reprise des exercices clôturés avant ce lot ---


def _cloture_sans_ecriture(jour):
    """Un exercice clôturé à l'ancienne : statut posé sans écriture de clôture."""
    exercice = services.exercice_pour(jour)
    exercice.statut = StatutExercice.CLOTURE
    exercice.save(update_fields=["statut", "updated_at"])
    return exercice


def test_la_commande_de_reprise_pose_la_cloture_manquante_et_equilibre_le_bilan():
    from django.core.management import call_command

    _vente(JOUR_2025, "1000")
    _cloture_sans_ecriture(JOUR_2025)

    call_command("ecrire_clotures_historiques")
    call_command("ecrire_clotures_historiques")  # rejouable

    assert EcritureComptable.objects.filter(origine=services.ORIGINE_CLOTURE).count() == 1
    _vente(JOUR_2026, "400")
    rapport = services.bilan(services.exercice_pour(JOUR_2026))
    assert rapport["total_actif"] == rapport["total_passif_avec_resultat"] == Decimal("1400")


def test_la_commande_de_reprise_en_simulation_n_ecrit_rien():
    from django.core.management import call_command

    _vente(JOUR_2025, "1000")
    _cloture_sans_ecriture(JOUR_2025)

    call_command("ecrire_clotures_historiques", "--dry-run")

    assert not EcritureComptable.objects.filter(origine=services.ORIGINE_CLOTURE).exists()
```

#### `apps/accounting/tests/test_contre_passation.py`

*318 lignes* — Contre-passation : une écriture validée ne se corrige que par une écriture inverse (audit : ACC-07).

```python
"""Contre-passation : une écriture validée ne se corrige que par une écriture inverse (audit : ACC-07).

Annuler un règlement ou un mouvement manuel doit aussi retirer son effet du grand livre, sinon la
trésorerie et les comptes 521/571/411 divergent sans trace."""

from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounting import services
from apps.accounting.constants import COMPTE_CLIENTS
from apps.accounting.exceptions import ContrePassationImpossible, CompteInconnu, ExerciceCloture
from apps.accounting.models import (
    Compte,
    EcritureComptable,
    ExerciceComptable,
    Journal,
    SensEcriture,
    StatutExercice,
)
from apps.accounting.services import LigneSaisie
from apps.billing import services as billing_services
from apps.billing.models import ModePaiement, Reglement
from apps.billing.tests.helpers import emise, finances
from apps.finance import services as finance_services
from apps.finance.models import LigneReleve, MouvementManuel, NatureMouvement, SensMouvement

from .factories import CompteFactory

pytestmark = pytest.mark.django_db

JOUR = date(2026, 9, 5)


def _solde(numero):
    ligne = {l["compte__numero"]: l for l in services.balance()}.get(numero)
    return Decimal("0") if ligne is None else ligne["total_debit"] - ligne["total_credit"]


def _ecriture(*, date_ecriture=JOUR, montant="1000"):
    charge, tresorerie = CompteFactory(), CompteFactory()
    return services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date_ecriture, libelle="Achat",
        piece_reference="PIECE-1",
        lignes=[
            LigneSaisie(compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal(montant)),
            LigneSaisie(
                compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal(montant),
                tiers_type="CLIENT", tiers_id=7,
            ),
        ],
        origine="TEST", origine_id=1,
    )


# --- le service ---


def test_contre_passer_inverse_chaque_ligne_et_garde_l_original_intact():
    ecriture = _ecriture()

    inverse = services.contre_passer(ecriture, motif="Erreur de saisie")

    assert inverse.pk != ecriture.pk
    assert inverse.origine == "CONTRE_PASSATION" and inverse.origine_id == ecriture.pk
    assert inverse.journal == ecriture.journal and inverse.piece_reference == "PIECE-1"
    assert inverse.date_ecriture == timezone.localdate()
    assert inverse.numero and inverse.numero != ecriture.numero
    assert ecriture.numero in inverse.libelle and "Erreur de saisie" in inverse.libelle
    avant = {(l.compte_id, l.sens, l.montant) for l in ecriture.lignes.all()}
    apres = {(l.compte_id, l.sens, l.montant) for l in inverse.lignes.all()}
    inverse_sens = {SensEcriture.DEBIT: SensEcriture.CREDIT, SensEcriture.CREDIT: SensEcriture.DEBIT}
    assert apres == {(c, inverse_sens[s], m) for c, s, m in avant}
    ligne_tiers = inverse.lignes.exclude(tiers_type="").get()
    assert (ligne_tiers.tiers_type, ligne_tiers.tiers_id) == ("CLIENT", 7)
    assert ecriture.lignes.count() == 2  # l'écriture d'origine n'a pas bougé


def test_les_comptes_reviennent_a_zero_une_fois_contre_passee():
    ecriture = _ecriture(montant="2500")
    comptes = [l.compte.numero for l in ecriture.lignes.select_related("compte")]

    services.contre_passer(ecriture)

    assert [_solde(numero) for numero in comptes] == [Decimal("0"), Decimal("0")]


def test_contre_passer_est_idempotente():
    ecriture = _ecriture()

    premiere = services.contre_passer(ecriture)
    seconde = services.contre_passer(ecriture)

    assert premiere.pk == seconde.pk
    assert EcritureComptable.objects.filter(origine="CONTRE_PASSATION").count() == 1


def test_contre_passer_accepte_une_date_explicite():
    ecriture = _ecriture()

    assert services.contre_passer(ecriture, date_ecriture=date(2026, 9, 20)).date_ecriture == date(2026, 9, 20)


def test_un_brouillon_ne_se_contre_passe_pas():
    brouillon = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Brouillon")

    with pytest.raises(ContrePassationImpossible, match="brouillon"):
        services.contre_passer(brouillon)


def test_une_contre_passation_ne_se_contre_passe_pas():
    inverse = services.contre_passer(_ecriture())

    with pytest.raises(ContrePassationImpossible, match="ne se contre-passe pas"):
        services.contre_passer(inverse)


def test_une_ecriture_d_un_exercice_clos_se_contre_passe_dans_l_exercice_ouvert():
    ecriture = _ecriture(date_ecriture=date(2024, 6, 1))
    ExerciceComptable.objects.filter(annee=2024).update(statut=StatutExercice.CLOTURE)

    inverse = services.contre_passer(ecriture)

    assert inverse.date_ecriture == timezone.localdate()
    assert inverse.date_ecriture.year != 2024


def test_contre_passer_est_refusee_si_l_exercice_du_jour_est_clos():
    ecriture = _ecriture()
    services.exercice_pour(timezone.localdate())
    ExerciceComptable.objects.filter(annee=timezone.localdate().year).update(statut=StatutExercice.CLOTURE)

    with pytest.raises(ExerciceCloture):
        services.contre_passer(ecriture)

    assert not EcritureComptable.objects.filter(origine="CONTRE_PASSATION").exists()


def test_contre_passer_origine_ne_fait_rien_sans_ecriture_d_origine():
    assert services.contre_passer_origine("REGLEMENT", 999999) is None


def test_contre_passer_origine_retrouve_l_ecriture_par_son_evenement_source():
    ecriture = _ecriture()

    inverse = services.contre_passer_origine("TEST", 1, motif="Doublon")

    assert inverse.origine_id == ecriture.pk and "Doublon" in inverse.libelle


# --- l'annulation d'un règlement ---


def _reglement(montant="100000", mode=ModePaiement.VIREMENT, jour=JOUR):
    facture = emise(prix="1000000")
    return billing_services.enregistrer_reglement(
        facture, finances(), montant=Decimal(montant), mode=mode, date_reglement=jour
    )


def test_annuler_un_reglement_contre_passe_son_ecriture():
    reglement = _reglement("100000")
    assert _solde("521000") == Decimal("100000")

    billing_services.annuler_reglement(reglement, finances(), motif="Chèque sans provision")

    inverse = EcritureComptable.objects.get(origine="CONTRE_PASSATION")
    assert "Chèque sans provision" in inverse.libelle
    assert _solde("521000") == Decimal("0")
    # la créance du client est rétablie : 411 = TTC de la facture, comme avant le règlement
    assert _solde(COMPTE_CLIENTS) == reglement.facture.montant_ttc


def test_annuler_un_reglement_ancien_se_contre_passe_aujourd_hui():
    reglement = _reglement(jour=date(2026, 9, 1))

    billing_services.annuler_reglement(reglement, finances(), motif="Erreur")

    inverse = EcritureComptable.objects.get(origine="CONTRE_PASSATION")
    assert inverse.date_ecriture == timezone.localdate()


def test_annuler_un_reglement_est_tout_ou_rien_si_la_contre_passation_est_impossible():
    reglement = _reglement()
    Compte.objects.filter(numero="521000").update(actif=False)

    with pytest.raises(CompteInconnu):
        billing_services.annuler_reglement(reglement, finances(), motif="Erreur")

    assert Reglement.objects.filter(pk=reglement.pk).exists()  # l'annulation est annulée avec elle
    assert not EcritureComptable.objects.filter(origine="CONTRE_PASSATION").exists()


def test_annuler_un_reglement_jamais_comptabilise_n_echoue_pas():
    reglement = _reglement()
    EcritureComptable.objects.filter(origine="REGLEMENT", origine_id=reglement.pk).update(origine="ANCIEN")

    billing_services.annuler_reglement(reglement, finances(), motif="Erreur")

    assert not EcritureComptable.objects.filter(origine="CONTRE_PASSATION").exists()


# --- l'annulation d'un mouvement manuel ---


def _mouvement(sens=SensMouvement.ENTREE, montant="50000"):
    return finance_services.enregistrer_mouvement(
        finances(), sens=sens, date_mouvement=JOUR, libelle="Apport", montant=Decimal(montant),
        mode=ModePaiement.VIREMENT, nature=NatureMouvement.APPORT,
    )


@pytest.mark.parametrize("sens", [SensMouvement.ENTREE, SensMouvement.SORTIE])
def test_annuler_un_mouvement_manuel_contre_passe_son_ecriture(sens):
    mouvement = _mouvement(sens)
    assert _solde("521000") != Decimal("0")

    finance_services.annuler_mouvement(mouvement, finances(), motif="Doublon")

    assert EcritureComptable.objects.filter(origine="CONTRE_PASSATION").count() == 1
    assert _solde("521000") == Decimal("0")


# --- le pointage bancaire ---


def _releve(sens=SensMouvement.ENTREE, montant="50000"):
    return finance_services.saisir_ligne_releve(
        finances(), date_operation=JOUR, libelle="Relevé", montant=Decimal(montant), sens=sens
    )


def test_annuler_un_mouvement_defait_le_pointage_de_sa_ligne_de_releve():
    mouvement = _mouvement()
    ligne = _releve()
    finance_services.pointer_ligne_releve(ligne, finances(), origine="MANUEL", mouvement_id=mouvement.pk)

    finance_services.annuler_mouvement(mouvement, finances(), motif="Doublon")

    ligne.refresh_from_db()
    assert ligne.pointee is False and ligne.mouvement_origine == "" and ligne.mouvement_id is None


def test_annuler_un_reglement_defait_le_pointage_de_sa_ligne_de_releve():
    reglement = _reglement("100000")
    ligne = _releve(montant="100000")
    finance_services.pointer_ligne_releve(ligne, finances(), origine="REGLEMENT", mouvement_id=reglement.pk)
    autre_mouvement = _mouvement(montant="1")  # un mouvement sans rapport, sur une autre ligne : reste intact
    autre = _releve(montant="1")
    finance_services.pointer_ligne_releve(autre, finances(), origine="MANUEL", mouvement_id=autre_mouvement.pk)

    billing_services.annuler_reglement(reglement, finances(), motif="Erreur")

    ligne.refresh_from_db()
    autre.refresh_from_db()
    assert ligne.pointee is False and autre.pointee is True
    assert LigneReleve.objects.count() == 2


def test_depointer_mouvement_renvoie_le_nombre_de_lignes_defaites():
    mouvement = _mouvement()
    finance_services.pointer_ligne_releve(_releve(), finances(), origine="MANUEL", mouvement_id=mouvement.pk)

    assert finance_services.depointer_mouvement("MANUEL", mouvement.pk) == 1
    assert finance_services.depointer_mouvement("MANUEL", mouvement.pk) == 0
    assert MouvementManuel.objects.filter(pk=mouvement.pk).exists()


# --- reprise de l'historique ---


def _annulation_ancienne(*objets):
    """Simule des annulations faites avant ce lot : les objets disparaissent sans contre-passation."""
    EcritureComptable.objects.filter(origine="CONTRE_PASSATION").delete()
    for objet in objets:
        type(objet).objects.filter(pk=objet.pk).update(is_deleted=True, deleted_at=timezone.now())


def test_la_reprise_contre_passe_les_annulations_anterieures_et_se_rejoue_sans_doublon():
    from io import StringIO

    from django.core.management import call_command

    reglement, mouvement = _reglement("100000"), _mouvement()
    _annulation_ancienne(reglement, mouvement)
    sortie = StringIO()

    call_command("contre_passer_historique_annulations", "--dry-run", stdout=sortie)
    assert "Simulation" in sortie.getvalue() and "2 annulation(s)" in sortie.getvalue()
    assert not EcritureComptable.objects.filter(origine="CONTRE_PASSATION").exists()

    call_command("contre_passer_historique_annulations", stdout=sortie)
    assert EcritureComptable.objects.filter(origine="CONTRE_PASSATION").count() == 2
    assert _solde("521000") == Decimal("0")

    sortie = StringIO()
    call_command("contre_passer_historique_annulations", stdout=sortie)
    assert "0 annulation(s) contre-passée(s) (2 déjà faites" in sortie.getvalue()
    assert EcritureComptable.objects.filter(origine="CONTRE_PASSATION").count() == 2


def test_la_reprise_ignore_ce_qui_n_a_jamais_ete_comptabilise_et_signale_l_impossible():
    from io import StringIO

    from django.core.management import call_command

    jamais, bloque = _reglement("1000"), _reglement("2000")
    EcritureComptable.objects.filter(origine="REGLEMENT", origine_id=jamais.pk).update(origine="ANCIEN")
    _annulation_ancienne(jamais, bloque)
    Compte.objects.filter(numero="521000").update(actif=False)
    sortie, erreurs = StringIO(), StringIO()

    call_command("contre_passer_historique_annulations", stdout=sortie, stderr=erreurs)

    assert "1 jamais comptabilisées, 1 impossible(s)" in sortie.getvalue()
    assert f"REGLEMENT #{bloque.pk} non contre-passé" in erreurs.getvalue()
```

#### `apps/accounting/tests/test_models.py`

*60 lignes* — Immuabilité : une écriture validée (et ses lignes) ne se modifie ni ne se supprime.

```python
"""Immuabilité : une écriture validée (et ses lignes) ne se modifie ni ne se supprime."""

from datetime import date
from decimal import Decimal

import pytest

from apps.accounting import services
from apps.accounting.exceptions import EcritureVerrouillee
from apps.accounting.models import Journal, SensEcriture
from apps.accounting.services import LigneSaisie

from .factories import CompteFactory

pytestmark = pytest.mark.django_db

JOUR = date(2026, 9, 1)


def _ecriture():
    charge, tresorerie = CompteFactory(), CompteFactory()
    return services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES,
        date_ecriture=JOUR,
        libelle="Test",
        lignes=[
            LigneSaisie(compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("1000")),
            LigneSaisie(compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("1000")),
        ],
    )


def test_une_ecriture_validee_ne_se_modifie_pas():
    ecriture = _ecriture()

    ecriture.libelle = "Modifié"
    with pytest.raises(EcritureVerrouillee):
        ecriture.save()


def test_une_ecriture_validee_ne_se_supprime_pas():
    ecriture = _ecriture()

    with pytest.raises(EcritureVerrouillee):
        ecriture.delete()


def test_une_ligne_d_ecriture_ne_se_modifie_pas():
    ligne = _ecriture().lignes.first()

    ligne.montant = Decimal("1")
    with pytest.raises(ValueError):
        ligne.save()


def test_une_ligne_d_une_ecriture_validee_ne_se_supprime_pas():
    ligne = _ecriture().lignes.first()

    with pytest.raises(EcritureVerrouillee):
        ligne.delete()
```

#### `apps/accounting/tests/test_receivers.py`

*281 lignes* — Intégration : la validation d'une facture et l'enregistrement d'un règlement (billing)

```python
"""Intégration : la validation d'une facture et l'enregistrement d'un règlement (billing)
génèrent toujours leur écriture comptable — cahier-des-charges.md:340."""

from datetime import date
from decimal import Decimal

import pytest

from apps.accounting.constants import COMPTE_CLIENTS, COMPTE_TVA_COLLECTEE, COMPTE_VENTES_TRANSPORT
from apps.accounting.models import EcritureComptable, Journal, SensEcriture
from apps.billing import services as billing_services
from apps.billing.models import CategorieDepense, ModePaiement, OrigineDepense
from apps.billing.tests.helpers import a_valider, direction, emise, finances
from apps.customers.tests.factories import ClientFactory
from apps.finance import services as finance_services
from apps.finance.models import NatureMouvement, SensMouvement

pytestmark = pytest.mark.django_db


def test_facture_validee_genere_une_ecriture_equilibree():
    facture = emise(prix="1000000")

    ecriture = EcritureComptable.objects.get(origine="FACTURE", origine_id=facture.pk)

    assert ecriture.journal == Journal.VENTES
    assert ecriture.numero.startswith("VTE-2026-")
    assert ecriture.piece_reference == facture.numero
    lignes = {l.compte.numero: (l.sens, l.montant) for l in ecriture.lignes.all()}
    assert lignes[COMPTE_CLIENTS] == (SensEcriture.DEBIT, facture.montant_ttc)
    assert lignes[COMPTE_VENTES_TRANSPORT] == (SensEcriture.CREDIT, facture.montant_ht)
    assert lignes[COMPTE_TVA_COLLECTEE] == (SensEcriture.CREDIT, facture.montant_tva)
    total_debit = sum(m for sens, m in lignes.values() if sens == SensEcriture.DEBIT)
    total_credit = sum(m for sens, m in lignes.values() if sens == SensEcriture.CREDIT)
    assert total_debit == total_credit == facture.montant_ttc


def test_ligne_clients_est_rattachee_au_client_de_la_facture():
    facture = emise()

    ecriture = EcritureComptable.objects.get(origine="FACTURE", origine_id=facture.pk)
    ligne_clients = ecriture.lignes.get(compte__numero=COMPTE_CLIENTS)

    assert ligne_clients.tiers_type == "CLIENT"
    assert ligne_clients.tiers_id == facture.client_id


def test_une_facture_exoneree_ne_cree_pas_de_ligne_tva():
    client = ClientFactory(taux_tva=Decimal("0"), motif_exoneration="EXPORT")

    facture = emise(client=client)

    assert facture.montant_tva == 0
    ecriture = EcritureComptable.objects.get(origine="FACTURE", origine_id=facture.pk)
    assert ecriture.lignes.count() == 2
    assert not ecriture.lignes.filter(compte__numero=COMPTE_TVA_COLLECTEE).exists()


def test_valider_une_facture_deja_validee_ne_duplique_pas_l_ecriture():
    facture = emise()
    nb_avant = EcritureComptable.objects.filter(origine="FACTURE", origine_id=facture.pk).count()

    from apps.billing.exceptions import TransitionFactureInterdite

    with pytest.raises(TransitionFactureInterdite):
        billing_services.valider(facture, direction())

    assert EcritureComptable.objects.filter(origine="FACTURE", origine_id=facture.pk).count() == nb_avant == 1


# --- règlements (Phase 2) ---


@pytest.mark.parametrize(
    ("mode", "compte_attendu", "journal_attendu"),
    [
        (ModePaiement.VIREMENT, "521000", Journal.BANQUE),
        (ModePaiement.CHEQUE, "521000", Journal.BANQUE),
        (ModePaiement.ESPECES, "571000", Journal.CAISSE),
        (ModePaiement.WAVE, "521900", Journal.BANQUE),
        (ModePaiement.ORANGE_MONEY, "521900", Journal.BANQUE),
        (ModePaiement.MTN_MONEY, "521900", Journal.BANQUE),
    ],
)
def test_reglement_enregistre_genere_une_ecriture_selon_le_mode(mode, compte_attendu, journal_attendu):
    facture = emise(prix="1000000")

    reglement = billing_services.enregistrer_reglement(
        facture, finances(), montant=Decimal("100000"), mode=mode, date_reglement=date(2026, 9, 5),
    )

    ecriture = EcritureComptable.objects.get(origine="REGLEMENT", origine_id=reglement.pk)
    assert ecriture.journal == journal_attendu
    assert ecriture.date_ecriture == date(2026, 9, 5)
    lignes = {l.compte.numero: (l.sens, l.montant) for l in ecriture.lignes.all()}
    assert lignes[compte_attendu] == (SensEcriture.DEBIT, Decimal("100000"))
    assert lignes[COMPTE_CLIENTS] == (SensEcriture.CREDIT, Decimal("100000"))


def test_ligne_clients_du_reglement_est_rattachee_au_client():
    facture = emise()

    reglement = billing_services.enregistrer_reglement(
        facture, finances(), montant=facture.montant_ttc, mode=ModePaiement.VIREMENT,
        date_reglement=date(2026, 9, 5),
    )

    ecriture = EcritureComptable.objects.get(origine="REGLEMENT", origine_id=reglement.pk)
    ligne_clients = ecriture.lignes.get(compte__numero=COMPTE_CLIENTS)
    assert ligne_clients.tiers_type == "CLIENT"
    assert ligne_clients.tiers_id == facture.client_id


def test_deux_reglements_sur_la_meme_facture_generent_deux_ecritures_distinctes():
    facture = emise(prix="1000000")

    premier = billing_services.enregistrer_reglement(
        facture, finances(), montant=Decimal("400000"), mode=ModePaiement.ESPECES,
        date_reglement=date(2026, 9, 5),
    )
    second = billing_services.enregistrer_reglement(
        facture, finances(), montant=Decimal("600000"), mode=ModePaiement.VIREMENT,
        date_reglement=date(2026, 9, 10),
    )

    ecritures = EcritureComptable.objects.filter(origine="REGLEMENT", origine_id__in=[premier.pk, second.pk])
    assert ecritures.count() == 2


# --- dépenses automatiques (Phase 3) ---


def _depense_automatique(origine_id, *, categorie=CategorieDepense.CARBURANT, mode=ModePaiement.ESPECES):
    return billing_services.comptabiliser_depense_automatique(
        origine=OrigineDepense.PLEIN, origine_id=origine_id, categorie=categorie,
        date_depense=date(2026, 9, 5), libelle="Plein — AB-1234-CI", montant=Decimal("50000"),
        mode=mode,
    )


@pytest.mark.parametrize(
    ("categorie", "compte_charge"),
    [
        (CategorieDepense.CARBURANT, "605100"),
        (CategorieDepense.PIECES, "605800"),
        (CategorieDepense.MAINTENANCE, "624100"),
        (CategorieDepense.FRAIS_MISSION, "628100"),
    ],
)
def test_depense_automatique_genere_une_ecriture_selon_la_categorie(categorie, compte_charge):
    depense = _depense_automatique(1001, categorie=categorie)

    ecriture = EcritureComptable.objects.get(origine="DEPENSE", origine_id=depense.pk)
    assert ecriture.journal == Journal.CAISSE  # ESPECES par défaut
    lignes = {l.compte.numero: (l.sens, l.montant) for l in ecriture.lignes.all()}
    assert lignes[compte_charge] == (SensEcriture.DEBIT, Decimal("50000"))
    assert lignes["571000"] == (SensEcriture.CREDIT, Decimal("50000"))


@pytest.mark.parametrize(
    ("categorie", "compte_charge"),
    [
        (CategorieDepense.PEAGES, "628100"),
        (CategorieDepense.ENTRETIEN, "624100"),
        (CategorieDepense.FRAIS_ADMIN, "658000"),
        (CategorieDepense.AUTRE, "658000"),
    ],
)
def test_depense_manuelle_genere_une_ecriture_selon_la_categorie(categorie, compte_charge):
    depense = billing_services.enregistrer_depense(
        finances(), categorie=categorie, date_depense=date(2026, 9, 5), libelle="Test",
        montant=Decimal("12000"), mode=ModePaiement.ESPECES,
    )

    ecriture = EcritureComptable.objects.get(origine="DEPENSE", origine_id=depense.pk)
    assert ecriture.journal == Journal.CAISSE
    lignes = {l.compte.numero: (l.sens, l.montant) for l in ecriture.lignes.all()}
    assert lignes[compte_charge] == (SensEcriture.DEBIT, Decimal("12000"))
    assert lignes["571000"] == (SensEcriture.CREDIT, Decimal("12000"))


def test_depense_avec_tva_deductible_genere_une_ecriture_a_3_lignes():
    depense = billing_services.enregistrer_depense(
        finances(), categorie=CategorieDepense.PEAGES, date_depense=date(2026, 9, 5), libelle="Péage facturé",
        montant=Decimal("11800"), montant_tva=Decimal("1800"), mode=ModePaiement.ESPECES,
    )

    ecriture = EcritureComptable.objects.get(origine="DEPENSE", origine_id=depense.pk)
    lignes = {l.compte.numero: (l.sens, l.montant) for l in ecriture.lignes.all()}
    assert lignes["628100"] == (SensEcriture.DEBIT, Decimal("10000"))  # charge au HT
    assert lignes["445200"] == (SensEcriture.DEBIT, Decimal("1800"))  # TVA déductible
    assert lignes["571000"] == (SensEcriture.CREDIT, Decimal("11800"))  # trésorerie au TTC
    total_debit = sum(m for sens, m in lignes.values() if sens == SensEcriture.DEBIT)
    assert total_debit == Decimal("11800")  # écriture équilibrée


def test_depense_sans_tva_ne_genere_aucune_ligne_445200():
    depense = billing_services.enregistrer_depense(
        finances(), categorie=CategorieDepense.PEAGES, date_depense=date(2026, 9, 5), libelle="Péage sans facture",
        montant=Decimal("5000"), mode=ModePaiement.ESPECES,
    )

    ecriture = EcritureComptable.objects.get(origine="DEPENSE", origine_id=depense.pk)
    assert not ecriture.lignes.filter(compte__numero="445200").exists()
    assert ecriture.lignes.count() == 2


def test_rejouer_la_meme_source_ne_duplique_pas_l_ecriture():
    premiere = _depense_automatique(1002)
    seconde = _depense_automatique(1002)  # même origine_id : Depense.get_or_create retombe dessus

    assert premiere.pk == seconde.pk
    assert EcritureComptable.objects.filter(origine="DEPENSE", origine_id=premiere.pk).count() == 1


def test_un_ordre_de_decaissement_avec_mode_reel_ne_passe_pas_par_la_caisse_provisoire():
    depense = _depense_automatique(1003, categorie=CategorieDepense.PIECES, mode=ModePaiement.VIREMENT)

    ecriture = EcritureComptable.objects.get(origine="DEPENSE", origine_id=depense.pk)
    assert ecriture.journal == Journal.BANQUE
    assert ecriture.lignes.filter(compte__numero="521000", sens=SensEcriture.CREDIT).exists()


def test_changer_le_mode_reclasse_la_tresorerie():
    depense = _depense_automatique(1004)  # ESPECES -> 571000 par défaut

    billing_services.changer_mode_depense(depense, finances(), mode=ModePaiement.VIREMENT)

    reclassements = EcritureComptable.objects.filter(journal=Journal.OPERATIONS_DIVERSES)
    ecriture = reclassements.latest("pk")
    lignes = {l.compte.numero: (l.sens, l.montant) for l in ecriture.lignes.all()}
    assert lignes["521000"] == (SensEcriture.DEBIT, Decimal("50000"))
    assert lignes["571000"] == (SensEcriture.CREDIT, Decimal("50000"))


def test_changer_le_mode_vers_le_meme_compte_de_tresorerie_ne_reclasse_rien():
    depense = _depense_automatique(1005, mode=ModePaiement.VIREMENT)  # Banque
    nb_avant = EcritureComptable.objects.filter(journal=Journal.OPERATIONS_DIVERSES).count()

    billing_services.changer_mode_depense(depense, finances(), mode=ModePaiement.CHEQUE)  # Banque aussi

    assert EcritureComptable.objects.filter(journal=Journal.OPERATIONS_DIVERSES).count() == nb_avant


# --- mouvements manuels de trésorerie (Phase 4) ---


@pytest.mark.parametrize(
    ("nature", "compte_contrepartie"),
    [
        (NatureMouvement.SOLDE_OUVERTURE, "101000"),
        (NatureMouvement.APPORT, "101000"),
        (NatureMouvement.RETRAIT, "108000"),
        (NatureMouvement.FRAIS_BANCAIRE, "631000"),
        (NatureMouvement.AUTRE, "658000"),
    ],
)
def test_une_entree_de_mouvement_manuel_debite_la_tresorerie(nature, compte_contrepartie):
    mouvement = finance_services.enregistrer_mouvement(
        finances(), sens=SensMouvement.ENTREE, date_mouvement=date(2026, 9, 5), libelle="Test",
        montant=Decimal("200000"), mode=ModePaiement.VIREMENT, nature=nature,
    )

    ecriture = EcritureComptable.objects.get(origine="MOUVEMENT", origine_id=mouvement.pk)
    assert ecriture.journal == Journal.BANQUE
    lignes = {l.compte.numero: (l.sens, l.montant) for l in ecriture.lignes.all()}
    assert lignes["521000"] == (SensEcriture.DEBIT, Decimal("200000"))
    assert lignes[compte_contrepartie] == (SensEcriture.CREDIT, Decimal("200000"))


def test_une_sortie_de_mouvement_manuel_credite_la_tresorerie():
    mouvement = finance_services.enregistrer_mouvement(
        finances(), sens=SensMouvement.SORTIE, date_mouvement=date(2026, 9, 5), libelle="Retrait",
        montant=Decimal("50000"), mode=ModePaiement.ESPECES, nature=NatureMouvement.RETRAIT,
    )

    ecriture = EcritureComptable.objects.get(origine="MOUVEMENT", origine_id=mouvement.pk)
    assert ecriture.journal == Journal.CAISSE
    lignes = {l.compte.numero: (l.sens, l.montant) for l in ecriture.lignes.all()}
    assert lignes["571000"] == (SensEcriture.CREDIT, Decimal("50000"))
    assert lignes["108000"] == (SensEcriture.DEBIT, Decimal("50000"))
```

#### `apps/accounting/tests/test_services.py`

*761 lignes* — Moteur d'écritures : équilibre, idempotence, comptes inconnus/inactifs ; saisie manuelle

```python
"""Moteur d'écritures : équilibre, idempotence, comptes inconnus/inactifs ; saisie manuelle
d'opérations diverses (Phase 4) ; exercice comptable et clôture (Phase 5) ; rapports (Phase 6)."""

from datetime import date
from decimal import Decimal

import pytest

from apps.accounting import services
from apps.accounting.exceptions import (
    ActionComptableNonAutorisee,
    ClotureImpossible,
    CompteDejaExistant,
    CompteInconnu,
    EcritureNonEquilibree,
    EcritureVerrouillee,
    ExerciceCloture,
)
from apps.accounting.models import (
    Compte,
    ExerciceComptable,
    Journal,
    LigneEcriture,
    SensEcriture,
    StatutEcriture,
    StatutExercice,
)
from apps.accounting.services import LigneSaisie
from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing.tests.helpers import direction, finances

from .factories import CompteFactory

pytestmark = pytest.mark.django_db

JOUR = date(2026, 9, 1)
# Un exercice ne se clôture qu'une fois l'année terminée : les tests de clôture visent une année passée.
JOUR_PASSE = date(2024, 6, 1)


def _lignes_equilibrees(charge, tresorerie, montant="1000"):
    montant = Decimal(montant)
    return [
        LigneSaisie(compte=charge.numero, sens=SensEcriture.DEBIT, montant=montant),
        LigneSaisie(compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=montant),
    ]


def test_passer_ecriture_equilibree_cree_lignes():
    charge, tresorerie = CompteFactory(), CompteFactory()

    ecriture = services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES,
        date_ecriture=JOUR,
        libelle="Test",
        lignes=_lignes_equilibrees(charge, tresorerie),
    )

    assert ecriture.numero.startswith("OD-2026-")
    assert ecriture.lignes.count() == 2
    assert {l.compte_id for l in ecriture.lignes.all()} == {charge.pk, tresorerie.pk}


def test_passer_ecriture_desequilibree_leve_erreur_et_ne_cree_rien():
    charge, tresorerie = CompteFactory(), CompteFactory()
    lignes = [
        LigneSaisie(compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("1000")),
        LigneSaisie(compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("900")),
    ]

    with pytest.raises(EcritureNonEquilibree, match="1000.*900|900.*1000"):
        services.passer_ecriture(
            journal=Journal.OPERATIONS_DIVERSES, date_ecriture=JOUR, libelle="Test", lignes=lignes
        )

    assert LigneEcriture.objects.count() == 0


def test_passer_ecriture_refuse_un_montant_negatif_ou_nul():
    charge, tresorerie = CompteFactory(), CompteFactory()
    lignes = [
        LigneSaisie(compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("0")),
        LigneSaisie(compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("0")),
    ]

    with pytest.raises(EcritureNonEquilibree):
        services.passer_ecriture(
            journal=Journal.OPERATIONS_DIVERSES, date_ecriture=JOUR, libelle="Test", lignes=lignes
        )


def test_passer_ecriture_refuse_moins_de_deux_lignes():
    charge = CompteFactory()

    with pytest.raises(EcritureNonEquilibree):
        services.passer_ecriture(
            journal=Journal.OPERATIONS_DIVERSES,
            date_ecriture=JOUR,
            libelle="Test",
            lignes=[LigneSaisie(compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("1000"))],
        )


def test_passer_ecriture_refuse_un_compte_inconnu():
    tresorerie = CompteFactory()

    with pytest.raises(CompteInconnu, match="999999"):
        services.passer_ecriture(
            journal=Journal.OPERATIONS_DIVERSES,
            date_ecriture=JOUR,
            libelle="Test",
            lignes=[
                LigneSaisie(compte="999999", sens=SensEcriture.DEBIT, montant=Decimal("1000")),
                LigneSaisie(compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("1000")),
            ],
        )


def test_passer_ecriture_refuse_un_compte_inactif():
    charge, tresorerie = CompteFactory(actif=False), CompteFactory()

    with pytest.raises(CompteInconnu):
        services.passer_ecriture(
            journal=Journal.OPERATIONS_DIVERSES,
            date_ecriture=JOUR,
            libelle="Test",
            lignes=_lignes_equilibrees(charge, tresorerie),
        )


def test_passer_ecriture_idempotente_par_origine():
    charge, tresorerie = CompteFactory(), CompteFactory()
    lignes = _lignes_equilibrees(charge, tresorerie)

    premiere = services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=JOUR, libelle="Test",
        lignes=lignes, origine="TEST", origine_id=42,
    )
    seconde = services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=JOUR, libelle="Autre libellé",
        lignes=lignes, origine="TEST", origine_id=42,
    )

    assert premiere.pk == seconde.pk
    assert LigneEcriture.objects.count() == 2  # pas de doublon


def test_grand_livre_filtre_par_compte_et_periode():
    charge, tresorerie = CompteFactory(), CompteFactory()
    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date(2026, 1, 15), libelle="Janvier",
        lignes=_lignes_equilibrees(charge, tresorerie),
    )
    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date(2026, 6, 15), libelle="Juin",
        lignes=_lignes_equilibrees(charge, tresorerie),
    )

    lignes_annee = services.grand_livre(charge, debut=date(2026, 1, 1), fin=date(2026, 12, 31))
    lignes_premier_semestre = services.grand_livre(charge, debut=date(2026, 1, 1), fin=date(2026, 3, 31))

    assert lignes_annee.count() == 2
    assert lignes_premier_semestre.count() == 1


def test_grand_livre_exclut_les_brouillons_non_valides():
    charge = CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Brouillon")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )

    assert services.grand_livre(charge).count() == 0


# --- plan comptable (Lot F, autonomie comptable) ---


def test_creer_un_compte():
    compte = services.creer_compte(
        finances(), numero="999999", libelle="Compte de test", nature="CHARGE"
    )

    assert (compte.numero, compte.libelle, compte.nature, compte.actif) == ("999999", "Compte de test", "CHARGE", True)


def test_creer_un_compte_refuse_un_numero_vide():
    with pytest.raises(CompteInconnu, match="numéro"):
        services.creer_compte(finances(), numero="  ", libelle="x", nature="CHARGE")


def test_creer_un_compte_refuse_une_nature_inconnue():
    with pytest.raises(CompteInconnu, match="Nature"):
        services.creer_compte(finances(), numero="999999", libelle="x", nature="INCONNUE")


def test_creer_un_compte_refuse_un_numero_deja_pris():
    services.creer_compte(finances(), numero="999999", libelle="Premier", nature="CHARGE")

    with pytest.raises(CompteDejaExistant):
        services.creer_compte(finances(), numero="999999", libelle="Second", nature="PRODUIT")


def test_creer_un_compte_refuse_un_libelle_vide():
    with pytest.raises(CompteInconnu, match="libellé"):
        services.creer_compte(finances(), numero="999999", libelle="  ", nature="CHARGE")


def test_creer_un_compte_refuse_un_role_non_autorise():
    with pytest.raises(ActionComptableNonAutorisee):
        services.creer_compte(
            UserFactory(role=Role.CHAUFFEUR), numero="999999", libelle="x", nature="CHARGE"
        )


def test_modifier_un_compte_corrige_le_libelle_et_le_statut():
    compte = CompteFactory(libelle="Ancien libellé", actif=True)

    services.modifier_compte(compte, finances(), libelle="Nouveau libellé", actif=False)

    compte.refresh_from_db()
    assert (compte.libelle, compte.actif) == ("Nouveau libellé", False)


def test_modifier_un_compte_refuse_un_libelle_vide():
    compte = CompteFactory()

    with pytest.raises(CompteInconnu, match="libellé"):
        services.modifier_compte(compte, finances(), libelle=" ", actif=True)


def test_modifier_un_compte_refuse_un_role_non_autorise():
    compte = CompteFactory()

    with pytest.raises(ActionComptableNonAutorisee):
        services.modifier_compte(compte, UserFactory(role=Role.CHAUFFEUR), libelle="x", actif=True)


def test_un_compte_desactive_est_refuse_dans_une_nouvelle_ecriture():
    compte = CompteFactory()
    services.modifier_compte(compte, finances(), libelle=compte.libelle, actif=False)
    autre = CompteFactory()

    with pytest.raises(CompteInconnu):
        services.passer_ecriture(
            journal=Journal.OPERATIONS_DIVERSES, date_ecriture=JOUR, libelle="Test",
            lignes=_lignes_equilibrees(compte, autre),
        )


# --- saisie manuelle d'opérations diverses (Phase 4) ---


def test_creer_une_ecriture_manuelle_ouvre_un_brouillon_sans_numero():
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")

    assert ecriture.statut == StatutEcriture.BROUILLON
    assert ecriture.numero == ""
    assert ecriture.lignes.count() == 0


def test_creer_une_ecriture_manuelle_refuse_un_role_non_autorise():
    with pytest.raises(ActionComptableNonAutorisee):
        services.creer_ecriture_manuelle(
            UserFactory(role=Role.CHARGE_CLIENTELE), date_ecriture=JOUR, libelle="Test"
        )


def test_ajouter_puis_supprimer_une_ligne_sur_un_brouillon():
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")

    ligne = services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )
    assert ecriture.lignes.count() == 1

    services.supprimer_ligne_manuelle(ligne, finances())
    assert ecriture.lignes.count() == 0


def test_valider_une_ecriture_manuelle_equilibree_attribue_un_numero():
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("5000")
    )

    validee = services.valider_ecriture_manuelle(ecriture, direction())

    assert validee.statut == StatutEcriture.VALIDEE
    assert validee.numero.startswith("OD-2026-")
    assert validee.valide_par is not None


def test_valider_une_ecriture_desequilibree_est_refuse():
    charge = CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )

    with pytest.raises(EcritureNonEquilibree):
        services.valider_ecriture_manuelle(ecriture, direction())

    ecriture.refresh_from_db()
    assert ecriture.statut == StatutEcriture.BROUILLON


def test_seule_la_direction_valide_une_ecriture_manuelle_strict():
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("5000")
    )

    with pytest.raises(ActionComptableNonAutorisee):
        services.valider_ecriture_manuelle(ecriture, finances())
    with pytest.raises(ActionComptableNonAutorisee):
        services.valider_ecriture_manuelle(ecriture, UserFactory(role=Role.ADMIN, is_superuser=True))


def test_une_fois_validee_on_ne_peut_plus_ajouter_ni_supprimer_de_ligne():
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )
    ligne = services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("5000")
    )
    services.valider_ecriture_manuelle(ecriture, direction())

    with pytest.raises(EcritureVerrouillee):
        services.ajouter_ligne_manuelle(
            ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("1")
        )
    with pytest.raises(EcritureVerrouillee):
        services.supprimer_ligne_manuelle(ligne, finances())


def test_abandonner_un_brouillon():
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")

    services.abandonner_ecriture_manuelle(ecriture, finances())

    from apps.accounting.models import EcritureComptable

    assert not EcritureComptable.objects.filter(pk=ecriture.pk).exists()
    assert EcritureComptable.all_objects.get(pk=ecriture.pk).is_deleted


def test_on_ne_peut_pas_abandonner_une_ecriture_deja_validee():
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("5000")
    )
    services.valider_ecriture_manuelle(ecriture, direction())

    with pytest.raises(EcritureVerrouillee):
        services.abandonner_ecriture_manuelle(ecriture, finances())


def test_creer_une_ecriture_manuelle_refuse_un_libelle_vide():
    with pytest.raises(EcritureNonEquilibree):
        services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="   ")


def test_ajouter_une_ligne_refuse_un_montant_negatif_ou_nul():
    charge = CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")

    with pytest.raises(EcritureNonEquilibree):
        services.ajouter_ligne_manuelle(
            ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("0")
        )


def test_valider_une_ecriture_avec_deux_lignes_desequilibrees_est_refuse():
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("4000")
    )

    with pytest.raises(EcritureNonEquilibree, match="5000.*4000|4000.*5000"):
        services.valider_ecriture_manuelle(ecriture, direction())


# --- exercice comptable et clôture (Phase 5) ---


def test_exercice_pour_cree_l_exercice_de_l_annee_s_il_n_existe_pas():
    exercice = services.exercice_pour(date(2026, 3, 15))

    assert exercice.annee == 2026
    assert exercice.date_debut == date(2026, 1, 1)
    assert exercice.date_fin == date(2026, 12, 31)
    assert exercice.statut == StatutExercice.OUVERT


def test_exercice_pour_est_idempotent():
    premier = services.exercice_pour(date(2026, 3, 15))
    second = services.exercice_pour(date(2026, 11, 1))

    assert premier.pk == second.pk
    assert ExerciceComptable.objects.count() == 1


def test_passer_une_ecriture_cree_son_exercice_au_passage():
    charge, tresorerie = CompteFactory(), CompteFactory()

    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date(2027, 5, 1), libelle="Test",
        lignes=_lignes_equilibrees(charge, tresorerie),
    )

    assert ExerciceComptable.objects.filter(annee=2027, statut=StatutExercice.OUVERT).exists()


def test_cloturer_un_exercice_verrouille_les_nouvelles_ecritures():
    charge, tresorerie = CompteFactory(), CompteFactory()
    exercice = services.exercice_pour(JOUR_PASSE)

    services.cloturer_exercice(exercice, direction())

    exercice.refresh_from_db()
    assert exercice.statut == StatutExercice.CLOTURE
    assert exercice.cloture_par is not None
    with pytest.raises(ExerciceCloture, match="2024"):
        services.passer_ecriture(
            journal=Journal.OPERATIONS_DIVERSES, date_ecriture=JOUR_PASSE, libelle="Trop tard",
            lignes=_lignes_equilibrees(charge, tresorerie),
        )


def test_cloturer_est_reserve_a_la_direction_strict():
    exercice = services.exercice_pour(JOUR)

    with pytest.raises(ActionComptableNonAutorisee):
        services.cloturer_exercice(exercice, finances())
    with pytest.raises(ActionComptableNonAutorisee):
        services.cloturer_exercice(exercice, UserFactory(role=Role.ADMIN, is_superuser=True))


def test_cloturer_un_exercice_deja_cloture_est_refuse():
    exercice = services.exercice_pour(JOUR_PASSE)
    services.cloturer_exercice(exercice, direction())

    with pytest.raises(ExerciceCloture):
        services.cloturer_exercice(exercice, direction())


def test_cloturer_refuse_s_il_reste_des_brouillons_dans_la_periode():
    exercice = services.exercice_pour(JOUR_PASSE)
    services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR_PASSE, libelle="Encore en brouillon")

    with pytest.raises(ClotureImpossible, match="brouillon"):
        services.cloturer_exercice(exercice, direction())

    exercice.refresh_from_db()
    assert exercice.statut == StatutExercice.OUVERT


def test_creer_une_ecriture_manuelle_dans_un_exercice_cloture_est_refuse():
    exercice = services.exercice_pour(JOUR_PASSE)
    services.cloturer_exercice(exercice, direction())

    with pytest.raises(ExerciceCloture):
        services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR_PASSE, libelle="Trop tard")


def test_valider_une_ecriture_manuelle_est_refuse_si_l_exercice_est_devenu_cloture():
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("5000")
    )
    # Simule une clôture concurrente (impossible via l'écran, qui bloque tant qu'un brouillon
    # reste dans la période — ce test vérifie la seconde ligne de défense au moment de valider).
    ExerciceComptable.objects.filter(annee=JOUR.year).update(statut=StatutExercice.CLOTURE)

    with pytest.raises(ExerciceCloture):
        services.valider_ecriture_manuelle(ecriture, direction())


# --- rapports : grand livre, balance, bilan, compte de résultat (Phase 6) ---


def _compte(numero):
    return Compte.objects.get(numero=numero)


def test_grand_livre_avec_solde_calcule_le_solde_cumule():
    caisse = _compte("571000")
    autre = CompteFactory()
    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date(2026, 1, 10), libelle="Un",
        lignes=[
            LigneSaisie(compte="571000", sens=SensEcriture.DEBIT, montant=Decimal("1000")),
            LigneSaisie(compte=autre.numero, sens=SensEcriture.CREDIT, montant=Decimal("1000")),
        ],
    )
    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date(2026, 1, 20), libelle="Deux",
        lignes=[
            LigneSaisie(compte=autre.numero, sens=SensEcriture.DEBIT, montant=Decimal("400")),
            LigneSaisie(compte="571000", sens=SensEcriture.CREDIT, montant=Decimal("400")),
        ],
    )

    lignes = services.grand_livre_avec_solde(caisse)

    assert [l["solde_cumule"] for l in lignes] == [Decimal("1000"), Decimal("600")]


def test_balance_agrege_debit_credit_et_solde_par_compte():
    charge, tresorerie = CompteFactory(), CompteFactory()
    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=JOUR, libelle="Test",
        lignes=_lignes_equilibrees(charge, tresorerie, montant="7000"),
    )

    lignes = {l["compte__numero"]: l for l in services.balance()}

    assert lignes[charge.numero]["total_debit"] == Decimal("7000")
    assert lignes[charge.numero]["solde_debiteur"] == Decimal("7000")
    assert lignes[charge.numero]["solde_crediteur"] == Decimal("0")
    assert lignes[tresorerie.numero]["total_credit"] == Decimal("7000")
    assert lignes[tresorerie.numero]["solde_crediteur"] == Decimal("7000")


def test_balance_filtre_par_periode():
    charge, tresorerie = CompteFactory(), CompteFactory()
    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date(2026, 1, 15), libelle="Janvier",
        lignes=_lignes_equilibrees(charge, tresorerie),
    )
    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date(2026, 6, 15), libelle="Juin",
        lignes=_lignes_equilibrees(charge, tresorerie),
    )

    lignes = {l["compte__numero"]: l for l in services.balance(debut=date(2026, 1, 1), fin=date(2026, 3, 31))}

    assert lignes[charge.numero]["total_debit"] == Decimal("1000")


def test_balance_exclut_les_brouillons_non_valides():
    charge = CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Brouillon")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )

    lignes = {l["compte__numero"]: l for l in services.balance()}

    assert charge.numero not in lignes


def test_declaration_tva_calcule_la_tva_nette():
    clients, ventes, tva_collectee = _compte("411000"), _compte("706100"), _compte("443300")
    charge, tva_deductible, caisse = _compte("628100"), _compte("445200"), _compte("571000")
    services.passer_ecriture(
        journal=Journal.VENTES, date_ecriture=JOUR, libelle="Vente",
        lignes=[
            LigneSaisie(compte=clients.numero, sens=SensEcriture.DEBIT, montant=Decimal("1180")),
            LigneSaisie(compte=ventes.numero, sens=SensEcriture.CREDIT, montant=Decimal("1000")),
            LigneSaisie(compte=tva_collectee.numero, sens=SensEcriture.CREDIT, montant=Decimal("180")),
        ],
    )
    services.passer_ecriture(
        journal=Journal.CAISSE, date_ecriture=JOUR, libelle="Péage facturé",
        lignes=[
            LigneSaisie(compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("100")),
            LigneSaisie(compte=tva_deductible.numero, sens=SensEcriture.DEBIT, montant=Decimal("18")),
            LigneSaisie(compte=caisse.numero, sens=SensEcriture.CREDIT, montant=Decimal("118")),
        ],
    )

    rapport = services.declaration_tva(debut=date(2026, 9, 1), fin=date(2026, 9, 30))

    assert rapport["tva_collectee"] == Decimal("180")
    assert rapport["tva_deductible"] == Decimal("18")
    assert rapport["tva_nette"] == Decimal("162")


def test_declaration_tva_negative_est_un_credit_reportable():
    charge, tva_deductible, caisse = _compte("628100"), _compte("445200"), _compte("571000")
    services.passer_ecriture(
        journal=Journal.CAISSE, date_ecriture=JOUR, libelle="Grosse dépense facturée",
        lignes=[
            LigneSaisie(compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("1000")),
            LigneSaisie(compte=tva_deductible.numero, sens=SensEcriture.DEBIT, montant=Decimal("180")),
            LigneSaisie(compte=caisse.numero, sens=SensEcriture.CREDIT, montant=Decimal("1180")),
        ],
    )

    rapport = services.declaration_tva(debut=date(2026, 9, 1), fin=date(2026, 9, 30))

    assert rapport["tva_collectee"] == Decimal("0")
    assert rapport["tva_deductible"] == Decimal("180")
    assert rapport["tva_nette"] == Decimal("-180")


def test_declaration_tva_filtre_par_periode():
    clients, ventes, tva_collectee = _compte("411000"), _compte("706100"), _compte("443300")
    services.passer_ecriture(
        journal=Journal.VENTES, date_ecriture=date(2026, 1, 15), libelle="Vente janvier",
        lignes=[
            LigneSaisie(compte=clients.numero, sens=SensEcriture.DEBIT, montant=Decimal("1180")),
            LigneSaisie(compte=ventes.numero, sens=SensEcriture.CREDIT, montant=Decimal("1000")),
            LigneSaisie(compte=tva_collectee.numero, sens=SensEcriture.CREDIT, montant=Decimal("180")),
        ],
    )

    rapport = services.declaration_tva(debut=date(2026, 6, 1), fin=date(2026, 6, 30))

    assert rapport["tva_collectee"] == Decimal("0")


def test_declaration_tva_exclut_les_brouillons_non_valides():
    tva_deductible = _compte("445200")
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Brouillon")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=tva_deductible.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )

    rapport = services.declaration_tva(debut=date(2026, 9, 1), fin=date(2026, 9, 30))

    assert rapport["tva_deductible"] == Decimal("0")


def test_compte_de_resultat_calcule_le_resultat_net():
    exercice = services.exercice_pour(JOUR)
    clients, ventes, tva = _compte("411000"), _compte("706100"), _compte("443300")
    caisse, carburant = _compte("571000"), _compte("605100")
    services.passer_ecriture(
        journal=Journal.VENTES, date_ecriture=JOUR, libelle="Vente",
        lignes=[
            LigneSaisie(compte=clients.numero, sens=SensEcriture.DEBIT, montant=Decimal("1180")),
            LigneSaisie(compte=ventes.numero, sens=SensEcriture.CREDIT, montant=Decimal("1000")),
            LigneSaisie(compte=tva.numero, sens=SensEcriture.CREDIT, montant=Decimal("180")),
        ],
    )
    services.passer_ecriture(
        journal=Journal.CAISSE, date_ecriture=JOUR, libelle="Plein",
        lignes=[
            LigneSaisie(compte=carburant.numero, sens=SensEcriture.DEBIT, montant=Decimal("300")),
            LigneSaisie(compte=caisse.numero, sens=SensEcriture.CREDIT, montant=Decimal("300")),
        ],
    )

    rapport = services.compte_de_resultat(exercice)

    assert rapport["total_produits"] == Decimal("1000")  # la TVA collectée n'est pas un produit
    assert rapport["total_charges"] == Decimal("300")
    assert rapport["resultat_net"] == Decimal("700")


def test_compte_de_resultat_exclut_les_brouillons_non_valides():
    exercice = services.exercice_pour(JOUR)
    charge = CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Brouillon")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )

    rapport = services.compte_de_resultat(exercice)

    assert rapport["total_charges"] == Decimal("0")
    assert rapport["charges"] == []


def test_bilan_equilibre_avec_le_resultat_net():
    exercice = services.exercice_pour(JOUR)
    clients, ventes = _compte("411000"), _compte("706100")
    services.passer_ecriture(
        journal=Journal.VENTES, date_ecriture=JOUR, libelle="Vente",
        lignes=[
            LigneSaisie(compte=clients.numero, sens=SensEcriture.DEBIT, montant=Decimal("1000")),
            LigneSaisie(compte=ventes.numero, sens=SensEcriture.CREDIT, montant=Decimal("1000")),
        ],
    )

    rapport = services.bilan(exercice)

    assert rapport["total_actif"] == Decimal("1000")
    assert rapport["total_passif"] == Decimal("0")
    assert rapport["resultat_net"] == Decimal("1000")
    assert rapport["total_passif_avec_resultat"] == rapport["total_actif"] == Decimal("1000")


def test_bilan_exclut_les_brouillons_non_valides():
    exercice = services.exercice_pour(JOUR)
    caisse = _compte("571000")
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Brouillon")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=caisse.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )

    rapport = services.bilan(exercice)

    assert rapport["total_actif"] == Decimal("0")
    assert rapport["actif"] == []


def test_bilan_est_cumulatif_mais_compte_de_resultat_reste_par_exercice():
    clients, ventes = _compte("411000"), _compte("706100")
    exercice_2025 = services.exercice_pour(date(2025, 6, 1))
    services.passer_ecriture(
        journal=Journal.VENTES, date_ecriture=date(2025, 6, 1), libelle="Vente 2025",
        lignes=[
            LigneSaisie(compte=clients.numero, sens=SensEcriture.DEBIT, montant=Decimal("500")),
            LigneSaisie(compte=ventes.numero, sens=SensEcriture.CREDIT, montant=Decimal("500")),
        ],
    )
    exercice_2026 = services.exercice_pour(JOUR)

    bilan_2026 = services.bilan(exercice_2026)
    resultat_2026 = services.compte_de_resultat(exercice_2026)

    assert bilan_2026["total_actif"] == Decimal("500")  # cumulatif : reprend 2025
    assert resultat_2026["total_produits"] == Decimal("0")  # la vente 2025 n'est pas dans 2026
    assert services.compte_de_resultat(exercice_2025)["total_produits"] == Decimal("500")


def test_bilan_classe_aussi_les_comptes_de_passif():
    exercice = services.exercice_pour(JOUR)
    caisse, capital = _compte("571000"), _compte("101000")
    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=JOUR, libelle="Apport",
        lignes=[
            LigneSaisie(compte=caisse.numero, sens=SensEcriture.DEBIT, montant=Decimal("2000")),
            LigneSaisie(compte=capital.numero, sens=SensEcriture.CREDIT, montant=Decimal("2000")),
        ],
    )

    rapport = services.bilan(exercice)

    lignes_passif = {l["compte__numero"]: l for l in rapport["passif"]}
    assert lignes_passif[capital.numero]["montant"] == Decimal("2000")
    assert rapport["total_passif"] == Decimal("2000")
    assert rapport["total_actif"] == Decimal("2000")
```

#### `apps/finance/tests/test_services.py`

*496 lignes* — Trésorerie (règlements, dépenses, mouvements manuels) et indicateurs financiers.

```python
"""Trésorerie (règlements, dépenses, mouvements manuels) et indicateurs financiers."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services as billing
from apps.billing.exceptions import ActionFactureNonAutorisee, MontantInvalide
from apps.billing.models import ModePaiement
from apps.billing.tests.helpers import JOUR, direction, emise, finances
from apps.drivers.tests.factories import ChauffeurFactory
from apps.finance import services
from apps.finance.models import MouvementManuel, SensMouvement
from apps.fleet.tests.factories import VehiculeFactory
from apps.fuel import services as fuel
from apps.garage import services as garage
from apps.garage.models import LieuReparation, TypeOr
from apps.inventory import services as stock
from apps.inventory.tests.factories import ArticleFactory

pytestmark = pytest.mark.django_db

SEPT = (date(2026, 9, 1), date(2026, 9, 30))


def _manuel(sens=SensMouvement.ENTREE, montant="100000", *, mode=ModePaiement.VIREMENT, jour=JOUR,
            libelle="Apport", acteur=None):
    return services.enregistrer_mouvement(
        acteur or finances(), sens=sens, date_mouvement=jour, libelle=libelle,
        montant=Decimal(montant), mode=mode,
    )


def _reglement(facture, montant, mode=ModePaiement.VIREMENT, jour=JOUR):
    return billing.enregistrer_reglement(
        facture, finances(), montant=Decimal(montant), mode=mode, date_reglement=jour
    )


def _depense(montant, mode=ModePaiement.ESPECES, jour=JOUR, categorie="PEAGES"):
    return billing.enregistrer_depense(
        finances(), categorie=categorie, date_depense=jour, libelle="Péage", montant=Decimal(montant), mode=mode
    )


# --- mouvements manuels ---


def test_un_mouvement_manuel_s_enregistre_et_s_annule_avec_un_motif():
    mouvement = _manuel()

    services.annuler_mouvement(mouvement, finances(), motif="Doublon")

    assert not MouvementManuel.objects.filter(pk=mouvement.pk).exists()
    assert MouvementManuel.all_objects.get(pk=mouvement.pk).motif_annulation == "Doublon"


@pytest.mark.parametrize(
    ("libelle", "montant", "jour", "message"),
    [
        ("  ", "10", JOUR, "libellé"),
        ("x", "0", JOUR, "strictement positif"),
        ("x", "10", date(2999, 1, 1), "futur"),
    ],
)
def test_mouvements_invalides(libelle, montant, jour, message):
    with pytest.raises(MontantInvalide, match=message):
        _manuel(libelle=libelle, montant=montant, jour=jour)


def test_les_mouvements_sont_reserves_a_la_saisie_facturation():
    # Retour réunion : la DIRECTION (même largeur que l'ADMIN) est désormais dans la SAISIE ;
    # le Parc Auto, lui, n'y a jamais eu accès.
    with pytest.raises(ActionFactureNonAutorisee):
        _manuel(acteur=UserFactory(role=Role.PARCAUTO))
    mouvement = _manuel()
    with pytest.raises(ActionFactureNonAutorisee):
        services.annuler_mouvement(mouvement, UserFactory(role=Role.PARCAUTO), motif="x")
    with pytest.raises(MontantInvalide, match="motif"):
        services.annuler_mouvement(mouvement, finances(), motif=" ")


def test_la_direction_peut_desormais_saisir_un_mouvement():
    """Retour réunion : la DIRECTION a la même largeur que l'ADMIN pour la saisie."""
    assert _manuel(acteur=direction()).pk


# --- journal et soldes ---


def test_le_solde_reunit_reglements_depenses_et_mouvements_par_compte():
    facture = emise(prix="1000000")  # TTC 1 180 000
    _reglement(facture, "500000", ModePaiement.VIREMENT)
    _reglement(facture, "100000", ModePaiement.WAVE)
    _depense("20000", ModePaiement.ESPECES)
    _manuel(SensMouvement.ENTREE, "50000", mode=ModePaiement.ESPECES, libelle="Solde de caisse")
    _manuel(SensMouvement.SORTIE, "5000", mode=ModePaiement.VIREMENT, libelle="Frais bancaires")

    soldes = services.soldes_par_compte()

    assert soldes["BANQUE"] == Decimal("495000")  # 500 000 - 5 000
    assert soldes["CAISSE"] == Decimal("30000")  # 50 000 - 20 000
    assert soldes["MOBILE_MONEY"] == Decimal("100000")
    assert soldes["total"] == Decimal("625000")


def test_un_reglement_annule_ne_compte_plus():
    facture = emise(prix="1000000")
    reglement = _reglement(facture, "300000")
    billing.annuler_reglement(reglement, finances(), motif="Erreur")

    assert services.soldes_par_compte()["total"] == 0
    assert services.mouvements() == []


def test_le_journal_est_trie_et_decrit_chaque_origine():
    facture = emise(prix="1000000")
    _reglement(facture, "100000", jour=date(2026, 9, 3))
    _depense("5000", jour=date(2026, 9, 5))
    _manuel(jour=date(2026, 9, 4), libelle="Apport")

    journal = services.mouvements()

    assert [(m["origine"], m["sens"]) for m in journal] == [
        ("DEPENSE", "SORTIE"), ("MANUEL", "ENTREE"), ("REGLEMENT", "ENTREE"),
    ]
    assert journal[2]["libelle"].startswith(f"Règlement {facture.numero} · ")
    assert journal[2]["compte"] == "BANQUE" and journal[0]["compte"] == "CAISSE"


def test_le_journal_se_filtre_par_periode_sens_et_compte():
    facture = emise(prix="1000000")
    _reglement(facture, "100000", ModePaiement.WAVE, date(2026, 9, 3))
    _depense("5000", ModePaiement.ESPECES, date(2026, 9, 10))
    _manuel(SensMouvement.SORTIE, "1000", mode=ModePaiement.VIREMENT, jour=date(2026, 9, 15), libelle="Frais")

    assert len(services.mouvements(date_debut=date(2026, 9, 5))) == 2
    assert len(services.mouvements(date_fin=date(2026, 9, 5))) == 1
    assert [m["origine"] for m in services.mouvements(sens="ENTREE")] == ["REGLEMENT"]
    assert sorted(m["origine"] for m in services.mouvements(sens="SORTIE")) == ["DEPENSE", "MANUEL"]
    assert [m["origine"] for m in services.mouvements(compte="MOBILE_MONEY")] == ["REGLEMENT"]
    assert services.mouvements(compte="CAISSE")[0]["origine"] == "DEPENSE"


def test_synthese_de_periode_entrees_sorties_variation():
    facture = emise(prix="1000000")
    _reglement(facture, "400000", jour=date(2026, 9, 3))
    _manuel(SensMouvement.ENTREE, "100000", jour=date(2026, 9, 4))
    _depense("30000", jour=date(2026, 9, 6))
    _manuel(SensMouvement.SORTIE, "20000", jour=date(2026, 9, 7), libelle="Frais")
    _depense("999", jour=date(2026, 8, 6))  # hors période

    assert services.synthese_periode(*SEPT) == {
        "entrees": Decimal("500000"), "sorties": Decimal("50000"), "variation": Decimal("450000"),
    }


def test_sans_mouvement_tout_est_a_zero():
    assert services.soldes_par_compte()["total"] == 0
    assert services.synthese_periode(*SEPT)["variation"] == 0


# --- charges et indicateurs ---


def _or_cloture(jour_cloture, main_oeuvre="30000", pieces=2):
    ordre = garage.ouvrir_or(
        VehiculeFactory(), type_or=TypeOr.CURATIF, lieu=LieuReparation.INTERNE, motif="Freins"
    )
    article = ArticleFactory(reference=f"P-{ordre.pk}", quantite=0)
    stock.enregistrer_entree(article, quantite=10, prix_unitaire=Decimal("5000"))
    stock.sortir_pour_or(article, quantite=pieces, ordre=ordre)
    garage.cloturer_or(ordre, cout_main_oeuvre=Decimal(main_oeuvre))
    type(ordre).objects.filter(pk=ordre.pk).update(
        date_cloture=timezone.now().replace(year=jour_cloture.year, month=jour_cloture.month, day=jour_cloture.day)
    )
    return ordre


def _plein(litres, prix, jour, camion=None, km=1000, ticket="T"):
    return fuel.enregistrer_plein(
        vehicule=camion or VehiculeFactory(), chauffeur=ChauffeurFactory(), date_plein=jour, station="T",
        quantite_litres=Decimal(litres), prix_unitaire=Decimal(prix), km_compteur=km, numero_ticket=ticket,
    )


def test_le_cout_du_carburant_est_litres_fois_prix_sur_la_periode():
    _plein("100", "655", date(2026, 9, 3), ticket="A")
    _plein("50", "660", date(2026, 9, 8), ticket="B")
    _plein("500", "700", date(2026, 8, 30), ticket="C")  # hors période (500 L : dans le réservoir de 600 L)

    assert fuel.cout_carburant(*SEPT) == Decimal("98500")  # 65 500 + 33 000


def test_le_cout_des_or_clotures_compte_main_d_oeuvre_et_pieces_de_la_periode():
    _or_cloture(date(2026, 9, 10), main_oeuvre="30000", pieces=2)  # 30 000 + 2 x 5 000
    _or_cloture(date(2026, 8, 10), main_oeuvre="99999", pieces=1)  # hors période

    assert stock.cout_des_or_clotures(*SEPT) == Decimal("40000")


def test_charges_regroupe_depenses_carburant_pieces_et_main_d_oeuvre():
    """Le carburant, les pièces achetées et la main-d'œuvre des OR sont des dépenses comme les autres."""
    from apps.billing.models import Depense, OrigineDepense

    _depense("20000", jour=date(2026, 9, 2))
    _plein("100", "655", date(2026, 9, 3))
    _or_cloture(date(2026, 9, 10), main_oeuvre="30000", pieces=2)  # achat de 10 pièces à 5 000 + main-d'œuvre
    Depense.objects.filter(origine__in=[OrigineDepense.ACHAT_STOCK, OrigineDepense.MAIN_OEUVRE_OR]).update(
        date_depense=date(2026, 9, 10)
    )

    charges = services.charges(*SEPT)

    assert charges == {
        "depenses": Decimal("20000"),
        "carburant": Decimal("65500"),
        "pieces": Decimal("50000"),  # comptées à l'achat, pas à la sortie vers l'OR
        "main_oeuvre": Decimal("30000"),
        "maintenance": Decimal("80000"),
        "frais_mission": Decimal("0"),
        "total": Decimal("165500"),
        "tva_deductible": Decimal("0"),
        "total_ht": Decimal("165500"),
    }


def test_indicateurs_du_mois():
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 10))
    emise(prix="500000", aujourd_hui=date(2026, 9, 12))  # créance non échue au 20/09
    _reglement(facture, "600000", jour=date(2026, 9, 15))
    _depense("100000", jour=date(2026, 9, 5))

    kpi = services.indicateurs(*SEPT, aujourd_hui=date(2026, 9, 20))

    assert kpi["chiffre_affaires"] == Decimal("1500000")  # HT
    assert kpi["encaisse"] == Decimal("600000")
    assert kpi["charges"]["total"] == Decimal("100000")
    assert kpi["marge_nette"] == Decimal("1400000")
    assert kpi["creances"]["total"] == Decimal("1180000") - Decimal("600000") + Decimal("590000")
    assert kpi["creances"]["nombre_echues"] == 0
    assert kpi["tresorerie"] == Decimal("500000")  # 600 000 encaissés - 100 000 dépensés


def _depense_avec_tva(montant, tva, jour=JOUR):
    return billing.enregistrer_depense(
        finances(), categorie="PEAGES", date_depense=jour, libelle="Péage", montant=Decimal(montant),
        mode=ModePaiement.ESPECES, montant_tva=Decimal(tva),
    )


def test_la_marge_nette_se_calcule_hors_taxes_des_deux_cotes():
    """Audit : la marge retranchait des charges TTC d'un CA HT, donc sous-estimée de la TVA récupérable."""
    emise(prix="1000000", aujourd_hui=date(2026, 9, 10))  # CA HT 1 000 000
    _depense_avec_tva("118000", "18000", jour=date(2026, 9, 5))  # 100 000 HT + 18 000 de TVA récupérable

    kpi = services.indicateurs(*SEPT, aujourd_hui=date(2026, 9, 20))

    assert kpi["chiffre_affaires"] == Decimal("1000000")
    assert kpi["charges"]["total"] == Decimal("118000")  # ce qui a été payé : égal à la page Dépenses
    assert kpi["charges"]["tva_deductible"] == Decimal("18000")
    assert kpi["charges"]["total_ht"] == Decimal("100000")
    assert kpi["marge_nette"] == Decimal("900000")  # et non 882 000


def test_la_marge_nette_est_celle_du_compte_de_resultat_comptable():
    """Même résultat que la comptabilité : la TVA déductible est un actif (445200), pas une charge."""
    from apps.accounting import services as compta

    emise(prix="1000000", aujourd_hui=date(2026, 9, 10))
    _depense_avec_tva("118000", "18000", jour=date(2026, 9, 5))

    resultat = compta.compte_de_resultat(compta.exercice_pour(date(2026, 9, 20)))

    assert services.indicateurs(*SEPT, aujourd_hui=date(2026, 9, 20))["marge_nette"] == resultat["resultat_net"]


def test_sans_tva_la_marge_est_inchangee():
    emise(prix="1000000", aujourd_hui=date(2026, 9, 10))
    _depense("100000", jour=date(2026, 9, 5))

    kpi = services.indicateurs(*SEPT)

    assert kpi["charges"]["tva_deductible"] == Decimal("0")
    assert kpi["marge_nette"] == Decimal("900000")


def test_la_marge_peut_etre_negative():
    _depense("300000", jour=date(2026, 9, 5))

    assert services.indicateurs(*SEPT)["marge_nette"] == Decimal("-300000")


def test_un_utilisateur_de_role_rh_saisit_desormais_comme_la_finance():
    """Retour réunion : la RH fait tout ce que fait la FINANCES, y compris la trésorerie."""
    assert _manuel(acteur=UserFactory(role=Role.RH)).pk


# --- rapprochement bancaire (Lot G) ---


def _ligne_releve(sens=SensMouvement.ENTREE, montant="100000", jour=JOUR, libelle="Virement client",
                   acteur=None, reference=""):
    return services.saisir_ligne_releve(
        acteur or finances(), date_operation=jour, libelle=libelle, montant=Decimal(montant), sens=sens,
        reference=reference,
    )


def test_une_ligne_de_releve_se_saisit_a_la_main():
    ligne = _ligne_releve(reference="REF1")

    assert ligne.pk
    assert ligne.pointee is False
    assert ligne.reference == "REF1"


@pytest.mark.parametrize(
    ("libelle", "montant", "sens", "jour", "message"),
    [
        ("  ", "10", SensMouvement.ENTREE, JOUR, "libellé"),
        ("x", "0", SensMouvement.ENTREE, JOUR, "strictement positif"),
        ("x", "10", "AUTRE", JOUR, "Sens inconnu"),
        ("x", "10", SensMouvement.ENTREE, date(2999, 1, 1), "futur"),
    ],
)
def test_saisie_de_ligne_de_releve_invalide(libelle, montant, sens, jour, message):
    with pytest.raises(MontantInvalide, match=message):
        services.saisir_ligne_releve(
            finances(), date_operation=jour, libelle=libelle, montant=Decimal(montant), sens=sens,
        )


def test_la_saisie_d_une_ligne_de_releve_est_reservee_a_la_saisie_facturation():
    with pytest.raises(ActionFactureNonAutorisee):
        _ligne_releve(acteur=UserFactory(role=Role.PARCAUTO))


def test_les_suggestions_proposent_le_mouvement_banque_de_meme_sens_et_montant_le_plus_proche():
    facture = emise(prix="1000000")
    proche = _reglement(facture, "100000", ModePaiement.VIREMENT, jour=date(2026, 9, 4))
    _reglement(facture, "200000", ModePaiement.VIREMENT, jour=date(2026, 9, 3))  # autre montant
    _depense("100000", ModePaiement.ESPECES, jour=date(2026, 9, 4))  # autre compte (Caisse)
    ligne = _ligne_releve(montant="100000", jour=date(2026, 9, 5))

    suggestions = services.suggestions_pointage(ligne)

    assert len(suggestions) == 1
    assert suggestions[0]["origine"] == "REGLEMENT" and suggestions[0]["pk"] == proche.pk


def test_pointer_associe_la_ligne_au_mouvement_choisi():
    facture = emise(prix="1000000")
    reglement = _reglement(facture, "100000", ModePaiement.VIREMENT)
    ligne = _ligne_releve(montant="100000")

    pointee = services.pointer_ligne_releve(ligne, finances(), origine="REGLEMENT", mouvement_id=reglement.pk)

    assert pointee.pointee is True
    assert pointee.mouvement_origine == "REGLEMENT" and pointee.mouvement_id == reglement.pk


def test_pointer_refuse_un_mouvement_deja_pointe_sur_une_autre_ligne():
    facture = emise(prix="1000000")
    reglement = _reglement(facture, "100000", ModePaiement.VIREMENT)
    premiere = _ligne_releve(montant="100000")
    services.pointer_ligne_releve(premiere, finances(), origine="REGLEMENT", mouvement_id=reglement.pk)
    seconde = _ligne_releve(montant="100000", libelle="Doublon")

    with pytest.raises(MontantInvalide, match="déjà pointé"):
        services.pointer_ligne_releve(seconde, finances(), origine="REGLEMENT", mouvement_id=reglement.pk)


def test_pointer_refuse_une_origine_inconnue():
    ligne = _ligne_releve()
    with pytest.raises(MontantInvalide, match="Origine"):
        services.pointer_ligne_releve(ligne, finances(), origine="AUTRE", mouvement_id=1)


def test_pointer_est_reserve_a_la_saisie_facturation():
    ligne = _ligne_releve()
    with pytest.raises(ActionFactureNonAutorisee):
        services.pointer_ligne_releve(ligne, UserFactory(role=Role.PARCAUTO), origine="MANUEL", mouvement_id=1)


def test_depointer_annule_le_pointage():
    facture = emise(prix="1000000")
    reglement = _reglement(facture, "100000", ModePaiement.VIREMENT)
    ligne = _ligne_releve(montant="100000")
    services.pointer_ligne_releve(ligne, finances(), origine="REGLEMENT", mouvement_id=reglement.pk)

    depointee = services.depointer_ligne_releve(ligne, finances())

    assert depointee.pointee is False
    assert depointee.mouvement_origine == "" and depointee.mouvement_id is None


def test_depointer_est_reserve_a_la_saisie_facturation():
    ligne = _ligne_releve()
    with pytest.raises(ActionFactureNonAutorisee):
        services.depointer_ligne_releve(ligne, UserFactory(role=Role.PARCAUTO))


def test_le_rapprochement_calcule_les_deux_soldes_et_l_ecart_quand_ils_concordent():
    facture = emise(prix="1000000")
    reglement = _reglement(facture, "100000", ModePaiement.VIREMENT, jour=date(2026, 9, 4))
    ligne = _ligne_releve(montant="100000", jour=date(2026, 9, 4))
    services.pointer_ligne_releve(ligne, finances(), origine="REGLEMENT", mouvement_id=reglement.pk)

    etat = services.rapprochement_bancaire(debut=date(2026, 9, 1), fin=date(2026, 9, 30))

    assert etat["solde_releve"] == Decimal("100000")
    assert etat["solde_comptable"] == Decimal("100000")
    assert etat["ecart"] == 0
    assert etat["lignes_non_pointees"] == []
    assert etat["mouvements_non_pointes"] == []


def test_le_rapprochement_signale_un_ecart_quand_une_operation_n_a_pas_ete_saisie():
    facture = emise(prix="1000000")
    _reglement(facture, "100000", ModePaiement.VIREMENT, jour=date(2026, 9, 4))  # jamais pointé
    _ligne_releve(montant="50000", jour=date(2026, 9, 5))  # frais bancaires jamais comptabilisés

    etat = services.rapprochement_bancaire(debut=date(2026, 9, 1), fin=date(2026, 9, 30))

    assert etat["solde_releve"] == Decimal("50000")
    assert etat["solde_comptable"] == Decimal("100000")
    assert etat["ecart"] == Decimal("-50000")
    assert len(etat["lignes_non_pointees"]) == 1
    assert len(etat["mouvements_non_pointes"]) == 1


def test_le_rapprochement_ignore_la_caisse_et_le_mobile_money():
    _depense("20000", ModePaiement.ESPECES, jour=date(2026, 9, 4))
    facture = emise(prix="1000000")
    _reglement(facture, "30000", ModePaiement.WAVE, jour=date(2026, 9, 4))

    etat = services.rapprochement_bancaire(debut=date(2026, 9, 1), fin=date(2026, 9, 30))

    assert etat["solde_comptable"] == 0
    assert etat["mouvements_banque"] == []


# --- pointage : le mouvement doit correspondre à la ligne (audit M10-03) ---


def test_pointer_refuse_un_mouvement_qui_n_existe_pas():
    ligne = _ligne_releve()

    with pytest.raises(MontantInvalide, match="n'existe pas sur le compte Banque"):
        services.pointer_ligne_releve(ligne, finances(), origine="REGLEMENT", mouvement_id=999999)

    ligne.refresh_from_db()
    assert ligne.pointee is False


def test_pointer_refuse_un_mouvement_d_un_autre_compte_que_la_banque():
    depense = _depense("100000", ModePaiement.ESPECES)  # Caisse
    ligne = _ligne_releve(montant="100000", sens=SensMouvement.SORTIE)

    with pytest.raises(MontantInvalide, match="Banque"):
        services.pointer_ligne_releve(ligne, finances(), origine="DEPENSE", mouvement_id=depense.pk)


def test_pointer_refuse_un_montant_different():
    reglement = _reglement(emise(prix="1000000"), "100000", ModePaiement.VIREMENT)
    ligne = _ligne_releve(montant="90000")

    with pytest.raises(MontantInvalide, match="même sens et même montant"):
        services.pointer_ligne_releve(ligne, finances(), origine="REGLEMENT", mouvement_id=reglement.pk)


def test_pointer_refuse_un_sens_different():
    reglement = _reglement(emise(prix="1000000"), "100000", ModePaiement.VIREMENT)  # entrée
    ligne = _ligne_releve(montant="100000", sens=SensMouvement.SORTIE)

    with pytest.raises(MontantInvalide, match="même sens et même montant"):
        services.pointer_ligne_releve(ligne, finances(), origine="REGLEMENT", mouvement_id=reglement.pk)


def test_pointer_refuse_une_ligne_deja_pointee():
    facture = emise(prix="1000000")
    premier = _reglement(facture, "100000", ModePaiement.VIREMENT)
    second = _reglement(facture, "100000", ModePaiement.VIREMENT)
    ligne = _ligne_releve(montant="100000")
    services.pointer_ligne_releve(ligne, finances(), origine="REGLEMENT", mouvement_id=premier.pk)

    with pytest.raises(MontantInvalide, match="déjà pointée"):
        services.pointer_ligne_releve(ligne, finances(), origine="REGLEMENT", mouvement_id=second.pk)

    ligne.refresh_from_db()
    assert ligne.mouvement_id == premier.pk  # le premier pointage n'a pas été écrasé en silence
```

## Étape 7 — Déclarer l'application et migrer

#### `config/settings/base.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/settings/base.py (avant)
+++ config/settings/base.py (après)
@@ -65,4 +65,5 @@
     "apps.billing",
     "apps.finance",
+    "apps.accounting",
 ]
 
```

```bash
python manage.py makemigrations accounting
python manage.py migrate
```

**Résultat attendu :** `Create model Compte`, `Create model EcritureComptable`,
`Create model LigneEcriture`, `Create model ExerciceComptable`, les contraintes, puis
`Applying accounting.0001_initial... OK`.

Puis la migration de données ci-dessus — vous ne pouvez pas la générer avec `makemigrations` (elle ne se
devine pas depuis `models.py`) : créez une migration **vide**, puis complétez-la avec le contenu montré
plus haut :

```bash
python manage.py makemigrations accounting --empty --name plan_comptable_seed
python manage.py migrate
```

**Résultat attendu :** `Applying accounting.0002_plan_comptable_seed... OK`.

## Vérifier le chapitre

```bash
python manage.py check
```

```bash
python -m pytest apps/accounting/tests/test_cloture_resultat.py apps/accounting/tests/test_contre_passation.py apps/accounting/tests/test_models.py apps/accounting/tests/test_receivers.py apps/accounting/tests/test_services.py apps/finance/tests/test_services.py -q --no-cov
```

**Résultat attendu :** `166 passed` (pour les 6 fichier(s) de tests présentés dans ce chapitre).

(Les tests d'écrans de `accounting` sont présentés au chapitre 27.)

Essai dans le shell : une écriture équilibrée sur deux comptes du plan comptable déjà seedé.

```bash
python manage.py shell -c "from datetime import date; from decimal import Decimal; from apps.accounting import services as s; lignes = [s.LigneSaisie(compte='411000', sens='DEBIT', montant=Decimal('118000')), s.LigneSaisie(compte='706100', sens='CREDIT', montant=Decimal('118000'))]; e = s.passer_ecriture(journal='VTE', date_ecriture=date.today(), libelle='Essai', lignes=lignes); print(e.numero, e.lignes.count())"
```

**Résultat attendu :** `VTE-<année>-0001 2` (le numéro commence par le journal Ventes, suivi de
l'année en cours ; l'écriture a bien 2 lignes équilibrées).

## Ce qu'il faut retenir

- Un **seul point d'entrée qui écrit** (`passer_ecriture`) garantit une invariant global (l'équilibre)
  mieux qu'une règle répétée dans chaque appelant.
- **Idempotence par clé d'origine** : indispensable dès qu'un événement peut être rejoué (signal relancé,
  commande de reprise d'historique).
- Une app « qui comptabilise » **s'abonne** aux signaux des autres, elle ne les importe jamais pour agir
  à leur place : `accounting` ne modifie ni `billing` ni `finance`.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 15 : app accounting (plan comptable, écritures équilibrées, comptabilisation automatique)"
```

---

[← Chapitre 14](14-finance.md) · [Sommaire](README.md) · [Chapitre 16 →](16-notifications.md)
