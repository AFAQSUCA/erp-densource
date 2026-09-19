"""Recherche des pleins et analyse par camion / chauffeur — cahier-des-charges.md:156."""

from datetime import date
from decimal import Decimal

import pytest

from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.fuel import services

from .test_services import _plein, _serie

pytestmark = pytest.mark.django_db


# --- recherche ---


def test_rechercher_pleins_par_camion_et_par_chauffeur():
    camion_a, camion_b = VehiculeFactory(), VehiculeFactory()
    chauffeur_a, chauffeur_b = ChauffeurFactory(), ChauffeurFactory()
    _plein(camion_a, chauffeur_a, km=1000, litres=100, jour=0)
    autre = _plein(camion_b, chauffeur_b, km=1000, litres=100, jour=0)

    assert list(services.rechercher_pleins(vehicule=camion_b)) == [autre]
    assert list(services.rechercher_pleins(chauffeur=chauffeur_b)) == [autre]


def test_rechercher_pleins_par_periode_bornes_incluses():
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    premier = _plein(camion, chauffeur, km=1000, litres=100, jour=0)  # 2026-09-01
    milieu = _plein(camion, chauffeur, km=1400, litres=120, jour=5)  # 2026-09-06
    dernier = _plein(camion, chauffeur, km=1800, litres=120, jour=10)  # 2026-09-11

    resultat = services.rechercher_pleins(date_debut=date(2026, 9, 6), date_fin=date(2026, 9, 6))

    assert list(resultat) == [milieu]
    assert set(services.rechercher_pleins(date_debut=date(2026, 9, 6))) == {milieu, dernier}
    assert set(services.rechercher_pleins(date_fin=date(2026, 9, 6))) == {premier, milieu}


def test_rechercher_pleins_par_texte_station_ou_ticket():
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    cible = _plein(
        camion, chauffeur, km=1000, litres=100, jour=0, station="Total Yopougon", numero_ticket="TKT-777"
    )
    _plein(VehiculeFactory(), chauffeur, km=1000, litres=100, jour=0)

    assert list(services.rechercher_pleins(recherche="yopougon")) == [cible]
    assert list(services.rechercher_pleins(recherche="tkt-777")) == [cible]


@pytest.mark.parametrize(
    ("alerte", "conso"),
    [
        ("JAUNE", "37"),  # +23 %
        ("ROUGE", "44"),  # +47 %
        ("ANOMALIE", "12"),  # sous 20 L/100 km (confirmé)
        ("SAISIE", "50"),  # +67 % (confirmé)
    ],
)
def test_rechercher_pleins_par_type_d_alerte(alerte, conso):
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _serie(camion, chauffeur, ["30"])
    dernier_km = 1400
    cible = _plein(
        camion, chauffeur, km=dernier_km + 400, litres=Decimal(conso) * 4, jour=5, confirmer=True
    )

    assert cible in services.rechercher_pleins(alerte=alerte)


def test_rechercher_pleins_a_surveiller_exclut_les_pleins_normaux():
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _serie(camion, chauffeur, ["30", "30"])

    assert services.rechercher_pleins(alerte="A_SURVEILLER").count() == 0
    _plein(camion, chauffeur, km=2200, litres=148, jour=5)  # 37 L/100 : jaune
    assert services.rechercher_pleins(alerte="A_SURVEILLER").count() == 1


def test_rechercher_pleins_ignore_une_alerte_inconnue_et_combine_les_criteres():
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    plein = _plein(camion, chauffeur, km=1000, litres=100, jour=0, station="Shell")
    _plein(VehiculeFactory(), chauffeur, km=1000, litres=100, jour=0, station="Shell")

    assert services.rechercher_pleins(alerte="???").count() == 2
    assert list(services.rechercher_pleins(vehicule=camion, recherche="shell")) == [plein]


def test_pleins_queryset_charge_camion_et_chauffeur_sans_requete_supplementaire(
    django_assert_num_queries,
):
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _plein(camion, chauffeur, km=1000, litres=100, jour=0)

    with django_assert_num_queries(1):
        for plein in services.pleins_queryset():
            plein.vehicule.immatriculation
            plein.chauffeur.personnel.nom


# --- analyse ---


def _deux_camions():
    camion_a, camion_b = VehiculeFactory(immatriculation="1111 AA 01"), VehiculeFactory(
        immatriculation="2222 BB 01"
    )
    chauffeur_a = ChauffeurFactory(personnel__prenom="Awa", personnel__nom="Koné")
    chauffeur_b = ChauffeurFactory(personnel__prenom="Issa", personnel__nom="Bamba")
    _serie(camion_a, chauffeur_a, ["30", "30"])  # 800 km, 240 L
    _serie(camion_b, chauffeur_b, ["40"])  # 400 km, 160 L
    return camion_a, camion_b


def test_consommation_par_vehicule_du_plus_gourmand_au_plus_econome():
    _deux_camions()

    resultat = services.consommation_par_vehicule()

    assert [g["libelle"] for g in resultat] == ["2222 BB 01", "1111 AA 01"]
    gourmand, econome = resultat
    assert (gourmand["consommation"], gourmand["pleins"], gourmand["distance"]) == (
        Decimal("40.00"),
        1,
        400,
    )
    assert (econome["consommation"], econome["pleins"], econome["distance"]) == (
        Decimal("30.00"),
        2,
        800,
    )
    assert econome["litres"] == Decimal("240.00")


def test_l_ecart_a_la_flotte_est_calcule_par_rapport_a_la_moyenne_ponderee():
    _deux_camions()  # flotte : 400 L / 1200 km = 33,33

    gourmand, econome = services.consommation_par_vehicule()

    assert gourmand["ecart_flotte_pct"] == Decimal("20.01")
    assert econome["ecart_flotte_pct"] == Decimal("-9.99")


def test_consommation_par_chauffeur_est_libellee_prenom_nom():
    _deux_camions()

    resultat = services.consommation_par_chauffeur()

    assert [g["libelle"] for g in resultat] == ["Issa Bamba", "Awa Koné"]
    assert resultat[0]["consommation"] == Decimal("40.00")


def test_deux_chauffeurs_homonymes_restent_distincts():
    camion = VehiculeFactory()
    premier = ChauffeurFactory(personnel__prenom="Awa", personnel__nom="Koné")
    second = ChauffeurFactory(personnel__prenom="Awa", personnel__nom="Koné")
    _plein(camion, premier, km=1000, litres=100, jour=0)
    _plein(camion, premier, km=1400, litres=120, jour=1)
    _plein(camion, second, km=1800, litres=160, jour=2)

    resultat = services.consommation_par_chauffeur()

    assert len(resultat) == 2
    assert {g["id"] for g in resultat} == {premier.pk, second.pk}


def test_l_analyse_signale_une_consommation_moyenne_hors_plage():
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _serie(camion, chauffeur, ["50"])  # 50 L/100 km : anomalie (confirmée)

    assert services.consommation_par_vehicule()[0]["anomalie"] is True


def test_l_analyse_est_vide_sans_consommation_calculee():
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _plein(camion, chauffeur, km=1000, litres=100, jour=0)  # premier plein : pas de conso

    assert services.consommation_par_vehicule() == []
    assert services.consommation_par_chauffeur() == []
