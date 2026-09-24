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
from .signals import entree_stock_enregistree, seuil_bas_atteint

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
    mouvement = _enregistrer(
        article, TypeMouvement.ENTREE, quantite, prix, acteur=acteur
    )
    entree_stock_enregistree.send(sender=MouvementStock, mouvement=mouvement)
    return mouvement


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
