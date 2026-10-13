"""Export Excel des listes (mêmes droits et filtres que la liste, valeurs brutes) — audit TECH-83."""

import io
from datetime import date
from decimal import Decimal

import openpyxl
import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.customers.tests.factories import ClientFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.fuel.tests.factories import PleinFactory
from apps.garage.tests.factories import OrdreReparationFactory
from apps.hr.models import Conge
from apps.hr.tests.factories import PersonnelFactory
from apps.inventory.tests.factories import ArticleFactory
from apps.missions.tests.factories import MissionFactory

pytestmark = pytest.mark.django_db


def _conge():
    return Conge.objects.create(
        employe=PersonnelFactory(), date_debut=date(2026, 10, 5), date_fin=date(2026, 10, 9), jours=5, motif="Repos"
    )


EXPORTS = [
    # (route, paramètres, rôle autorisé, fabrique, en-tête attendu, valeur brute attendue dans la ligne)
    ("missions:xlsx", {}, Role.CHARGE_CLIENTELE, lambda: MissionFactory(prix_convenu=Decimal("850000")),
     "Prix convenu (FCFA)", 850000),
    ("fleet:xlsx", {}, Role.PARCAUTO, lambda: VehiculeFactory(kilometrage=120000), "Kilométrage", 120000),
    ("fuel:xlsx", {}, Role.PARCAUTO, lambda: PleinFactory(), "Montant (FCFA)", None),
    ("inventory:articles_xlsx", {}, Role.PARCAUTO, lambda: ArticleFactory(quantite=7), "Quantité", 7),
    ("customers:xlsx", {}, Role.CHARGE_CLIENTELE, lambda: ClientFactory(delai_paiement_jours=45),
     "Délai de paiement (jours)", 45),
    ("drivers:xlsx", {}, Role.RH, lambda: ChauffeurFactory(), "Permis valide jusqu'au", None),
    ("hr:conges_xlsx", {"vue": "tous"}, Role.RH, _conge, "Jours", 5),
    ("hr:personnel_xlsx", {}, Role.RH, lambda: PersonnelFactory(nom="Kouamé"), "Nom", "Kouamé"),
    ("garage:xlsx", {}, Role.PARCAUTO, lambda: OrdreReparationFactory(), "Main-d'œuvre (FCFA)", None),
]


@pytest.mark.parametrize("route, parametres, role, fabrique, entete, valeur", EXPORTS, ids=[e[0] for e in EXPORTS])
def test_chaque_liste_s_exporte_en_excel_avec_des_valeurs_brutes(client, route, parametres, role, fabrique, entete, valeur):
    fabrique()
    client.force_login(UserFactory(role=role))

    reponse = client.get(reverse(route), parametres)

    assert reponse.status_code == 200
    assert reponse["Content-Type"].startswith("application/vnd.openxmlformats-officedocument.spreadsheetml")
    lignes = list(openpyxl.load_workbook(io.BytesIO(reponse.content)).active.iter_rows(values_only=True))
    en_tetes = next(ligne for ligne in lignes if entete in ligne)
    donnees = lignes[lignes.index(en_tetes) + 1]
    colonne = en_tetes.index(entete)
    assert donnees[colonne] not in (None, "")
    if valeur is not None:
        assert donnees[colonne] == valeur  # nombre ou texte brut, sans « FCFA » ni séparateur


@pytest.mark.parametrize("route", ["fleet:xlsx", "hr:personnel_xlsx", "customers:xlsx"])
def test_l_export_garde_les_droits_de_la_liste(client, route):
    client.force_login(UserFactory(role=Role.CHAUFFEUR))

    assert client.get(reverse(route)).status_code in (302, 403)


def test_chaque_liste_affiche_le_bouton_excel(client):
    client.force_login(UserFactory(role=Role.PARCAUTO))

    for liste, export in (("fleet:liste", "fleet:xlsx"), ("fuel:liste", "fuel:xlsx"), ("garage:liste", "garage:xlsx")):
        assert reverse(export) in client.get(reverse(liste)).content.decode(), liste
