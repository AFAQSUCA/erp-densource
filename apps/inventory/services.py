"""Logique métier du stock — cahier-des-charges.md:177-183.

Chaque mouvement est atomique, verrouille l'article, met à jour la quantité
(et le PUMP en entrée) en temps réel et écrit une ligne immuable dans
``MouvementStock``. ``inventory`` dépend de ``garage`` (la sortie est liée à un
OR), jamais l'inverse.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import F, QuerySet

from apps.garage.models import OrdreReparation, StatutOr

from .exceptions import (
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
    """Crée un article à stock nul : le stock initial arrive par une entrée."""
    return Article.objects.create(
        reference=reference,
        designation=designation,
        categorie=categorie,
        emplacement=emplacement,
        seuil_minimal=seuil_minimal,
    )


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
