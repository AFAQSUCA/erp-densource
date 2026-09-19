"""Lectures des apps métier qui alimentent le tableau de bord."""

from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.customers import services as customers_services
from apps.customers.models import TypeInteraction
from apps.customers.tests.factories import ClientFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet import services as fleet_services
from apps.fleet.models import StatutVehicule
from apps.fleet.tests.factories import VehiculeFactory
from apps.fuel import services as fuel_services
from apps.hr import services as hr_services
from apps.hr.models import Conge, Departement, StatutConge
from apps.hr.tests.factories import PersonnelFactory
from apps.missions import services as missions_services
from apps.missions.models import StatutMission
from apps.missions.tests.factories import MissionFactory

pytestmark = pytest.mark.django_db

AUJOURD_HUI = date(2026, 9, 1)
MAINTENANT = datetime(2026, 9, 1, 8, 0, tzinfo=dt_timezone.utc)


# --- flotte ---


def test_repartition_des_camions_par_statut_avec_zeros_et_total():
    for statut in (StatutVehicule.DISPONIBLE, StatutVehicule.DISPONIBLE, StatutVehicule.EN_MAINTENANCE):
        VehiculeFactory(statut=statut)

    repartition = fleet_services.repartition_statuts()

    assert repartition[StatutVehicule.DISPONIBLE] == 2
    assert repartition[StatutVehicule.EN_MAINTENANCE] == 1
    assert repartition[StatutVehicule.HORS_SERVICE] == 0
    assert repartition["total"] == 3


def test_repartition_sans_camion():
    assert fleet_services.repartition_statuts()["total"] == 0


# --- missions ---


def test_repartition_des_missions_par_statut():
    MissionFactory(statut=StatutMission.PLANIFIEE)
    MissionFactory(statut=StatutMission.PLANIFIEE)
    MissionFactory(statut=StatutMission.BROUILLON)

    repartition = missions_services.repartition_par_statut()

    assert repartition[StatutMission.PLANIFIEE] == 2
    assert repartition[StatutMission.BROUILLON] == 1
    assert repartition[StatutMission.LIVREE] == 0


def test_clients_actifs_compte_les_clients_distincts_sur_90_jours():
    actif, autre, ancien = ClientFactory(), ClientFactory(), ClientFactory()
    MissionFactory(client=actif)
    MissionFactory(client=actif)  # deux missions, un seul client
    MissionFactory(client=autre)
    vieille = MissionFactory(client=ancien)
    type(vieille).objects.filter(pk=vieille.pk).update(created_at=timezone.now() - timedelta(days=120))

    assert missions_services.clients_actifs() == 2


def _livree(client, montant, *, jours=10, statut=StatutMission.LIVREE):
    mission = MissionFactory(
        client=client, statut=statut, prix_convenu=Decimal(montant),
        vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory(),
    )
    type(mission).objects.filter(pk=mission.pk).update(
        date_livraison=timezone.now() - timedelta(days=jours)
    )
    return mission


def test_meilleurs_clients_classes_par_montant_livre_ou_cloture():
    petit, gros, moyen, quatrieme = (ClientFactory(raison_sociale=n) for n in ("Petit", "Gros", "Moyen", "Quatrième"))
    _livree(gros, "900000")
    _livree(gros, "300000", statut=StatutMission.CLOTUREE)
    _livree(moyen, "800000")
    _livree(petit, "100000")
    _livree(quatrieme, "50000")

    classement = missions_services.meilleurs_clients(limite=3)

    assert [c["client"] for c in classement] == ["Gros", "Moyen", "Petit"]
    assert classement[0]["montant"] == Decimal("1200000") and classement[0]["missions"] == 2


def test_meilleurs_clients_ignore_les_missions_non_livrees_et_trop_anciennes():
    client = ClientFactory()
    MissionFactory(client=client, statut=StatutMission.PLANIFIEE, prix_convenu=Decimal("5000000"))
    _livree(client, "700000", jours=400)  # plus de 12 mois

    assert missions_services.meilleurs_clients() == []


def test_meilleurs_clients_departage_les_egalites_par_nom():
    b, a = ClientFactory(raison_sociale="Beta"), ClientFactory(raison_sociale="Alpha")
    _livree(b, "500000")
    _livree(a, "500000")

    assert [c["client"] for c in missions_services.meilleurs_clients()] == ["Alpha", "Beta"]


# --- clients ---


def test_reclamations_recentes_ne_compte_que_les_reclamations_des_30_derniers_jours():
    client, auteur = ClientFactory(), UserFactory(role=Role.CHARGE_CLIENTELE)
    for type_interaction, age in (
        (TypeInteraction.RECLAMATION, 2),
        (TypeInteraction.RECLAMATION, 20),
        (TypeInteraction.RECLAMATION, 45),  # trop ancienne
        (TypeInteraction.APPEL, 1),  # pas une réclamation
    ):
        customers_services.enregistrer_interaction(
            client, auteur, type_interaction=type_interaction, resume="x",
            date_interaction=timezone.now() - timedelta(days=age),
        )

    assert customers_services.reclamations_recentes() == 2


# --- RH ---


def _personnel(**surcharges):
    return PersonnelFactory(**surcharges)


def _conge(employe, statut, debut, fin, **surcharges):
    return Conge.objects.create(
        employe=employe, date_debut=debut, date_fin=fin, jours=5, motif="x", statut=statut, **surcharges
    )


def test_effectif_par_departement_avec_zeros():
    _personnel(departement=Departement.COMMERCIAL)
    _personnel(departement=Departement.COMMERCIAL)
    _personnel(departement=Departement.PARC_AUTO)

    effectif = {d["code"]: d["nombre"] for d in hr_services.effectif_par_departement()}

    assert effectif[Departement.COMMERCIAL] == 2 and effectif[Departement.PARC_AUTO] == 1
    assert effectif[Departement.DIRECTION] == 0
    assert len(effectif) == len(Departement.choices)


def test_absents_du_jour_inclut_les_conges_approuves_ou_en_cours_qui_couvrent_la_date():
    a, b, c, d = (_personnel() for _ in range(4))
    _conge(a, StatutConge.EN_COURS, date(2026, 8, 31), date(2026, 9, 4))
    _conge(b, StatutConge.APPROUVE, date(2026, 9, 1), date(2026, 9, 1))  # le jour même
    _conge(c, StatutConge.APPROUVE, date(2026, 9, 2), date(2026, 9, 5))  # pas encore
    _conge(d, StatutConge.REFUSE, date(2026, 8, 31), date(2026, 9, 4))  # refusé

    assert {x.employe for x in hr_services.absents_du_jour(AUJOURD_HUI)} == {a, b}


def test_prochains_conges_dans_les_30_jours_tries_par_date():
    a, b, c = _personnel(), _personnel(), _personnel()
    _conge(a, StatutConge.APPROUVE, date(2026, 9, 20), date(2026, 9, 25))
    _conge(b, StatutConge.APPROUVE, date(2026, 9, 5), date(2026, 9, 9))
    _conge(c, StatutConge.APPROUVE, date(2026, 12, 1), date(2026, 12, 5))  # trop loin

    assert [x.employe for x in hr_services.prochains_conges(AUJOURD_HUI)] == [b, a]


def test_conges_en_attente_par_niveau():
    a, b = _personnel(), _personnel()
    _conge(a, StatutConge.DEMANDE, date(2026, 10, 1), date(2026, 10, 5))
    _conge(a, StatutConge.DEMANDE, date(2026, 11, 1), date(2026, 11, 5))
    _conge(b, StatutConge.VALIDATION_N1, date(2026, 10, 1), date(2026, 10, 5))
    _conge(b, StatutConge.APPROUVE, date(2026, 12, 1), date(2026, 12, 5))

    assert hr_services.conges_en_attente() == {"n1": 2, "n2": 1}


def test_conges_en_retard_selon_le_delai_du_niveau_en_cours():
    a, b, c = _personnel(), _personnel(), _personnel()
    passe, futur = MAINTENANT - timedelta(hours=1), MAINTENANT + timedelta(hours=1)
    retard_n1 = _conge(a, StatutConge.DEMANDE, date(2026, 10, 1), date(2026, 10, 5), date_limite_n1=passe)
    _conge(b, StatutConge.DEMANDE, date(2026, 10, 1), date(2026, 10, 5), date_limite_n1=futur)
    retard_n2 = _conge(c, StatutConge.VALIDATION_N1, date(2026, 10, 1), date(2026, 10, 5), date_limite_n2=passe)
    _conge(a, StatutConge.APPROUVE, date(2026, 12, 1), date(2026, 12, 5), date_limite_n1=passe)

    assert set(hr_services.conges_en_retard(MAINTENANT)) == {retard_n1, retard_n2}


# --- carburant ---


def _plein_alerte(jours_avant):
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    debut = timezone.localdate() - timedelta(days=jours_avant + 5)
    fuel_services.enregistrer_plein(
        vehicule=camion, chauffeur=chauffeur, date_plein=debut, station="T",
        quantite_litres=Decimal("100"), prix_unitaire=Decimal("655"), km_compteur=1000,
        numero_ticket=f"D-{camion.pk}-0",
    )
    return fuel_services.enregistrer_plein(
        vehicule=camion, chauffeur=chauffeur, date_plein=timezone.localdate() - timedelta(days=jours_avant),
        station="T", quantite_litres=Decimal("200"), prix_unitaire=Decimal("655"),
        km_compteur=1400, numero_ticket=f"D-{camion.pk}-1", confirmer_alerte_saisie=True,
    )


def test_pleins_a_surveiller_peut_se_limiter_aux_pleins_recents():
    recent = _plein_alerte(3)
    ancien = _plein_alerte(60)  # 50 L/100 km : anomalie

    tous = set(fuel_services.pleins_a_surveiller())
    recents = set(
        fuel_services.pleins_a_surveiller(depuis=timezone.localdate() - timedelta(days=30))
    )

    assert {recent, ancien} <= tous
    assert recent in recents and ancien not in recents
