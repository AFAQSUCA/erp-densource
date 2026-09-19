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
