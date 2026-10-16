# Chapitre 2 — Le socle : l'app core

> 36 fichier(s) dans ce chapitre, 2529 lignes de code.

## Ce que vous allez construire

**`core`**, le socle : ce qui est utilisé par *toutes* les autres applications et qui ne dépend d'aucune.
On y trouve :

| Élément | À quoi il sert |
|---|---|
| `BaseModel` | classe mère de tous les modèles métier : dates de création/modification et **suppression logique** |
| `prochain_numero` | distribue des numéros `MIS-2026-0001`, `FACT-2026-0001`… sans doublon |
| `etat_echeance` | dit si un document est valide, à renouveler (30 jours avant) ou expiré |
| `filtrer_par_texte` | recherche qui ignore accents et majuscules (« traore » trouve « Traoré ») |
| `nombre`, `pourcentage_signe` | affichage des nombres à la française |
| `RegistreSections` | un mécanisme pour qu'une fiche affiche des blocs fournis par d'autres apps |
| middlewares | mémoriser la requête courante (pour l'audit) et ajouter les en-têtes de sécurité |

Le socle porte aussi des mécanismes plus récents, présentés avec les fichiers restants de l'étape 6 :

| Élément | À quoi il sert |
|---|---|
| `ErreurMetier` + `ErreurMetierMiddleware` | une règle métier refusée **par une autre app** (budget dépassé, exercice clôturé…) devient un **message** suivi d'un retour à la page précédente, au lieu d'une erreur 500 |
| `medias.py` | les **fichiers téléversés** ne sont jamais servis librement : Django contrôle le rôle, puis demande à Nginx de les envoyer (`X-Accel-Redirect`) |
| `immuable.py` | les **tables append-only** (journal d'audit, mouvements de stock) : un manager qui refuse `update()` / `delete()` en masse, et les triggers PostgreSQL posés par les migrations des chapitres 4 et 12 |
| `xlsx.py` | l'**export Excel** : `reponse_classeur` fabrique un `.xlsx` aux **valeurs brutes** (montants en nombres, dates en dates) ; un texte qui commence par `=` reste du texte, jamais une formule |
| `pdf.py`, `classeurs.py` | le **PDF** d'un rapport, fabriqué par le serveur (ReportLab) à partir de blocs (titres, tableaux, paires libellé/valeur) ; la lecture prudente des **classeurs Excel importés** |
| `documents_pdf.py`, `tasks.py` | les PDF **préparés en tâche de fond** par Celery : la requête rend la main, une page d'attente lance le téléchargement quand le fichier est prêt ; seul le demandeur le télécharge, le fichier est effacé après 24 h |
| `montants.py`, `doublons.py` | deux gardes réutilisées par toutes les apps : un montant saisi en FCFA est **entier** (centimes refusés), et un double clic ne crée pas deux fois la même opération |
| `mesures.py` | les **mesures pour Prometheus** (requêtes, erreurs, temps de réponse par écran, base et cache joignables) servies sur `/metriques/` avec un jeton |
| `statiques.py` | des noms de fichiers statiques **versionnés** en production, pour que les navigateurs ne gardent jamais une ancienne feuille de style |

La recherche texte (`search.py`) transforme chaque champ en texte avant de le comparer : sur PostgreSQL,
`LOWER()` refuse un champ d'adresse IP, et la recherche du journal d'audit en dépend.

## Prérequis

- Chapitre 1 terminé : `python manage.py check` répond « no issues ».

## Notions Django de ce chapitre

- **Modèle** : une classe Python qui décrit une **table** de la base ; chaque attribut est une **colonne**.
  Django génère le SQL (c'est l'**ORM**).
- **Modèle abstrait** (`class Meta: abstract = True`) : un modèle qui n'a *pas* de table ; il sert de
  modèle mère. Les colonnes qu'il déclare sont copiées dans chaque modèle enfant.
- **Manager** (`objects`) : le point d'entrée des requêtes (`Modele.objects.filter(...)`). On peut en
  définir un qui filtre d'office (ici : ne pas montrer les lignes « supprimées »).
- **Migration** : un fichier qui décrit comment faire évoluer la base pour suivre les modèles.
  `makemigrations` l'écrit, `migrate` l'applique.
- **Signal** : une annonce (« la connexion à la base vient d'être créée ») à laquelle une fonction peut
  s'abonner.
- **`AppConfig.ready()`** : code exécuté **une fois au démarrage** de Django.
- **Middleware** : une classe qui voit **chaque requête** avant et après la vue.
- **Test avec pytest** : une fonction `test_…` avec des `assert` ; le marqueur
  `pytest.mark.django_db` autorise l'accès à la base ; chaque test travaille sur une base vide, annulée à la fin.

## Étape 1 — Créer l'application

```bash
mkdir -p apps/core/tests
```

#### Fichiers vides à créer

Ces fichiers n'ont aucun contenu ; ils servent à faire de leur dossier un *paquet Python* (sans eux, `import apps.xxx` échouerait). Créez d'abord les dossiers, puis les fichiers :

```bash
mkdir -p apps\core apps\core\tests
touch apps/core/__init__.py
touch apps/core/tests/__init__.py
```

> Sous PowerShell, `mkdir -p` s'écrit `New-Item -ItemType Directory -Force <dossier>` et `touch fichier` s'écrit `New-Item -ItemType File -Force fichier`. Vous pouvez aussi créer ces fichiers avec votre éditeur.

> **`apps/core/tests/__init__.py` vide** : sans ce fichier, pytest ne saurait pas que `tests` est un
> paquet et les `import` relatifs entre tests échoueraient.

## Étape 2 — Les constantes et le modèle de base

#### `apps/core/constants.py`

*5 lignes* — Constantes métier partagées entre apps.

```python
"""Constantes métier partagées entre apps."""

# Alerte préventive 30 jours avant expiration d'un document réglementaire
# (cahier-des-charges.md:95, glossaire-metier.md:10-11).
DELAI_ALERTE_JOURS = 30
```

Une constante partagée : **30 jours** avant l'expiration d'un document, une alerte préventive part.

#### `apps/core/models.py`

*139 lignes*

```python
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class ActiveManager(models.Manager):
    """Manager par défaut : exclut les enregistrements soft-supprimés.

    ADR-006 (architecture.md:509-514) : tous les querysets doivent filtrer
    ``is_deleted=False``. ``BaseModel.all_objects`` reste disponible pour
    les vues ADMIN ayant besoin de voir les enregistrements supprimés.
    """

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class BaseModel(models.Model):
    """Socle commun à tous les modèles métier.

    Timestamps + soft delete + hooks d'audit — conventions.md:25-26.
    Toute app métier doit hériter de ce modèle plutôt que de
    ``models.Model`` directement.
    """

    created_at = models.DateTimeField(_("créé le"), auto_now_add=True)
    updated_at = models.DateTimeField(_("modifié le"), auto_now=True)

    is_deleted = models.BooleanField(_("supprimé"), default=False)
    deleted_at = models.DateTimeField(_("supprimé le"), null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("supprimé par"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False, deleted_by=None):
        """Suppression logique uniquement — conventions.md §3, §9.

        Aucun ``DELETE`` physique sur les données sensibles : ce modèle
        n'expose la suppression réelle que via :meth:`hard_delete`.
        """
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = deleted_by
        self.save(
            using=using,
            update_fields=["is_deleted", "deleted_at", "deleted_by", "updated_at"],
        )

    def hard_delete(self, using=None, keep_parents=False):
        """Suppression physique réelle — réservée aux migrations/purges RGPD."""
        super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=["is_deleted", "deleted_at", "deleted_by", "updated_at"])


class CompteurNumero(models.Model):
    """Dernier numéro attribué par préfixe et par année (MIS-2026-0007...).

    Table technique (pas de soft delete) : un compteur ne se supprime jamais,
    sous peine de réattribuer un numéro déjà émis.
    """

    prefixe = models.CharField(_("préfixe"), max_length=10)
    annee = models.PositiveSmallIntegerField(_("année"))
    dernier = models.PositiveIntegerField(_("dernier numéro attribué"), default=0)

    class Meta:
        verbose_name = _("compteur de numéros")
        verbose_name_plural = _("compteurs de numéros")
        constraints = [
            models.UniqueConstraint(
                fields=["prefixe", "annee"], name="compteur_numero_unique"
            ),
        ]

    def __str__(self):
        return f"{self.prefixe}-{self.annee} : {self.dernier}"


class StatutDocumentPdf(models.TextChoices):
    EN_ATTENTE = "EN_ATTENTE", _("En préparation")
    PRET = "PRET", _("Prêt")
    ECHEC = "ECHEC", _("Échec")


def _chemin_document_pdf(document, nom):
    # Nom imprévisible (la clé) : le fichier n'est de toute façon servi qu'au demandeur (core.documents_pdf).
    return f"pdf-generes/{document.cle}.pdf"


class DocumentPdf(models.Model):
    """PDF préparé en tâche de fond par Celery (cahier-des-charges.md:294 ; audit TECH-70).

    Table technique, sans suppression logique : un fichier temporaire, réservé au demandeur et effacé après
    ``PDF_CONSERVATION_HEURES`` par les tâches quotidiennes. ``parametres`` porte les données du rapport le temps
    de la génération, puis est vidé.
    """

    cle = models.UUIDField(_("clé"), default=uuid.uuid4, unique=True, editable=False)
    demande_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("demandé par"), on_delete=models.CASCADE, related_name="+"
    )
    titre = models.CharField(_("titre"), max_length=200)
    nom_fichier = models.CharField(_("nom du fichier"), max_length=255)
    url_retour = models.CharField(_("page d'origine"), max_length=500, blank=True)
    parametres = models.JSONField(_("données du rapport"), default=dict, blank=True)
    statut = models.CharField(
        _("statut"), max_length=12, choices=StatutDocumentPdf.choices, default=StatutDocumentPdf.EN_ATTENTE
    )
    fichier = models.FileField(_("fichier"), upload_to=_chemin_document_pdf, blank=True)
    erreur = models.TextField(_("erreur"), blank=True)
    created_at = models.DateTimeField(_("demandé le"), auto_now_add=True)
    termine_le = models.DateTimeField(_("terminé le"), null=True, blank=True)

    class Meta:
        verbose_name = _("document PDF")
        verbose_name_plural = _("documents PDF")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.titre} ({self.get_statut_display()})"
```

À retenir dans ce fichier :

- **Suppression logique.** `delete()` ne supprime rien : il pose `is_deleted = True`, la date et l'auteur.
  Sur des données sensibles (factures, missions, personnel), on ne détruit jamais une ligne : on peut
  ainsi toujours retrouver l'historique.
- **Deux managers.** `objects = ActiveManager()` **cache** les lignes supprimées (c'est ce qu'utilise
  presque tout le code) ; `all_objects` les montre toutes.
- **`CompteurNumero`** : une table technique : pour chaque couple (préfixe, année), le dernier numéro
  attribué. Sa contrainte d'unicité (`UniqueConstraint`) est posée **dans la base** : même si un bug
  du code l'oubliait, la base refuserait un doublon.
- `auto_now_add=True` (posé une fois à la création) et `auto_now=True` (mis à jour à chaque `save()`).

#### `apps/core/services.py`

*83 lignes* — Services transverses.

```python
"""Services transverses."""

import calendar
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from .constants import DELAI_ALERTE_JOURS

from .models import CompteurNumero


@transaction.atomic
def prochain_numero(prefixe: str, annee: int | None = None) -> str:
    """Numéro suivant au format ``PREFIXE-ANNEE-0001`` (remis à 1 chaque année).

    Formats du CDC : ``MIS-2026-XXXX`` (cahier-des-charges.md:129),
    ``OR-2026-XXXX`` (:165), ``FACT-2026-XXXX`` (:183).

    ``get_or_create`` puis verrou de ligne : deux appels simultanés ne
    peuvent pas obtenir le même numéro (verrou effectif sous PostgreSQL).
    """
    annee = annee or timezone.localdate().year
    compteur, _ = CompteurNumero.objects.get_or_create(prefixe=prefixe, annee=annee)
    compteur = CompteurNumero.objects.select_for_update().get(pk=compteur.pk)
    compteur.dernier += 1
    compteur.save(update_fields=["dernier"])
    return f"{prefixe}-{annee}-{compteur.dernier:04d}"


def etat_echeance(
    date_expiration: date | None,
    *,
    aujourd_hui: date | None = None,
    jours: int = DELAI_ALERTE_JOURS,
) -> tuple[str, int | None]:
    """Situation d'un document ou d'une échéance : ``(état, jours restants)``.

    États : ``EXPIRE`` (date dépassée), ``A_RENOUVELER`` (échéance dans ``jours``
    jours ou moins, le jour même compris), ``VALIDE``, ``MANQUANT`` (aucune date).
    Alerte préventive à 30 jours (cahier-des-charges.md:95, glossaire-metier.md:10-11).
    """
    if date_expiration is None:
        return "MANQUANT", None
    restants = (date_expiration - (aujourd_hui or timezone.localdate())).days
    if restants < 0:
        return "EXPIRE", restants
    return ("A_RENOUVELER" if restants <= jours else "VALIDE"), restants


# --- séries mensuelles (graphiques du tableau de bord) ---


def debuts_de_mois(jour: date, nombre: int) -> list[date]:
    """Premiers jours des ``nombre`` derniers mois, celui de ``jour`` compris, du plus ancien au plus récent."""
    resultat = []
    for decalage in range(nombre - 1, -1, -1):
        annee, mois = divmod(jour.year * 12 + jour.month - 1 - decalage, 12)
        resultat.append(date(annee, mois + 1, 1))
    return resultat


def fin_de_mois(debut: date) -> date:
    return debut.replace(day=calendar.monthrange(debut.year, debut.month)[1])


def total_par_mois(queryset, champ_date: str, champ_valeur: str | None = "montant") -> dict[tuple[int, int], Decimal | int]:
    """Somme de ``champ_valeur`` (ou nombre de lignes si ``None``) par mois de ``champ_date``, en une requête.

    Clé : ``(année, mois)``. Les mois sans ligne sont absents : lire avec ``.get(cle, 0)``.
    """
    agregat = Sum(champ_valeur) if champ_valeur else Count("pk")
    lignes = (
        queryset.annotate(_mois=TruncMonth(champ_date))
        .values_list("_mois")
        .annotate(_total=agregat)
        .order_by()
    )
    return {(mois.year, mois.month): total for mois, total in lignes if mois is not None and total is not None}
```

`prochain_numero` est le premier vrai **service** du projet (une fonction qui porte une règle métier).
Deux détails importants :

- `@transaction.atomic` : tout se passe dans une transaction, « tout ou rien ».
- `select_for_update()` : **verrouille la ligne** du compteur pendant l'opération, pour que deux personnes
  qui créent une mission au même instant n'obtiennent pas le même numéro. (SQLite, qu'on utilise en
  développement, ignore ce verrou ; il est effectif avec PostgreSQL en production.)

`etat_echeance` est une **fonction pure** : mêmes entrées, même sortie, aucun accès à la base. Elle
est donc très simple à tester (voir `test_echeance.py`).

## Étape 3 — Recherche, formats et blocs d'affichage

#### `apps/core/search.py`

*74 lignes* — Recherche texte insensible aux accents et à la casse (« traore » trouve « Traoré »).

```python
"""Recherche texte insensible aux accents et à la casse (« traore » trouve « Traoré »).

``icontains`` ne suffit pas : sur SQLite il ne gère la casse que pour l'ASCII (« TRAORÉ » ne
trouve pas « Traoré ») et, partout, « Kone » ne trouve pas « Koné ». On compare donc des
valeurs normalisées (minuscules, sans accents) des deux côtés :

- PostgreSQL : ``LOWER(TRANSLATE(champ, accents, lettres))``, sans extension à installer ;
- SQLite (développement, tests) : fonction ``NORMALISER`` enregistrée à la connexion
  (:func:`enregistrer_fonction_sqlite`).

Le texte cherché est normalisé avec la même table (:func:`normaliser`), pour que les deux
côtés restent identiques. Plusieurs mots : chacun doit se trouver dans au moins un des champs
(« moussa traore » trouve Moussa Traoré).
"""

from django.db.models import CharField, Func, Q, QuerySet, Value
from django.db.models.functions import Cast, Lower

ACCENTS = "àâäáãåçéèêëíìîïñóòôöõúùûüýÿ"
SANS_ACCENT = "aaaaaaceeeeiiiinooooouuuuyy"


def normaliser(texte: str) -> str:
    """Minuscules sans accents, avec la même table que la requête SQL."""
    return (texte or "").lower().translate(str.maketrans(ACCENTS, SANS_ACCENT))


class Normalise(Func):
    """Valeur d'un champ texte normalisée pour la recherche (voir le module)."""

    arity = 1

    def __init__(self, expression):
        super().__init__(expression, output_field=CharField())

    def as_sqlite(self, compiler, connection, **contexte):
        return super().as_sql(compiler, connection, function="NORMALISER", **contexte)

    def as_sql(self, compiler, connection, **contexte):
        # Minuscules d'abord, puis suppression des accents : la table ACCENTS/SANS_ACCENT n'a que
        # des lettres minuscules, donc « TRANSLATE » avant « LOWER » laisserait passer un accent
        # majuscule (« É » → toujours « É » après TRANSLATE, puis « é » après LOWER : l'accent
        # reste). Même ordre que `normaliser()` ci-dessus (``.lower().translate(...)``).
        (expression,) = self.get_source_expressions()
        # Cast en texte : sur PostgreSQL, LOWER() n'accepte pas un champ « inet » (adresse IP du journal d'audit)
        # et la recherche répondait par une erreur 500. Sans effet sur un champ déjà texte.
        minuscule = Lower(Cast(expression, CharField()))
        traduit = Func(minuscule, Value(ACCENTS), Value(SANS_ACCENT), function="TRANSLATE")
        return traduit.as_sql(compiler, connection)


def enregistrer_fonction_sqlite(sender, connection, **kwargs):
    """Signal ``connection_created`` : rend ``NORMALISER`` disponible dans SQLite."""
    if connection.vendor == "sqlite":
        connection.connection.create_function("NORMALISER", 1, normaliser, deterministic=True)


def filtrer_par_texte(queryset: QuerySet, recherche: str, *champs: str) -> QuerySet:
    """Garde les lignes où chaque mot de ``recherche`` figure dans l'un des ``champs``.

    Les champs peuvent traverser des relations (``"client__raison_sociale"``). Une recherche
    vide ne filtre rien. Les ``%`` et ``_`` saisis sont traités comme du texte.
    """
    mots = normaliser(recherche).split()
    if not mots:
        return queryset
    alias = {f"_recherche_{i}": Normalise(champ) for i, champ in enumerate(champs)}
    queryset = queryset.alias(**alias)
    for mot in mots:
        conditions = Q()
        for nom in alias:
            conditions |= Q(**{f"{nom}__contains": mot})
        queryset = queryset.filter(conditions)
    return queryset
```

Pourquoi ne pas simplement écrire `nom__icontains="traore"` ? Parce que ce filtre ne trouve pas
« Traoré » (accent) et, sous SQLite, ne gère pas la casse des lettres accentuées. La solution : comparer
des textes **normalisés** (minuscules, sans accents) des deux côtés. Sous PostgreSQL on utilise
`LOWER(TRANSLATE(...))` ; sous SQLite on **enregistre une fonction SQL** `NORMALISER` à chaque
connexion (c'est le rôle de `apps.py`, plus bas).

#### `apps/core/formats.py`

*31 lignes* — Formatage des nombres pour l'affichage, selon la langue active (français : « 1 500,5 »).

```python
"""Formatage des nombres pour l'affichage, selon la langue active (français : « 1 500,5 »).

À utiliser pour tout nombre écrit dans un message : ``f"{valeur}"`` afficherait un
point décimal (« 1500.50 ») alors que les templates affichent une virgule.

Le formatage de Django (``number_format``) **tronque** les décimales au lieu de les
arrondir (66,67 devient « 66,6 ») : on arrondit donc d'abord, demi supérieur, comme
le filtre de template ``floatformat``.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.utils.formats import number_format


def _arrondi(valeur, decimales: int) -> Decimal:
    return Decimal(str(valeur)).quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)


def nombre(valeur, decimales: int = 0) -> str:
    """Nombre arrondi, avec séparateur de milliers et décimale de la langue active."""
    return number_format(
        _arrondi(valeur, decimales), decimal_pos=decimales, use_l10n=True, force_grouping=True
    )


def pourcentage_signe(valeur, decimales: int = 1) -> str:
    """Pourcentage signé et arrondi : ``+23,3`` / ``-10,0`` / ``0,0`` (sans le symbole %)."""
    arrondi = _arrondi(valeur, decimales)
    signe = "+" if arrondi > 0 else "-" if arrondi < 0 else ""
    return signe + number_format(abs(arrondi), decimal_pos=decimales, use_l10n=True)
```

Pourquoi un module de formats ? Écrire `f"{valeur}"` afficherait « 1500.50 » (point anglais). Ici on
affiche « 1 500,5 ». Django tronque les décimales au lieu de les arrondir ; on arrondit donc d'abord
(demi supérieur).

#### `apps/core/sections.py`

*48 lignes* — Blocs d'affichage enregistrables dans la fiche d'une autre app.

```python
"""Blocs d'affichage enregistrables dans la fiche d'une autre app.

Une fiche (ex. celle d'un camion, app ``fleet``) expose un ``RegistreSections`` ;
les apps situées « en dessous » (ex. ``garage``) y enregistrent un fournisseur de
bloc dans leur ``AppConfig.ready()``. La fiche affiche alors ces blocs sans
jamais importer ces apps (sens des dépendances, architecture.md:161-163).

Un fournisseur reçoit les arguments passés à :meth:`RegistreSections.sections` et
retourne ``{"template": "...", "contexte": {...}}`` ou ``None`` (rien à afficher,
par exemple selon le rôle).
"""

from __future__ import annotations

from typing import Any, Callable

from django.template import TemplateDoesNotExist
from django.template.loader import get_template

Fournisseur = Callable[..., "dict[str, Any] | None"]


class RegistreSections:
    def __init__(self) -> None:
        self._fournisseurs: list[Fournisseur] = []

    def enregistrer(self, fournisseur: Fournisseur) -> None:
        """Ajoute un fournisseur (idempotent : sûr si ``ready()`` est rappelé)."""
        if fournisseur not in self._fournisseurs:
            self._fournisseurs.append(fournisseur)

    def sections(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        """Blocs à afficher, dans l'ordre d'enregistrement.

        Un bloc dont le gabarit n'existe pas est ignoré : la fiche reste affichable même si l'écran de
        l'app qui fournit ce bloc n'est pas (encore) installé.
        """
        blocs = []
        for fournisseur in self._fournisseurs:
            bloc = fournisseur(*args, **kwargs)
            if not bloc:
                continue
            try:
                get_template(bloc["template"])
            except TemplateDoesNotExist:
                continue
            blocs.append(bloc)
        return blocs
```

C'est un **registre**. Exemple concret : la fiche d'un camion (app `fleet`) veut afficher un bloc
« Maintenance » fourni par `garage`. Mais `fleet` ne doit pas *importer* `garage` (les dépendances vont
dans un seul sens). Alors `fleet` crée un `RegistreSections`, et `garage` y **enregistre** un fournisseur
au démarrage. La fiche affiche ce qui s'est inscrit, sans jamais connaître `garage`.

Les blocs dont le gabarit n'existe pas (encore) sont simplement ignorés.

## Étape 4 — Middlewares et formulaires

#### `apps/core/middleware.py`

*124 lignes*

```python
import logging
import threading

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme

from .exceptions import ErreurMetier

logger = logging.getLogger(__name__)

_local = threading.local()


class CurrentRequestMiddleware:
    """Stocke la requête courante en thread-local.

    Permet aux signaux ``post_save``/``post_delete`` (déclenchés hors du
    cycle requête/réponse classique, ex. tâches Celery) d'accéder à
    l'utilisateur, l'IP et le user-agent pour alimenter ``audit_log``
    (ADR-003, architecture.md:488-493) sans coupler chaque modèle au
    framework de requêtes HTTP.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _local.request = request
        try:
            return self.get_response(request)
        finally:
            _local.request = None


class ErreurMetierMiddleware:
    """Filet de sécurité : une erreur métier non interceptée par son écran devient un message.

    L'opération est déjà annulée (les services sont atomiques). L'utilisateur revient à la page d'où
    il vient avec le message de l'erreur, au lieu d'une erreur 500. L'API a son propre gestionnaire
    (``apps.api.exceptions``) et n'est pas concernée.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if not isinstance(exception, ErreurMetier) or request.path.startswith("/api/"):
            return None
        origine = request.META.get("HTTP_REFERER", "")
        if not url_has_allowed_host_and_scheme(
            origine, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            origine = ""
        # Un GET qui échoue ne doit pas se renvoyer vers lui-même (boucle de redirections).
        if request.method == "GET" and (not origine or origine.split("?")[0].endswith(request.path)):
            return None
        logger.warning("Erreur métier non interceptée sur %s : %s", request.path, exception)
        messages.error(request, str(exception))
        return redirect(origine or "/")


def get_current_request():
    return getattr(_local, "request", None)


def get_current_user():
    request = get_current_request()
    if request is not None and request.user.is_authenticated:
        return request.user
    return None


def get_client_ip(request):
    """Adresse du client, sans se laisser tromper par un en-tête forgé.

    ``X-Forwarded-For`` est écrit par le client aussi bien que par les proxys : le lire aveuglément
    permettrait de prendre n'importe quelle adresse (et d'échapper à la limitation d'essais).
    On ne l'utilise donc que si ``TRUSTED_PROXY_COUNT`` proxys de confiance sont déclarés, et on
    prend l'adresse ajoutée par le dernier d'entre eux (en partant de la fin de la liste).
    """
    proxys = getattr(settings, "TRUSTED_PROXY_COUNT", 0)
    if proxys > 0:
        adresses = [
            a.strip() for a in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if a.strip()
        ]
        if len(adresses) >= proxys:
            return adresses[-proxys]
    return request.META.get("REMOTE_ADDR")


class SecurityHeadersMiddleware:
    """Ajoute la politique de sécurité du contenu (CSP) et la politique des fonctions du navigateur.

    Marque aussi ``Cache-Control: private`` toute réponse qui ne dit rien de sa mise en cache : derrière
    Cloudflare (audit TECH-71), une page, un export ou un fichier d'un utilisateur ne doit jamais être gardé
    dans un cache partagé et resservi à un autre. Seuls les fichiers statiques, servis par Nginx, sont publics.

    Les autres en-têtes (HSTS, X-Frame-Options, nosniff, Referrer-Policy) sont posés par Django
    (``SecurityMiddleware``, ``XFrameOptionsMiddleware``) selon les réglages de ``settings``.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        reponse = self.get_response(request)
        nom = (
            "Content-Security-Policy-Report-Only"
            if settings.CSP_REPORT_ONLY
            else "Content-Security-Policy"
        )
        politique = settings.CSP_DOCS if request.path.startswith("/api/v1/docs/") else settings.CSP
        if nom not in reponse:
            reponse[nom] = politique
        if "Permissions-Policy" not in reponse:
            reponse["Permissions-Policy"] = settings.PERMISSIONS_POLICY
        if "Cache-Control" not in reponse:
            reponse["Cache-Control"] = "private"
        return reponse
```

Trois éléments :

- **`CurrentRequestMiddleware`** garde la requête en cours dans une variable propre au fil d'exécution,
  pour que le journal d'audit sache **qui** a fait quoi, depuis **quelle adresse**.
- **`get_client_ip`** : l'adresse du client. Méfiance : l'en-tête `X-Forwarded-For` peut être écrit par
  n'importe quel client. On ne le lit que derrière un nombre déclaré de proxys de confiance
  (`TRUSTED_PROXY_COUNT`), sinon un attaquant pourrait falsifier son adresse et contourner les limites
  d'essais.
- **`SecurityHeadersMiddleware`** ajoute la politique de sécurité du contenu (CSP) et la politique des
  fonctions du navigateur (la caméra reste permise pour le scan des QR).

#### `apps/core/forms.py`

*27 lignes*

```python
from django import forms

CHAMP = (
    "block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm "
    "text-slate-900 shadow-sm placeholder:text-slate-500 focus:border-marque-600 "
    "focus:outline-none focus:ring-2 focus:ring-marque-600/30"
)


def corriger_format_date(widget) -> None:
    """Un ``<input type="date">`` n'accepte que ``AAAA-MM-JJ``.

    En français, Django écrit la valeur initiale en ``JJ/MM/AAAA`` : le navigateur la refuse et le champ
    s'affiche vide (date du jour non préremplie, date existante perdue à la modification).
    """
    if isinstance(widget, forms.DateInput) and widget.input_type == "date":
        widget.format = "%Y-%m-%d"


class StyleTailwindMixin:
    """Applique le style Tailwind commun à tous les champs d'un formulaire."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for champ in self.fields.values():
            champ.widget.attrs.setdefault("class", CHAMP)
            corriger_format_date(champ.widget)
```

Un tout petit mixin : il applique le même style Tailwind à tous les champs d'un formulaire.

## Étape 3 bis — Enregistrer l'application

#### `apps/core/apps.py`

*15 lignes*

```python
from django.apps import AppConfig
from django.db.backends.signals import connection_created


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    label = 'core'

    def ready(self):
        from .search import enregistrer_fonction_sqlite

        connection_created.connect(
            enregistrer_fonction_sqlite, dispatch_uid="core.recherche.sqlite"
        )
```

`ready()` s'exécute au démarrage : elle abonne `enregistrer_fonction_sqlite` au signal
`connection_created`, ce qui rend la fonction `NORMALISER` disponible dans SQLite.

#### `apps/core/admin.py`

*61 lignes* — Règles communes à l'admin Django pour les modèles à suppression logique (``BaseModel``) — audit AUD-04, TECH-57.

```python
"""Règles communes à l'admin Django pour les modèles à suppression logique (``BaseModel``) — audit AUD-04, TECH-57.

L'action « Supprimer la sélection » de l'admin appelle ``QuerySet.delete()`` : un ``DELETE`` physique, qui
contourne la suppression logique de ``BaseModel`` (et, pour les données d'exploitation, les règles métier des
services : contre-passation d'une dépense, statut d'une mission...). Deux comportements, au choix de chaque admin :

- :class:`SansSuppressionAdmin` : données d'exploitation (plein, mission, OR, article, congé) ; rien ne se supprime
  depuis l'admin, une correction passe par l'application.
- :class:`SuppressionLogiqueAdmin` : fiches de référence (client, camion, employé...) ; la suppression marque la
  fiche « supprimée » (réversible), l'admin montre aussi les fiches supprimées et permet de les restaurer — c'est la
  « restauration (administration) » demandée par l'import quand une ligne correspond à une fiche supprimée
  (audit AV-15).
"""

from django.contrib import admin, messages
from django.db import IntegrityError, transaction


class SansSuppressionAdmin(admin.ModelAdmin):
    def has_delete_permission(self, request, obj=None):
        return False


class SuppressionLogiqueAdmin(admin.ModelAdmin):
    actions = ["restaurer"]

    def get_queryset(self, request):
        """Fiches supprimées comprises (filtre « supprimé ») : sans cela, aucune ne pouvait être restaurée."""
        return self.model.all_objects.all()

    def get_list_display(self, request):
        return (*super().get_list_display(request), "is_deleted")

    def get_list_filter(self, request):
        return (*super().get_list_filter(request), "is_deleted")

    def delete_model(self, request, obj):
        obj.delete(deleted_by=request.user)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            obj.delete(deleted_by=request.user)

    @admin.action(description="Restaurer les fiches supprimées sélectionnées")
    def restaurer(self, request, queryset):
        restaurees, refusees = 0, []
        for obj in queryset.filter(is_deleted=True):
            try:
                with transaction.atomic():
                    obj.restore()
            except IntegrityError:  # une fiche active porte déjà le même identifiant (n°, date...)
                refusees.append(str(obj))
            else:
                restaurees += 1
        self.message_user(request, f"{restaurees} fiche(s) restaurée(s).", messages.SUCCESS)
        if refusees:
            self.message_user(
                request,
                "Non restaurée(s), une fiche active porte déjà le même identifiant : " + ", ".join(refusees) + ".",
                messages.ERROR,
            )
```

Rien à administrer pour l'instant (un modèle technique n'a pas d'écran).

## Étape 5 — Déclarer l'application dans les réglages

Modifiez `config/settings/base.py` :

#### `config/settings/base.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/settings/base.py (avant)
+++ config/settings/base.py (après)
@@ -52,4 +52,5 @@
 
 LOCAL_APPS = [
+    "apps.core",
 ]
 
@@ -74,5 +75,7 @@
 MIDDLEWARE = [
     # En premier : chronomètre toute la chaîne et sert /metriques/ à Prometheus (audit TECH-24, apps/core/mesures.py).
+    "apps.core.mesures.MesuresMiddleware",
     "django.middleware.security.SecurityMiddleware",
+    "apps.core.middleware.SecurityHeadersMiddleware",
     "corsheaders.middleware.CorsMiddleware",
     "django.contrib.sessions.middleware.SessionMiddleware",
@@ -82,4 +85,6 @@
     "django.contrib.messages.middleware.MessageMiddleware",
     "django.middleware.clickjacking.XFrameOptionsMiddleware",
+    "apps.core.middleware.CurrentRequestMiddleware",
+    "apps.core.middleware.ErreurMetierMiddleware",
 ]
 
```

#### `config/urls.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/urls.py (avant)
+++ config/urls.py (après)
@@ -10,8 +10,10 @@
 from django.views.generic import RedirectView
 
+from apps.core.medias import MediaProtegeView
 
 urlpatterns = [
     # Les navigateurs (et l'administration Django) réclament /favicon.ico : on renvoie vers l'icône du site.
     path("favicon.ico", RedirectView.as_view(url=settings.STATIC_URL + "img/favicon.png", permanent=True)),
+    path("medias/<path:chemin>", MediaProtegeView.as_view(), name="media"),
     # PDF préparés en tâche de fond (audit TECH-70) : page d'attente, puis téléchargement par le seul demandeur.
     path("admin/", admin.site.urls),
```

Les deux lignes de `MIDDLEWARE` ajoutent nos deux middlewares ; `"apps.core"` déclare l'application.

## Étape 6 — Les fichiers restants (README et tests)

#### `apps/core/README.md`

*52 lignes* — core

```markdown
# core

Rôle : socle transverse (`BaseModel` avec timestamps + soft delete, mixins,
permissions communes). Aucune dépendance vers les autres apps métier —
c'est la racine du graphe de dépendances (architecture.md:99-163).

Entités principales : `BaseModel` (abstrait) — à créer à l'étape 1.

Recherche texte (`search.py`) : `filtrer_par_texte(queryset, texte, *champs)` compare des valeurs
sans accents ni majuscules (« traore » trouve « Traoré », « moussa traore » trouve Moussa
Traoré) ; à utiliser pour tout champ de recherche des listes plutôt que `icontains`. Sur
PostgreSQL : `LOWER(TRANSLATE(...))` sans extension ; sur SQLite : fonction `NORMALISER`
enregistrée à la connexion. `views.PaginationTolerante` : une page inexistante ou illisible
affiche la première ou la dernière page au lieu d'une erreur 404.

Formulaires (`forms.py`) : `StyleTailwindMixin` applique le style commun **et** écrit les champs `type="date"` au
format `AAAA-MM-JJ` que le navigateur exige (en français, Django écrivait `JJ/MM/AAAA` : la date du jour ou la date
existante n'apparaissait pas dans le champ). À utiliser pour tout formulaire.

Graphiques (`graphiques.py`, balises `graphiques`) et séries mensuelles (`services.py` : `debuts_de_mois`,
`total_par_mois`) : voir `apps/dashboard/README.md`.

Rapports imprimables (`rapports.py`, `views.ImpressionListeMixin`, `templates/rapports/`) — cahier-des-charges.md:82,
305 « Export PDF et Excel » : une page HTML autonome (pas `base.html`) avec un bouton « Imprimer » qui ouvre
l'impression du navigateur (Ctrl+P / Enregistrer au format PDF) ; même mécanisme que `billing.facture_print`,
généralisé pour ne pas le récrire à chaque écran. `contexte_rapport()` fournit l'en-tête (entreprise, titre,
généré le/par) ; `ImpressionListeMixin` transforme un `ListView` existant en rapport (mêmes rôles, recherche et
filtres, sans pagination, plafonné à 500 lignes) — voir les `*ImprimerView` de `missions`, `fleet`, `hr`,
`drivers`, `inventory`, `garage`, `fuel`, `customers`, `billing` et `audit`. La trésorerie (`finance`) et le
tableau de bord (`dashboard`) ont chacun leur propre vue, plus riches qu'une simple liste. Un nouveau rapport
de liste : sous-classer le `ListView` existant, ajouter `titre_impression` et `colonnes`, l'inscrire dans
`urls.py`, ajouter le bouton dans le gabarit avec `?{{ request.GET.urlencode }}` pour reprendre les filtres.



En-tête commune (`_entete_impression.html`) : logo (`static/img/logo-emblem.jpg`), raison sociale en bordeaux (`#8b0319`) et filet orange (`#f28a14`) — les couleurs du logo (`frontend/tailwind.config.js`), reprises aussi par le PDF des codes de mission (`apps/missions/documents.py`, ReportLab). Tout nouveau document imprimable doit inclure `_style_impression.html` et `_entete_impression.html` pour rester cohérent avec les autres ; c'est aussi le cas de la facture (`billing.facture_print`), qui les réutilise pour son propre en-tête.

**Fichiers téléversés** (`medias.py`) : jamais servis en libre accès. Une app qui stocke des fichiers déclare le préfixe de son `upload_to` et les rôles autorisés (`enregistrer_media("demandes_depense", permissions.X)` dans `AppConfig.ready()`) ; `/medias/<chemin>` (`MediaProtegeView`) exige la connexion et le rôle, refuse les chemins avec `..`, et ne sert à personne un préfixe non déclaré. Seuls les PDF et images courantes s'affichent dans le navigateur, le reste (HTML, SVG...) est téléchargé. En production (`MEDIA_ACCEL_REDIRECT`), Django répond `X-Accel-Redirect` et Nginx envoie le fichier depuis `/medias-internes/`, emplacement `internal` : Django ne lit pas le fichier. `MEDIA_URL` vaut `medias/`, donc `champ.url` pointe déjà vers cette vue.

**Erreurs métier** (`exceptions.ErreurMetier`, `middleware.ErreurMetierMiddleware`) : une opération peut échouer à cause d'une autre app (plein refusé parce que l'enveloppe de dépense est dépassée) ; l'erreur traverse alors l'écran d'origine, qui ne connaît pas cette famille. Les erreurs métier héritent d'`ErreurMetier` (`BillingError` pour l'instant) et, si l'écran ne les attrape pas, le middleware les transforme en message avec retour à la page d'origine au lieu d'une erreur 500 (l'API a son propre gestionnaire, `apps/api/exceptions.py`). Un GET sans page d'origine n'est pas masqué (pas de boucle de redirections).

**Export Excel** (`xlsx.py`) : `reponse_classeur(nom, feuilles)` fabrique un .xlsx aux **valeurs brutes** (montants en nombres, dates en
dates) ; un texte commençant par `=` reste du texte (pas de formule injectée). `ExportXlsxMixin` fait d'une vue d'impression de liste
(`ImpressionListeMixin`) un export Excel de mêmes droits et filtres : `class XExporterXlsxView(ExportXlsxMixin, XImprimerView)`, avec des
`colonnes` en valeurs brutes. **Tables append-only** (`immuable.py`) : `AppendOnlyQuerySet` (manager qui refuse `update`/`delete` en masse)
et triggers PostgreSQL (journal d'audit, mouvements de stock). La recherche texte (`search.py`) caste les champs en texte : sur PostgreSQL,
`LOWER()` refusait un champ `inet` (adresse IP du journal d'audit).

**Fichiers statiques versionnés** (`statiques.py`) : en production (`config/settings/prod.py`), `StockageStatiqueVersionne` renomme chaque fichier avec une
empreinte de son contenu (`tailwind.41cac255b7fb.css`). Nginx garde `/static/` 30 jours : sans empreinte, un téléphone continuait d'afficher l'ancien
`tailwind.css` avec de nouveaux gabarits, et une classe ajoutée depuis (`grid-cols-6`) manquait — la barre de navigation du chauffeur s'empilait en
colonne. Une référence introuvable dans une feuille de style (polices Font Awesome non copiées) laisse l'URL telle quelle au lieu de faire échouer `collectstatic`.
```

#### `apps/core/exceptions.py`

*7 lignes*

```python
class ErreurMetier(Exception):
    """Base des erreurs métier d'une app dont le message est destiné à l'utilisateur.

    Une opération peut échouer à cause d'une autre app (ex. un plein refusé parce que l'enveloppe de
    dépense est dépassée) : l'erreur traverse alors l'écran d'origine, qui ne connaît pas cette famille
    d'erreurs. ``ErreurMetierMiddleware`` la transforme en message plutôt qu'en erreur 500.
    """
```

#### `apps/core/classeurs.py`

*39 lignes* — Classeurs Excel déposés par les utilisateurs : contrôle avant ouverture — audit AV-16.

```python
"""Classeurs Excel déposés par les utilisateurs : contrôle avant ouverture — audit AV-16.

Un ``.xlsx`` est une archive zip. Une archive piégée (« bombe zip ») pèse quelques ko et se décompresse en
plusieurs Go : ouverte par openpyxl, elle saturerait la mémoire du serveur. On lit donc d'abord le sommaire de
l'archive et on refuse ce qui se décompresserait trop. La taille annoncée suffit : le module ``zipfile`` de
Python ne décompresse jamais un élément au-delà de la taille qu'il annonce.
"""

from __future__ import annotations

import zipfile

from .exceptions import ErreurMetier

# Un classeur de collecte (quelques milliers de lignes au plus) tient en quelques Mo une fois décompressé.
TAILLE_DECOMPRESSEE_MAX = 50 * 1024 * 1024
ELEMENTS_MAX = 500


class ClasseurSuspect(ErreurMetier):
    """Archive refusée avant ouverture : trop volumineuse une fois décompressée, ou trop d'éléments."""


def exiger_classeur_raisonnable(fichier) -> None:
    """Refuse (``ClasseurSuspect``) une archive trop volumineuse une fois décompressée ; remet ``fichier`` au début.
    Un fichier qui n'est pas une archive est laissé au lecteur Excel, qui le refusera avec son propre message."""
    try:
        with zipfile.ZipFile(fichier) as archive:
            elements = archive.infolist()
    except zipfile.BadZipFile:
        return
    finally:
        fichier.seek(0)
    if len(elements) > ELEMENTS_MAX:
        raise ClasseurSuspect("Ce fichier contient trop d'éléments pour un classeur de collecte : il est refusé.")
    if sum(element.file_size for element in elements) > TAILLE_DECOMPRESSEE_MAX:
        raise ClasseurSuspect(
            "Ce fichier est trop volumineux une fois décompressé pour un classeur de collecte : il est refusé."
        )
```

#### `apps/core/documents_pdf.py`

*155 lignes* — PDF préparés en tâche de fond par Celery (cahier-des-charges.md:294 « Tâches async Celery (… PDF) » ; décision

```python
"""PDF préparés en tâche de fond par Celery (cahier-des-charges.md:294 « Tâches async Celery (… PDF) » ; décision
du 13/10/2026, audit TECH-70).

La requête rassemble les données du rapport (droits, filtres : rien ne change pour eux), les range dans un
:class:`~apps.core.models.DocumentPdf` et rend la main tout de suite : la mise en page ReportLab, la partie lente,
se fait dans le processus ``celery worker``. L'utilisateur arrive sur une page « Préparation de votre PDF » qui se
recharge seule et lance le téléchargement dès que le fichier est prêt. Seul le demandeur peut le télécharger ; les
fichiers sont effacés après ``PDF_CONSERVATION_HEURES`` (tâches quotidiennes).

Sans worker (développement, tests : ``PDF_EN_TACHE_DE_FOND`` désactivé), le PDF est rendu dans la requête, comme
avant. Restent toujours générés dans la requête, sans jamais être stockés : les codes d'une mission (un secret) et
l'autorisation de congé (document personnel d'une page).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import TemplateView, View

from . import pdf
from .models import DocumentPdf, StatutDocumentPdf

logger = logging.getLogger(__name__)

# Au-delà, un document toujours « en préparation » signale un worker arrêté : la page cesse de se recharger.
DELAI_ATTENTE_MAX = timedelta(minutes=5)


def _adresse_de_retour(request) -> str:
    """La page d'où vient la demande, sans ``format=pdf`` (sinon « Retour » relancerait la génération)."""
    parametres = request.GET.copy()
    parametres.pop("format", None)
    return f"{request.path}?{parametres.urlencode()}" if parametres else request.path


def telecharger(
    request, *, titre: str, sous_titre: str = "", blocs: list, entreprise: dict, genere_par: str,
    genere_le: datetime, paysage: bool | None = None,
) -> HttpResponse:
    """Réponse à un « Télécharger en PDF » : le fichier lui-même (sans worker), ou la page d'attente du document
    confié à Celery."""
    if not settings.PDF_EN_TACHE_DE_FOND:
        contenu = pdf.generer_pdf(
            titre=titre, sous_titre=sous_titre, blocs=blocs, entreprise=entreprise, genere_par=genere_par,
            genere_le=genere_le, paysage=paysage,
        )
        return pdf.reponse_pdf(contenu, titre)

    from .tasks import generer_document_pdf

    document = DocumentPdf.objects.create(
        demande_par=request.user,
        titre=titre[:200],
        nom_fichier=pdf.nom_fichier_pdf(titre),
        url_retour=_adresse_de_retour(request)[:500],
        parametres={
            "titre": titre, "sous_titre": sous_titre, "blocs": pdf.blocs_vers_donnees(blocs),
            "entreprise": entreprise, "genere_par": genere_par, "genere_le": genere_le.isoformat(),
            "paysage": paysage,
        },
    )
    # Après la validation de la transaction : le worker doit trouver le document en base.
    transaction.on_commit(lambda: generer_document_pdf.delay(document.pk))
    return redirect("document_pdf", cle=document.cle)


def preparer(document_id: int) -> None:
    """Met en page le PDF d'un document en attente et l'enregistre (appelé par la tâche Celery). Rejouer la tâche
    ne refait rien : seul un document encore « en préparation » est traité."""
    document = DocumentPdf.objects.filter(pk=document_id, statut=StatutDocumentPdf.EN_ATTENTE).first()
    if document is None:
        return
    p = document.parametres
    try:
        contenu = pdf.generer_pdf(
            titre=p["titre"], sous_titre=p["sous_titre"], blocs=pdf.blocs_depuis_donnees(p["blocs"]),
            entreprise=p["entreprise"], genere_par=p["genere_par"], genere_le=datetime.fromisoformat(p["genere_le"]),
            paysage=p.get("paysage"),
        )
    except Exception as erreur:  # le demandeur doit l'apprendre, pas attendre indéfiniment
        logger.exception("Échec de la génération du PDF %s", document.pk)
        document.statut = StatutDocumentPdf.ECHEC
        document.erreur = str(erreur)[:500]
    else:
        document.fichier.save(f"{document.cle}.pdf", ContentFile(contenu), save=False)
        document.statut = StatutDocumentPdf.PRET
    document.parametres = {}  # les données du rapport ne servent plus
    document.termine_le = timezone.now()
    document.save()


def purger(*, maintenant: datetime | None = None) -> int:
    """Efface les documents (et leurs fichiers) plus vieux que ``PDF_CONSERVATION_HEURES``. Tâches quotidiennes."""
    limite = (maintenant or timezone.now()) - timedelta(hours=settings.PDF_CONSERVATION_HEURES)
    purges = 0
    for document in DocumentPdf.objects.filter(created_at__lt=limite):
        if document.fichier:
            document.fichier.delete(save=False)
        document.delete()
        purges += 1
    return purges


def _document_du_demandeur(request, cle) -> DocumentPdf:
    """Le document, s'il a été demandé par l'utilisateur connecté : 404 pour tout autre (même l'ADMIN), comme un
    lien qui n'existe pas."""
    return get_object_or_404(DocumentPdf, cle=cle, demande_par=request.user)


class DocumentPdfView(LoginRequiredMixin, TemplateView):
    """Page d'attente : se recharge toutes les 2 secondes, puis lance le téléchargement."""

    template_name = "core/document_pdf.html"

    def get_context_data(self, **kwargs):
        document = _document_du_demandeur(self.request, kwargs["cle"])
        en_attente = document.statut == StatutDocumentPdf.EN_ATTENTE
        return super().get_context_data(
            document=document,
            en_attente=en_attente,
            bloque=en_attente and document.created_at < timezone.now() - DELAI_ATTENTE_MAX,
            heures_conservation=settings.PDF_CONSERVATION_HEURES,
            **kwargs,
        )


class DocumentPdfTelechargerView(LoginRequiredMixin, View):
    http_method_names = ["get"]

    def get(self, request, cle):
        document = _document_du_demandeur(request, cle)
        if document.statut != StatutDocumentPdf.PRET or not document.fichier:
            raise Http404
        if getattr(settings, "MEDIA_ACCEL_REDIRECT", False):
            # Nginx envoie le fichier depuis son emplacement interne (comme les fichiers téléversés, core.medias).
            reponse = HttpResponse(content_type="application/pdf")
            reponse["X-Accel-Redirect"] = "/medias-internes/" + document.fichier.name
        else:
            try:
                reponse = FileResponse(document.fichier.open("rb"), content_type="application/pdf")
            except FileNotFoundError:
                raise Http404
        reponse["Content-Disposition"] = f'attachment; filename="{document.nom_fichier}"'
        reponse["X-Content-Type-Options"] = "nosniff"
        reponse["Cache-Control"] = "private, no-store"
        return reponse
```

#### `apps/core/doublons.py`

*28 lignes* — Protection contre la double saisie (double clic, formulaire renvoyé) — audit AUD-06.

```python
"""Protection contre la double saisie (double clic, formulaire renvoyé) — audit AUD-06.

Le navigateur n'envoie un formulaire qu'une fois (``static/js/app.js``), mais seule une vérification côté
serveur est sûre : un enregistrement **identique** créé il y a moins de :data:`DELAI_DOUBLON` est refusé. Un
second règlement réel du même montant le même jour reste possible une minute plus tard.
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import QuerySet
from django.utils import timezone

from .exceptions import ErreurMetier

DELAI_DOUBLON = timedelta(seconds=60)


def exiger_pas_de_doublon_recent(
    identiques: QuerySet, *, quoi: str, erreur: type[Exception] = ErreurMetier
) -> None:
    """``identiques`` : les enregistrements qui auraient exactement les mêmes valeurs (le modèle a ``created_at``)."""
    if identiques.filter(created_at__gte=timezone.now() - DELAI_DOUBLON).exists():
        raise erreur(
            f"{quoi} identique vient d'être enregistré(e) : saisie en double (double clic) ignorée. "
            "S'il s'agit vraiment d'une seconde opération, recommencez dans une minute."
        )
```

#### `apps/core/graphiques.py`

*139 lignes* — Préparation des graphiques du tableau de bord : des données à ce que le gabarit affiche.

```python
"""Préparation des graphiques du tableau de bord : des données à ce que le gabarit affiche.

Aucun calcul métier ici : on reçoit des séries déjà calculées (par les services des apps) et on
en tire les proportions, les graduations et les libellés. Le rendu est du HTML/CSS (classes
``viz-*`` de ``frontend/input.css``), donc sans script, compatible avec la CSP stricte, et le
texte reste du vrai texte (lisible, sélectionnable, lu par les lecteurs d'écran).

Deux formes seulement, choisies selon le travail à faire :
- ``barres_horizontales`` : comparer des grandeurs par catégorie (statuts, départements, clients) ;
- ``colonnes_groupees`` : suivre 2 ou 3 séries dans le temps (CA, encaissé, charges par mois).
Les deux portent une équivalence en tableau (``tableau``) : rien n'est lisible uniquement à la souris.
"""

from __future__ import annotations

from decimal import Decimal

from .formats import nombre

# Palette catégorielle validée (dataviz/scripts/validate_palette.js, surface #ffffff) : le bleu,
# l'orange et l'aqua, dans cet ordre. Les codes couleur vivent dans frontend/input.css.
MAX_SERIES = 3
GRADUATIONS = 4  # nombre d'intervalles de l'axe vertical

_PAS = (1, 2, 2.5, 5, 10)
_PAS_ENTIERS = (1, 2, 5, 10)  # des comptes (missions...) : pas de graduation à virgule


def _pas_lisible(brut: float, pas=_PAS) -> float:
    """Plus petit pas « rond » (1, 2, 2,5, 5 × 10^n) supérieur ou égal à ``brut``."""
    if brut <= 0:
        return 1
    puissance = 10 ** (len(str(int(brut))) - 1) if brut >= 1 else 1
    for facteur in pas:
        if facteur * puissance >= brut:
            return facteur * puissance
    return 10 * puissance


def compact(valeur) -> str:
    """Valeur d'axe courte : ``0``, ``500 k``, ``1,5 M``, ``2 Md``."""
    valeur = Decimal(valeur)
    for seuil, suffixe in ((Decimal(10) ** 9, "Md"), (Decimal(10) ** 6, "M"), (Decimal(10) ** 3, "k")):
        if abs(valeur) >= seuil:
            reduit = valeur / seuil
            decimales = 0 if reduit == reduit.to_integral_value() else 1
            return f"{nombre(reduit, decimales)} {suffixe}"
    return nombre(valeur)


def barres_horizontales(lignes, *, unite: str = "", maximum=None) -> dict:
    """Barres horizontales, une par catégorie, valeur au bout de la barre.

    ``lignes`` : suite de dicts ``libelle``, ``valeur`` et, facultatif, ``url`` (lien du libellé) et
    ``detail`` (texte secondaire). L'échelle part de 0 ; ``maximum`` la fixe (sinon : la plus grande
    valeur). Retourne ``{"lignes": [...], "unite": ..., "vide": bool}`` ; chaque ligne reçoit
    ``valeur_texte`` et ``largeur`` (pourcentage entier de la piste, 0 pour une valeur nulle).
    """
    lignes = [dict(ligne) for ligne in lignes]
    plus_grand = Decimal(maximum) if maximum is not None else max((Decimal(l["valeur"]) for l in lignes), default=0)
    for ligne in lignes:
        valeur = Decimal(ligne["valeur"])
        ligne["valeur_texte"] = nombre(valeur)
        if valeur > 0 and plus_grand > 0:
            # jamais moins de 1 % : une valeur non nulle doit rester visible
            ligne["largeur"] = max(1, min(100, round(valeur / plus_grand * 100)))
        else:
            ligne["largeur"] = 0
    return {
        "lignes": lignes,
        "unite": unite,
        "vide": not any(Decimal(l["valeur"]) for l in lignes),
    }


def colonnes_groupees(categories, series, *, unite: str = "", entier: bool = False) -> dict:
    """Colonnes groupées : une grappe par catégorie (un mois), une colonne par série.

    ``categories`` : libellés de l'axe horizontal. ``series`` : suite de dicts ``nom`` et ``valeurs``
    (une par catégorie, ≥ 0), 3 au plus (au-delà, regrouper ou faire deux graphiques : la palette
    validée ne garantit pas davantage). La couleur suit la série (rang 1, 2, 3), jamais sa valeur.
    ``entier`` : des comptes, l'axe ne graduera qu'en nombres entiers.

    Retourne :
    - ``graduations`` : de haut en bas, ``etiquette`` et ``position`` (% depuis le bas) ;
    - ``grappes`` : ``libelle`` (+ ``libelle_court`` et ``sous_libelle`` pour l'axe), ``colonnes`` (``serie``, ``rang``, ``hauteur`` %, ``valeur_texte``) et
      ``bord`` (``debut``/``milieu``/``fin`` : de quel côté l'infobulle s'aligne pour ne pas déborder) ;
    - ``legende`` : ``nom`` et ``rang`` ; ``tableau`` : ``entetes`` et ``lignes`` ; ``vide``.
    """
    series = list(series)
    if len(series) > MAX_SERIES:
        raise ValueError(f"{MAX_SERIES} séries au plus par graphique")
    valeurs = [[Decimal(v) for v in s["valeurs"]] for s in series]
    plus_grand = max((v for serie in valeurs for v in serie), default=Decimal(0))
    pas = _pas_lisible(float(plus_grand) / GRADUATIONS, _PAS_ENTIERS if entier else _PAS) if plus_grand > 0 else 1
    haut = Decimal(str(pas)) * GRADUATIONS

    graduations = [
        {"etiquette": compact(haut * i / GRADUATIONS), "position": round(100 * i / GRADUATIONS)}
        for i in range(GRADUATIONS, -1, -1)
    ]

    grappes = []
    dernier = len(categories) - 1
    for i, libelle in enumerate(categories):
        colonnes = []
        for rang, (serie, valeurs_serie) in enumerate(zip(series, valeurs), start=1):
            valeur = valeurs_serie[i]
            colonnes.append({
                "serie": serie["nom"],
                "rang": rang,
                # jamais moins de 1 % : une valeur non nulle doit rester visible
                "hauteur": max(1.0, round(float(valeur / haut * 100), 1)) if valeur > 0 else 0,
                "valeur_texte": nombre(valeur),
            })
        court, _, suffixe = libelle.rpartition(" ")
        grappes.append({
            "libelle": libelle,
            # sur l'axe, le dernier mot (l'année) passe à la ligne : 6 mois tiennent sur un écran de téléphone
            "libelle_court": court or libelle,
            "sous_libelle": suffixe if court else "",
            "colonnes": colonnes,
            "bord": "debut" if i == 0 else "fin" if i == dernier else "milieu",
        })

    return {
        "graduations": graduations,
        "grappes": grappes,
        "legende": [{"nom": s["nom"], "rang": rang} for rang, s in enumerate(series, start=1)],
        "unite": unite,
        "tableau": {
            "entetes": [s["nom"] for s in series],
            "lignes": [
                {"libelle": libelle, "valeurs": [nombre(valeurs[j][i]) for j in range(len(series))]}
                for i, libelle in enumerate(categories)
            ],
        },
        "vide": plus_grand == 0,
    }
```

#### `apps/core/immuable.py`

*69 lignes* — Tables append-only (journal d'audit, journal des mouvements de stock) : protection en profondeur.

```python
"""Tables append-only (journal d'audit, journal des mouvements de stock) : protection en profondeur.

Une ligne de ces journaux ne se modifie ni ne se supprime jamais. ``save()`` / ``delete()`` du modèle
refusent déjà, mais ``QuerySet.update()``, ``QuerySet.delete()`` ou du SQL direct les contournaient
(audit M1-05 / M8-06). Deux protections s'ajoutent :

* :class:`AppendOnlyQuerySet` : le manager du modèle refuse ``update`` / ``delete`` / ``bulk_update`` ;
* un trigger PostgreSQL ``BEFORE UPDATE OR DELETE`` (migrations ``audit.0002`` et ``inventory.0002``) :
  même un accès SQL direct à la base lève une erreur. Sans effet sous SQLite (développement, tests).

Purge légale (rétention du journal d'audit : ≥ 5 ans, README de ``audit``) : elle se fait hors application,
par un administrateur de la base qui désactive explicitement le trigger le temps de l'opération.
"""

from django.db import models

FONCTION = "interdire_modification_append_only"


class AppendOnlyQuerySet(models.QuerySet):
    """QuerySet qui refuse toute modification ou suppression en masse."""

    def update(self, **kwargs):
        raise ValueError(f"{self.model.__name__} est append-only : modification interdite.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValueError(f"{self.model.__name__} est append-only : modification interdite.")

    def delete(self):
        raise ValueError(f"{self.model.__name__} est append-only : suppression interdite.")


def poser_triggers(schema_editor, table: str, *, tolere_detachement_utilisateur: bool = False) -> None:
    """Pose le trigger append-only sur ``table`` (PostgreSQL seulement, sinon ne fait rien).

    ``tolere_detachement_utilisateur`` : le journal d'audit garde ``on_delete=SET_NULL`` sur l'utilisateur ;
    le seul UPDATE admis est donc celui qui passe ``utilisateur_id`` à NULL sans toucher à rien d'autre.
    """
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        f"""
        CREATE OR REPLACE FUNCTION {FONCTION}() RETURNS trigger AS $fn$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION '% est append-only : suppression interdite', TG_TABLE_NAME;
            END IF;
            IF TG_OP = 'UPDATE' AND TG_ARGV[0] = 'detachement' AND NEW.utilisateur_id IS NULL
               AND (to_jsonb(NEW) - 'utilisateur_id') = (to_jsonb(OLD) - 'utilisateur_id') THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION '% est append-only : modification interdite', TG_TABLE_NAME;
        END;
        $fn$ LANGUAGE plpgsql;
        """,
        params=None,  # le « % » de RAISE EXCEPTION n'est pas un paramètre à substituer
    )
    argument = "detachement" if tolere_detachement_utilisateur else "strict"
    schema_editor.execute(f"DROP TRIGGER IF EXISTS append_only ON {table};")
    schema_editor.execute(
        f"CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON {table} "
        f"FOR EACH ROW EXECUTE FUNCTION {FONCTION}('{argument}');"
    )


def retirer_triggers(schema_editor, table: str) -> None:
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(f"DROP TRIGGER IF EXISTS append_only ON {table};")
```

#### `apps/core/medias.py`

*65 lignes* — Fichiers téléversés (devis, justificatifs) : servis par l'application, jamais en accès libre.

```python
"""Fichiers téléversés (devis, justificatifs) : servis par l'application, jamais en accès libre.

Chaque app qui stocke des fichiers déclare le préfixe de son ``upload_to`` et les rôles autorisés à les
lire (``enregistrer_media``). Un fichier dont le préfixe n'est déclaré nulle part n'est servi à personne.
En production, Django ne lit pas le fichier : il répond ``X-Accel-Redirect`` et Nginx l'envoie depuis un
emplacement interne (``MEDIA_ACCEL_REDIRECT``), inaccessible directement depuis l'extérieur.
"""

from __future__ import annotations

import mimetypes
from collections.abc import Iterable

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import SuspiciousFileOperation
from django.http import FileResponse, Http404, HttpResponse
from django.utils._os import safe_join
from django.views import View

_PREFIXES: dict[str, frozenset[str]] = {}

# Types affichés dans le navigateur ; tout le reste (HTML, SVG...) est téléchargé, jamais exécuté.
TYPES_AFFICHABLES = frozenset({"application/pdf", "image/png", "image/jpeg", "image/gif", "image/webp"})


def enregistrer_media(prefixe: str, roles: Iterable[str]) -> None:
    _PREFIXES[prefixe.strip("/") + "/"] = frozenset(roles)


class MediaProtegeView(LoginRequiredMixin, View):
    http_method_names = ["get"]

    def get(self, request, chemin):
        # Le rôle se contrôle sur le préfixe : un « .. » permettrait d'en sortir tout en restant dans MEDIA_ROOT.
        segments = chemin.replace("\\", "/").split("/")
        if "\0" in chemin or any(s in ("", ".", "..") for s in segments):
            raise Http404
        roles = next((r for prefixe, r in _PREFIXES.items() if chemin.startswith(prefixe)), None)
        if roles is None or request.user.role_effectif not in roles:
            raise Http404
        try:
            fichier = safe_join(settings.MEDIA_ROOT, chemin)
        except SuspiciousFileOperation:
            raise Http404
        type_mime = mimetypes.guess_type(fichier)[0] or "application/octet-stream"
        affichable = type_mime in TYPES_AFFICHABLES
        if getattr(settings, "MEDIA_ACCEL_REDIRECT", False):
            reponse = HttpResponse(content_type=type_mime)
            reponse["X-Accel-Redirect"] = "/medias-internes/" + chemin
            reponse["Content-Disposition"] = _disposition(affichable, chemin)
        else:
            try:
                reponse = FileResponse(open(fichier, "rb"), content_type=type_mime)
            except (FileNotFoundError, IsADirectoryError):
                raise Http404
            reponse["Content-Disposition"] = _disposition(affichable, chemin)
        reponse["X-Content-Type-Options"] = "nosniff"
        reponse["Cache-Control"] = "private, no-store"
        return reponse


def _disposition(affichable: bool, chemin: str) -> str:
    nom = chemin.rsplit("/", 1)[-1].replace('"', "")
    return f'{"inline" if affichable else "attachment"}; filename="{nom}"'
```

#### `apps/core/mesures.py`

*244 lignes* — Mesures techniques pour Prometheus (cahier-des-charges.md:256 ; décision du 13/10/2026, audit TECH-24).

```python
"""Mesures techniques pour Prometheus (cahier-des-charges.md:256 ; décision du 13/10/2026, audit TECH-24).

Sans dépendance : l'application écrit elle-même le format texte que lit Prometheus.

- **Requêtes** (:class:`MesuresMiddleware`, en tête de ``MIDDLEWARE``) : nombre par écran, méthode et classe de
  statut (``2xx``... ``5xx``), temps passé par écran, histogramme global des temps de réponse. Les compteurs sont
  dans le cache (Redis en production) : partagés entre les processus Gunicorn, qui sinon compteraient chacun de leur
  côté. Une panne du cache ne bloque jamais une requête : la mesure est simplement perdue.
- **Jauges**, calculées à chaque lecture : base de données et cache joignables, file d'attente Celery, PDF en
  préparation ; d'autres apps ajoutent les leurs (:func:`enregistrer_jauge`, ex. âge de la dernière sauvegarde).

Lecture : ``GET /metriques/`` avec ``Authorization: Bearer <METRIQUES_JETON>``. Sans jeton configuré, l'adresse
n'existe pas ; Nginx la refuse de toute façon depuis l'extérieur (nginx/nginx.conf). Le middleware répond avant
tout le reste : Prometheus appelle ``web:8000`` en HTTP sur le réseau interne, sans passer par le contrôle du nom de
domaine (ALLOWED_HOSTS) ni la redirection HTTPS.
"""

from __future__ import annotations

import hmac
import logging
import time
from collections.abc import Callable
from functools import lru_cache

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import HttpResponse
from django.urls import URLPattern, URLResolver, get_resolver

logger = logging.getLogger(__name__)

CHEMIN = "/metriques/"
PREFIXE = "mesures"
METHODES = ("GET", "POST", "autre")
STATUTS = ("1xx", "2xx", "3xx", "4xx", "5xx")
SEUILS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0)  # secondes ; le CDC vise < 500 ms et < 2 s
SANS_NOM = "sans_nom"  # écran sans nom d'URL
AUCUNE = "aucune"  # adresse inconnue (404 avant tout écran)

_JAUGES: list[tuple[str, str, Callable[[], float | None]]] = []


def enregistrer_jauge(nom: str, aide: str, fonction: Callable[[], float | None]) -> None:
    """Ajoute une jauge, calculée à chaque lecture ; ``None`` = valeur indisponible, la ligne est omise."""
    if all(existant != nom for existant, _, _ in _JAUGES):
        _JAUGES.append((nom, aide, fonction))


# --- compteurs ---


def _incrementer(cle: str, valeur: int = 1) -> None:
    try:
        cache.incr(cle, valeur)
    except ValueError:  # première fois : la clé n'existe pas encore
        cache.add(cle, 0, timeout=None)
        cache.incr(cle, valeur)


def _cle_requetes(vue: str, methode: str, statut: str) -> str:
    return f"{PREFIXE}:req:{vue}:{methode}:{statut}"


def _cle_duree(vue: str) -> str:
    return f"{PREFIXE}:duree_ms:{vue}"


def _cle_seuil(indice: int) -> str:
    return f"{PREFIXE}:seuil:{indice}"


def enregistrer_requete(vue: str, methode: str, code: int, duree: float) -> None:
    methode = methode if methode in METHODES else "autre"
    statut = f"{code // 100}xx" if 100 <= code < 600 else "5xx"
    indice = next((i for i, seuil in enumerate(SEUILS) if duree <= seuil), len(SEUILS))
    try:
        _incrementer(_cle_requetes(vue, methode, statut))
        _incrementer(_cle_duree(vue), round(duree * 1000))
        _incrementer(_cle_seuil(indice))
    except Exception:  # le cache ne doit jamais faire échouer une requête
        logger.debug("Mesure perdue (cache indisponible)", exc_info=True)


@lru_cache(maxsize=1)
def noms_des_vues() -> tuple[str, ...]:
    """Tous les noms d'écran possibles (``espace:nom``) : les compteurs se relisent sans liste des clés existantes."""
    noms = set()

    def parcourir(motifs, prefixe=""):
        for motif in motifs:
            if isinstance(motif, URLResolver):
                parcourir(motif.url_patterns, f"{prefixe}{motif.namespace}:" if motif.namespace else prefixe)
            elif isinstance(motif, URLPattern) and motif.name:
                noms.add(f"{prefixe}{motif.name}")

    parcourir(get_resolver().url_patterns)
    return tuple(sorted(noms)) + (SANS_NOM, AUCUNE)


# --- jauges du socle ---


def _base_disponible() -> float:
    try:
        with connection.cursor() as curseur:
            curseur.execute("SELECT 1")
        return 1
    except Exception:
        return 0


def _cache_disponible() -> float:
    try:
        cache.set(f"{PREFIXE}:sonde", 1, timeout=60)
        return 1 if cache.get(f"{PREFIXE}:sonde") == 1 else 0
    except Exception:
        return 0


def _file_celery() -> float | None:
    """Tâches en attente dans la file Celery par défaut (Redis) ; rien sans courtier (développement)."""
    if settings.CELERY_TASK_ALWAYS_EAGER:
        return None
    try:
        from celery import current_app

        with current_app.connection_for_write() as connexion:
            return connexion.default_channel.client.llen(current_app.conf.task_default_queue or "celery")
    except Exception:
        return None


def _pdf_en_preparation() -> float:
    from .models import DocumentPdf, StatutDocumentPdf

    return DocumentPdf.objects.filter(statut=StatutDocumentPdf.EN_ATTENTE).count()


enregistrer_jauge("erp_base_de_donnees_disponible", "1 si la base de données répond, 0 sinon.", _base_disponible)
enregistrer_jauge("erp_cache_disponible", "1 si le cache (Redis) répond, 0 sinon.", _cache_disponible)
enregistrer_jauge("erp_celery_file_attente", "Tâches Celery en attente d'un worker.", _file_celery)
enregistrer_jauge("erp_pdf_en_preparation", "PDF demandés, pas encore prêts (tâche de fond).", _pdf_en_preparation)


# --- format texte de Prometheus ---


def _echapper(valeur: str) -> str:
    return valeur.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _nombre(valeur: float) -> str:
    return str(int(valeur)) if float(valeur).is_integer() else repr(float(valeur))


def exposition() -> str:
    """Toutes les mesures, au format texte de Prometheus (version 0.0.4)."""
    vues = noms_des_vues()
    cles_requetes = {
        _cle_requetes(v, m, s): (v, m, s) for v in vues for m in METHODES for s in STATUTS
    }
    cles_durees = {_cle_duree(v): v for v in vues}
    cles_seuils = [_cle_seuil(i) for i in range(len(SEUILS) + 1)]
    try:
        valeurs = cache.get_many([*cles_requetes, *cles_durees, *cles_seuils])
    except Exception:
        valeurs = {}

    lignes = [
        "# HELP erp_requetes_total Requêtes traitées, par écran, méthode et classe de statut.",
        "# TYPE erp_requetes_total counter",
    ]
    for cle, (vue, methode, statut) in cles_requetes.items():
        if cle in valeurs:
            lignes.append(
                f'erp_requetes_total{{vue="{_echapper(vue)}",methode="{methode}",statut="{statut}"}} {valeurs[cle]}'
            )

    lignes += [
        "# HELP erp_vue_duree_secondes_total Temps total passé dans chaque écran (moyenne = rapport au nombre de requêtes).",
        "# TYPE erp_vue_duree_secondes_total counter",
    ]
    somme_ms = 0
    for cle, vue in cles_durees.items():
        if cle in valeurs:
            somme_ms += valeurs[cle]
            lignes.append(f'erp_vue_duree_secondes_total{{vue="{_echapper(vue)}"}} {_nombre(valeurs[cle] / 1000)}')

    lignes += [
        "# HELP erp_requete_duree_secondes Temps de réponse des requêtes.",
        "# TYPE erp_requete_duree_secondes histogram",
    ]
    cumul = 0
    for indice, cle in enumerate(cles_seuils):
        cumul += valeurs.get(cle, 0)
        borne = "+Inf" if indice == len(SEUILS) else _nombre(SEUILS[indice])
        lignes.append(f'erp_requete_duree_secondes_bucket{{le="{borne}"}} {cumul}')
    lignes.append(f"erp_requete_duree_secondes_sum {_nombre(somme_ms / 1000)}")
    lignes.append(f"erp_requete_duree_secondes_count {cumul}")

    for nom, aide, fonction in _JAUGES:
        try:
            valeur = fonction()
        except Exception:
            logger.warning("Jauge %s indisponible", nom, exc_info=True)
            valeur = None
        if valeur is not None:
            lignes += [f"# HELP {nom} {aide}", f"# TYPE {nom} gauge", f"{nom} {_nombre(valeur)}"]
    return "\n".join(lignes) + "\n"


def _jeton_valide(request) -> bool:
    attendu = settings.METRIQUES_JETON
    entete = request.META.get("HTTP_AUTHORIZATION", "")
    return bool(attendu) and entete.startswith("Bearer ") and hmac.compare_digest(entete[7:].encode(), attendu.encode())


class MesuresMiddleware:
    """Compte chaque requête et sert ``/metriques/`` ; à placer en premier dans ``MIDDLEWARE``."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == CHEMIN and settings.METRIQUES_JETON:
            if not _jeton_valide(request):
                reponse = HttpResponse("Jeton manquant ou invalide.\n", status=401, content_type="text/plain")
                reponse["WWW-Authenticate"] = 'Bearer realm="metriques"'
                return reponse
            reponse = HttpResponse(exposition(), content_type="text/plain; version=0.0.4; charset=utf-8")
            reponse["Cache-Control"] = "no-store"
            return reponse

        debut = time.perf_counter()
        reponse = self.get_response(request)
        correspondance = getattr(request, "resolver_match", None)
        if correspondance is None:
            vue = AUCUNE
        else:
            vue = correspondance.view_name if correspondance.url_name else SANS_NOM
        enregistrer_requete(vue, request.method, reponse.status_code, time.perf_counter() - debut)
        return reponse
```

#### `apps/core/montants.py`

*22 lignes* — Montants en FCFA saisis : toujours des nombres entiers, le franc CFA ne se divisant pas en centimes dans la

```python
"""Montants en FCFA saisis : toujours des nombres entiers, le franc CFA ne se divisant pas en centimes dans la
pratique (décision du 12/10/2026, avenant-montants-fcfa.md, audit AUD-05).

Un montant saisi avec des décimales est **refusé**, jamais arrondi en silence. Les montants calculés (TVA, TTC,
coût d'un plein = litres × prix) gardent leurs règles d'arrondi propres.
"""

from __future__ import annotations

from decimal import Decimal

from .exceptions import ErreurMetier
from .formats import nombre


def exiger_montant_entier(montant, *, libelle: str = "Le montant", erreur: type[Exception] = ErreurMetier) -> Decimal:
    """Le montant en ``Decimal`` s'il est entier ; sinon ``erreur`` (l'exception métier de l'app appelante, pour
    que son écran affiche le message)."""
    valeur = Decimal(montant)
    if valeur != valeur.to_integral_value():
        raise erreur(f"{libelle} doit être un nombre entier de FCFA, sans centimes ({nombre(valeur, 2)} saisi).")
    return valeur
```

#### `apps/core/pdf.py`

*274 lignes* — PDF des rapports, générés par le serveur (cahier-des-charges.md:305 « Export PDF » ; décision du 12/10/2026 :

```python
"""PDF des rapports, générés par le serveur (cahier-des-charges.md:305 « Export PDF » ; décision du 12/10/2026 :
avenant-export-pdf.md).

Un rapport = des blocs (titres, paragraphes, tableaux, paires libellé/valeur), mis en page par ReportLab
(``platypus``) : texte qui passe à la ligne, tableau découpé sur plusieurs pages avec sa ligne de titres répétée,
paysage automatique pour un tableau large. Chaque page porte l'en-tête de l'entreprise (logo, raison sociale,
adresse, NCC) et un pied « Généré le … par … — Page N », comme les rapports imprimables HTML.
"""

from __future__ import annotations

import io
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
from xml.sax.saxutils import escape

from django.contrib.staticfiles import finders
from django.http import HttpResponse
from django.utils import timezone
from django.utils.text import slugify
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

from .formats import nombre

MARQUE = colors.HexColor("#8B0319")
ACCENT = colors.HexColor("#F28A14")
GRIS = colors.HexColor("#475569")
ENCRE = colors.HexColor("#0f172a")
FOND_TITRES = colors.HexColor("#f1f5f9")
FILET = colors.HexColor("#cbd5e1")
MARGE = 15 * mm
HAUT_ENTETE = 30 * mm
COLONNES_PORTRAIT_MAX = 6  # au-delà, le tableau passe en paysage

STYLE_TEXTE = ParagraphStyle("texte", fontName="Helvetica", fontSize=9, leading=12, textColor=ENCRE)
STYLE_CELLULE = ParagraphStyle("cellule", fontName="Helvetica", fontSize=8, leading=10, textColor=ENCRE)
STYLE_ENTETE = ParagraphStyle("entete", parent=STYLE_CELLULE, fontName="Helvetica-Bold")
STYLE_TITRE = ParagraphStyle("titre", fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=ENCRE)
STYLE_SOUS_TITRE = ParagraphStyle("sous_titre", parent=STYLE_TEXTE, textColor=GRIS)
STYLE_SECTION = ParagraphStyle("section", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=MARQUE,
                               spaceBefore=6, spaceAfter=3)


@dataclass
class Tableau:
    """Tableau d'un rapport. ``alignes_a_droite`` : indices des colonnes de montants. ``total`` : dernière ligne
    mise en gras (totaux)."""

    entetes: list[str]
    lignes: list[list]
    alignes_a_droite: set[int] = field(default_factory=set)
    total: list | None = None
    largeurs: list[float] | None = None  # en proportions (somme libre), sinon parts égales
    sans_entete: bool = False


@dataclass
class Section:
    titre: str


@dataclass
class Texte:
    texte: str
    discret: bool = False


@dataclass
class Rubriques:
    """Paires « libellé : valeur » (résumé, indicateurs)."""

    paires: list[tuple[str, str]]


def _texte(valeur) -> str:
    return escape("" if valeur is None else str(valeur)).replace("\n", "<br/>")


def _tableau(bloc: Tableau, largeur_utile: float) -> LongTable:
    def cellule(valeur, style, colonne):
        style_colonne = ParagraphStyle(f"{style.name}-d", parent=style, alignment=2) if colonne in bloc.alignes_a_droite else style
        return Paragraph(_texte(valeur), style_colonne)

    donnees = [] if bloc.sans_entete else [[cellule(e, STYLE_ENTETE, i) for i, e in enumerate(bloc.entetes)]]
    donnees += [[cellule(v, STYLE_CELLULE, i) for i, v in enumerate(ligne)] for ligne in bloc.lignes]
    if not donnees:
        donnees = [[cellule("", STYLE_CELLULE, i) for i in range(len(bloc.entetes))]]
    if bloc.total is not None:
        donnees.append([cellule(v, STYLE_ENTETE, i) for i, v in enumerate(bloc.total)])
    parts = bloc.largeurs or [1] * len(bloc.entetes)
    largeurs = [largeur_utile * p / sum(parts) for p in parts]
    tableau = LongTable(donnees, colWidths=largeurs, repeatRows=0 if bloc.sans_entete else 1)
    style = [] if bloc.sans_entete else [
        ("BACKGROUND", (0, 0), (-1, 0), FOND_TITRES),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, GRIS),
    ]
    style += [
        ("LINEBELOW", (0, 0 if bloc.sans_entete else 1), (-1, -1), 0.25, FILET),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if bloc.total is not None:
        style += [("LINEABOVE", (0, -1), (-1, -1), 0.8, GRIS), ("BACKGROUND", (0, -1), (-1, -1), FOND_TITRES)]
    tableau.setStyle(TableStyle(style))
    return tableau


def generer_pdf(
    *, titre: str, sous_titre: str = "", blocs: list, entreprise: dict, genere_par: str,
    genere_le: datetime | None = None, paysage: bool | None = None,
) -> bytes:
    """PDF d'un rapport. ``paysage`` : par défaut, si un tableau dépasse ``COLONNES_PORTRAIT_MAX`` colonnes."""
    if paysage is None:
        paysage = any(isinstance(b, Tableau) and len(b.entetes) > COLONNES_PORTRAIT_MAX for b in blocs)
    taille = landscape(A4) if paysage else A4
    largeur, hauteur = taille
    genere_le = timezone.localtime(genere_le or timezone.now())
    tampon = io.BytesIO()
    document = SimpleDocTemplate(
        tampon, pagesize=taille, leftMargin=MARGE, rightMargin=MARGE, topMargin=MARGE + HAUT_ENTETE,
        bottomMargin=MARGE + 8 * mm, title=titre, author=entreprise.get("nom", ""), creator="DEN Source ERP",
    )
    largeur_utile = largeur - 2 * MARGE

    def decor(c, doc):
        c.saveState()
        haut = hauteur - MARGE
        logo = finders.find("img/logo-emblem.jpg")
        if logo:
            c.drawImage(logo, MARGE, haut - 18 * mm, width=18 * mm, height=18 * mm, preserveAspectRatio=True, mask="auto")
        x = MARGE + 22 * mm
        c.setFillColor(MARQUE)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(x, haut - 6 * mm, entreprise.get("nom", ""))
        c.setFillColor(GRIS)
        c.setFont("Helvetica", 8)
        ligne = haut - 11 * mm
        for texte in ((entreprise.get("adresse") or "").replace("\n", " · "), f"NCC {entreprise['ncc']}" if entreprise.get("ncc") else ""):
            if texte:
                c.drawString(x, ligne, texte)
                ligne -= 4 * mm
        c.setStrokeColor(ACCENT)
        c.setLineWidth(1.5)
        c.line(MARGE, haut - 22 * mm, largeur - MARGE, haut - 22 * mm)
        c.setFillColor(GRIS)
        c.setFont("Helvetica", 7.5)
        c.drawString(MARGE, MARGE, f"Généré le {genere_le:%d/%m/%Y à %H:%M} par {genere_par} — DEN Source ERP")
        c.drawRightString(largeur - MARGE, MARGE, f"Page {doc.page}")
        c.restoreState()

    histoire = [Paragraph(_texte(titre), STYLE_TITRE)]
    if sous_titre:
        histoire.append(Paragraph(_texte(sous_titre), STYLE_SOUS_TITRE))
    histoire.append(Spacer(1, 5 * mm))
    for bloc in blocs:
        if isinstance(bloc, Tableau):
            histoire.append(_tableau(bloc, largeur_utile))
            histoire.append(Spacer(1, 4 * mm))
        elif isinstance(bloc, Section):
            histoire.append(Paragraph(_texte(bloc.titre), STYLE_SECTION))
        elif isinstance(bloc, Rubriques):
            if bloc.paires:
                rubriques = Tableau(
                    entetes=["", ""], lignes=[list(p) for p in bloc.paires], alignes_a_droite={1}, largeurs=[2, 1],
                    sans_entete=True,
                )
                table_rubriques = _tableau(rubriques, largeur_utile * 0.6)
                table_rubriques.hAlign = "RIGHT"  # comme les totaux d'une facture
                histoire.append(table_rubriques)
            histoire.append(Spacer(1, 4 * mm))
        elif isinstance(bloc, Texte):
            histoire.append(Paragraph(_texte(bloc.texte), STYLE_SOUS_TITRE if bloc.discret else STYLE_TEXTE))
            histoire.append(Spacer(1, 2 * mm))
    document.build(histoire, onFirstPage=decor, onLaterPages=decor)
    return tampon.getvalue()


def cellule(valeur) -> str:
    """Valeur brute d'une feuille de rapport (celle de l'export Excel) mise en forme pour le PDF : montants avec
    séparateur de milliers (décimales seulement s'il y en a), dates JJ/MM/AAAA, vide pour ``None``."""
    if valeur is None:
        return ""
    if isinstance(valeur, bool):
        return "Oui" if valeur else "Non"
    if isinstance(valeur, (int, float, Decimal)):
        decimale = Decimal(str(valeur))
        return nombre(decimale, 0 if decimale == decimale.to_integral_value() else 2)
    if isinstance(valeur, datetime):
        return f"{timezone.localtime(valeur):%d/%m/%Y %H:%M}" if timezone.is_aware(valeur) else f"{valeur:%d/%m/%Y %H:%M}"
    if isinstance(valeur, date):
        return f"{valeur:%d/%m/%Y}"
    return str(valeur)


def blocs_depuis_feuilles(feuilles: list[dict]) -> list:
    """Feuilles d'un export Excel (``apps.core.xlsx.classeur``) → blocs PDF : mêmes chiffres dans les deux formats.
    Un titre de section par feuille quand il y en a plusieurs (ex. actif et passif du bilan)."""
    blocs = []
    for feuille in feuilles:
        if len(feuilles) > 1:
            blocs.append(Section(feuille["titre"]))
        lignes = feuille["lignes"]
        chiffres = {
            i for i in range(len(feuille["entetes"]))
            if any(isinstance(l[i], (int, float, Decimal)) and not isinstance(l[i], bool) for l in lignes if len(l) > i)
            or (feuille.get("pied") and isinstance(feuille["pied"][i], (int, float, Decimal)))
        }
        blocs.append(Tableau(
            entetes=feuille["entetes"],
            lignes=[[cellule(v) for v in ligne] for ligne in lignes],
            alignes_a_droite=chiffres,
            total=[cellule(v) for v in feuille["pied"]] if feuille.get("pied") else None,
        ))
        if not lignes:
            blocs.append(Texte("Aucune ligne.", discret=True))
    return blocs


def nom_fichier_pdf(titre: str) -> str:
    """``<titre>-<date>.pdf``."""
    return f"{slugify(titre) or 'rapport'}-{timezone.localdate():%Y-%m-%d}.pdf"


def reponse_pdf(contenu: bytes, titre: str) -> HttpResponse:
    """Réponse de téléchargement : ``<titre>-<date>.pdf``."""
    reponse = HttpResponse(contenu, content_type="application/pdf")
    reponse["Content-Disposition"] = f'attachment; filename="{nom_fichier_pdf(titre)}"'
    return reponse


# --- blocs transmis à la tâche Celery (apps.core.documents_pdf, audit TECH-70) ---

_TYPES_DE_BLOCS = {classe.__name__: classe for classe in (Tableau, Section, Texte, Rubriques)}


def _valeur_json(valeur):
    """Contenu d'une cellule en texte : le PDF l'affiche de toute façon avec ``str`` (montant, date...)."""
    return None if valeur is None else str(valeur)


def blocs_vers_donnees(blocs: list) -> list[dict]:
    """Blocs d'un rapport en données JSON, pour la tâche Celery (qui ne transporte que du JSON)."""
    donnees = []
    for bloc in blocs:
        champs = asdict(bloc)
        if isinstance(bloc, Tableau):
            champs["lignes"] = [[_valeur_json(v) for v in ligne] for ligne in bloc.lignes]
            champs["entetes"] = [_valeur_json(e) for e in bloc.entetes]
            champs["total"] = None if bloc.total is None else [_valeur_json(v) for v in bloc.total]
            champs["alignes_a_droite"] = sorted(bloc.alignes_a_droite)
        elif isinstance(bloc, Rubriques):
            champs["paires"] = [[_valeur_json(libelle), _valeur_json(valeur)] for libelle, valeur in bloc.paires]
        donnees.append({"type": type(bloc).__name__, **champs})
    return donnees


def blocs_depuis_donnees(donnees: list[dict]) -> list:
    """Inverse de :func:`blocs_vers_donnees` ; un type inconnu est refusé (``KeyError``)."""
    blocs = []
    for champs in donnees:
        champs = dict(champs)
        classe = _TYPES_DE_BLOCS[champs.pop("type")]
        if classe is Tableau:
            champs["alignes_a_droite"] = set(champs["alignes_a_droite"])
        elif classe is Rubriques:
            champs["paires"] = [tuple(paire) for paire in champs["paires"]]
        blocs.append(classe(**champs))
    return blocs
```

#### `apps/core/rapports.py`

*43 lignes* — Aides communes aux rapports imprimables (trésorerie, tableau de bord, listes, journal d'audit).

```python
"""Aides communes aux rapports imprimables (trésorerie, tableau de bord, listes, journal d'audit).

Chaque rapport est une page HTML autonome (pas `base.html` : pas de menu ni de barre latérale dans le
tirage), avec le bouton « Imprimer » (`data-imprimer`, voir `static/js/app.js`) qui ouvre l'impression du
navigateur — l'utilisateur choisit « Enregistrer au format PDF » ou une imprimante. Même mécanisme que
`billing.facture_print` ; ce module en généralise l'en-tête pour ne pas le récrire à chaque rapport.

Chaque rapport se télécharge aussi en vrai PDF, généré par le serveur (`apps.core.pdf`, bouton « Télécharger
en PDF », `url_pdf`) : décision du 12/10/2026, avenant-export-pdf.md.
"""

from __future__ import annotations

from django.conf import settings
from django.utils import timezone


def contexte_entreprise() -> dict:
    return {
        "nom": settings.ENTREPRISE_NOM,
        "adresse": settings.ENTREPRISE_ADRESSE,
        "ncc": settings.ENTREPRISE_NCC,
    }


def url_pdf(request, chemin: str | None = None) -> str:
    """Adresse du même rapport en PDF (mêmes filtres, ``format=pdf``) : bouton « Télécharger en PDF ». ``chemin`` :
    une autre vue que la page courante (ex. l'export Excel d'un rapport comptable, qui sait aussi rendre le PDF)."""
    parametres = request.GET.copy()
    parametres["format"] = "pdf"
    return f"{chemin or request.path}?{parametres.urlencode()}"


def contexte_rapport(request, *, titre: str, sous_titre: str = "") -> dict:
    """Contexte commun à tout gabarit de `templates/rapports/` : en-tête entreprise, titre, généré le/par."""
    utilisateur = request.user
    return {
        "entreprise": contexte_entreprise(),
        "titre": titre,
        "sous_titre": sous_titre,
        "genere_par": utilisateur.get_full_name() or utilisateur.get_username(),
        "genere_le": timezone.now(),
    }
```

#### `apps/core/statiques.py`

*21 lignes* — Fichiers statiques à noms versionnés, tolérants aux ressources absentes.

```python
"""Fichiers statiques à noms versionnés, tolérants aux ressources absentes.

``ManifestStaticFilesStorage`` renomme chaque fichier avec une empreinte de son contenu
(``tailwind.css`` → ``tailwind.4f2a9c1b7e3d.css``) : le nom change dès que le contenu change, donc un cache à longue durée
(Nginx : 30 jours) ne sert jamais un fichier périmé. Il refuse pourtant de collecter un fichier qui en cite un autre
introuvable : la feuille de style de Font Awesome cite des polices (``fa-brands-400.woff2``…) que ``frontend/vendor.js``
ne copie pas, car l'interface n'utilise que les icônes « solid » et « regular ». Ici, une référence introuvable reste
telle quelle au lieu de faire échouer ``collectstatic`` (et donc le démarrage du conteneur).
"""

from django.contrib.staticfiles.storage import ManifestStaticFilesStorage


class StockageStatiqueVersionne(ManifestStaticFilesStorage):
    manifest_strict = False  # une page qui cite un fichier absent du manifeste garde son URL au lieu de lever une erreur

    def hashed_name(self, name, content=None, filename=None):
        try:
            return super().hashed_name(name, content, filename)
        except ValueError:
            return name
```

#### `apps/core/tasks.py`

*13 lignes* — Tâches Celery du socle commun.

```python
"""Tâches Celery du socle commun."""

from __future__ import annotations

from celery import shared_task

from . import documents_pdf


@shared_task
def generer_document_pdf(document_id: int) -> None:
    """Met en page un PDF demandé depuis un écran (audit TECH-70) — hors du chemin de la requête."""
    documents_pdf.preparer(document_id)
```

#### `apps/core/xlsx.py`

*151 lignes* — Export Excel (.xlsx) des listes et des rapports.

```python
"""Export Excel (.xlsx) des listes et des rapports.

Le même contenu que l'impression, mais exploitable dans un tableur : les montants sont de vrais nombres
(totaux, tris et filtres fonctionnent) et les dates de vraies dates, pas du texte formaté.

Une feuille = un dictionnaire ``{"titre", "sous_titre", "entetes", "lignes", "pied"}`` (``sous_titre`` et ``pied``
facultatifs ; ``pied`` est une ligne de totaux en gras). :func:`reponse_classeur` en fait un téléchargement.

Un texte qui commence par ``=`` est écrit comme du texte, jamais comme une formule : un libellé saisi par un
utilisateur ne doit pas pouvoir s'exécuter à l'ouverture du fichier.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

TYPE_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FORMAT_MONTANT = "#,##0.00"
FORMAT_DATE = "dd/mm/yyyy"
FORMAT_DATE_HEURE = "dd/mm/yyyy hh:mm"
LARGEUR_MAX = 60
INTERDITS_TITRE = set("[]:*?/\\")


def _ecrire(cellule, valeur) -> None:
    if isinstance(valeur, bool):
        cellule.value = "Oui" if valeur else "Non"
    elif isinstance(valeur, Decimal):
        cellule.value = float(valeur)
        cellule.number_format = FORMAT_MONTANT
    elif isinstance(valeur, datetime):
        if timezone.is_aware(valeur):
            valeur = timezone.localtime(valeur).replace(tzinfo=None)
        cellule.value = valeur
        cellule.number_format = FORMAT_DATE_HEURE
    elif isinstance(valeur, date):
        cellule.value = valeur
        cellule.number_format = FORMAT_DATE
    elif isinstance(valeur, str):
        cellule.value = valeur
        if valeur.startswith("="):
            cellule.data_type = "s"  # du texte, pas une formule
    else:
        cellule.value = valeur


def _titre_feuille(titre: str, deja: set[str]) -> str:
    propre = "".join("-" if c in INTERDITS_TITRE else c for c in titre).strip()[:31] or "Feuille"
    candidat, n = propre, 2
    while candidat.lower() in deja:
        suffixe = f" ({n})"
        candidat = propre[: 31 - len(suffixe)] + suffixe
        n += 1
    deja.add(candidat.lower())
    return candidat


def classeur(feuilles: list[dict]) -> bytes:
    """Classeur Excel (octets) : une feuille par élément de ``feuilles``."""
    wb = Workbook()
    wb.remove(wb.active)
    noms: set[str] = set()
    gras = Font(bold=True)
    fond_entete = PatternFill("solid", fgColor="E2E8F0")
    for donnees in feuilles:
        feuille = wb.create_sheet(_titre_feuille(donnees["titre"], noms))
        ligne = 1
        feuille.cell(row=ligne, column=1, value=donnees["titre"]).font = Font(bold=True, size=14)
        ligne += 1
        if donnees.get("sous_titre"):
            _ecrire(feuille.cell(row=ligne, column=1), donnees["sous_titre"])
            ligne += 1
        ligne += 1
        ligne_entetes = ligne
        for colonne, entete in enumerate(donnees["entetes"], start=1):
            cellule = feuille.cell(row=ligne, column=colonne, value=entete)
            cellule.font, cellule.fill = gras, fond_entete
            cellule.alignment = Alignment(wrap_text=True, vertical="center")
        for valeurs in donnees["lignes"]:
            ligne += 1
            for colonne, valeur in enumerate(valeurs, start=1):
                _ecrire(feuille.cell(row=ligne, column=colonne), valeur)
        if donnees.get("pied"):
            ligne += 1
            for colonne, valeur in enumerate(donnees["pied"], start=1):
                cellule = feuille.cell(row=ligne, column=colonne)
                _ecrire(cellule, valeur)
                cellule.font = gras
        feuille.freeze_panes = feuille.cell(row=ligne_entetes + 1, column=1)
        for colonne, entete in enumerate(donnees["entetes"], start=1):
            plus_long = max(
                [len(str(entete))]
                + [len(str(v)) for v in (ligne_[colonne - 1] for ligne_ in donnees["lignes"] if len(ligne_) >= colonne)]
            )
            feuille.column_dimensions[get_column_letter(colonne)].width = min(max(plus_long + 2, 10), LARGEUR_MAX)
    tampon = BytesIO()
    wb.save(tampon)
    return tampon.getvalue()


def reponse_classeur(nom_fichier: str, feuilles: list[dict]) -> HttpResponse:
    """Téléchargement d'un classeur ; ``nom_fichier`` sans extension (la date du jour y est ajoutée)."""
    reponse = HttpResponse(classeur(feuilles), content_type=TYPE_XLSX)
    reponse["Content-Disposition"] = f'attachment; filename="{nom_fichier}_{timezone.localdate():%Y-%m-%d}.xlsx"'
    return reponse


def reponse_rapport(request, nom_fichier: str, feuilles: list[dict], *, titre: str, sous_titre: str = ""):
    """Classeur Excel, ou ``?format=pdf`` : le même rapport en PDF, construit sur les mêmes feuilles (mêmes
    chiffres dans les deux formats ; avenant-export-pdf.md)."""
    if request.GET.get("format") != "pdf":
        return reponse_classeur(nom_fichier, feuilles)
    from . import documents_pdf, pdf
    from .rapports import contexte_rapport

    contexte = contexte_rapport(request, titre=titre, sous_titre=sous_titre)
    return documents_pdf.telecharger(
        request, titre=titre, sous_titre=sous_titre, blocs=pdf.blocs_depuis_feuilles(feuilles),
        entreprise=contexte["entreprise"], genere_par=contexte["genere_par"], genere_le=contexte["genere_le"],
    )


class ExportXlsxMixin:
    """Fait d'une vue d'impression de liste (:class:`apps.core.views.ImpressionListeMixin`) un export Excel.

    ``class XExporterXlsxView(ExportXlsxMixin, XImprimerView)`` : mêmes droits, mêmes filtres, mêmes lignes
    que l'impression. ``colonnes`` y est redéclaré avec des **valeurs brutes** (nombres, dates) au lieu du texte
    formaté de l'impression ; ``nom_fichier`` donne le nom du téléchargement.
    """

    nom_fichier = "export"
    limite_impression = 10000  # un tableur supporte bien plus qu'une page imprimée

    def render_to_response(self, context, **kwargs):
        feuille = {
            "titre": self.get_titre_impression(),
            "sous_titre": self.get_sous_titre_impression(),
            "entetes": context["entetes"],
            "lignes": context["lignes"],
        }
        if context.get("tronque"):
            feuille["pied"] = [f"Export limité aux {self.limite_impression} premières lignes : affinez les filtres."]
        return reponse_classeur(self.nom_fichier, [feuille])
```

#### `apps/core/tests/test_compatibilite_postgresql.py`

*30 lignes* — Garde-fous pour PostgreSQL (la production), que la suite lancée sur SQLite ne voit pas.

```python
"""Garde-fous pour PostgreSQL (la production), que la suite lancée sur SQLite ne voit pas.

``select_for_update()`` combiné à ``select_related`` verrouille aussi les tables jointes ; PostgreSQL refuse de
verrouiller le côté facultatif d'une jointure (« FOR UPDATE cannot be applied to the nullable side of an outer
join ») alors que SQLite ne verrouille rien : la sortie du personnel plantait en production (erreur 500). Il faut
``select_for_update(of=("self",))``.
"""

import re
from pathlib import Path

APPS = Path(__file__).resolve().parents[2]

# Une même expression (sans point-virgule ni ligne vide) qui verrouille sans « of= » et charge une relation.
VERROU_AVEC_JOINTURE = re.compile(
    r"select_for_update\(\)[^;\n]*select_related|select_related\([^)]*\)[^;\n]*select_for_update\(\)"
)


def test_aucun_verrou_sans_of_sur_une_requete_avec_jointure():
    fautifs = []
    for fichier in APPS.rglob("*.py"):
        if "tests" in fichier.parts or "migrations" in fichier.parts:
            continue
        texte = fichier.read_text(encoding="utf-8")
        for correspondance in VERROU_AVEC_JOINTURE.finditer(texte):
            ligne = texte.count("\n", 0, correspondance.start()) + 1
            fautifs.append(f"{fichier.relative_to(APPS.parent)}:{ligne}")

    assert not fautifs, "select_for_update(of=(\"self\",)) attendu : " + ", ".join(fautifs)
```

#### `apps/core/tests/test_echeance.py`

*38 lignes* — Calcul d'échéance partagé — alerte à 30 jours (cahier-des-charges.md:95).

```python
"""Calcul d'échéance partagé — alerte à 30 jours (cahier-des-charges.md:95)."""

from datetime import date

import pytest

from apps.core.services import etat_echeance

AUJOURDHUI = date(2026, 9, 20)


@pytest.mark.parametrize(
    ("expiration", "etat", "restants"),
    [
        (None, "MANQUANT", None),
        (date(2026, 9, 19), "EXPIRE", -1),  # hier : expiré
        (date(2026, 8, 1), "EXPIRE", -50),
        (date(2026, 9, 20), "A_RENOUVELER", 0),  # aujourd'hui : encore valable, à renouveler
        (date(2026, 10, 20), "A_RENOUVELER", 30),  # 30 jours : alerte
        (date(2026, 10, 21), "VALIDE", 31),  # 31 jours : pas encore
        (date(2030, 1, 1), "VALIDE", 1199),
    ],
)
def test_etat_echeance_selon_les_jours_restants(expiration, etat, restants):
    assert etat_echeance(expiration, aujourd_hui=AUJOURDHUI) == (etat, restants)


def test_le_delai_d_alerte_est_parametrable():
    assert etat_echeance(date(2026, 10, 20), aujourd_hui=AUJOURDHUI, jours=15) == ("VALIDE", 30)
    assert etat_echeance(date(2026, 10, 5), aujourd_hui=AUJOURDHUI, jours=15) == ("A_RENOUVELER", 15)


def test_par_defaut_la_date_du_jour_est_utilisee():
    from django.utils import timezone

    aujourdhui = timezone.localdate()

    assert etat_echeance(aujourdhui) == ("A_RENOUVELER", 0)
```

#### `apps/core/tests/test_formats.py`

*43 lignes*

```python
from decimal import Decimal

import pytest

from apps.core.formats import nombre, pourcentage_signe


@pytest.mark.parametrize(
    ("valeur", "decimales", "attendu"),
    [
        (Decimal("1500"), 0, "1 500"),
        (Decimal("1500.5"), 1, "1 500,5"),
        (Decimal("38500.00"), 0, "38 500"),
        (Decimal("30"), 1, "30,0"),
        (0, 0, "0"),
        (Decimal("100.33"), 2, "100,33"),
        (Decimal("1500.5"), 0, "1 501"),  # arrondi au demi supérieur, pas tronqué
        (Decimal("66.666"), 1, "66,7"),
        (Decimal("0.005"), 2, "0,01"),
    ],
)
def test_nombre_utilise_la_virgule_et_le_separateur_de_milliers_francais(valeur, decimales, attendu):
    assert nombre(valeur, decimales).replace("\xa0", " ").replace(" ", " ") == attendu


@pytest.mark.parametrize(
    ("valeur", "attendu"),
    [
        (Decimal("23.33"), "+23,3"),
        (Decimal("-9.99"), "-10,0"),
        (Decimal("0"), "0,0"),
        (Decimal("60.00"), "+60,0"),
        (-5, "-5,0"),
        (Decimal("66.67"), "+66,7"),  # arrondi, pas tronqué
        (Decimal("-0.04"), "0,0"),  # arrondi à zéro : pas de signe
    ],
)
def test_pourcentage_signe(valeur, attendu):
    assert pourcentage_signe(valeur) == attendu


def test_pourcentage_signe_accepte_le_nombre_de_decimales():
    assert pourcentage_signe(Decimal("66.666"), decimales=2) == "+66,67"
```

#### `apps/core/tests/test_graphiques.py`

*143 lignes* — Préparation des graphiques : proportions, graduations lisibles, garde-fous.

```python
"""Préparation des graphiques : proportions, graduations lisibles, garde-fous."""

from decimal import Decimal

import pytest
from django.template import Context, Template

from apps.core import graphiques


def _texte(valeur: str) -> str:
    return valeur.replace(" ", " ").replace("\xa0", " ")


# --- barres horizontales ---


def test_les_barres_sont_proportionnelles_a_la_plus_grande_valeur():
    g = graphiques.barres_horizontales([
        {"libelle": "A", "valeur": 200}, {"libelle": "B", "valeur": 50}, {"libelle": "C", "valeur": 0},
    ])

    assert [ligne["largeur"] for ligne in g["lignes"]] == [100, 25, 0]
    assert [ligne["valeur_texte"] for ligne in g["lignes"]] == ["200", "50", "0"]
    assert g["vide"] is False


def test_une_petite_valeur_non_nulle_reste_visible():
    g = graphiques.barres_horizontales([{"libelle": "Gros", "valeur": 1_000_000}, {"libelle": "Petit", "valeur": 1}])

    assert g["lignes"][1]["largeur"] == 1


def test_le_maximum_impose_fixe_l_echelle():
    g = graphiques.barres_horizontales([{"libelle": "A", "valeur": 30}], maximum=120)

    assert g["lignes"][0]["largeur"] == 25


def test_sans_valeur_le_graphique_est_vide():
    assert graphiques.barres_horizontales([])["vide"] is True
    assert graphiques.barres_horizontales([{"libelle": "A", "valeur": 0}])["vide"] is True


def test_les_valeurs_decimales_et_les_details_sont_conserves():
    g = graphiques.barres_horizontales(
        [{"libelle": "Alpha", "valeur": Decimal("1250000"), "url": "/x/", "detail": "3 missions"}], unite="FCFA"
    )

    ligne = g["lignes"][0]
    assert _texte(ligne["valeur_texte"]) == "1 250 000"
    assert (ligne["url"], ligne["detail"], g["unite"]) == ("/x/", "3 missions", "FCFA")


# --- colonnes groupées ---


def test_les_graduations_sont_des_nombres_ronds_et_couvrent_la_plus_grande_valeur():
    g = graphiques.colonnes_groupees(["a", "b"], [{"nom": "CA", "valeurs": [Decimal("1180000"), Decimal("300000")]}])

    etiquettes = [t["etiquette"] for t in g["graduations"]]
    assert etiquettes == ["2 M", "1,5 M", "1 M", "500 k", "0"]
    assert [t["position"] for t in g["graduations"]] == [100, 75, 50, 25, 0]
    assert g["grappes"][0]["colonnes"][0]["hauteur"] == 59.0  # 1 180 000 / 2 000 000


@pytest.mark.parametrize("plus_grand, attendu", [
    (Decimal("1000"), "1 k"),
    (Decimal("7"), "8"),
    (Decimal("95000000"), "100 M"),
    (Decimal("3000000000"), "4 Md"),
])
def test_le_haut_de_l_axe_est_un_pas_rond(plus_grand, attendu):
    g = graphiques.colonnes_groupees(["m"], [{"nom": "S", "valeurs": [plus_grand]}])

    assert _texte(g["graduations"][0]["etiquette"]) == attendu


def test_chaque_serie_garde_son_rang_de_couleur():
    g = graphiques.colonnes_groupees(
        ["m1", "m2"],
        [{"nom": "CA", "valeurs": [10, 20]}, {"nom": "Encaissé", "valeurs": [5, 0]}, {"nom": "Charges", "valeurs": [1, 2]}],
        unite="FCFA",
    )

    assert [(e["nom"], e["rang"]) for e in g["legende"]] == [("CA", 1), ("Encaissé", 2), ("Charges", 3)]
    assert [c["rang"] for c in g["grappes"][0]["colonnes"]] == [1, 2, 3]
    assert g["grappes"][1]["colonnes"][1]["hauteur"] == 0  # valeur nulle : pas de colonne


def test_l_infobulle_s_aligne_sur_les_bords_pour_ne_pas_deborder():
    g = graphiques.colonnes_groupees(["a", "b", "c"], [{"nom": "S", "valeurs": [1, 2, 3]}])

    assert [grappe["bord"] for grappe in g["grappes"]] == ["debut", "milieu", "fin"]


def test_le_tableau_reprend_toutes_les_valeurs():
    g = graphiques.colonnes_groupees(["janv.", "févr."], [{"nom": "CA", "valeurs": [1000, 2500]}, {"nom": "Charges", "valeurs": [0, 400]}])

    assert g["tableau"]["entetes"] == ["CA", "Charges"]
    assert [(l["libelle"], [_texte(v) for v in l["valeurs"]]) for l in g["tableau"]["lignes"]] == [
        ("janv.", ["1 000", "0"]), ("févr.", ["2 500", "400"]),
    ]


def test_au_dela_de_trois_series_le_graphique_est_refuse():
    with pytest.raises(ValueError):
        graphiques.colonnes_groupees(["m"], [{"nom": str(i), "valeurs": [1]} for i in range(4)])


def test_sans_aucune_valeur_le_graphique_est_vide():
    assert graphiques.colonnes_groupees(["m"], [{"nom": "CA", "valeurs": [0]}])["vide"] is True


# --- rendu ---


def test_le_rendu_des_colonnes_offre_legende_infobulle_et_tableau():
    g = graphiques.colonnes_groupees(
        ["janv.", "févr."], [{"nom": "CA", "valeurs": [1000, 2000]}, {"nom": "Charges", "valeurs": [500, 100]}], unite="FCFA"
    )

    html = Template('{% load graphiques %}{% graphique_colonnes g "test" %}').render(Context({"g": g}))

    assert 'aria-label="Légende"' in html and "viz-s2" in html
    assert 'role="tooltip"' in html and 'tabindex="0"' in html  # même contenu au clavier qu'à la souris
    assert 'id="test-tableau"' in html and "Voir en tableau" in html


def test_le_rendu_echappe_les_libelles():
    g = graphiques.barres_horizontales([{"libelle": "<script>alert(1)</script>", "valeur": 3}])

    html = Template("{% load graphiques %}{% graphique_barres g %}").render(Context({"g": g}))

    assert "<script>" not in html and "&lt;script&gt;" in html


def test_un_graphique_vide_affiche_le_message_sans_barre():
    g = graphiques.barres_horizontales([])

    html = Template('{% load graphiques %}{% graphique_barres g "Rien à montrer." %}').render(Context({"g": g}))

    assert "Rien à montrer." in html and "viz-barre" not in html
```

#### `apps/core/tests/test_models.py`

*72 lignes* — Tests du mixin BaseModel — conventions.md §7.

```python
"""Tests du mixin BaseModel — conventions.md §7.

BaseModel est abstrait et n'a pas encore de modèle concret réel (arrivera
avec fleet/hr à l'étape 2). On le teste via un modèle jetable créé pour la
durée du test (``isolate_apps`` + ``schema_editor``), pattern recommandé
par Django pour tester des mixins de modèles.
"""

from django.db import connection, models
from django.test import TransactionTestCase
from django.test.utils import isolate_apps

from apps.core.models import BaseModel


@isolate_apps("apps.core")
class BaseModelSoftDeleteTests(TransactionTestCase):
    """TransactionTestCase (pas TestCase) : la création de table via
    schema_editor est incompatible avec le bloc atomic ouvert par
    TestCase.setUpClass sous SQLite."""
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        class Gadget(BaseModel):
            nom = models.CharField(max_length=50)

            class Meta:
                app_label = "core"

        cls.Gadget = Gadget
        with connection.schema_editor() as editor:
            editor.create_model(cls.Gadget)

    @classmethod
    def tearDownClass(cls):
        with connection.schema_editor() as editor:
            editor.delete_model(cls.Gadget)
        super().tearDownClass()

    def test_default_manager_excludes_soft_deleted_records(self):
        gadget = self.Gadget.objects.create(nom="Pneu")
        gadget.delete()

        self.assertEqual(self.Gadget.objects.count(), 0)
        self.assertEqual(self.Gadget.all_objects.count(), 1)

    def test_delete_sets_soft_delete_fields_without_removing_row(self):
        gadget = self.Gadget.objects.create(nom="Pneu")

        gadget.delete()
        gadget.refresh_from_db()

        self.assertTrue(gadget.is_deleted)
        self.assertIsNotNone(gadget.deleted_at)

    def test_hard_delete_removes_row_physically(self):
        gadget = self.Gadget.objects.create(nom="Pneu")
        pk = gadget.pk

        gadget.hard_delete()

        self.assertFalse(self.Gadget.all_objects.filter(pk=pk).exists())

    def test_restore_clears_soft_delete_fields(self):
        gadget = self.Gadget.objects.create(nom="Pneu")
        gadget.delete()

        gadget.restore()

        self.assertTrue(self.Gadget.objects.filter(pk=gadget.pk).exists())
        self.assertFalse(self.Gadget.objects.get(pk=gadget.pk).is_deleted)
```

#### `apps/core/tests/test_numerotation.py`

*44 lignes*

```python
import pytest

from apps.core.models import CompteurNumero
from apps.core.services import prochain_numero

pytestmark = pytest.mark.django_db


def test_premier_numero_de_l_annee_commence_a_0001():
    assert prochain_numero("MIS", 2026) == "MIS-2026-0001"


def test_les_numeros_sont_consecutifs():
    numeros = [prochain_numero("MIS", 2026) for _ in range(3)]

    assert numeros == ["MIS-2026-0001", "MIS-2026-0002", "MIS-2026-0003"]


def test_chaque_prefixe_a_son_propre_compteur():
    prochain_numero("MIS", 2026)

    assert prochain_numero("OR", 2026) == "OR-2026-0001"
    assert prochain_numero("MIS", 2026) == "MIS-2026-0002"


def test_le_compteur_repart_de_1_chaque_annee():
    prochain_numero("FACT", 2026)
    prochain_numero("FACT", 2026)

    assert prochain_numero("FACT", 2027) == "FACT-2027-0001"


def test_annee_par_defaut_est_l_annee_courante():
    from django.utils import timezone

    numero = prochain_numero("MIS")

    assert numero == f"MIS-{timezone.localdate().year}-0001"


def test_au_dela_de_9999_le_numero_s_allonge_sans_collision():
    CompteurNumero.objects.create(prefixe="MIS", annee=2026, dernier=9999)

    assert prochain_numero("MIS", 2026) == "MIS-2026-10000"
```

#### `apps/core/tests/test_secret_key_prod.py`

*51 lignes* — Le réglage de production refuse de démarrer avec une SECRET_KEY publique (audit : SECRET_KEY par défaut).

```python
"""Le réglage de production refuse de démarrer avec une SECRET_KEY publique (audit : SECRET_KEY par défaut)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[3]
CLE_SURE = "k" * 10 + "Z" * 10 + "9" * 10 + "!" * 10 + "abcdef"


def _importer_prod(**variables):
    env = {
        k: v for k, v in os.environ.items() if k not in ("SECRET_KEY", "DJANGO_SETTINGS_MODULE")
    }
    env.update(
        ALLOWED_HOSTS="erp.example.org",
        DATABASE_URL="postgres://u:p@localhost:5432/d",
        REDIS_URL="redis://localhost:6379/0",
        **variables,
    )
    return subprocess.run(
        [sys.executable, "-c", "import config.settings.prod"],
        cwd=RACINE, env=env, capture_output=True, text=True, timeout=60,
    )


@pytest.mark.parametrize(
    "cle",
    ["django-insecure-change-me-in-env", "django-insecure-autre", "change-me", "trop-courte"],
)
def test_la_production_refuse_une_cle_par_defaut_ou_trop_courte(cle):
    resultat = _importer_prod(SECRET_KEY=cle)

    assert resultat.returncode != 0
    assert "SECRET_KEY" in resultat.stderr and "ImproperlyConfigured" in resultat.stderr


def test_la_production_refuse_l_absence_de_cle():
    resultat = _importer_prod()  # ni .env ni variable : la valeur par défaut du dépôt s'applique

    assert resultat.returncode != 0
    assert "ImproperlyConfigured" in resultat.stderr


def test_la_production_demarre_avec_une_vraie_cle():
    resultat = _importer_prod(SECRET_KEY=CLE_SURE)

    assert resultat.returncode == 0, resultat.stderr
```

#### `apps/core/tests/test_sections.py`

*64 lignes*

```python
import pytest

from apps.core import sections as module_sections
from apps.core.sections import RegistreSections


@pytest.fixture(autouse=True)
def gabarits_presents(request, monkeypatch):
    """Ces tests décrivent l'ordre et les arguments ; l'existence des gabarits a ses propres tests."""
    if "gabarit_reel" not in request.keywords:
        monkeypatch.setattr(module_sections, "get_template", lambda nom: None)


def _bloc(nom):
    return lambda *args, **kwargs: {"template": f"{nom}.html", "contexte": {"args": args}}


def test_un_registre_vide_ne_donne_aucun_bloc():
    assert RegistreSections().sections("x") == []


def test_les_blocs_sont_retournes_dans_l_ordre_d_enregistrement():
    registre = RegistreSections()
    registre.enregistrer(_bloc("a"))
    registre.enregistrer(_bloc("b"))

    assert [b["template"] for b in registre.sections()] == ["a.html", "b.html"]


def test_les_arguments_sont_transmis_aux_fournisseurs():
    registre = RegistreSections()
    registre.enregistrer(_bloc("a"))

    assert registre.sections("camion", "utilisateur")[0]["contexte"]["args"] == (
        "camion",
        "utilisateur",
    )


def test_un_fournisseur_qui_retourne_none_est_ignore():
    registre = RegistreSections()
    registre.enregistrer(lambda *args, **kwargs: None)
    registre.enregistrer(_bloc("b"))

    assert [b["template"] for b in registre.sections()] == ["b.html"]


def test_enregistrer_deux_fois_le_meme_fournisseur_est_sans_effet():
    registre = RegistreSections()
    fournisseur = _bloc("a")

    registre.enregistrer(fournisseur)
    registre.enregistrer(fournisseur)

    assert len(registre.sections()) == 1


@pytest.mark.gabarit_reel
def test_un_bloc_dont_le_gabarit_n_existe_pas_est_ignore():
    registre = RegistreSections()
    registre.enregistrer(_bloc("gabarit-qui-n-existe-pas"))
    registre.enregistrer(lambda *a, **k: {"template": "admin/base.html", "contexte": {}})

    assert [b["template"] for b in registre.sections()] == ["admin/base.html"]
```

#### `apps/core/tests/test_statiques.py`

*79 lignes* — Fichiers statiques versionnés en production : un fichier modifié change de nom, donc le cache de 30 jours de Nginx ne

```python
"""Fichiers statiques versionnés en production : un fichier modifié change de nom, donc le cache de 30 jours de Nginx ne
sert plus jamais un ancien ``tailwind.css`` (les téléphones affichaient la barre du chauffeur en colonne)."""

import re

import pytest
from django.core.management import call_command
from django.test import override_settings

STOCKAGE = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "apps.core.statiques.StockageStatiqueVersionne"},
}


@pytest.fixture
def statiques(tmp_path):
    source, racine = tmp_path / "source", tmp_path / "collecte"
    (source / "css").mkdir(parents=True)
    (source / "css" / "site.css").write_text("body { color: red; }", encoding="utf-8")
    # une feuille de style qui cite une police absente, comme Font Awesome : ne doit pas faire échouer la collecte
    (source / "css" / "icones.css").write_text("@font-face { src: url(../polices/absente.woff2); }", encoding="utf-8")
    with override_settings(STORAGES=STOCKAGE, STATIC_ROOT=racine, STATICFILES_DIRS=[source]):
        yield source, racine


def _collecter():
    call_command("collectstatic", "--noinput", verbosity=0)


def test_un_fichier_statique_prend_une_empreinte_dans_son_nom(statiques):
    from django.templatetags.static import static

    _, racine = statiques
    _collecter()

    url = static("css/site.css")

    assert re.fullmatch(r"/static/css/site\.[0-9a-f]{12}\.css", url)
    assert (racine / url.removeprefix("/static/")).read_text(encoding="utf-8") == "body { color: red; }"


def test_le_nom_change_quand_le_contenu_change(statiques):
    from django.templatetags.static import static

    source, _ = statiques
    _collecter()
    avant = static("css/site.css")
    (source / "css" / "site.css").write_text("body { color: blue; }", encoding="utf-8")
    from django.contrib.staticfiles.storage import staticfiles_storage

    staticfiles_storage.hashed_files.clear()  # nouvelle collecte = nouveau processus
    _collecter()

    assert static("css/site.css") != avant


def test_une_police_citee_mais_absente_ne_fait_pas_echouer_la_collecte(statiques):
    _collecter()  # lèverait ValueError avec ManifestStaticFilesStorage nu


def test_la_production_utilise_ce_stockage(monkeypatch):
    import os
    import subprocess
    import sys
    from pathlib import Path

    env = {k: v for k, v in os.environ.items() if k not in ("SECRET_KEY", "DJANGO_SETTINGS_MODULE")}
    env.update(
        SECRET_KEY="Zq9!" * 12, ALLOWED_HOSTS="erp.example.org", DATABASE_URL="postgres://u:p@localhost:5432/d",
        REDIS_URL="redis://localhost:6379/0",
    )
    code = "import config.settings.prod as p; print(p.STORAGES['staticfiles']['BACKEND'])"
    resultat = subprocess.run(
        [sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[3], env=env, capture_output=True, text=True,
        timeout=60,
    )

    assert resultat.stdout.strip() == "apps.core.statiques.StockageStatiqueVersionne", resultat.stderr
```

Lisez les tests : ils **documentent** le comportement. Par exemple `test_numerotation.py` prouve que deux
appels donnent des numéros consécutifs, et que la numérotation repart à 1 chaque année.

## Étape 7 — Générer la migration

Django compare vos modèles à l'état précédent et écrit la migration :

```bash
python manage.py makemigrations core
```

**Résultat attendu :**

```text
Migrations for 'core':
  apps\core\migrations\0001_compteur_numero.py
    + Create model CompteurNumero
```

(Le nom du fichier peut différer légèrement : `0001_initial.py`. Cela n'a pas d'importance.)

> ⚠️ **Ne lancez pas encore `python manage.py migrate`.** Le modèle *utilisateur* de l'ERP sera créé au
> chapitre suivant. Django exige qu'il existe **avant** la toute première migration ; sinon la base
> se retrouve dans un état incohérent. Les tests, eux, utilisent une base temporaire : vous pouvez
> les lancer.

## Vérifier le chapitre

```bash
python manage.py check
```

```bash
python -m pytest apps/core/tests/test_compatibilite_postgresql.py apps/core/tests/test_echeance.py apps/core/tests/test_formats.py apps/core/tests/test_graphiques.py apps/core/tests/test_models.py apps/core/tests/test_numerotation.py apps/core/tests/test_secret_key_prod.py apps/core/tests/test_sections.py apps/core/tests/test_statiques.py -q --no-cov
```

**Résultat attendu :** `68 passed, 3 failed` (pour les 9 fichier(s) de tests présentés dans ce chapitre).

Des tests échouent à ce stade, **c'est normal** : ils vérifient des écrans qui n'existent pas encore (par exemple la page d'accueil). Ils passeront au chapitre indiqué :

- `test_graphiques.py::test_le_rendu_des_colonnes_offre_legende_infobulle_et_tableau` → chapitre 18 (« Le socle de l'interface : gabarits, styles, connexion, notifications »)
- `test_graphiques.py::test_le_rendu_echappe_les_libelles` → chapitre 18 (« Le socle de l'interface : gabarits, styles, connexion, notifications »)
- `test_graphiques.py::test_un_graphique_vide_affiche_le_message_sans_barre` → chapitre 18 (« Le socle de l'interface : gabarits, styles, connexion, notifications »)

Petits essais dans le shell (aucune base nécessaire) :

```bash
python manage.py shell -c "from apps.core.search import normaliser; print(normaliser('TRAORÉ Moussa'))"
python manage.py shell -c "from apps.core.formats import nombre, pourcentage_signe; print(nombre(1500.5, 1), pourcentage_signe(23.333))"
```

**Résultat attendu :** `traore moussa`, puis `1 500,5 +23,3` (avec des espaces insécables).

> **Si des tests échouent** avec `no such function: NORMALISER` : `apps.py` n'est pas pris en compte
> (vérifiez `"apps.core"` dans `LOCAL_APPS`). Avec `RuntimeError: Model class … doesn't declare an explicit
> app_label` : l'application n'est pas listée dans `INSTALLED_APPS`.

## Ce qu'il faut retenir

- Un **service** est une fonction qui porte une règle ; les vues ne font qu'appeler des services.
- La **suppression logique** est le comportement par défaut : on ne détruit pas les données sensibles.
- Un **registre** (sections) permet à deux apps de collaborer **sans s'importer**.
- Les **tests** sont la documentation exécutable : lisez-les avant le code.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 2 : app core (BaseModel, numérotation, recherche, formats, sections, middlewares)"
```

---

[← Chapitre 1](01-squelette.md) · [Sommaire](README.md) · [Chapitre 3 →](03-accounts.md)
