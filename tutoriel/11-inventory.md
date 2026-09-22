# Chapitre 11 — Le stock de pièces : l'app inventory

> 16 fichier(s) dans ce chapitre, 1449 lignes de code.

## Ce que vous allez construire

**`inventory`** : le **magasin de pièces détachées**, avec sa valeur.

| Élément | Règle |
|---|---|
| `Article` | référence unique, désignation, catégorie, emplacement, **quantité**, **seuil minimal** (0 = non surveillé), **PUMP** |
| **PUMP** | *prix unitaire moyen pondéré* : recalculé à chaque **entrée d'achat** ; chaque sortie est valorisée à ce prix |
| `MouvementStock` | le **journal des mouvements** : entrées (achat), sorties (liées à un **OR ouvert**), ajustements (**motif obligatoire**) |
| Alerte de seuil | quand un mouvement fait passer un article **au seuil ou en dessous**, un signal `seuil_bas_atteint` est émis |
| Coût d'un OR | main-d'œuvre + pièces sorties, calculé automatiquement |

Deux règles fortes : la **quantité** et le **PUMP** d'un article **ne changent que par un mouvement** (jamais à
la main), et le journal des mouvements est **immuable** : une erreur se corrige par un ajustement motivé.

## Prérequis

- Chapitres 1 à 10 terminés.

## Notions Django de ce chapitre

- **Le PUMP** : `(stock × PUMP actuel + quantité entrée × prix d'achat) / nouveau stock`. Exemple : 10
  pièces à 1 000 puis 10 pièces à 2 000 donnent un PUMP de 1 500.
- **Journal « append-only »** : `MouvementStock` n'est pas un `BaseModel` (pas de suppression logique) : on
  n'efface ni ne modifie jamais un mouvement.
- **Verrou sur l'article** pendant un mouvement : deux sorties simultanées ne peuvent pas rendre le stock
  négatif.
- **`ROUND_HALF_UP`** : l'arrondi « commercial » (0,5 arrondit vers le haut), au centime.
- **Un formulaire déjà présent dans la couche métier** : `forms.py` est ici présenté avec `inventory` (et non
  avec les écrans) parce que `sections.py` en a besoin **au démarrage** ; il ne dépend que de `core.forms`.
- **Sections** : `inventory` ajoute le bloc « Pièces utilisées » à la fiche d'un OR de `garage`.

## Étape 1 — Créer l'application

```bash
mkdir -p apps/inventory/tests
```

#### Fichiers vides à créer

Ces fichiers n'ont aucun contenu ; ils servent à faire de leur dossier un *paquet Python* (sans eux, `import apps.xxx` échouerait). Créez d'abord les dossiers, puis les fichiers :

```bash
mkdir -p apps\inventory apps\inventory\tests
touch apps/inventory/__init__.py
touch apps/inventory/tests/__init__.py
```

> Sous PowerShell, `mkdir -p` s'écrit `New-Item -ItemType Directory -Force <dossier>` et `touch fichier` s'écrit `New-Item -ItemType File -Force fichier`. Vous pouvez aussi créer ces fichiers avec votre éditeur.

## Étape 2 — Modèles

#### `apps/inventory/models.py`

*153 lignes*

```python
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class Article(BaseModel):
    """Pièce détachée du magasin — cahier-des-charges.md:177-179.

    ``quantite`` et ``pump`` ne se modifient que par les mouvements de
    ``services.py`` : ne jamais les éditer à la main.
    """

    reference = models.CharField(_("référence"), max_length=50, unique=True)
    designation = models.CharField(_("désignation"), max_length=200)
    categorie = models.CharField(_("catégorie"), max_length=100, blank=True)
    emplacement = models.CharField(_("emplacement"), max_length=100, blank=True)
    quantite = models.PositiveIntegerField(_("quantité en stock"), default=0)
    seuil_minimal = models.PositiveIntegerField(
        _("seuil minimal"),
        default=0,
        help_text=_("0 = pas d'alerte de seuil pour cet article."),
    )
    pump = models.DecimalField(
        _("PUMP (FCFA)"),
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text=_("Prix unitaire moyen pondéré."),
    )

    class Meta:
        verbose_name = _("article")
        verbose_name_plural = _("articles")
        ordering = ["reference"]
        indexes = [models.Index(fields=["designation"])]

    def __str__(self):
        return f"{self.reference} - {self.designation}"

    @property
    def sous_seuil(self) -> bool:
        """Stock au niveau du seuil minimal ou en dessous (seuil 0 = désactivé)."""
        return self.seuil_minimal > 0 and self.quantite <= self.seuil_minimal

    @property
    def valeur_stock(self) -> Decimal:
        """Valorisation du stock au PUMP."""
        return self.quantite * self.pump


class TypeMouvement(models.TextChoices):
    """3 types de mouvements — cahier-des-charges.md:180-181."""

    ENTREE = "ENTREE", _("Entrée (achat)")
    SORTIE = "SORTIE", _("Sortie (liée à un OR)")
    AJUSTEMENT = "AJUSTEMENT", _("Ajustement")


class MouvementStock(models.Model):
    """Ligne du journal des mouvements de stock — append-only.

    Comme ``AuditLog``, un mouvement ne se modifie ni ne se supprime : une
    erreur se corrige par un mouvement d'ajustement. Ce n'est donc pas un
    ``BaseModel`` (pas de soft delete) : la valeur de ``Article.quantite``
    doit toujours être la somme des variations.
    """

    article = models.ForeignKey(
        Article,
        verbose_name=_("article"),
        on_delete=models.PROTECT,
        related_name="mouvements",
    )
    type_mouvement = models.CharField(
        _("type"), max_length=12, choices=TypeMouvement.choices
    )
    variation = models.IntegerField(
        _("variation"), help_text=_("Positive en entrée, négative en sortie.")
    )
    quantite_apres = models.PositiveIntegerField(_("stock après mouvement"))
    prix_unitaire = models.DecimalField(
        _("prix unitaire (FCFA)"),
        max_digits=12,
        decimal_places=2,
        help_text=_("Prix d'achat en entrée ; PUMP au moment du mouvement sinon."),
    )
    ordre_reparation = models.ForeignKey(
        "garage.OrdreReparation",
        verbose_name=_("ordre de réparation"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="mouvements_stock",
    )
    motif = models.TextField(_("motif"), blank=True)
    acteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("acteur"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    date_mouvement = models.DateTimeField(_("date"), auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _("mouvement de stock")
        verbose_name_plural = _("mouvements de stock")
        ordering = ["-date_mouvement", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(type_mouvement=TypeMouvement.ENTREE) | Q(variation__gt=0),
                name="mouvement_entree_variation_positive",
            ),
            models.CheckConstraint(
                condition=~Q(type_mouvement=TypeMouvement.SORTIE) | Q(variation__lt=0),
                name="mouvement_sortie_variation_negative",
            ),
            models.CheckConstraint(
                condition=~Q(type_mouvement=TypeMouvement.AJUSTEMENT)
                | ~Q(variation=0),
                name="mouvement_ajustement_non_nul",
            ),
            # architecture.md:230 : or_id NULL si Entrée, NOT NULL si Sortie.
            models.CheckConstraint(
                condition=~Q(type_mouvement=TypeMouvement.SORTIE)
                | Q(ordre_reparation__isnull=False),
                name="mouvement_sortie_requiert_or",
            ),
            models.CheckConstraint(
                condition=~Q(type_mouvement=TypeMouvement.ENTREE)
                | Q(ordre_reparation__isnull=True),
                name="mouvement_entree_sans_or",
            ),
        ]

    def __str__(self):
        return f"{self.get_type_mouvement_display()} {self.variation:+d} {self.article.reference}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError(
                "MouvementStock est append-only : corriger par un ajustement."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("MouvementStock est append-only : suppression interdite.")
```

`Article` déclare `quantite` et `pump` **sans les rendre modifiables à la main** dans l'interface : seuls les
services les changent. `MouvementStock` garde, pour chaque mouvement, la variation (positive ou négative), le prix, le **stock après**
(pour retracer l'historique), l'auteur et, pour un ajustement, le **motif**.

## Étape 3 — Règles métier

#### `apps/inventory/exceptions.py`

*30 lignes*

```python
class StockError(Exception):
    """Erreur métier sur le stock."""


class QuantiteInvalide(StockError):
    """Quantité nulle ou négative, ou ajustement à zéro."""


class PrixInvalide(StockError):
    """Prix d'achat nul ou négatif."""


class StockInsuffisant(StockError):
    """La sortie demandée dépasse la quantité en stock."""


class OrCloture(StockError):
    """Sortie de pièces impossible sur un OR déjà clôturé (coût figé)."""


class MotifRequis(StockError):
    """Un ajustement d'inventaire doit être justifié."""


class ArticleInvalide(StockError):
    """Référence ou désignation vide, seuil négatif."""


class DoublonArticle(StockError):
    """Référence déjà utilisée par un autre article."""
```

#### `apps/inventory/services.py`

*331 lignes* — Logique métier du stock — cahier-des-charges.md:177-183.

```python
"""Logique métier du stock — cahier-des-charges.md:177-183.

Chaque mouvement est atomique, verrouille l'article, met à jour la quantité
(et le PUMP en entrée) en temps réel et écrit une ligne immuable dans
``MouvementStock``. ``inventory`` dépend de ``garage`` (la sortie est liée à un
OR), jamais l'inverse.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import F, QuerySet

from apps.core.search import filtrer_par_texte
from apps.garage.models import OrdreReparation, StatutOr

from .exceptions import (
    ArticleInvalide,
    DoublonArticle,
    MotifRequis,
    OrCloture,
    PrixInvalide,
    QuantiteInvalide,
    StockInsuffisant,
)
from .models import Article, MouvementStock, TypeMouvement
from .signals import seuil_bas_atteint

CENTIME = Decimal("0.01")


def _verrouiller(objet):
    type(objet)._base_manager.select_for_update().filter(pk=objet.pk).first()
    objet.refresh_from_db()
    return objet


def _enregistrer(
    article: Article,
    type_mouvement: str,
    variation: int,
    prix_unitaire: Decimal,
    *,
    ordre: OrdreReparation | None = None,
    motif: str = "",
    acteur=None,
) -> MouvementStock:
    """Applique la variation à l'article, journalise et alerte si seuil franchi.

    L'appelant a verrouillé l'article et vérifié que le stock reste >= 0 ;
    ``article.pump`` est déjà à jour pour une entrée.
    """
    etait_sous_seuil = article.sous_seuil
    article.quantite += variation
    article.save(update_fields=["quantite", "pump", "updated_at"])
    mouvement = MouvementStock.objects.create(
        article=article,
        type_mouvement=type_mouvement,
        variation=variation,
        quantite_apres=article.quantite,
        prix_unitaire=prix_unitaire,
        ordre_reparation=ordre,
        motif=motif,
        acteur=acteur,
    )
    if variation < 0 and article.sous_seuil and not etait_sous_seuil:
        seuil_bas_atteint.send(sender=Article, article=article)
    return mouvement


@transaction.atomic
def creer_article(
    *,
    reference: str,
    designation: str,
    categorie: str = "",
    emplacement: str = "",
    seuil_minimal: int = 0,
) -> Article:
    """Crée un article à stock nul : le stock initial arrive par une entrée.

    La référence est normalisée (majuscules, sans espaces autour) et doit être
    unique, y compris parmi les articles supprimés logiquement.
    """
    reference = reference.strip().upper()
    _verifier_fiche(reference=reference, designation=designation, seuil_minimal=seuil_minimal)
    if Article.all_objects.filter(reference=reference).exists():
        raise DoublonArticle(f"La référence {reference} est déjà utilisée.")
    return Article.objects.create(
        reference=reference,
        designation=designation.strip(),
        categorie=categorie.strip(),
        emplacement=emplacement.strip(),
        seuil_minimal=seuil_minimal,
    )


def _verifier_fiche(*, reference: str, designation: str, seuil_minimal: int) -> None:
    if not reference:
        raise ArticleInvalide("La référence est obligatoire.")
    if not designation.strip():
        raise ArticleInvalide("La désignation est obligatoire.")
    if seuil_minimal < 0:
        raise ArticleInvalide("Le seuil minimal ne peut pas être négatif.")


@transaction.atomic
def modifier_article(
    article: Article,
    *,
    designation: str,
    categorie: str = "",
    emplacement: str = "",
    seuil_minimal: int = 0,
) -> Article:
    """Met à jour la fiche. Référence, quantité et PUMP ne changent jamais ici :
    la référence identifie l'article, la quantité et le PUMP viennent des mouvements."""
    _verifier_fiche(
        reference=article.reference, designation=designation, seuil_minimal=seuil_minimal
    )
    _verrouiller(article)
    article.designation = designation.strip()
    article.categorie = categorie.strip()
    article.emplacement = emplacement.strip()
    article.seuil_minimal = seuil_minimal
    article.save(
        update_fields=["designation", "categorie", "emplacement", "seuil_minimal", "updated_at"]
    )
    return article


@transaction.atomic
def enregistrer_entree(
    article: Article, *, quantite: int, prix_unitaire: Decimal, acteur=None
) -> MouvementStock:
    """Entrée (achat) : augmente le stock et recalcule le PUMP.

    PUMP = (stock x PUMP actuel + quantité x prix d'achat) / nouveau stock,
    arrondi au centime.
    """
    if quantite <= 0:
        raise QuantiteInvalide("La quantité entrée doit être strictement positive.")
    prix = Decimal(prix_unitaire)
    if prix <= 0:
        raise PrixInvalide("Le prix d'achat doit être strictement positif.")

    _verrouiller(article)
    valeur = Decimal(article.quantite) * article.pump + Decimal(quantite) * prix
    article.pump = (valeur / Decimal(article.quantite + quantite)).quantize(
        CENTIME, rounding=ROUND_HALF_UP
    )
    return _enregistrer(
        article, TypeMouvement.ENTREE, quantite, prix, acteur=acteur
    )


@transaction.atomic
def sortir_pour_or(
    article: Article, *, quantite: int, ordre: OrdreReparation, acteur=None
) -> MouvementStock:
    """Sortie de pièces pour un OR ouvert, valorisée au PUMP du moment.

    Le coût des pièces de l'OR s'en déduit automatiquement (:func:`cout_pieces`).
    Un OR clôturé n'accepte plus de sortie : son coût est figé.
    """
    if quantite <= 0:
        raise QuantiteInvalide("La quantité sortie doit être strictement positive.")
    _verrouiller(ordre)
    if ordre.statut != StatutOr.OUVERT:
        raise OrCloture(f"L'OR {ordre.numero} est clôturé : sortie impossible.")
    _verrouiller(article)
    if quantite > article.quantite:
        raise StockInsuffisant(
            f"Stock insuffisant pour {article.reference} : {quantite} demandé(s), "
            f"{article.quantite} disponible(s)."
        )
    return _enregistrer(
        article,
        TypeMouvement.SORTIE,
        -quantite,
        article.pump,
        ordre=ordre,
        acteur=acteur,
    )


@transaction.atomic
def ajuster_stock(
    article: Article, *, variation: int, motif: str, acteur=None
) -> MouvementStock:
    """Ajustement d'inventaire (+/-), justifié par un motif ; PUMP inchangé."""
    if variation == 0:
        raise QuantiteInvalide("Un ajustement ne peut pas être nul.")
    if not motif.strip():
        raise MotifRequis("Un ajustement de stock doit être justifié.")
    _verrouiller(article)
    if article.quantite + variation < 0:
        raise StockInsuffisant(
            f"Ajustement impossible : le stock de {article.reference} deviendrait négatif."
        )
    return _enregistrer(
        article,
        TypeMouvement.AJUSTEMENT,
        variation,
        article.pump,
        motif=motif,
        acteur=acteur,
    )


# --- consultation ---


def articles_sous_seuil() -> QuerySet[Article]:
    """Articles au seuil minimal ou en dessous (centre d'alertes du tableau de
    bord, cahier-des-charges.md:231-232). Seuil 0 = article non surveillé."""
    return Article.objects.filter(
        seuil_minimal__gt=0, quantite__lte=F("seuil_minimal")
    )


def cout_pieces(ordre: OrdreReparation) -> Decimal:
    """Coût automatique des pièces utilisées sur un OR (cahier-des-charges.md:167-168).

    Somme des sorties, chacune valorisée au PUMP de son moment. Calculé en
    Python : l'arithmétique décimale de SQLite passerait par des flottants.
    """
    lignes = MouvementStock.objects.filter(
        ordre_reparation=ordre, type_mouvement=TypeMouvement.SORTIE
    ).values_list("variation", "prix_unitaire")
    return sum((-variation * prix for variation, prix in lignes), Decimal("0"))


def cout_total(ordre: OrdreReparation) -> Decimal:
    """Coût total d'un OR : main-d'œuvre + pièces."""
    return ordre.cout_main_oeuvre + cout_pieces(ordre)


# --- lecture pour les écrans ---


def articles_en_stock() -> QuerySet[Article]:
    """Articles dont il reste au moins une unité (choix d'une sortie de pièces)."""
    return Article.objects.filter(quantite__gt=0).order_by("reference")


def sorties_de_l_or(ordre: OrdreReparation) -> QuerySet[MouvementStock]:
    """Sorties de pièces d'un OR, de la plus ancienne à la plus récente."""
    return (
        MouvementStock.objects.select_related("article")
        .filter(ordre_reparation=ordre, type_mouvement=TypeMouvement.SORTIE)
        .order_by("date_mouvement", "pk")
    )


def rechercher_articles(
    *, recherche: str = "", categorie: str = "", sous_seuil: bool = False
) -> QuerySet[Article]:
    """Articles filtrés par texte (référence, désignation, catégorie, emplacement),
    catégorie exacte et/ou stock au seuil ou en dessous."""
    articles = Article.objects.order_by("reference")
    articles = filtrer_par_texte(
        articles, recherche, "reference", "designation", "categorie", "emplacement"
    )
    if categorie:
        articles = articles.filter(categorie=categorie)
    if sous_seuil:
        articles = articles.filter(pk__in=articles_sous_seuil().values("pk"))
    return articles


def categories_articles() -> list[str]:
    """Catégories utilisées, sans doublon ni valeur vide, triées."""
    return sorted(
        set(Article.objects.exclude(categorie="").values_list("categorie", flat=True))
    )


def valeur_totale_stock() -> Decimal:
    """Valeur du stock au PUMP. Somme en Python : SQLite passerait par des flottants."""
    return sum(
        (quantite * pump for quantite, pump in Article.objects.values_list("quantite", "pump")),
        Decimal("0"),
    )


def mouvements_queryset() -> QuerySet[MouvementStock]:
    """Mouvements avec article, OR et acteur chargés (évite les requêtes en boucle)."""
    return MouvementStock.objects.select_related("article", "ordre_reparation", "acteur")


def rechercher_mouvements(
    *, type_mouvement: str | None = None, recherche: str = ""
) -> QuerySet[MouvementStock]:
    """Journal des mouvements filtré par type et texte (article, n° d'OR, motif)."""
    mouvements = mouvements_queryset()
    if type_mouvement in TypeMouvement.values:
        mouvements = mouvements.filter(type_mouvement=type_mouvement)
    mouvements = filtrer_par_texte(
        mouvements,
        recherche,
        "article__reference",
        "article__designation",
        "ordre_reparation__numero",
        "motif",
    )
    return mouvements


def mouvements_de_l_article(article: Article, *, limite: int = 20) -> QuerySet[MouvementStock]:
    """Derniers mouvements d'un article, du plus récent au plus ancien."""
    return mouvements_queryset().filter(article=article)[:limite]


def cout_des_or_clotures(debut: date, fin: date) -> Decimal:
    """Coût (main-d'œuvre + pièces au PUMP) des OR clôturés pendant la période, en FCFA.

    Alimente les charges du mois (cahier-des-charges.md:227). Les pièces sont lues en une
    seule requête pour tous les OR de la période.
    """
    ordres = OrdreReparation.objects.filter(
        statut=StatutOr.CLOTURE, date_cloture__date__range=(debut, fin)
    )
    main_oeuvre = sum(ordres.values_list("cout_main_oeuvre", flat=True), Decimal("0"))
    sorties = MouvementStock.objects.filter(
        ordre_reparation__in=ordres, type_mouvement=TypeMouvement.SORTIE
    ).values_list("variation", "prix_unitaire")
    return main_oeuvre + sum((-variation * prix for variation, prix in sorties), Decimal("0"))
```

À lire :

1. **`creer_article`** : référence normalisée (majuscules), unique **même parmi les articles supprimés**. Un
   article naît à **stock nul** : le stock initial arrive par une entrée.
2. **`enregistrer_entree`** : recalcule le PUMP (formule ci-dessus, arrondie au centime).
3. **`sortir_pour_or`** : refuse un OR clôturé (`OrCloture`) et un stock insuffisant (`StockInsuffisant`) ;
   valorise la sortie au PUMP **du moment**.
4. **`ajuster_stock`** : corrige l'inventaire ; **le motif est obligatoire** (`MotifRequis`).
5. **`articles_sous_seuil`**, **`valeur_totale_stock`**, **`cout_pieces`**, **`cout_total`** : des lectures
   pour les écrans et le tableau de bord.

#### `apps/inventory/signals.py`

*10 lignes* — Signaux émis par le stock (souscrits par ``notifications``, étape 5).

```python
"""Signaux émis par le stock (souscrits par ``notifications``, étape 5)."""

from django.dispatch import Signal

# Émis quand un mouvement fait passer un article au niveau de son seuil minimal
# (ou en dessous) alors qu'il était au-dessus — cahier-des-charges.md:337-338.
# Arguments : ``article`` (instance à jour). Émis dans la transaction du
# mouvement : un récepteur qui envoie un message doit utiliser
# ``transaction.on_commit``.
seuil_bas_atteint = Signal()
```

#### `apps/inventory/permissions.py`

*11 lignes* — Qui peut consulter et faire bouger le stock.

```python
"""Qui peut consulter et faire bouger le stock.

Cahier-des-charges.md:44-55 : le PARCAUTO gère les « mouvements de stock,
inventaires » ; la DIRECTION est en « lecture seule sur Parc Auto ». L'ADMIN a tous
les droits.
"""

from apps.accounts.models import Role

CONSULTATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.PARCAUTO})
MODIFICATION = frozenset({Role.ADMIN, Role.PARCAUTO})
```

#### `apps/inventory/forms.py`

*68 lignes*

```python
from django import forms

from apps.core.forms import StyleTailwindMixin

from . import services


class SortieForm(StyleTailwindMixin, forms.Form):
    """Sortie de pièces pour un OR (cahier-des-charges.md:180-181)."""

    article = forms.ModelChoiceField(label="Pièce", queryset=None)
    quantite = forms.IntegerField(label="Quantité", min_value=1, initial=1)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["article"].queryset = services.articles_en_stock()
        self.fields["article"].label_from_instance = lambda a: (
            f"{a.reference} - {a.designation} ({a.quantite} en stock)"
        )


class ArticleForm(StyleTailwindMixin, forms.Form):
    """Fiche article (cahier-des-charges.md:177-178)."""

    designation = forms.CharField(label="Désignation", max_length=200)
    categorie = forms.CharField(label="Catégorie", max_length=100, required=False)
    emplacement = forms.CharField(label="Emplacement", max_length=100, required=False)
    seuil_minimal = forms.IntegerField(
        label="Seuil minimal",
        min_value=0,
        initial=0,
        help_text="Une alerte s'affiche quand le stock atteint ce niveau. 0 = pas d'alerte.",
    )


class ArticleCreationForm(ArticleForm):
    """Création : la référence se saisit une seule fois, elle ne change plus ensuite."""

    reference = forms.CharField(label="Référence", max_length=50)
    field_order = ["reference", "designation", "categorie", "emplacement", "seuil_minimal"]


class EntreeForm(StyleTailwindMixin, forms.Form):
    """Entrée en stock (achat) : le PUMP est recalculé avec le prix d'achat."""

    quantite = forms.IntegerField(label="Quantité achetée", min_value=1)
    prix_unitaire = forms.DecimalField(
        label="Prix d'achat unitaire (FCFA)",
        min_value=0,
        decimal_places=2,
        max_digits=12,
    )


class AjustementForm(StyleTailwindMixin, forms.Form):
    """Ajustement d'inventaire : correction (+ ou -), toujours justifiée."""

    variation = forms.IntegerField(
        label="Variation (+ pour ajouter, - pour retirer)",
        help_text="Écart constaté entre le stock informatique et le stock compté.",
    )
    motif = forms.CharField(label="Motif", widget=forms.Textarea(attrs={"rows": 2}))

    def clean_variation(self):
        variation = self.cleaned_data["variation"]
        if variation == 0:
            raise forms.ValidationError("La variation ne peut pas être nulle.")
        return variation
```

#### `apps/inventory/sections.py`

*34 lignes* — Bloc « Pièces utilisées » ajouté à la fiche d'un OR (garage) — voir core/sections.py.

```python
"""Bloc « Pièces utilisées » ajouté à la fiche d'un OR (garage) — voir core/sections.py.

Le coût automatique des pièces et le total de l'OR (main-d'œuvre + pièces) sont
affichés ici : ``garage`` n'a pas à connaître le stock (architecture.md:161-163).
"""

from apps.garage.models import StatutOr

from . import permissions, services
from .forms import SortieForm


def section_pieces(ordre, utilisateur):
    role = utilisateur.role_effectif
    if role not in permissions.CONSULTATION:
        return None
    peut_sortir = role in permissions.MODIFICATION and ordre.statut == StatutOr.OUVERT
    return {
        "template": "inventory/_pieces_or.html",
        "contexte": {
            "lignes": [
                {
                    "article": m.article,
                    "quantite": -m.variation,
                    "prix_unitaire": m.prix_unitaire,
                    "montant": -m.variation * m.prix_unitaire,
                }
                for m in services.sorties_de_l_or(ordre)
            ],
            "cout_pieces": services.cout_pieces(ordre),
            "cout_total": services.cout_total(ordre),
            "form_sortie": SortieForm() if peut_sortir else None,
        },
    }
```

Le bloc « Pièces utilisées » d'un OR, avec son formulaire de sortie. Il n'est visible que si le rôle a le droit
de consulter le stock.

## Étape 4 — Administration, démarrage, tests

#### `apps/inventory/admin.py`

*45 lignes*

```python
from django.contrib import admin

from .models import Article, MouvementStock


class MouvementLectureSeule(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    """Fiche modifiable, sauf quantité et PUMP : ils ne bougent que par les
    mouvements de apps/inventory/services.py."""

    list_display = ("reference", "designation", "categorie", "quantite", "seuil_minimal", "pump")
    list_filter = ("categorie",)
    search_fields = ("reference", "designation")
    readonly_fields = ("quantite", "pump")

    def get_queryset(self, request):
        return Article.objects.all()


@admin.register(MouvementStock)
class MouvementStockAdmin(MouvementLectureSeule):
    list_display = (
        "date_mouvement",
        "article",
        "type_mouvement",
        "variation",
        "quantite_apres",
        "ordre_reparation",
    )
    list_filter = ("type_mouvement",)
    search_fields = ("article__reference", "ordre_reparation__numero")

    def get_queryset(self, request):
        return MouvementStock.objects.select_related("article", "ordre_reparation")
```

#### `apps/inventory/apps.py`

*20 lignes*

```python
from django.apps import AppConfig


class InventoryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.inventory'
    label = 'inventory'

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer
        from apps.garage.sections import DETAIL_OR

        from . import permissions, sections

        DETAIL_OR.enregistrer(sections.section_pieces)
        enregistrer(
            EntreeMenu(
                "Stock", "inventory:articles", "fa-boxes-stacked", permissions.CONSULTATION, ordre=50
            )
        )
```

#### `apps/inventory/tests/factories.py`

*15 lignes*

```python
import factory

from apps.inventory.models import Article


class ArticleFactory(factory.django.DjangoModelFactory):
    """Article à stock nul et PUMP nul (comme ``creer_article``)."""

    class Meta:
        model = Article

    reference = factory.Sequence(lambda n: f"REF-{n:04d}")
    designation = factory.Sequence(lambda n: f"Plaquettes de frein {n}")
    categorie = "Freinage"
    emplacement = "Rayon A1"
```

#### `apps/inventory/README.md`

*36 lignes* — inventory

```markdown
# inventory

Rôle : magasin de pièces détachées — cahier-des-charges.md:177-183.

Entités :
- `Article` : référence, désignation, catégorie, emplacement, quantité, seuil
  minimal (0 = non surveillé), PUMP. `quantite` et `pump` ne bougent que par les
  mouvements.
- `MouvementStock` : journal immuable (append-only) des entrées (achat), sorties
  (liées à un OR ouvert) et ajustements (motif obligatoire). Une erreur se corrige
  par un ajustement.

Services (`services.py`) : `creer_article`, `enregistrer_entree` (recalcule le
PUMP pondéré), `sortir_pour_or` (valorisée au PUMP du moment), `ajuster_stock`,
`articles_sous_seuil`, `cout_pieces`, `cout_total` (main-d'œuvre + pièces d'un OR).

Signal `signals.seuil_bas_atteint` : émis quand un mouvement fait passer un article
au seuil minimal ou en dessous ; `notifications` (étape 5) s'y abonnera.

Dépend de `garage` (la sortie est liée à un OR), jamais l'inverse.

Interface (`views.py`, `templates/inventory/`) :
- liste des articles (recherche, catégorie, « sous le seuil »), valeur totale du stock au
  PUMP et nombre d'articles à réapprovisionner ; fiche d'un article avec ses derniers
  mouvements ; création et modification de la fiche (la référence ne change plus) ;
  entrée d'achat (recalcule le PUMP) ; ajustement d'inventaire (toujours motivé) ;
  journal global des mouvements, filtrable.
- bloc « Pièces utilisées » de la fiche d'un OR (sorties valorisées au PUMP, coût des pièces,
  coût total) et formulaire de sortie de pièces.
- un message d'alerte s'affiche quand un ajustement ou une sortie fait atteindre le seuil
  minimal (le signal `seuil_bas_atteint` reste disponible pour les notifications).

Accès : ADMIN, DIRECTION (lecture seule) et PARCAUTO (`permissions.py`) ; seuls ADMIN et
PARCAUTO créent, modifient, enregistrent des mouvements et font sortir des pièces.
Services ajoutés : `rechercher_articles`, `categories_articles`, `valeur_totale_stock`,
`modifier_article`, `rechercher_mouvements`, `mouvements_de_l_article`.
```

#### `apps/inventory/tests/test_fiche.py`

*219 lignes* — Fiche article, recherche, valeur du stock et journal — cahier-des-charges.md:177-183.

```python
"""Fiche article, recherche, valeur du stock et journal — cahier-des-charges.md:177-183."""

from decimal import Decimal

import pytest

from apps.garage import services as garage_services
from apps.garage.models import LieuReparation, TypeOr
from apps.inventory import services
from apps.inventory.exceptions import ArticleInvalide, DoublonArticle
from apps.inventory.models import Article, TypeMouvement

from .factories import ArticleFactory

pytestmark = pytest.mark.django_db


def _approvisionne(quantite=10, prix="1000", **surcharges):
    article = ArticleFactory(**surcharges)
    services.enregistrer_entree(article, quantite=quantite, prix_unitaire=Decimal(prix))
    return article


def _ordre():
    from apps.fleet.tests.factories import VehiculeFactory

    return garage_services.ouvrir_or(
        VehiculeFactory(), type_or=TypeOr.CURATIF, lieu=LieuReparation.INTERNE, motif="Freins"
    )


# --- création ---


def test_creer_article_normalise_la_reference_et_nettoie_les_champs():
    article = services.creer_article(
        reference="  fr-0012 ",
        designation="  Plaquettes  ",
        categorie=" Freinage ",
        emplacement=" A1 ",
        seuil_minimal=4,
    )

    assert (article.reference, article.designation) == ("FR-0012", "Plaquettes")
    assert (article.categorie, article.emplacement, article.seuil_minimal) == ("Freinage", "A1", 4)
    assert (article.quantite, article.pump) == (0, 0)


def test_deux_references_qui_ne_different_que_par_la_casse_sont_un_doublon():
    services.creer_article(reference="FR-1", designation="A")

    with pytest.raises(DoublonArticle, match="FR-1"):
        services.creer_article(reference="fr-1", designation="B")


def test_la_reference_d_un_article_supprime_logiquement_reste_reservee():
    services.creer_article(reference="FR-1", designation="A").delete()

    with pytest.raises(DoublonArticle):
        services.creer_article(reference="FR-1", designation="B")


@pytest.mark.parametrize(
    "donnees",
    [
        {"reference": "  ", "designation": "A"},
        {"reference": "FR-1", "designation": "   "},
        {"reference": "FR-1", "designation": "A", "seuil_minimal": -1},
    ],
)
def test_creer_article_refuse_les_donnees_invalides(donnees):
    with pytest.raises(ArticleInvalide):
        services.creer_article(**donnees)

    assert Article.objects.count() == 0


# --- modification ---


def test_modifier_article_change_la_fiche_sans_toucher_reference_stock_ni_pump():
    article = _approvisionne(10, "1000", reference="FR-1")

    services.modifier_article(
        article, designation="Disques", categorie="Freinage", emplacement="B2", seuil_minimal=3
    )

    article.refresh_from_db()
    assert (article.designation, article.categorie, article.emplacement, article.seuil_minimal) == (
        "Disques",
        "Freinage",
        "B2",
        3,
    )
    assert (article.reference, article.quantite, article.pump) == ("FR-1", 10, Decimal("1000.00"))


@pytest.mark.parametrize(
    "donnees", [{"designation": " "}, {"designation": "A", "seuil_minimal": -2}]
)
def test_modifier_article_refuse_les_donnees_invalides(donnees):
    article = ArticleFactory(designation="Ancien")

    with pytest.raises(ArticleInvalide):
        services.modifier_article(article, **donnees)

    article.refresh_from_db()
    assert article.designation == "Ancien"


# --- recherche ---


def test_rechercher_articles_par_texte_dans_tous_les_champs():
    cible = ArticleFactory(
        reference="ZZ-9", designation="Courroie", categorie="Moteur", emplacement="Rayon Z"
    )
    ArticleFactory()

    for terme in ("zz-9", "courroie", "moteur", "rayon z"):
        assert list(services.rechercher_articles(recherche=terme)) == [cible], terme


def test_rechercher_articles_par_categorie_exacte():
    moteur = ArticleFactory(categorie="Moteur")
    ArticleFactory(categorie="Freinage")

    assert list(services.rechercher_articles(categorie="Moteur")) == [moteur]


def test_rechercher_articles_sous_le_seuil_seulement():
    bas = _approvisionne(5, seuil_minimal=5)
    _approvisionne(6, seuil_minimal=5)
    _approvisionne(1, seuil_minimal=0)  # non surveillé

    assert list(services.rechercher_articles(sous_seuil=True)) == [bas]


def test_rechercher_articles_combine_les_filtres_et_trie_par_reference():
    b = ArticleFactory(reference="B-1", categorie="Moteur")
    a = ArticleFactory(reference="A-1", categorie="Moteur")
    ArticleFactory(reference="C-1", categorie="Freinage")

    assert list(services.rechercher_articles(categorie="Moteur")) == [a, b]
    assert list(services.rechercher_articles(recherche="a-1", categorie="Moteur")) == [a]


def test_categories_articles_sans_doublon_ni_valeur_vide_et_triees():
    ArticleFactory(categorie="Moteur")
    ArticleFactory(categorie="Freinage")
    ArticleFactory(categorie="Moteur")
    ArticleFactory(categorie="")

    assert services.categories_articles() == ["Freinage", "Moteur"]


# --- valeur ---


def test_valeur_totale_du_stock_au_pump_en_decimal_exact():
    _approvisionne(10, "1000")
    _approvisionne(4, "2500.50")

    assert services.valeur_totale_stock() == Decimal("20002.00")


def test_valeur_totale_du_stock_vide_est_nulle():
    ArticleFactory()

    assert services.valeur_totale_stock() == Decimal("0")


# --- journal ---


def test_rechercher_mouvements_par_type():
    article = _approvisionne(10)
    services.sortir_pour_or(article, quantite=2, ordre=_ordre())
    services.ajuster_stock(article, variation=-1, motif="Casse")

    assert services.rechercher_mouvements().count() == 3
    assert services.rechercher_mouvements(type_mouvement=TypeMouvement.ENTREE).count() == 1
    assert services.rechercher_mouvements(type_mouvement=TypeMouvement.SORTIE).count() == 1
    assert services.rechercher_mouvements(type_mouvement="???").count() == 3


def test_rechercher_mouvements_par_article_ordre_ou_motif():
    article = _approvisionne(10, reference="PLQ-7")
    ordre = _ordre()
    services.sortir_pour_or(article, quantite=1, ordre=ordre)
    services.ajuster_stock(article, variation=2, motif="Retour magasin")
    _approvisionne(3, reference="AUTRE")

    assert services.rechercher_mouvements(recherche="plq-7").count() == 3
    assert services.rechercher_mouvements(recherche=ordre.numero).count() == 1
    assert services.rechercher_mouvements(recherche="retour").count() == 1


def test_mouvements_de_l_article_du_plus_recent_au_plus_ancien_avec_limite():
    article = _approvisionne(10)
    for _ in range(3):
        services.ajuster_stock(article, variation=1, motif="Comptage")

    recents = list(services.mouvements_de_l_article(article, limite=2))

    assert [m.quantite_apres for m in recents] == [13, 12]


def test_mouvements_queryset_charge_article_or_et_acteur_sans_requete_supplementaire(
    django_assert_num_queries,
):
    article = _approvisionne(10)
    services.sortir_pour_or(article, quantite=1, ordre=_ordre())

    with django_assert_num_queries(1):
        for m in services.mouvements_queryset():
            m.article.reference
            m.ordre_reparation
            m.acteur
```

#### `apps/inventory/tests/test_models.py`

*112 lignes*

```python
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.garage.tests.factories import OrdreReparationFactory
from apps.inventory.models import MouvementStock, TypeMouvement

from .factories import ArticleFactory

pytestmark = pytest.mark.django_db


def _mouvement(article, type_mouvement, variation, ordre=None):
    return MouvementStock.objects.create(
        article=article,
        type_mouvement=type_mouvement,
        variation=variation,
        quantite_apres=10,
        prix_unitaire=Decimal("1000"),
        ordre_reparation=ordre,
    )


# --- article ---


def test_reference_unique():
    ArticleFactory(reference="FR-001")

    with pytest.raises(IntegrityError), transaction.atomic():
        ArticleFactory(reference="FR-001")


@pytest.mark.parametrize(
    ("quantite", "seuil", "attendu"),
    [
        (4, 5, True),  # sous le seuil
        (5, 5, True),  # au seuil : « atteint »
        (6, 5, False),
        (0, 0, False),  # seuil 0 = article non surveillé
    ],
)
def test_sous_seuil(quantite, seuil, attendu):
    article = ArticleFactory.build(quantite=quantite, seuil_minimal=seuil)

    assert article.sous_seuil is attendu


def test_valeur_du_stock_au_pump():
    article = ArticleFactory.build(quantite=4, pump=Decimal("2500.50"))

    assert article.valeur_stock == Decimal("10002.00")


def test_quantite_negative_refusee_par_la_base():
    with pytest.raises(IntegrityError), transaction.atomic():
        ArticleFactory(quantite=-1)


# --- journal des mouvements ---


def test_un_mouvement_ne_peut_pas_etre_modifie():
    mouvement = _mouvement(ArticleFactory(), TypeMouvement.ENTREE, 5)
    mouvement.motif = "modifié"

    with pytest.raises(ValueError, match="append-only"):
        mouvement.save()


def test_un_mouvement_ne_peut_pas_etre_supprime():
    mouvement = _mouvement(ArticleFactory(), TypeMouvement.ENTREE, 5)

    with pytest.raises(ValueError, match="append-only"):
        mouvement.delete()


def test_entree_avec_variation_negative_refusee_par_la_base():
    with pytest.raises(IntegrityError), transaction.atomic():
        _mouvement(ArticleFactory(), TypeMouvement.ENTREE, -5)


def test_sortie_avec_variation_positive_refusee_par_la_base():
    with pytest.raises(IntegrityError), transaction.atomic():
        _mouvement(
            ArticleFactory(), TypeMouvement.SORTIE, 5, OrdreReparationFactory()
        )


def test_sortie_sans_or_refusee_par_la_base():
    with pytest.raises(IntegrityError), transaction.atomic():
        _mouvement(ArticleFactory(), TypeMouvement.SORTIE, -5, ordre=None)


def test_entree_liee_a_un_or_refusee_par_la_base():
    with pytest.raises(IntegrityError), transaction.atomic():
        _mouvement(
            ArticleFactory(), TypeMouvement.ENTREE, 5, OrdreReparationFactory()
        )


def test_ajustement_nul_refuse_par_la_base():
    with pytest.raises(IntegrityError), transaction.atomic():
        _mouvement(ArticleFactory(), TypeMouvement.AJUSTEMENT, 0)


def test_ajustement_positif_ou_negatif_sans_or_accepte():
    article = ArticleFactory()

    _mouvement(article, TypeMouvement.AJUSTEMENT, 3)
    _mouvement(article, TypeMouvement.AJUSTEMENT, -3)
```

#### `apps/inventory/tests/test_services.py`

*349 lignes* — Stock, PUMP et coût des pièces — cahier-des-charges.md:177-183 et :337-338.

```python
"""Stock, PUMP et coût des pièces — cahier-des-charges.md:177-183 et :337-338."""

from decimal import Decimal

import pytest
from django.db.models import Sum

from apps.accounts.tests.factories import UserFactory
from apps.garage import services as garage_services
from apps.garage.tests.test_services import _ouvrir
from apps.inventory import services
from apps.inventory.exceptions import (
    MotifRequis,
    OrCloture,
    PrixInvalide,
    QuantiteInvalide,
    StockInsuffisant,
)
from apps.inventory.models import MouvementStock, TypeMouvement
from apps.inventory.signals import seuil_bas_atteint

from .factories import ArticleFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def alertes():
    """Références des articles pour lesquels ``seuil_bas_atteint`` a été émis."""
    recues = []

    def recepteur(sender, article, **kwargs):
        recues.append(article.reference)

    seuil_bas_atteint.connect(recepteur, weak=False)
    yield recues
    seuil_bas_atteint.disconnect(recepteur)


def _approvisionne(quantite=10, prix="1000", **surcharges):
    article = ArticleFactory(**surcharges)
    services.enregistrer_entree(article, quantite=quantite, prix_unitaire=Decimal(prix))
    return article


# --- création ---


def test_creer_article_demarre_a_stock_et_pump_nuls():
    article = services.creer_article(
        reference="FR-001", designation="Disque", seuil_minimal=4
    )

    assert (article.quantite, article.pump, article.seuil_minimal) == (0, 0, 4)


# --- entrée et PUMP ---


def test_premiere_entree_fixe_le_stock_et_le_pump_au_prix_d_achat():
    article = ArticleFactory()

    mouvement = services.enregistrer_entree(
        article, quantite=10, prix_unitaire=Decimal("1000")
    )

    article.refresh_from_db()
    assert (article.quantite, article.pump) == (10, Decimal("1000.00"))
    assert mouvement.type_mouvement == TypeMouvement.ENTREE
    assert (mouvement.variation, mouvement.quantite_apres) == (10, 10)
    assert mouvement.prix_unitaire == Decimal("1000.00")


def test_deuxieme_entree_recalcule_le_pump_pondere():
    article = _approvisionne(10, "1000")

    services.enregistrer_entree(article, quantite=10, prix_unitaire=Decimal("2000"))

    article.refresh_from_db()
    assert (article.quantite, article.pump) == (20, Decimal("1500.00"))


def test_le_pump_est_arrondi_au_centime():
    article = _approvisionne(2, "100")

    services.enregistrer_entree(article, quantite=1, prix_unitaire=Decimal("101"))

    article.refresh_from_db()
    assert article.pump == Decimal("100.33")  # 301 / 3 = 100,3333...


def test_entree_apres_stock_epuise_repart_du_nouveau_prix():
    article = _approvisionne(1, "1000")
    services.ajuster_stock(article, variation=-1, motif="Casse")

    services.enregistrer_entree(article, quantite=5, prix_unitaire=Decimal("800"))

    article.refresh_from_db()
    assert (article.quantite, article.pump) == (5, Decimal("800.00"))


@pytest.mark.parametrize("quantite", [0, -3])
def test_entree_refuse_une_quantite_nulle_ou_negative(quantite):
    with pytest.raises(QuantiteInvalide):
        services.enregistrer_entree(
            ArticleFactory(), quantite=quantite, prix_unitaire=Decimal("100")
        )


@pytest.mark.parametrize("prix", ["0", "-5"])
def test_entree_refuse_un_prix_nul_ou_negatif(prix):
    with pytest.raises(PrixInvalide):
        services.enregistrer_entree(
            ArticleFactory(), quantite=1, prix_unitaire=Decimal(prix)
        )


def test_entree_enregistre_l_acteur():
    acteur = UserFactory()
    article = ArticleFactory()

    mouvement = services.enregistrer_entree(
        article, quantite=1, prix_unitaire=Decimal("10"), acteur=acteur
    )

    assert mouvement.acteur == acteur


# --- sortie liée à un OR ---


def test_sortie_diminue_le_stock_a_la_valeur_du_pump_sans_le_modifier():
    article = _approvisionne(10, "1000")
    ordre = _ouvrir()

    mouvement = services.sortir_pour_or(article, quantite=4, ordre=ordre)

    article.refresh_from_db()
    assert (article.quantite, article.pump) == (6, Decimal("1000.00"))
    assert mouvement.type_mouvement == TypeMouvement.SORTIE
    assert (mouvement.variation, mouvement.quantite_apres) == (-4, 6)
    assert mouvement.prix_unitaire == Decimal("1000.00")
    assert mouvement.ordre_reparation == ordre


def test_sortie_de_tout_le_stock_est_autorisee():
    article = _approvisionne(3)

    services.sortir_pour_or(article, quantite=3, ordre=_ouvrir())

    article.refresh_from_db()
    assert article.quantite == 0


def test_sortie_refusee_si_stock_insuffisant_et_ne_change_rien():
    article = _approvisionne(3)

    with pytest.raises(StockInsuffisant):
        services.sortir_pour_or(article, quantite=4, ordre=_ouvrir())

    article.refresh_from_db()
    assert article.quantite == 3
    assert MouvementStock.objects.filter(type_mouvement=TypeMouvement.SORTIE).count() == 0


@pytest.mark.parametrize("quantite", [0, -1])
def test_sortie_refuse_une_quantite_nulle_ou_negative(quantite):
    with pytest.raises(QuantiteInvalide):
        services.sortir_pour_or(
            _approvisionne(), quantite=quantite, ordre=_ouvrir()
        )


def test_sortie_refusee_sur_un_or_cloture():
    article = _approvisionne()
    ordre = _ouvrir()
    garage_services.cloturer_or(ordre)

    with pytest.raises(OrCloture):
        services.sortir_pour_or(article, quantite=1, ordre=ordre)

    article.refresh_from_db()
    assert article.quantite == 10


# --- alerte de seuil bas (cahier-des-charges.md:337-338) ---


def test_alerte_quand_la_sortie_atteint_le_seuil(alertes):
    article = _approvisionne(10, seuil_minimal=5)

    services.sortir_pour_or(article, quantite=4, ordre=_ouvrir())
    assert alertes == []  # 6 restants : encore au-dessus du seuil

    services.sortir_pour_or(article, quantite=1, ordre=_ouvrir())
    assert alertes == [article.reference]  # 5 restants = seuil atteint


def test_pas_de_nouvelle_alerte_tant_que_l_article_reste_sous_le_seuil(alertes):
    article = _approvisionne(10, seuil_minimal=5)
    ordre = _ouvrir()
    services.sortir_pour_or(article, quantite=6, ordre=ordre)  # 4 : alerte
    services.sortir_pour_or(article, quantite=1, ordre=ordre)  # 3 : déjà sous le seuil

    assert alertes == [article.reference]


def test_nouvelle_alerte_apres_reapprovisionnement_puis_nouveau_franchissement(alertes):
    article = _approvisionne(10, seuil_minimal=5)
    ordre = _ouvrir()
    services.sortir_pour_or(article, quantite=6, ordre=ordre)
    services.enregistrer_entree(article, quantite=20, prix_unitaire=Decimal("1000"))

    services.sortir_pour_or(article, quantite=20, ordre=ordre)

    assert alertes == [article.reference, article.reference]


def test_aucune_alerte_pour_un_article_sans_seuil(alertes):
    article = _approvisionne(3, seuil_minimal=0)

    services.sortir_pour_or(article, quantite=3, ordre=_ouvrir())

    assert alertes == []


def test_un_ajustement_negatif_peut_aussi_declencher_l_alerte(alertes):
    article = _approvisionne(10, seuil_minimal=5)

    services.ajuster_stock(article, variation=-5, motif="Inventaire : casse")

    assert alertes == [article.reference]


def test_une_entree_ne_declenche_jamais_d_alerte(alertes):
    article = ArticleFactory(seuil_minimal=5)

    services.enregistrer_entree(article, quantite=2, prix_unitaire=Decimal("10"))

    assert alertes == []


def test_articles_sous_seuil_liste_les_articles_a_reapprovisionner():
    bas = _approvisionne(5, seuil_minimal=5)
    _approvisionne(6, seuil_minimal=5)
    _approvisionne(1, seuil_minimal=0)  # non surveillé

    assert list(services.articles_sous_seuil()) == [bas]


# --- ajustement ---


def test_ajustement_positif_valorise_au_pump_sans_le_changer():
    article = _approvisionne(10, "1000")

    mouvement = services.ajuster_stock(article, variation=2, motif="Inventaire")

    article.refresh_from_db()
    assert (article.quantite, article.pump) == (12, Decimal("1000.00"))
    assert mouvement.type_mouvement == TypeMouvement.AJUSTEMENT
    assert mouvement.motif == "Inventaire"
    assert mouvement.ordre_reparation is None


def test_ajustement_negatif_diminue_le_stock():
    article = _approvisionne(10)

    services.ajuster_stock(article, variation=-3, motif="Pièces cassées")

    article.refresh_from_db()
    assert article.quantite == 7


def test_ajustement_refuse_un_stock_negatif():
    article = _approvisionne(2)

    with pytest.raises(StockInsuffisant):
        services.ajuster_stock(article, variation=-3, motif="Erreur")

    article.refresh_from_db()
    assert article.quantite == 2


def test_ajustement_refuse_une_variation_nulle():
    with pytest.raises(QuantiteInvalide):
        services.ajuster_stock(_approvisionne(), variation=0, motif="x")


@pytest.mark.parametrize("motif", ["", "   "])
def test_ajustement_exige_un_motif(motif):
    with pytest.raises(MotifRequis):
        services.ajuster_stock(_approvisionne(), variation=1, motif=motif)


# --- cohérence du journal ---


def test_la_quantite_en_stock_est_toujours_la_somme_des_variations():
    article = ArticleFactory()
    ordre = _ouvrir()
    services.enregistrer_entree(article, quantite=10, prix_unitaire=Decimal("1000"))
    services.sortir_pour_or(article, quantite=3, ordre=ordre)
    services.ajuster_stock(article, variation=-2, motif="Casse")
    services.enregistrer_entree(article, quantite=5, prix_unitaire=Decimal("1200"))
    services.sortir_pour_or(article, quantite=4, ordre=ordre)

    article.refresh_from_db()
    somme = article.mouvements.aggregate(total=Sum("variation"))["total"]
    assert article.quantite == somme == 6
    dernier = article.mouvements.order_by("-pk").first()
    assert dernier.quantite_apres == article.quantite


# --- coût des pièces d'un OR (cahier-des-charges.md:167-168) ---


def test_cout_des_pieces_valorise_chaque_sortie_au_pump_de_son_moment():
    article = _approvisionne(10, "1000")
    ordre = _ouvrir()
    services.sortir_pour_or(article, quantite=2, ordre=ordre)  # 2 x 1000
    services.enregistrer_entree(article, quantite=8, prix_unitaire=Decimal("2000"))
    # stock 16, PUMP = (8 x 1000 + 8 x 2000) / 16 = 1500
    services.sortir_pour_or(article, quantite=4, ordre=ordre)  # 4 x 1500

    assert services.cout_pieces(ordre) == Decimal("8000.00")


def test_cout_des_pieces_ignore_les_autres_or_et_les_ajustements():
    article = _approvisionne(10, "1000")
    ordre, autre = _ouvrir(), _ouvrir()
    services.sortir_pour_or(article, quantite=2, ordre=ordre)
    services.sortir_pour_or(article, quantite=5, ordre=autre)
    services.ajuster_stock(article, variation=-1, motif="Casse")

    assert services.cout_pieces(ordre) == Decimal("2000.00")


def test_cout_des_pieces_est_nul_sans_sortie():
    assert services.cout_pieces(_ouvrir()) == Decimal("0")


def test_cout_total_de_l_or_ajoute_la_main_d_oeuvre_aux_pieces():
    article = _approvisionne(10, "1000")
    ordre = _ouvrir()
    services.sortir_pour_or(article, quantite=3, ordre=ordre)
    garage_services.cloturer_or(ordre, cout_main_oeuvre=Decimal("45000"))

    assert services.cout_total(ordre) == Decimal("48000.00")
```

## Étape 5 — Déclarer l'application et migrer

#### `config/settings/base.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/settings/base.py (avant)
+++ config/settings/base.py (après)
@@ -58,4 +58,5 @@
     "apps.missions",
     "apps.garage",
+    "apps.inventory",
 ]
 
```

```bash
python manage.py makemigrations inventory
python manage.py migrate
```

**Résultat attendu :** `Create model Article`, `Create model MouvementStock`, puis
`Applying inventory.0001_initial... OK`.

## Vérifier le chapitre

```bash
python manage.py check
```

```bash
python -m pytest apps/inventory/tests/test_fiche.py apps/inventory/tests/test_models.py apps/inventory/tests/test_services.py -q --no-cov
```

**Résultat attendu :** `69 passed` (pour les 3 fichier(s) de tests présentés dans ce chapitre).

Essai dans le shell : vérifier le calcul du PUMP.

```bash
python manage.py shell -c "from decimal import Decimal; from apps.inventory import services as s; a = s.creer_article(reference='pn-0455', designation='Pneu 315/80 R22.5', seuil_minimal=4); s.enregistrer_entree(a, quantite=10, prix_unitaire=Decimal('1000')); s.enregistrer_entree(a, quantite=10, prix_unitaire=Decimal('2000')); a.refresh_from_db(); print(a.reference, a.quantite, a.pump)"
```

**Résultat attendu :** `PN-0455 20 1500.00`.

## Ce qu'il faut retenir

- Une valeur **dérivée d'un historique** (quantité, PUMP) ne se modifie que **par un mouvement** ; l'historique
  est immuable, on corrige par un nouveau mouvement.
- Ce qu'on arrondit (l'argent) s'arrondit **une seule fois, au bon endroit**, avec la règle prévue.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 11 : app inventory (stock de pièces, PUMP, mouvements, seuils)"
```

---

[← Chapitre 10](10-garage.md) · [Sommaire](README.md) · [Chapitre 12 →](12-fuel.md)
