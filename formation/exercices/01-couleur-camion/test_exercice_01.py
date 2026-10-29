"""Exercice 1 — Ajouter la couleur d'un camion (formation/exercices/01-couleur-camion).

À copier dans apps/fleet/tests/ puis : python -m pytest apps/fleet/tests/test_exercice_01.py -q --no-cov
"""

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.fleet import services
from apps.fleet.models import Vehicule
from apps.fleet.tests.factories import VehiculeFactory

pytestmark = pytest.mark.django_db

FICHE = {
    "immatriculation": "4321 CD 01", "marque": "Renault", "modele": "T480", "annee": "2022",
    "vin": "VF6T480000000001A", "kilometrage": "12000", "capacite_charge_t": "26.5", "reservoir_l": "700",
    "chauffeur_habituel": "",
}


def test_la_couleur_est_un_champ_facultatif_de_30_caracteres():
    champ = Vehicule._meta.get_field("couleur")

    assert champ.max_length == 30 and champ.blank


def test_le_service_enregistre_la_couleur_sans_espaces_autour():
    camion = services.creer_vehicule(
        immatriculation="1111 AB 01", marque="Volvo", modele="FH", annee=2021, vin="YV2RT40A5LB000001",
        kilometrage=0, capacite_charge_t=25, reservoir_l=600, couleur="  Blanc  ",
    )

    assert camion.couleur == "Blanc"


def test_un_camion_cree_sans_couleur_reste_valide():
    camion = services.creer_vehicule(
        immatriculation="2222 AB 01", marque="Volvo", modele="FH", annee=2021, vin="YV2RT40A5LB000002",
        kilometrage=0, capacite_charge_t=25, reservoir_l=600,
    )

    assert camion.couleur == ""


def test_l_ecran_cree_modifie_et_affiche_la_couleur(client):
    client.force_login(UserFactory(role=Role.PARCAUTO))

    client.post(reverse("fleet:creer"), {**FICHE, "couleur": "Bleu"})
    camion = Vehicule.objects.get()
    assert camion.couleur == "Bleu"

    page = client.get(reverse("fleet:modifier", args=[camion.pk])).content.decode()
    assert 'value="Bleu"' in page  # le formulaire de modification reprend la couleur

    client.post(reverse("fleet:modifier", args=[camion.pk]), {**FICHE, "couleur": "Rouge"})
    camion.refresh_from_db()
    assert camion.couleur == "Rouge"

    fiche = client.get(reverse("fleet:detail", args=[camion.pk])).content.decode()
    assert "Couleur" in fiche and "Rouge" in fiche


def test_la_fiche_d_un_camion_sans_couleur_affiche_un_tiret(client):
    client.force_login(UserFactory(role=Role.PARCAUTO))
    camion = VehiculeFactory()

    fiche = client.get(reverse("fleet:detail", args=[camion.pk])).content.decode()

    assert "Couleur" in fiche
