"""Rapport imprimable du tableau de bord : mêmes blocs et mêmes droits que l'écran."""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing.tests.helpers import emise
from apps.customers.tests.factories import ClientFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.missions.models import StatutMission
from apps.missions.tests.factories import MissionFactory

pytestmark = pytest.mark.django_db


def _texte(reponse) -> str:
    return reponse.content.decode().replace(" ", " ").replace("\xa0", " ")


def test_impression_du_tableau_de_bord_direction(client):
    client.force_login(UserFactory(role=Role.DIRECTION))
    VehiculeFactory(statut="DISPONIBLE")
    MissionFactory(client=ClientFactory(), statut=StatutMission.PLANIFIEE)

    reponse = client.get(reverse("home_imprimer"))

    assert reponse.status_code == 200
    texte = _texte(reponse)
    assert "Tableau de bord" in texte and "Direction" in texte
    assert "Exploitation" in texte and "Camions par statut" in texte
    assert "Finances du mois" in texte


def test_le_tableau_de_bord_du_chauffeur_n_est_pas_imprime_comme_un_bureau(client):
    from apps.hr.tests.factories import PersonnelFactory

    chauffeur = ChauffeurFactory(personnel=PersonnelFactory(utilisateur=UserFactory(role=Role.CHAUFFEUR)))
    client.force_login(chauffeur.personnel.utilisateur)

    texte = _texte(client.get(reverse("home_imprimer")))

    assert "Aucun rapport de bureau" in texte


def test_le_role_parcauto_ne_voit_pas_les_missions_dans_le_rapport(client):
    client.force_login(UserFactory(role=Role.PARCAUTO))
    VehiculeFactory(statut="DISPONIBLE")

    texte = _texte(client.get(reverse("home_imprimer")))

    assert "Camions par statut" in texte and "Missions par statut" not in texte


def test_le_rapport_suit_la_periode_demandee(client):
    client.force_login(UserFactory(role=Role.FINANCES))
    emise(prix="1000000", aujourd_hui=date(2026, 9, 1))

    reponse = client.get(reverse("home_imprimer"), {"periode": "12"})

    assert len(reponse.context["finances"]["graphique_mensuel"]["grappes"]) == 12


def test_un_role_sans_acces_financier_n_a_pas_ce_bloc(client):
    client.force_login(UserFactory(role=Role.RH))

    texte = _texte(client.get(reverse("home_imprimer")))

    assert "Finances du mois" not in texte and "Ressources humaines" in texte


def test_le_lien_imprimer_est_sur_le_tableau_de_bord(client):
    client.force_login(UserFactory(role=Role.DIRECTION))

    page = client.get(reverse("home")).content.decode()

    assert reverse("home_imprimer") in page
