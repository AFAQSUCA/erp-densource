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
