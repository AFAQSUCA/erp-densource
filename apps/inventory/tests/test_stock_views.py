"""Écrans du stock : articles, fiche, entrées, ajustements, journal."""

from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.garage import services as garage_services
from apps.garage.models import LieuReparation, TypeOr
from apps.inventory import services
from apps.inventory.models import Article, MouvementStock, TypeMouvement

from .factories import ArticleFactory

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    utilisateur = UserFactory(role=role)
    client.force_login(utilisateur)
    return utilisateur


def _messages(reponse):
    return [(m.level_tag, str(m)) for m in reponse.context["messages"]]


def _approvisionne(quantite=10, prix="1000", **surcharges):
    article = ArticleFactory(**surcharges)
    services.enregistrer_entree(article, quantite=quantite, prix_unitaire=Decimal(prix))
    return article


def _ordre():
    from apps.fleet.tests.factories import VehiculeFactory

    return garage_services.ouvrir_or(
        VehiculeFactory(), type_or=TypeOr.CURATIF, lieu=LieuReparation.INTERNE, motif="Freins"
    )


def _detail(article):
    return reverse("inventory:article_detail", args=[article.pk])


# --- accès par rôle ---


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.PARCAUTO])
def test_le_stock_est_consultable_par_le_parc_auto_la_direction_et_l_admin(client, role):
    _connecte(client, role)
    article = ArticleFactory()

    assert client.get(reverse("inventory:articles")).status_code == 200
    assert client.get(_detail(article)).status_code == 200
    assert client.get(reverse("inventory:mouvements")).status_code == 200


@pytest.mark.parametrize("role", [Role.RH, Role.FINANCES, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR])
def test_le_stock_est_interdit_aux_autres_roles(client, role):
    _connecte(client, role)
    article = ArticleFactory()

    for nom, args in (
        ("inventory:articles", []),
        ("inventory:article_detail", [article.pk]),
        ("inventory:article_creer", []),
        ("inventory:article_modifier", [article.pk]),
        ("inventory:mouvements", []),
    ):
        assert client.get(reverse(nom, args=args)).status_code == 403, nom


def test_la_direction_est_en_lecture_seule_sur_le_stock(client):
    _connecte(client, Role.DIRECTION)
    article = _approvisionne(10)

    assert client.get(reverse("inventory:article_creer")).status_code == 403
    assert client.get(reverse("inventory:article_modifier", args=[article.pk])).status_code == 403
    assert client.post(
        reverse("inventory:entree", args=[article.pk]), {"quantite": "5", "prix_unitaire": "900"}
    ).status_code == 403
    assert client.post(
        reverse("inventory:ajustement", args=[article.pk]), {"variation": "-3", "motif": "x"}
    ).status_code == 403
    article.refresh_from_db()
    assert article.quantite == 10


def test_un_visiteur_non_connecte_est_renvoye_vers_la_connexion(client):
    reponse = client.get(reverse("inventory:articles"))

    assert reponse.status_code == 302
    assert reponse.url.startswith(reverse("accounts:login"))


def test_le_menu_stock_est_visible_du_parc_auto_pas_de_la_rh(client):
    _connecte(client, Role.PARCAUTO)
    assert 'href="/stock/"' in client.get(reverse("home")).content.decode()

    autre = Client()
    _connecte(autre, Role.RH)
    assert 'href="/stock/"' not in autre.get(reverse("home")).content.decode()


# --- liste ---


def test_la_liste_affiche_les_articles_et_les_indicateurs(client):
    _connecte(client, Role.PARCAUTO)
    _approvisionne(10, "1000", reference="FR-1", designation="Plaquettes", categorie="Freinage")
    _approvisionne(4, "2500", reference="FI-2", designation="Filtre", seuil_minimal=5)

    reponse = client.get(reverse("inventory:articles"))
    contenu = reponse.content.decode().replace("\xa0", " ").replace(" ", " ")

    assert "FR-1" in contenu and "Plaquettes" in contenu and "Freinage" in contenu
    assert reponse.context["valeur_totale"] == Decimal("20000.00")
    assert "20 000 FCFA" in contenu
    assert reponse.context["nombre_sous_seuil"] == 1
    assert "Stock bas" in contenu


def test_la_liste_distingue_rupture_et_stock_bas(client):
    _connecte(client, Role.PARCAUTO)
    epuise = _approvisionne(2, seuil_minimal=3)
    services.ajuster_stock(epuise, variation=-2, motif="Vol")
    _approvisionne(3, seuil_minimal=5)

    contenu = client.get(reverse("inventory:articles")).content.decode()

    assert "Rupture" in contenu and "Stock bas" in contenu


def test_la_liste_vide_affiche_un_message(client):
    _connecte(client, Role.PARCAUTO)

    assert "Aucun article trouvé" in client.get(reverse("inventory:articles")).content.decode()


def test_la_liste_filtre_par_texte_categorie_et_seuil(client):
    _connecte(client, Role.PARCAUTO)
    moteur = _approvisionne(10, reference="MO-1", categorie="Moteur")
    bas = _approvisionne(1, reference="FR-1", categorie="Freinage", seuil_minimal=5)

    par_texte = client.get(reverse("inventory:articles"), {"q": "mo-1"})
    par_categorie = client.get(reverse("inventory:articles"), {"categorie": "Moteur"})
    sous_seuil = client.get(reverse("inventory:articles"), {"alerte": "1"})

    assert list(par_texte.context["articles"]) == [moteur]
    assert list(par_categorie.context["articles"]) == [moteur]
    assert list(sous_seuil.context["articles"]) == [bas]


def test_la_liste_est_paginee_par_20(client):
    _connecte(client, Role.PARCAUTO)
    for _ in range(21):
        ArticleFactory()

    assert len(client.get(reverse("inventory:articles"), {"page": 2}).context["articles"]) == 1


def test_la_liste_n_effectue_pas_une_requete_par_article(client, django_assert_max_num_queries):
    _connecte(client, Role.PARCAUTO)
    for _ in range(15):
        ArticleFactory()

    with django_assert_max_num_queries(12):
        client.get(reverse("inventory:articles"))


def test_les_donnees_saisies_sont_echappees_contre_le_xss(client):
    _connecte(client, Role.PARCAUTO)
    article = ArticleFactory(designation="<script>alert(1)</script>")

    for url in (reverse("inventory:articles"), _detail(article)):
        contenu = client.get(url).content.decode()
        assert "<script>alert(1)</script>" not in contenu
        assert "&lt;script&gt;" in contenu


# --- fiche ---


def test_la_fiche_affiche_les_indicateurs_et_le_journal(client):
    _connecte(client, Role.PARCAUTO)
    article = _approvisionne(10, "1000", reference="PLQ-1", emplacement="Rayon A2")
    ordre = _ordre()
    services.sortir_pour_or(article, quantite=3, ordre=ordre)
    services.ajuster_stock(article, variation=-1, motif="Pièce cassée")

    reponse = client.get(_detail(article))
    contenu = reponse.content.decode()

    assert "Rayon A2" in contenu
    assert ordre.numero in contenu and reverse("garage:detail", args=[ordre.pk]) in contenu
    assert "Pièce cassée" in contenu
    assert "achat à" in contenu
    assert [m.variation for m in reponse.context["mouvements"]] == [-1, -3, 10]


def test_la_fiche_propose_les_formulaires_au_parc_auto_seulement(client):
    article = _approvisionne(10)
    _connecte(client, Role.PARCAUTO)
    page = client.get(_detail(article)).content.decode()
    assert reverse("inventory:entree", args=[article.pk]) in page
    assert reverse("inventory:ajustement", args=[article.pk]) in page

    direction = Client()
    _connecte(direction, Role.DIRECTION)
    page = direction.get(_detail(article)).content.decode()
    assert reverse("inventory:entree", args=[article.pk]) not in page
    assert reverse("inventory:article_modifier", args=[article.pk]) not in page


def test_la_fiche_d_un_article_inconnu_est_introuvable(client):
    _connecte(client, Role.PARCAUTO)

    assert client.get(reverse("inventory:article_detail", args=[999999])).status_code == 404


def test_la_fiche_sans_mouvement_invite_a_enregistrer_une_entree(client):
    _connecte(client, Role.PARCAUTO)

    assert "entrée d'achat" in client.get(_detail(ArticleFactory())).content.decode()


# --- création et modification ---


def _donnees_article(**surcharges):
    donnees = {
        "reference": "fr-0012",
        "designation": "Plaquettes de frein",
        "categorie": "Freinage",
        "emplacement": "Rayon A1",
        "seuil_minimal": "4",
    }
    donnees.update(surcharges)
    return donnees


def test_creer_un_article(client):
    _connecte(client, Role.PARCAUTO)

    reponse = client.post(reverse("inventory:article_creer"), _donnees_article(), follow=True)

    article = Article.objects.get()
    assert reponse.redirect_chain[-1][0] == _detail(article)
    assert (article.reference, article.seuil_minimal, article.quantite) == ("FR-0012", 4, 0)
    assert any("FR-0012" in texte and "entrée d'achat" in texte for _, texte in _messages(reponse))


def test_creer_un_doublon_affiche_l_erreur_sans_creer(client):
    _connecte(client, Role.PARCAUTO)
    ArticleFactory(reference="FR-0012")

    reponse = client.post(reverse("inventory:article_creer"), _donnees_article())

    assert reponse.status_code == 200
    assert "déjà utilisée" in reponse.content.decode()
    assert Article.objects.count() == 1


@pytest.mark.parametrize(
    "champ", [{"reference": ""}, {"designation": ""}, {"seuil_minimal": "-1"}, {"seuil_minimal": "abc"}]
)
def test_creer_avec_des_donnees_invalides_est_refuse(client, champ):
    _connecte(client, Role.PARCAUTO)

    reponse = client.post(reverse("inventory:article_creer"), _donnees_article(**champ))

    assert reponse.status_code == 200 and reponse.context["form"].errors
    assert Article.objects.count() == 0


def test_le_formulaire_de_modification_est_prerempli_sans_la_reference(client):
    _connecte(client, Role.PARCAUTO)
    article = ArticleFactory(designation="Ancien", seuil_minimal=7)

    reponse = client.get(reverse("inventory:article_modifier", args=[article.pk]))

    assert reponse.context["form"].initial["designation"] == "Ancien"
    assert "reference" not in reponse.context["form"].fields


def test_modifier_un_article(client):
    _connecte(client, Role.PARCAUTO)
    article = _approvisionne(10, "1000")

    client.post(
        reverse("inventory:article_modifier", args=[article.pk]),
        {"designation": "Disques", "categorie": "Freinage", "emplacement": "B1", "seuil_minimal": "2"},
    )

    article.refresh_from_db()
    assert (article.designation, article.seuil_minimal) == ("Disques", 2)
    assert (article.quantite, article.pump) == (10, Decimal("1000.00"))


def test_modifier_avec_une_designation_vide_est_refuse(client):
    _connecte(client, Role.PARCAUTO)
    article = ArticleFactory(designation="Ancien")

    reponse = client.post(
        reverse("inventory:article_modifier", args=[article.pk]),
        {"designation": "", "seuil_minimal": "0"},
    )

    article.refresh_from_db()
    assert reponse.context["form"].errors and article.designation == "Ancien"


def test_modifier_un_article_inconnu_est_introuvable(client):
    _connecte(client, Role.PARCAUTO)

    assert client.get(reverse("inventory:article_modifier", args=[999999])).status_code == 404


# --- entrée d'achat ---


def test_enregistrer_une_entree_recalcule_le_pump_et_le_dit(client):
    utilisateur = _connecte(client, Role.PARCAUTO)
    article = _approvisionne(10, "1000")

    reponse = client.post(
        reverse("inventory:entree", args=[article.pk]),
        {"quantite": "10", "prix_unitaire": "2000"},
        follow=True,
    )

    article.refresh_from_db()
    assert (article.quantite, article.pump) == (20, Decimal("1500.00"))
    dernier = MouvementStock.objects.filter(type_mouvement=TypeMouvement.ENTREE).latest("pk")
    assert dernier.acteur == utilisateur
    assert any(
        "Stock : 20" in texte and "1 500 FCFA" in texte.replace(" ", " ")
        for _, texte in _messages(reponse)
    )


@pytest.mark.parametrize(
    "donnees",
    [
        {"quantite": "0", "prix_unitaire": "100"},
        {"quantite": "-3", "prix_unitaire": "100"},
        {"quantite": "x", "prix_unitaire": "100"},
        {"quantite": "1", "prix_unitaire": ""},
        {"quantite": "1", "prix_unitaire": "-5"},
    ],
)
def test_une_entree_invalide_est_refusee_par_le_formulaire(client, donnees):
    _connecte(client, Role.PARCAUTO)
    article = _approvisionne(10)

    client.post(reverse("inventory:entree", args=[article.pk]), donnees)

    article.refresh_from_db()
    assert article.quantite == 10


def test_un_prix_d_achat_nul_est_refuse_par_le_service_avec_un_message(client):
    _connecte(client, Role.PARCAUTO)
    article = _approvisionne(10)

    reponse = client.post(
        reverse("inventory:entree", args=[article.pk]),
        {"quantite": "1", "prix_unitaire": "0"},
        follow=True,
    )

    article.refresh_from_db()
    assert article.quantite == 10
    assert any("strictement positif" in texte for _, texte in _messages(reponse))


# --- ajustement d'inventaire ---


def test_ajuster_le_stock_a_la_hausse(client):
    _connecte(client, Role.PARCAUTO)
    article = _approvisionne(10, "1000")

    reponse = client.post(
        reverse("inventory:ajustement", args=[article.pk]),
        {"variation": "3", "motif": "Comptage annuel"},
        follow=True,
    )

    article.refresh_from_db()
    assert (article.quantite, article.pump) == (13, Decimal("1000.00"))
    assert any("+3" in texte for _, texte in _messages(reponse))
    assert MouvementStock.objects.filter(motif="Comptage annuel").exists()


def test_un_ajustement_qui_atteint_le_seuil_affiche_l_alerte_de_stock_bas(client):
    _connecte(client, Role.PARCAUTO)
    article = _approvisionne(10, seuil_minimal=5)

    reponse = client.post(
        reverse("inventory:ajustement", args=[article.pk]),
        {"variation": "-5", "motif": "Pièces cassées"},
        follow=True,
    )

    niveaux = _messages(reponse)
    assert any(niveau == "warning" and "Stock bas" in texte for niveau, texte in niveaux)


@pytest.mark.parametrize(
    "donnees",
    [
        {"variation": "0", "motif": "x"},
        {"variation": "5", "motif": ""},
        {"variation": "5", "motif": "   "},
        {"variation": "abc", "motif": "x"},
    ],
)
def test_un_ajustement_invalide_est_refuse(client, donnees):
    _connecte(client, Role.PARCAUTO)
    article = _approvisionne(10)

    client.post(reverse("inventory:ajustement", args=[article.pk]), donnees)

    article.refresh_from_db()
    assert article.quantite == 10
    assert MouvementStock.objects.filter(type_mouvement=TypeMouvement.AJUSTEMENT).count() == 0


def test_un_ajustement_qui_rendrait_le_stock_negatif_est_refuse(client):
    _connecte(client, Role.PARCAUTO)
    article = _approvisionne(2)

    reponse = client.post(
        reverse("inventory:ajustement", args=[article.pk]),
        {"variation": "-3", "motif": "Erreur"},
        follow=True,
    )

    article.refresh_from_db()
    assert article.quantite == 2
    assert any("négatif" in texte for _, texte in _messages(reponse))


def test_les_actions_de_stock_refusent_le_get_et_un_article_inconnu(client):
    _connecte(client, Role.PARCAUTO)
    article = _approvisionne(10)

    assert client.get(reverse("inventory:entree", args=[article.pk])).status_code == 405
    assert client.get(reverse("inventory:ajustement", args=[article.pk])).status_code == 405
    assert client.post(reverse("inventory:entree", args=[999999]), {}).status_code == 404
    assert client.post(reverse("inventory:ajustement", args=[999999]), {}).status_code == 404


# --- alerte de seuil à la sortie de pièces ---


def test_une_sortie_qui_atteint_le_seuil_affiche_l_alerte_de_stock_bas(client):
    _connecte(client, Role.PARCAUTO)
    article = _approvisionne(10, seuil_minimal=5)
    ordre = _ordre()

    reponse = client.post(
        reverse("inventory:sortie_or", args=[ordre.pk]),
        {"article": article.pk, "quantite": "5"},
        follow=True,
    )

    assert any(niveau == "warning" and article.reference in texte for niveau, texte in _messages(reponse))


def test_une_sortie_au_dessus_du_seuil_n_affiche_pas_d_alerte(client):
    _connecte(client, Role.PARCAUTO)
    article = _approvisionne(10, seuil_minimal=5)

    reponse = client.post(
        reverse("inventory:sortie_or", args=[_ordre().pk]),
        {"article": article.pk, "quantite": "2"},
        follow=True,
    )

    assert not any(niveau == "warning" for niveau, _ in _messages(reponse))


# --- journal ---


def test_le_journal_liste_et_filtre_les_mouvements(client):
    _connecte(client, Role.DIRECTION)
    article = _approvisionne(10, reference="PLQ-7")
    services.sortir_pour_or(article, quantite=2, ordre=_ordre())
    services.ajuster_stock(article, variation=-1, motif="Casse")

    tous = client.get(reverse("inventory:mouvements"))
    sorties = client.get(reverse("inventory:mouvements"), {"type": "SORTIE"})
    par_motif = client.get(reverse("inventory:mouvements"), {"q": "casse"})

    assert len(tous.context["mouvements"]) == 3
    assert [m.type_mouvement for m in sorties.context["mouvements"]] == ["SORTIE"]
    assert [m.motif for m in par_motif.context["mouvements"]] == ["Casse"]


def test_le_journal_vide_affiche_un_message(client):
    _connecte(client, Role.PARCAUTO)

    assert "Aucun mouvement trouvé" in client.get(reverse("inventory:mouvements")).content.decode()


def test_le_journal_est_pagine_par_30(client):
    _connecte(client, Role.PARCAUTO)
    article = _approvisionne(1)
    for _ in range(30):
        services.ajuster_stock(article, variation=1, motif="Comptage")

    page2 = client.get(reverse("inventory:mouvements"), {"page": 2})

    assert len(page2.context["mouvements"]) == 1


def test_le_journal_n_effectue_pas_une_requete_par_mouvement(client, django_assert_max_num_queries):
    _connecte(client, Role.PARCAUTO)
    article = _approvisionne(1)
    ordre = _ordre()
    for _ in range(10):
        services.ajuster_stock(article, variation=1, motif="Comptage")
    services.sortir_pour_or(article, quantite=2, ordre=ordre)

    with django_assert_max_num_queries(10):
        client.get(reverse("inventory:mouvements"))


def test_les_formulaires_du_stock_sont_proteges_par_csrf():
    client = Client(enforce_csrf_checks=True)
    client.force_login(UserFactory(role=Role.PARCAUTO))
    article = _approvisionne(10)

    assert client.post(reverse("inventory:article_creer"), _donnees_article()).status_code == 403
    assert client.post(
        reverse("inventory:entree", args=[article.pk]), {"quantite": "5", "prix_unitaire": "900"}
    ).status_code == 403
    assert client.post(
        reverse("inventory:ajustement", args=[article.pk]), {"variation": "-3", "motif": "x"}
    ).status_code == 403
    article.refresh_from_db()
    assert article.quantite == 10 and Article.objects.count() == 1
