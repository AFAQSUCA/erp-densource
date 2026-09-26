# Chapitre 2 — Le socle : l'app core

> 21 fichier(s) dans ce chapitre, 1093 lignes de code.

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

*93 lignes*

```python
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

*72 lignes* — Recherche texte insensible aux accents et à la casse (« traore » trouve « Traoré »).

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
from django.db.models.functions import Lower

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
        minuscule = Lower(expression)
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

*80 lignes*

```python
import threading

from django.conf import settings

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
    "text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-marque-600 "
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

*3 lignes*

```python
from django.contrib import admin

# Register your models here.
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
 
@@ -74,4 +75,5 @@
 MIDDLEWARE = [
     "django.middleware.security.SecurityMiddleware",
+    "apps.core.middleware.SecurityHeadersMiddleware",
     "corsheaders.middleware.CorsMiddleware",
     "django.contrib.sessions.middleware.SessionMiddleware",
@@ -81,4 +83,5 @@
     "django.contrib.messages.middleware.MessageMiddleware",
     "django.middleware.clickjacking.XFrameOptionsMiddleware",
+    "apps.core.middleware.CurrentRequestMiddleware",
 ]
 
```

Les deux lignes de `MIDDLEWARE` ajoutent nos deux middlewares ; `"apps.core"` déclare l'application.

## Étape 6 — Les fichiers restants (README et tests)

#### `apps/core/README.md`

*37 lignes* — core

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

#### `apps/core/rapports.py`

*35 lignes* — Aides communes aux rapports imprimables (trésorerie, tableau de bord, listes, journal d'audit).

```python
"""Aides communes aux rapports imprimables (trésorerie, tableau de bord, listes, journal d'audit).

Chaque rapport est une page HTML autonome (pas `base.html` : pas de menu ni de barre latérale dans le
tirage), avec le bouton « Imprimer » (`data-imprimer`, voir `static/js/app.js`) qui ouvre l'impression du
navigateur — l'utilisateur choisit « Enregistrer au format PDF » ou une imprimante. Même mécanisme que
`billing.facture_print` ; ce module en généralise l'en-tête pour ne pas le récrire à chaque rapport.

Le seul cas qui a besoin d'une mise en page pixel-près (document envoyé à un tiers) reste
`apps.missions.documents` (ReportLab) ; un rapport interne n'en a pas besoin.
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
python -m pytest apps/core/tests/test_echeance.py apps/core/tests/test_formats.py apps/core/tests/test_graphiques.py apps/core/tests/test_models.py apps/core/tests/test_numerotation.py apps/core/tests/test_sections.py -q --no-cov
```

**Résultat attendu :** `42 passed` (pour les 5 fichier(s) de tests présentés dans ce chapitre).

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
