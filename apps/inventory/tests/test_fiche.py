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
