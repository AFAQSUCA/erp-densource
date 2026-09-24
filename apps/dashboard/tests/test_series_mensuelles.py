"""Séries mensuelles, créances par ancienneté et sélecteur de période des graphiques du tableau de bord."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services as billing
from apps.billing.models import ModePaiement
from apps.billing.tests.helpers import emise, finances
from apps.core import services as core
from apps.customers.tests.factories import ClientFactory
from apps.dashboard import services
from apps.finance import services as finance_services
from apps.fuel import services as fuel_services
from apps.fuel.tests.factories import PleinFactory
from apps.missions import services as missions_services
from apps.missions.models import Mission, StatutMission
from apps.missions.tests.factories import MissionFactory

pytestmark = pytest.mark.django_db


# --- mois ---


def test_les_debuts_de_mois_remontent_de_douze_mois_a_travers_l_annee():
    assert core.debuts_de_mois(date(2026, 2, 10), 4) == [date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1), date(2026, 2, 1)]
    assert core.debuts_de_mois(date(2026, 9, 24), 1) == [date(2026, 9, 1)]


def test_la_fin_de_mois_tient_compte_de_fevrier_et_des_annees_bissextiles():
    assert core.fin_de_mois(date(2026, 2, 1)) == date(2026, 2, 28)
    assert core.fin_de_mois(date(2028, 2, 1)) == date(2028, 2, 29)
    assert core.fin_de_mois(date(2026, 12, 1)) == date(2026, 12, 31)


# --- totaux par mois ---


def test_les_totaux_par_mois_sont_ceux_des_lectures_mois_par_mois():
    """Le graphique doit donner les mêmes chiffres que les indicateurs du mois (pas de logique en double)."""
    finance = finances()
    for jour, prix in ((date(2026, 7, 5), "1000000"), (date(2026, 8, 12), "2000000")):
        facture = emise(prix=prix, aujourd_hui=jour)
        billing.enregistrer_reglement(
            facture, finance, montant=Decimal("400000"), mode=ModePaiement.VIREMENT, date_reglement=jour
        )
        billing.enregistrer_depense(
            finance, categorie="PEAGES", date_depense=jour, libelle="Péage", montant=Decimal("30000"), mode=ModePaiement.ESPECES
        )
    PleinFactory(date_plein=date(2026, 8, 20))

    historique = finance_services.historique_mensuel(date(2026, 9, 15), mois=3)

    assert [ligne["debut"] for ligne in historique] == [date(2026, 7, 1), date(2026, 8, 1), date(2026, 9, 1)]
    for ligne in historique[:2]:
        direct = finance_services.indicateurs(ligne["debut"], ligne["fin"], aujourd_hui=ligne["fin"])
        assert ligne["chiffre_affaires"] == direct["chiffre_affaires"]
        assert ligne["encaisse"] == direct["encaisse"]
        assert ligne["charges"] == direct["charges"]["total"]
    assert historique[1]["charges"] == Decimal("30000") + Decimal("120.00") * Decimal("655")


def test_le_cout_du_carburant_par_mois_somme_litres_fois_prix():
    PleinFactory(date_plein=date(2026, 8, 3), quantite_litres=Decimal("100"), prix_unitaire=Decimal("600"))
    PleinFactory(date_plein=date(2026, 8, 25), quantite_litres=Decimal("50"), prix_unitaire=Decimal("700"))
    PleinFactory(date_plein=date(2026, 9, 2), quantite_litres=Decimal("10"), prix_unitaire=Decimal("650"))

    par_mois = fuel_services.cout_carburant_par_mois(date(2026, 8, 1), date(2026, 9, 30))

    assert par_mois == {(2026, 8): Decimal("95000"), (2026, 9): Decimal("6500")}


def test_les_missions_creees_et_livrees_sont_comptees_par_mois():
    from apps.drivers.tests.factories import ChauffeurFactory
    from apps.fleet.tests.factories import VehiculeFactory

    client = ClientFactory()
    ancienne = MissionFactory(client=client)
    Mission.objects.filter(pk=ancienne.pk).update(created_at=timezone.now() - timedelta(days=45))
    MissionFactory(client=client)
    livree = MissionFactory(
        client=client, statut=StatutMission.LIVREE, vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory()
    )
    Mission.objects.filter(pk=livree.pk).update(date_livraison=timezone.now())
    aujourd_hui = timezone.localdate()

    par_mois = missions_services.missions_par_mois(aujourd_hui - timedelta(days=90), aujourd_hui)

    courant = (aujourd_hui.year, aujourd_hui.month)
    assert par_mois["creees"][courant] == 2 and sum(par_mois["creees"].values()) == 3
    assert par_mois["livrees"] == {courant: 1}


def test_creances_par_anciennete_repartit_le_reste_a_recouvrer_par_retard():
    emise(prix="100000", aujourd_hui=date(2026, 8, 25))  # échéance 24/09 : pas encore échue
    emise(prix="200000", aujourd_hui=date(2026, 8, 1))  # échue depuis 24 j
    emise(prix="300000", aujourd_hui=date(2026, 7, 1))  # échue depuis 55 j
    emise(prix="400000", aujourd_hui=date(2026, 5, 1))  # échue depuis plus de 60 j

    tranches = billing.creances_par_anciennete(date(2026, 9, 24))

    assert [t["libelle"] for t in tranches] == [
        "Pas encore échu", "En retard de 1 à 30 jours", "En retard de 31 à 60 jours", "En retard de plus de 60 jours",
    ]
    assert [t["montant"] for t in tranches] == [Decimal("118000"), Decimal("236000"), Decimal("354000"), Decimal("472000")]
    assert [t["nombre"] for t in tranches] == [1, 1, 1, 1]
    assert [t["echu"] for t in tranches] == [False, True, True, True]


def test_un_reglement_reduit_la_tranche_de_la_creance():
    facture = emise(prix="1000000", aujourd_hui=date(2026, 8, 1))
    billing.enregistrer_reglement(
        facture, finances(), montant=Decimal("500000"), mode=ModePaiement.WAVE, date_reglement=date(2026, 8, 10)
    )

    tranches = billing.creances_par_anciennete(date(2026, 9, 24))

    assert tranches[1]["montant"] == Decimal("680000") and tranches[1]["nombre"] == 1


# --- sélecteur de période ---


@pytest.mark.parametrize("valeur, attendu", [("3", 3), ("6", 6), ("12", 12), ("24", 6), ("abc", 6), (None, 6), ("", 6)])
def test_la_periode_n_accepte_que_3_6_ou_12_mois(valeur, attendu):
    assert services.periode_valide(valeur) == attendu


def test_le_tableau_de_bord_suit_la_periode_choisie(client):
    client.force_login(UserFactory(role=Role.DIRECTION))

    reponse = client.get(reverse("home"), {"periode": "12"})

    assert reponse.context["periode"] == 12
    assert len(reponse.context["finances"]["graphique_mensuel"]["grappes"]) == 12
    assert len(reponse.context["exploitation"]["graphique_missions_mois"]["grappes"]) == 12
    assert 'aria-current="true"' in reponse.content.decode()


def test_une_periode_invalide_revient_a_six_mois(client):
    client.force_login(UserFactory(role=Role.DIRECTION))

    reponse = client.get(reverse("home"), {"periode": "9999"})

    assert reponse.context["periode"] == 6


def test_le_selecteur_de_periode_n_apparait_que_s_il_y_a_des_graphiques_dans_le_temps(client):
    client.force_login(UserFactory(role=Role.RH))

    assert "Graphiques dans le temps" not in client.get(reverse("home")).content.decode()

    client.force_login(UserFactory(role=Role.FINANCES))

    assert "Graphiques dans le temps" in client.get(reverse("home")).content.decode()


# --- drill-down et nouveaux graphiques ---


def test_chaque_barre_de_statut_mene_a_la_liste_filtree(client):
    client.force_login(UserFactory(role=Role.DIRECTION))
    MissionFactory(client=ClientFactory(), statut=StatutMission.PLANIFIEE)

    reponse = client.get(reverse("home"))

    exploitation = reponse.context["exploitation"]
    camions = {l["libelle"]: l["url"] for l in exploitation["graphique_camions"]["lignes"]}
    missions = {l["libelle"]: l["url"] for l in exploitation["graphique_missions"]["lignes"]}
    assert camions["Disponible"] == f"{reverse('fleet:liste')}?statut=DISPONIBLE"
    assert missions["Planifiée"] == f"{reverse('missions:liste')}?statut=PLANIFIEE"
    assert client.get(missions["Planifiée"]).status_code == 200


def test_le_graphique_des_creances_est_affiche_a_la_finance(client):
    client.force_login(UserFactory(role=Role.FINANCES))
    emise(prix="1000000", aujourd_hui=date(2026, 8, 1))

    reponse = client.get(reverse("home"))

    lignes = reponse.context["finances"]["graphique_creances"]["lignes"]
    assert lignes[1]["detail"] == "1 facture"
    assert lignes[1]["url"] == f"{reverse('billing:factures')}?echues=on"
    assert lignes[0]["url"] == ""  # rien d'échu dans la première tranche : pas de lien
    assert "Créances par ancienneté" in reponse.content.decode()


def test_le_graphique_des_comptes_a_un_axe_entier():
    from apps.core import graphiques

    g = graphiques.colonnes_groupees(["a"], [{"nom": "Créées", "valeurs": [10]}], entier=True)

    assert [t["etiquette"] for t in g["graduations"]] == ["20", "15", "10", "5", "0"]
