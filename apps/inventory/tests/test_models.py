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
