"""Bloc « Pièces utilisées » de la fiche d'un OR et sortie de pièces par l'écran."""

from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.garage import services as garage_services
from apps.garage.models import LieuReparation, TypeOr
from apps.inventory import services
from apps.inventory.models import MouvementStock, TypeMouvement

from .factories import ArticleFactory

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    utilisateur = UserFactory(role=role)
    client.force_login(utilisateur)
    return utilisateur


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


def _ordre():
    from apps.fleet.tests.factories import VehiculeFactory

    return garage_services.ouvrir_or(
        VehiculeFactory(), type_or=TypeOr.CURATIF, lieu=LieuReparation.INTERNE, motif="Freins"
    )


def _article(quantite=10, prix="1000", **surcharges):
    article = ArticleFactory(**surcharges)
    services.enregistrer_entree(article, quantite=quantite, prix_unitaire=Decimal(prix))
    return article


def _detail(client, ordre):
    return client.get(reverse("garage:detail", args=[ordre.pk]))


# --- lecture ---


def test_articles_en_stock_exclut_les_articles_epuises_et_est_trie():
    b, a = _article(reference="B-1"), _article(reference="A-1")
    ArticleFactory(reference="Z-0")  # jamais approvisionné

    assert list(services.articles_en_stock()) == [a, b]


def test_sorties_de_l_or_ne_liste_que_les_sorties_de_cet_or():
    article = _article()
    ordre, autre = _ordre(), _ordre()
    services.sortir_pour_or(article, quantite=2, ordre=ordre)
    services.sortir_pour_or(article, quantite=1, ordre=autre)
    services.ajuster_stock(article, variation=-1, motif="Casse")

    sorties = list(services.sorties_de_l_or(ordre))

    assert len(sorties) == 1 and sorties[0].variation == -2


# --- bloc dans la fiche de l'OR ---


def test_la_fiche_de_l_or_affiche_les_pieces_et_le_cout_total(client):
    _connecte(client, Role.PARCAUTO)
    article = _article(10, "1000", reference="PLQ-01", designation="Plaquettes de frein")
    ordre = _ordre()
    services.sortir_pour_or(article, quantite=3, ordre=ordre)
    garage_services.cloturer_or(ordre, cout_main_oeuvre=Decimal("45000"))

    reponse = _detail(client, ordre)
    # Les espaces insécables des séparateurs de milliers sont normalisées.
    contenu = reponse.content.decode().replace(" ", " ").replace(" ", " ")

    assert "Pièces utilisées" in contenu
    assert "PLQ-01" in contenu and "Plaquettes de frein" in contenu
    assert "3 000" in contenu  # 3 x 1000 : montant de la ligne et total des pièces
    assert "45 000" in contenu  # main-d'œuvre
    assert "48 000" in contenu  # coût total
    bloc = reponse.context["sections"][0]["contexte"]
    assert bloc["cout_pieces"] == Decimal("3000.00")
    assert bloc["cout_total"] == Decimal("48000.00")
    assert bloc["lignes"][0]["quantite"] == 3
    assert bloc["lignes"][0]["montant"] == Decimal("3000.00")


def test_la_fiche_sans_sortie_le_dit(client):
    _connecte(client, Role.PARCAUTO)
    ordre = _ordre()

    assert "Aucune pièce sortie du stock" in _detail(client, ordre).content.decode()


def test_le_formulaire_de_sortie_est_propose_au_parc_auto_et_a_la_direction_sur_un_or_ouvert(client):
    """Retour réunion : la DIRECTION a désormais la même largeur que l'ADMIN (MODIFICATION)."""
    ordre = _ordre()
    _article()
    _connecte(client, Role.PARCAUTO)
    url = reverse("inventory:sortie_or", args=[ordre.pk])
    assert url in _detail(client, ordre).content.decode()

    direction = Client()
    _connecte(direction, Role.DIRECTION)
    assert url in _detail(direction, ordre).content.decode()

    garage_services.cloturer_or(ordre)
    assert url not in _detail(client, ordre).content.decode()


def test_le_choix_des_pieces_ne_propose_que_les_articles_en_stock(client):
    _connecte(client, Role.PARCAUTO)
    _article(reference="EN-STOCK")
    ArticleFactory(reference="EPUISE")
    ordre = _ordre()

    contenu = _detail(client, ordre).content.decode()

    assert "EN-STOCK" in contenu and "EPUISE" not in contenu


# --- sortie de pièces ---


def test_sortir_des_pieces_par_l_ecran(client):
    utilisateur = _connecte(client, Role.PARCAUTO)
    article = _article(10, "1000")
    ordre = _ordre()

    reponse = client.post(
        reverse("inventory:sortie_or", args=[ordre.pk]),
        {"article": article.pk, "quantite": "4"},
        follow=True,
    )

    article.refresh_from_db()
    mouvement = MouvementStock.objects.get(type_mouvement=TypeMouvement.SORTIE)
    assert article.quantite == 6
    assert (mouvement.variation, mouvement.ordre_reparation, mouvement.acteur) == (-4, ordre, utilisateur)
    assert reponse.redirect_chain[-1][0] == reverse("garage:detail", args=[ordre.pk])
    assert any(article.reference in m for m in _messages(reponse))


def test_sortir_plus_que_le_stock_est_refuse_avec_un_message(client):
    _connecte(client, Role.PARCAUTO)
    article = _article(3)
    ordre = _ordre()

    reponse = client.post(
        reverse("inventory:sortie_or", args=[ordre.pk]),
        {"article": article.pk, "quantite": "4"},
        follow=True,
    )

    article.refresh_from_db()
    assert article.quantite == 3
    assert any("Stock insuffisant" in m for m in _messages(reponse))


def test_sortir_sur_un_or_cloture_est_refuse(client):
    _connecte(client, Role.PARCAUTO)
    article = _article()
    ordre = _ordre()
    garage_services.cloturer_or(ordre)

    reponse = client.post(
        reverse("inventory:sortie_or", args=[ordre.pk]),
        {"article": article.pk, "quantite": "1"},
        follow=True,
    )

    article.refresh_from_db()
    assert article.quantite == 10
    assert any("clôturé" in m for m in _messages(reponse))


@pytest.mark.parametrize("donnees", [{"quantite": "0"}, {"quantite": "-2"}, {"quantite": "x"}, {"article": ""}])
def test_une_sortie_invalide_est_refusee_par_le_formulaire(client, donnees):
    _connecte(client, Role.PARCAUTO)
    article = _article()
    ordre = _ordre()
    envoi = {"article": article.pk, "quantite": "1"}
    envoi.update(donnees)

    client.post(reverse("inventory:sortie_or", args=[ordre.pk]), envoi)

    article.refresh_from_db()
    assert article.quantite == 10


def test_un_article_epuise_ne_peut_pas_etre_sorti(client):
    _connecte(client, Role.PARCAUTO)
    epuise = ArticleFactory()
    ordre = _ordre()

    client.post(reverse("inventory:sortie_or", args=[ordre.pk]), {"article": epuise.pk, "quantite": "1"})

    assert MouvementStock.objects.count() == 0


@pytest.mark.parametrize("role", [Role.RH, Role.FINANCES, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR])
def test_la_sortie_est_interdite_hors_parc_auto_et_direction(client, role):
    _connecte(client, role)
    article = _article()
    ordre = _ordre()

    reponse = client.post(reverse("inventory:sortie_or", args=[ordre.pk]), {"article": article.pk, "quantite": "1"})

    article.refresh_from_db()
    assert reponse.status_code == 403 and article.quantite == 10


def test_la_sortie_refuse_le_get_et_un_or_inconnu(client):
    _connecte(client, Role.PARCAUTO)
    ordre = _ordre()

    assert client.get(reverse("inventory:sortie_or", args=[ordre.pk])).status_code == 405
    assert client.post(reverse("inventory:sortie_or", args=[999999]), {}).status_code == 404


def test_la_sortie_est_protegee_par_csrf():
    client = Client(enforce_csrf_checks=True)
    client.force_login(UserFactory(role=Role.PARCAUTO))
    article = _article()
    ordre = _ordre()

    reponse = client.post(reverse("inventory:sortie_or", args=[ordre.pk]), {"article": article.pk, "quantite": "1"})

    article.refresh_from_db()
    assert reponse.status_code == 403 and article.quantite == 10


# --- gardes des blocs (défense en profondeur) ---


@pytest.mark.parametrize("role", [Role.RH, Role.FINANCES, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR])
def test_le_bloc_pieces_n_est_jamais_fourni_aux_roles_sans_acces(role):
    from types import SimpleNamespace

    from apps.inventory import sections

    assert sections.section_pieces(_ordre(), SimpleNamespace(role_effectif=role)) is None
