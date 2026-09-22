# Chapitre 2 — Le socle : l'app core

> 18 fichier(s) dans ce chapitre, 699 lignes de code.

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

*48 lignes* — Services transverses.

```python
"""Services transverses."""

from datetime import date

from django.db import transaction
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

*67 lignes* — Recherche texte insensible aux accents et à la casse (« traore » trouve « Traoré »).

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
        (expression,) = self.get_source_expressions()
        traduit = Func(expression, Value(ACCENTS), Value(SANS_ACCENT), function="TRANSLATE")
        return Lower(traduit).as_sql(compiler, connection)


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

*16 lignes*

```python
from django import forms

CHAMP = (
    "block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm "
    "text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-marque-600 "
    "focus:outline-none focus:ring-2 focus:ring-marque-600/30"
)


class StyleTailwindMixin:
    """Applique le style Tailwind commun à tous les champs d'un formulaire."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for champ in self.fields.values():
            champ.widget.attrs.setdefault("class", CHAMP)
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
@@ -49,4 +49,5 @@
 
 LOCAL_APPS = [
+    "apps.core",
 ]
 
@@ -66,4 +67,5 @@
 MIDDLEWARE = [
     "django.middleware.security.SecurityMiddleware",
+    "apps.core.middleware.SecurityHeadersMiddleware",
     "corsheaders.middleware.CorsMiddleware",
     "django.contrib.sessions.middleware.SessionMiddleware",
@@ -73,4 +75,5 @@
     "django.contrib.messages.middleware.MessageMiddleware",
     "django.middleware.clickjacking.XFrameOptionsMiddleware",
+    "apps.core.middleware.CurrentRequestMiddleware",
 ]
 
```

Les deux lignes de `MIDDLEWARE` ajoutent nos deux middlewares ; `"apps.core"` déclare l'application.

## Étape 6 — Les fichiers restants (README et tests)

#### `apps/core/README.md`

*14 lignes* — core

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
python -m pytest apps/core/tests/test_echeance.py apps/core/tests/test_formats.py apps/core/tests/test_models.py apps/core/tests/test_numerotation.py apps/core/tests/test_sections.py -q --no-cov
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
