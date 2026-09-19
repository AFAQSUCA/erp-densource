"""API mobile /api/v1/mobile/ : accès, isolement entre chauffeurs, secrets, cycle, erreurs HTTP."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.garage.models import Incident
from apps.missions.models import StatutMission

from .helpers import CODE_DESTINATAIRE, CODE_EXPEDITEUR, checklist_ok, chauffeur_avec_compte, mission_de

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _vider_le_cache():
    cache.clear()


def _api(compte):
    client = APIClient()
    client.force_authenticate(compte)
    return client


@pytest.fixture
def chauffeur():
    fiche, compte = chauffeur_avec_compte()
    return fiche, compte, _api(compte)


# --- accès ---


URLS_SANS_ARGUMENT = [
    "api:mobile:missions", "api:mobile:pleins", "api:mobile:incidents",
]


@pytest.mark.parametrize("nom", URLS_SANS_ARGUMENT)
def test_les_ressources_mobiles_exigent_un_compte_chauffeur(nom):
    assert APIClient().get(reverse(nom)).status_code == 401
    for role in (Role.ADMIN, Role.DIRECTION, Role.PARCAUTO, Role.RH, Role.FINANCES, Role.CHARGE_CLIENTELE):
        assert _api(UserFactory(role=role)).get(reverse(nom)).status_code == 403, (nom, role)


def test_un_compte_chauffeur_sans_fiche_du_personnel_est_refuse():
    orphelin = UserFactory(role=Role.CHAUFFEUR)

    assert _api(orphelin).get(reverse("api:mobile:missions")).status_code == 403


def test_un_vrai_jeton_jwt_de_chauffeur_ouvre_l_api_mobile():
    fiche, compte = chauffeur_avec_compte()
    mission_de(fiche)

    reponse = APIClient().get(
        reverse("api:mobile:missions"), HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(compte)}"
    )

    assert reponse.status_code == 200 and len(reponse.data) == 1


# --- missions ---


def test_le_chauffeur_ne_voit_que_ses_missions(chauffeur):
    fiche, _, api = chauffeur
    a_moi = mission_de(fiche)
    mission_de(ChauffeurFactory())

    reponse = api.get(reverse("api:mobile:missions"))

    assert [m["id"] for m in reponse.data] == [a_moi.pk]
    assert reponse.data[0]["actions"]["demarrer"] is True and reponse.data[0]["checklist_faite"] is False


def test_les_codes_secrets_et_le_prix_ne_sont_jamais_exposes(chauffeur):
    fiche, _, api = chauffeur
    mission = mission_de(fiche)

    for reponse in (api.get(reverse("api:mobile:missions")), api.get(reverse("api:mobile:mission", args=[mission.pk]))):
        texte = reponse.content.decode()
        assert CODE_EXPEDITEUR not in texte and CODE_DESTINATAIRE not in texte
        assert "code_expediteur" not in texte and "prix_convenu" not in texte and "850000" not in texte


def test_la_mission_d_un_autre_chauffeur_est_un_404_partout(chauffeur):
    _, _, api = chauffeur
    autre = mission_de(ChauffeurFactory())

    assert api.get(reverse("api:mobile:mission", args=[autre.pk])).status_code == 404
    for nom, corps in (
        ("demarrer", {}), ("recuperation", {"code": CODE_EXPEDITEUR}),
        ("livraison", {"code": CODE_DESTINATAIRE, "km_arrivee": 999999}), ("checklist", {"points": []}),
    ):
        reponse = api.post(reverse(f"api:mobile:{nom}", args=[autre.pk]), corps, format="json")
        assert reponse.status_code == 404, nom
        assert reponse.data["code"] == "mission_introuvable"
    autre.refresh_from_db()
    assert autre.statut == StatutMission.AFFECTEE  # rien n'a bougé


def test_cycle_de_la_mission_par_l_api(chauffeur):
    fiche, _, api = chauffeur
    mission = mission_de(fiche)
    km_depart = mission.vehicule.kilometrage

    demarrage = api.post(reverse("api:mobile:demarrer", args=[mission.pk]))
    recuperation = api.post(
        reverse("api:mobile:recuperation", args=[mission.pk]), {"code": CODE_EXPEDITEUR}, format="json"
    )
    livraison = api.post(
        reverse("api:mobile:livraison", args=[mission.pk]),
        {"code": CODE_DESTINATAIRE, "km_arrivee": km_depart + 400}, format="json",
    )

    assert [demarrage.status_code, recuperation.status_code, livraison.status_code] == [200, 200, 200]
    assert demarrage.data["statut"] == "EN_COURS_DEPART"
    assert recuperation.data["statut"] == "EN_COURS_COLIS_RECUPERE"
    assert livraison.data["statut"] == "LIVREE" and livraison.data["km_arrivee"] == km_depart + 400
    assert livraison.data["actions"] == {
        "checklist": False, "demarrer": False, "recuperation": False, "livraison": False,
    }


def test_les_refus_metier_donnent_un_400_avec_un_code_lisible(chauffeur):
    fiche, _, api = chauffeur
    mission = mission_de(fiche)

    trop_tot = api.post(reverse("api:mobile:recuperation", args=[mission.pk]), {"code": CODE_EXPEDITEUR}, format="json")
    api.post(reverse("api:mobile:demarrer", args=[mission.pk]))
    faux = api.post(reverse("api:mobile:recuperation", args=[mission.pk]), {"code": "FAUX0000"}, format="json")
    deja = api.post(reverse("api:mobile:demarrer", args=[mission.pk]))

    assert trop_tot.status_code == 400 and trop_tot.data["code"] == "transition_mission_interdite"
    assert faux.status_code == 400 and faux.data["code"] == "code_invalide"
    assert deja.status_code == 400 and "detail" in deja.data


def test_donnees_mal_formees_donnent_un_400_de_validation(chauffeur):
    fiche, _, api = chauffeur
    mission = mission_de(fiche, StatutMission.EN_COURS_COLIS_RECUPERE)

    sans_code = api.post(reverse("api:mobile:livraison", args=[mission.pk]), {"km_arrivee": 100}, format="json")
    km_negatif = api.post(
        reverse("api:mobile:livraison", args=[mission.pk]), {"code": CODE_DESTINATAIRE, "km_arrivee": -5}, format="json"
    )

    assert sans_code.status_code == 400 and "code" in sans_code.data
    assert km_negatif.status_code == 400 and "km_arrivee" in km_negatif.data


# --- check-list ---


def test_checklist_par_l_api_puis_refus_du_doublon(chauffeur):
    fiche, _, api = chauffeur
    mission = mission_de(fiche)
    corps = {"points": checklist_ok(PNEUS="Usé"), "remarque": "À surveiller"}

    premiere = api.post(reverse("api:mobile:checklist", args=[mission.pk]), corps, format="json")
    seconde = api.post(reverse("api:mobile:checklist", args=[mission.pk]), corps, format="json")

    assert premiere.status_code == 201 and premiere.data["nb_anomalies"] == 1
    assert seconde.status_code == 400 and seconde.data["code"] == "checklist_deja_remplie"
    detail = api.get(reverse("api:mobile:mission", args=[mission.pk]))
    assert detail.data["checklist_faite"] is True and detail.data["actions"]["checklist"] is False


def test_checklist_incomplete_ou_ko_sans_remarque_refusee(chauffeur):
    fiche, _, api = chauffeur
    mission = mission_de(fiche)
    url = reverse("api:mobile:checklist", args=[mission.pk])

    incomplete = api.post(url, {"points": checklist_ok()[:3]}, format="json")
    ko_muet = api.post(url, {"points": [{**p, "remarque": ""} for p in checklist_ok(FREINS="x")]}, format="json")

    assert incomplete.status_code == 400 and incomplete.data["code"] == "checklist_invalide"
    assert ko_muet.status_code == 400 and "Freins" in ko_muet.data["detail"]


# --- plein ---


def _plein_corps(**surcharges):
    corps = {"station": "Total Yopougon", "quantite_litres": "100.00", "prix_unitaire": "655",
             "km_compteur": 1000, "numero_ticket": "T-001"}
    corps.update(surcharges)
    return corps


def test_saisie_d_un_plein_par_l_api(chauffeur):
    fiche, _, api = chauffeur
    mission = mission_de(fiche)

    reponse = api.post(reverse("api:mobile:pleins"), _plein_corps(), format="json")

    assert reponse.status_code == 201
    assert reponse.data["vehicule"] == mission.vehicule.immatriculation and reponse.data["consommation"] is None
    assert [p["id"] for p in api.get(reverse("api:mobile:pleins")).data] == [reponse.data["id"]]


def test_un_plein_sans_camion_donne_un_400(chauffeur):
    _, _, api = chauffeur

    reponse = api.post(reverse("api:mobile:pleins"), _plein_corps(), format="json")

    assert reponse.status_code == 400 and reponse.data["code"] == "aucun_camion"


def test_plein_suspect_409_puis_confirmation(chauffeur):
    fiche, _, api = chauffeur
    mission_de(fiche)
    aujourd_hui = timezone.localdate()
    url = reverse("api:mobile:pleins")
    api.post(url, _plein_corps(numero_ticket="T-1", date_plein=str(aujourd_hui - timedelta(days=10))), format="json")
    for rang, km in enumerate((1400, 1800, 2200), start=2):
        api.post(url, _plein_corps(km_compteur=km, quantite_litres="120", numero_ticket=f"T-{rang}",
                                   date_plein=str(aujourd_hui - timedelta(days=10 - rang))), format="json")
    suspect = _plein_corps(km_compteur=2600, quantite_litres="300", numero_ticket="T-9")

    refuse = api.post(url, suspect, format="json")
    confirme = api.post(url, {**suspect, "confirmer": True}, format="json")

    assert refuse.status_code == 409 and refuse.data["code"] == "saisie_suspecte"
    assert Decimal(refuse.data["consommation"]) == Decimal("75.00") and "confirmer=true" in refuse.data["confirmer"]
    assert confirme.status_code == 201


def test_regles_du_plein_ticket_double_et_km_decroissant(chauffeur):
    fiche, _, api = chauffeur
    mission_de(fiche)
    url = reverse("api:mobile:pleins")
    api.post(url, _plein_corps(), format="json")

    double = api.post(url, _plein_corps(km_compteur=1500), format="json")
    recul = api.post(url, _plein_corps(km_compteur=900, numero_ticket="T-2"), format="json")

    assert double.status_code == 400 and double.data["code"] == "ticket_deja_enregistre"
    assert recul.status_code == 400 and recul.data["code"] == "kilometrage_invalide"


def test_plein_avec_donnees_invalides(chauffeur):
    fiche, _, api = chauffeur
    mission_de(fiche)

    reponse = api.post(reverse("api:mobile:pleins"), _plein_corps(quantite_litres="-3", station=""), format="json")

    assert reponse.status_code == 400 and {"quantite_litres", "station"} <= set(reponse.data)


def test_le_chauffeur_ne_declare_pas_de_plein_sur_le_camion_d_un_autre(chauffeur):
    fiche, _, api = chauffeur
    mission_de(fiche)
    etranger = VehiculeFactory()

    reponse = api.post(reverse("api:mobile:pleins"), _plein_corps(vehicule=etranger.pk), format="json")

    assert reponse.status_code == 400 and "n'est pas le vôtre" in reponse.data["detail"]


# --- incidents ---


def test_signalement_d_un_incident_par_l_api_et_liste(chauffeur):
    fiche, _, api = chauffeur
    mission = mission_de(fiche)

    reponse = api.post(
        reverse("api:mobile:incidents"),
        {"type_incident": "PANNE", "gravite": "GRAVE", "description": "Moteur qui chauffe",
         "lieu": "Km 120", "mission": mission.pk},
        format="json",
    )

    assert reponse.status_code == 201
    assert reponse.data["vehicule"] == mission.vehicule.immatriculation and reponse.data["statut"] == "SIGNALE"
    assert reponse.data["gravite_libelle"].startswith("Grave")
    assert [i["id"] for i in api.get(reverse("api:mobile:incidents")).data] == [reponse.data["id"]]
    assert Incident.objects.count() == 1


def test_incident_avec_donnees_invalides_ou_mission_etrangere(chauffeur):
    fiche, _, api = chauffeur
    autre = mission_de(ChauffeurFactory())
    url = reverse("api:mobile:incidents")

    mauvais_type = api.post(url, {"type_incident": "VOL", "gravite": "GRAVE", "description": "x"}, format="json")
    sans_description = api.post(url, {"type_incident": "PANNE", "gravite": "GRAVE", "description": ""}, format="json")
    mission_etrangere = api.post(
        url, {"type_incident": "PANNE", "gravite": "GRAVE", "description": "x", "mission": autre.pk}, format="json"
    )

    assert mauvais_type.status_code == 400 and "type_incident" in mauvais_type.data
    assert sans_description.status_code == 400
    assert mission_etrangere.status_code == 404 and not Incident.objects.exists()


def test_un_chauffeur_ne_voit_pas_les_incidents_d_un_autre(chauffeur):
    fiche, _, api = chauffeur
    VehiculeFactory(chauffeur_habituel=fiche)
    autre, compte_autre = chauffeur_avec_compte()
    VehiculeFactory(chauffeur_habituel=autre)
    _api(compte_autre).post(
        reverse("api:mobile:incidents"),
        {"type_incident": "AUTRE", "gravite": "FAIBLE", "description": "Chez l'autre"}, format="json",
    )

    assert api.get(reverse("api:mobile:incidents")).data == []


def test_la_liste_des_missions_mobiles_est_a_requetes_constantes(chauffeur, django_assert_max_num_queries):
    fiche, _, api = chauffeur
    for _ in range(10):
        mission_de(fiche)

    with django_assert_max_num_queries(30):
        assert len(api.get(reverse("api:mobile:missions")).data) == 10


def test_la_documentation_decrit_l_api_mobile():
    from django.test import Client

    http = Client()
    http.force_login(UserFactory(role=Role.ADMIN))

    chemins = http.get(reverse("api:schema"), {"format": "json"}).json()["paths"]

    for attendu in ("/api/v1/mobile/missions/", "/api/v1/mobile/missions/{id}/demarrer/",
                    "/api/v1/mobile/pleins/", "/api/v1/mobile/incidents/"):
        assert attendu in chemins, attendu
