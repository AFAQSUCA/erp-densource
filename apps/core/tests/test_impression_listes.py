"""Écrans d'impression des listes métier (``ImpressionListeMixin``) : accès, contenu, filtres repris."""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing.models import CategorieDepense, ModePaiement
from apps.billing.tests.helpers import brouillon, emise
from apps.customers.tests.factories import ClientFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.models import StatutVehicule
from apps.fleet.tests.factories import VehiculeFactory
from apps.fuel.tests.factories import PleinFactory
from apps.garage.models import LieuReparation, TypeOr
from apps.garage.tests.factories import OrdreReparationFactory
from apps.hr.models import Departement, StatutConge
from apps.hr.tests.factories import PersonnelFactory
from apps.inventory.tests.factories import ArticleFactory
from apps.missions.models import StatutMission
from apps.missions.tests.factories import MissionFactory

pytestmark = pytest.mark.django_db


def _texte(reponse) -> str:
    return reponse.content.decode().replace(" ", " ").replace("\xa0", " ")


# --- missions ---


def test_impression_des_missions(client):
    client.force_login(UserFactory(role=Role.DIRECTION))
    MissionFactory(numero="MIS-2026-0099", client=ClientFactory(raison_sociale="Bolloré"), statut=StatutMission.PLANIFIEE)

    reponse = client.get(reverse("missions:imprimer"), {"statut": "PLANIFIEE"})

    assert reponse.status_code == 200
    texte = _texte(reponse)
    assert "Missions" in texte and "MIS-2026-0099" in texte and "Bolloré" in texte
    assert "statut : Planifiée" in texte


def test_impression_des_missions_refusee_hors_role(client):
    client.force_login(UserFactory(role=Role.RH))

    assert client.get(reverse("missions:imprimer")).status_code == 403


# --- flotte ---


def test_impression_de_la_flotte(client):
    client.force_login(UserFactory(role=Role.PARCAUTO))
    VehiculeFactory(immatriculation="TEST 01 CI", statut=StatutVehicule.DISPONIBLE)

    reponse = client.get(reverse("fleet:imprimer"))

    assert "TEST 01 CI" in _texte(reponse) and "Flotte" in _texte(reponse)


# --- personnel et congés ---


def test_impression_du_personnel_sans_le_salaire(client):
    client.force_login(UserFactory(role=Role.RH))
    PersonnelFactory(nom="Diomandé", departement=Departement.EXPLOITATION, salaire_base=Decimal("999999"))

    texte = _texte(client.get(reverse("hr:personnel_imprimer"), {"departement": Departement.EXPLOITATION}))

    assert "Diomandé" in texte and "département : Exploitation" in texte
    assert "999" not in texte.replace("999999", "")  # le salaire n'est pas dans les colonnes imprimées


def test_impression_des_conges(client):
    rh = UserFactory(role=Role.RH)
    client.force_login(rh)
    chef = PersonnelFactory(nom="Chef", utilisateur=UserFactory(role=Role.PARCAUTO))
    employe = PersonnelFactory(nom="Koffi", superieur=chef)
    from apps.hr import services as hr_services

    hr_services.demander_conge(employe, date_debut=date(2026, 10, 5), date_fin=date(2026, 10, 9), motif="Repos")

    texte = _texte(client.get(reverse("hr:conges_imprimer"), {"vue": "tous"}))

    assert "Koffi" in texte and "tous les congés" in texte


# --- chauffeurs ---


def test_impression_des_chauffeurs(client):
    client.force_login(UserFactory(role=Role.RH))
    ChauffeurFactory(personnel__nom="Traoré", numero_permis="P-123")

    texte = _texte(client.get(reverse("drivers:imprimer")))

    assert "Traoré" in texte and "P-123" in texte


# --- stock ---


def test_impression_du_stock(client):
    client.force_login(UserFactory(role=Role.PARCAUTO))
    ArticleFactory(reference="PN-1", designation="Pneu", quantite=5, pump=Decimal("10000"))

    texte = _texte(client.get(reverse("inventory:articles_imprimer")))

    assert "PN-1" in texte and "Pneu" in texte and "50 000" in texte  # valeur en stock = 5 x 10 000


# --- garage : OR et incidents ---


def test_impression_des_or(client):
    client.force_login(UserFactory(role=Role.PARCAUTO))
    OrdreReparationFactory(numero="OR-2026-0099", type_or=TypeOr.CURATIF, lieu=LieuReparation.INTERNE)

    texte = _texte(client.get(reverse("garage:imprimer"), {"type": "CURATIF"}))

    assert "OR-2026-0099" in texte and "type : Curatif" in texte


# --- carburant ---


def test_impression_des_pleins(client):
    client.force_login(UserFactory(role=Role.PARCAUTO))
    PleinFactory(numero_ticket="TK-99", quantite_litres=Decimal("100"), prix_unitaire=Decimal("600"))

    texte = _texte(client.get(reverse("fuel:imprimer")))

    assert "TK-99" not in texte  # le ticket n'est pas dans les colonnes, mais le montant l'est
    assert "60 000" in texte


# --- clients ---


def test_impression_des_clients(client):
    client.force_login(UserFactory(role=Role.CHARGE_CLIENTELE))
    ClientFactory(raison_sociale="Sonatel Logistique")

    texte = _texte(client.get(reverse("customers:imprimer")))

    assert "Sonatel Logistique" in texte


# --- factures et dépenses ---


def test_impression_des_factures(client):
    client.force_login(UserFactory(role=Role.FINANCES))
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 1))
    brouillon(prix="500000")

    texte = _texte(client.get(reverse("billing:factures_imprimer"), {"statut": "EMISE"}))

    assert facture.numero in texte and "statut : Émise" in texte and "Sans numéro" not in texte


def test_impression_des_depenses_indique_l_origine(client):
    client.force_login(UserFactory(role=Role.FINANCES))
    from apps.billing import services as billing_services
    from apps.billing.tests.helpers import finances

    billing_services.enregistrer_depense(
        finances(), categorie="PEAGES", date_depense=date(2026, 9, 1), libelle="Péage",
        montant=Decimal("15000"), mode=ModePaiement.ESPECES,
    )
    from apps.fuel import services as fuel_services

    fuel_services.enregistrer_plein(
        vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory(), date_plein=date(2026, 9, 2), station="Total",
        quantite_litres=Decimal("50"), prix_unitaire=Decimal("600"), km_compteur=1000, numero_ticket="T-1",
    )

    texte = _texte(client.get(reverse("billing:depenses_imprimer")))

    assert "Péage" in texte and "Saisie" in texte
    assert "Carburant" in texte and "Automatique" in texte


# --- limite de lignes ---


def test_au_dela_de_la_limite_le_rapport_previent_et_tronque(monkeypatch, client):
    from apps.missions.views import MissionImprimerView

    monkeypatch.setattr(MissionImprimerView, "limite_impression", 2)
    client.force_login(UserFactory(role=Role.DIRECTION))
    for _ in range(3):
        MissionFactory(client=ClientFactory())

    reponse = client.get(reverse("missions:imprimer"))

    assert reponse.context["nombre"] == 2 and reponse.context["tronque"] is True
    assert "limité" in _texte(reponse)


# --- lien "Imprimer" présent sur chaque liste, avec les filtres actuels ---


@pytest.mark.parametrize(
    "role, url_liste, url_imprimer, requete",
    [
        (Role.DIRECTION, "missions:liste", "missions:imprimer", {"statut": "PLANIFIEE"}),
        (Role.PARCAUTO, "fleet:liste", "fleet:imprimer", {"statut": "DISPONIBLE"}),
        (Role.RH, "hr:personnel_liste", "hr:personnel_imprimer", {"departement": "RH"}),
        (Role.RH, "drivers:liste", "drivers:imprimer", {}),
        (Role.PARCAUTO, "inventory:articles", "inventory:articles_imprimer", {}),
        (Role.PARCAUTO, "garage:liste", "garage:imprimer", {}),
        (Role.PARCAUTO, "garage:incidents", "garage:incidents_imprimer", {}),
        (Role.PARCAUTO, "fuel:liste", "fuel:imprimer", {}),
        (Role.CHARGE_CLIENTELE, "customers:liste", "customers:imprimer", {}),
        (Role.FINANCES, "billing:factures", "billing:factures_imprimer", {}),
        (Role.FINANCES, "billing:depenses", "billing:depenses_imprimer", {}),
    ],
)
def test_le_lien_imprimer_reprend_les_filtres_de_la_liste(client, role, url_liste, url_imprimer, requete):
    client.force_login(UserFactory(role=role))

    page = client.get(reverse(url_liste), requete).content.decode()

    lien = reverse(url_imprimer)
    assert lien in page
    for cle, valeur in requete.items():
        assert f"{cle}%3D{valeur}" in page or f"{cle}={valeur}" in page
