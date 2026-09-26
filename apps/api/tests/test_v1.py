"""API bureau /api/v1 : droits par rôle, pagination, filtres, champs exposés, documentation."""

from datetime import date
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.test import Client as HttpClient
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services as billing
from apps.billing.models import ModePaiement
from apps.billing.tests.helpers import brouillon, emise
from apps.billing.tests.helpers import finances as compte_finances
from apps.customers.tests.factories import ClientFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.missions.models import StatutMission
from apps.missions.tests.factories import MissionFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _vider_le_cache():
    cache.clear()


def _api(role=Role.ADMIN):
    client = APIClient()
    client.force_authenticate(UserFactory(role=role))
    return client


RESSOURCES = {
    # Retour réunion : le Parc Auto affecte les missions, donc les consulte désormais aussi.
    "api:mission-list": {Role.ADMIN, Role.DIRECTION, Role.CHARGE_CLIENTELE, Role.PARCAUTO},
    "api:camion-list": {Role.ADMIN, Role.DIRECTION, Role.PARCAUTO},
    "api:chauffeur-list": {Role.ADMIN, Role.DIRECTION, Role.RH},
    "api:client-list": {Role.ADMIN, Role.DIRECTION, Role.CHARGE_CLIENTELE},
    # Retour réunion : la RH fait tout ce que fait la FINANCES, y compris consulter les factures.
    "api:facture-list": {Role.ADMIN, Role.DIRECTION, Role.FINANCES, Role.RH},
}


@pytest.mark.parametrize("nom", list(RESSOURCES))
@pytest.mark.parametrize("role", list(Role.values))
def test_chaque_ressource_suit_les_droits_de_l_ecran_correspondant(nom, role):
    reponse = _api(role).get(reverse(nom))

    assert reponse.status_code == (200 if role in RESSOURCES[nom] else 403), (nom, role)


@pytest.mark.parametrize("nom", list(RESSOURCES))
def test_sans_authentification_l_acces_est_refuse(nom):
    assert APIClient().get(reverse(nom)).status_code == 401


def test_un_vrai_jeton_jwt_ouvre_l_api():
    compte = UserFactory(role=Role.DIRECTION)
    client = APIClient()

    reponse = client.get(
        reverse("api:mission-list"), HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(compte)}"
    )

    assert reponse.status_code == 200


def test_l_api_est_en_lecture_seule():
    api = _api(Role.ADMIN)
    mission = MissionFactory()

    assert api.post(reverse("api:mission-list"), {}, format="json").status_code == 405
    assert api.put(reverse("api:mission-detail", args=[mission.pk]), {}, format="json").status_code == 405
    assert api.delete(reverse("api:mission-detail", args=[mission.pk])).status_code == 405


# --- missions ---


def test_une_mission_n_expose_jamais_ses_codes_secrets():
    mission = MissionFactory(code_expediteur="ABCD2345", code_destinataire="WXYZ6789")
    api = _api(Role.ADMIN)

    detail = api.get(reverse("api:mission-detail", args=[mission.pk]))
    liste = api.get(reverse("api:mission-list"))

    for reponse in (detail, liste):
        texte = reponse.content.decode()
        assert "ABCD2345" not in texte and "WXYZ6789" not in texte
        assert "code_expediteur" not in texte and "code_destinataire" not in texte


def test_le_detail_d_une_mission_donne_les_libelles():
    mission = MissionFactory(
        client=ClientFactory(raison_sociale="Cimaf CI"), statut=StatutMission.AFFECTEE,
        vehicule=VehiculeFactory(immatriculation="1234 AB 01"),
        chauffeur=ChauffeurFactory(),
    )

    donnees = _api(Role.DIRECTION).get(reverse("api:mission-detail", args=[mission.pk])).data

    assert donnees["numero"] == mission.numero and donnees["client"] == "Cimaf CI"
    assert donnees["vehicule"] == "1234 AB 01" and donnees["statut_libelle"] == "Affectée"
    assert donnees["chauffeur"] == f"{mission.chauffeur.personnel.prenom} {mission.chauffeur.personnel.nom}"


def test_les_missions_sont_paginees_par_20():
    for _ in range(25):
        MissionFactory()
    api = _api(Role.ADMIN)

    premiere = api.get(reverse("api:mission-list"))
    seconde = api.get(reverse("api:mission-list"), {"page": 2})

    assert premiere.data["count"] == 25 and len(premiere.data["results"]) == 20
    assert len(seconde.data["results"]) == 5 and premiere.data["next"] and seconde.data["previous"]


def test_les_missions_se_filtrent():
    cimaf = ClientFactory(raison_sociale="Cimaf Côte d'Ivoire")
    a = MissionFactory(client=cimaf, statut=StatutMission.PLANIFIEE, date_depart_prevue=date(2026, 10, 5))
    b = MissionFactory(statut=StatutMission.BROUILLON, date_depart_prevue=date(2026, 12, 1))
    api = _api(Role.ADMIN)
    url = reverse("api:mission-list")

    def numeros(**params):
        return {m["id"] for m in api.get(url, params).data["results"]}

    assert numeros(q="CIMAF") == {a.pk}  # accents et casse ignorés, comme à l'écran
    assert numeros(statut="PLANIFIEE") == {a.pk}
    assert numeros(client=cimaf.pk) == {a.pk}
    assert numeros(depart_apres="2026-11-01") == {b.pk}
    assert numeros(depart_avant="2026-10-31") == {a.pk}
    assert api.get(url, {"statut": "N_IMPORTE_QUOI"}).status_code == 400


def test_la_liste_des_missions_est_a_requetes_constantes(django_assert_max_num_queries):
    for _ in range(15):
        MissionFactory(vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory(), statut=StatutMission.AFFECTEE)
    api = _api(Role.ADMIN)

    with django_assert_max_num_queries(6):
        assert api.get(reverse("api:mission-list")).status_code == 200


# --- camions, chauffeurs, clients ---


def test_camions_filtres_par_statut_et_texte():
    a = VehiculeFactory(immatriculation="1111 AA 01", statut="DISPONIBLE", marque="Renault")
    VehiculeFactory(immatriculation="2222 BB 01", statut="EN_MISSION", marque="Volvo")
    api = _api(Role.PARCAUTO)
    url = reverse("api:camion-list")

    assert [v["id"] for v in api.get(url, {"statut": "DISPONIBLE"}).data["results"]] == [a.pk]
    assert [v["id"] for v in api.get(url, {"q": "renault"}).data["results"]] == [a.pk]
    assert api.get(reverse("api:camion-detail", args=[a.pk])).data["immatriculation"] == "1111 AA 01"


def test_chauffeurs_avec_leur_identite_et_recherche_sans_accent():
    fiche = ChauffeurFactory(personnel__nom="Traoré", personnel__prenom="Moussa")
    ChauffeurFactory(personnel__nom="Bamba")
    api = _api(Role.RH)

    resultats = api.get(reverse("api:chauffeur-list"), {"q": "traore"}).data["results"]

    assert [c["id"] for c in resultats] == [fiche.pk]
    assert resultats[0]["nom"] == "Traoré" and resultats[0]["matricule"] == fiche.personnel.matricule


def test_clients_filtre_exonere_et_charge_clientele():
    normal = ClientFactory(raison_sociale="Normal")
    exonere = ClientFactory(raison_sociale="Exonéré", taux_tva=Decimal("0"), motif_exoneration="ONG")
    api = _api(Role.CHARGE_CLIENTELE)
    url = reverse("api:client-list")

    assert [c["id"] for c in api.get(url, {"exonere": "true"}).data["results"]] == [exonere.pk]
    assert [c["id"] for c in api.get(url, {"exonere": "false"}).data["results"]] == [normal.pk]
    assert {c["raison_sociale"] for c in api.get(url).data["results"]} == {"Normal", "Exonéré"}
    assert api.get(url).data["results"][0]["delai_paiement_jours"] == 30


# --- factures ---


def test_facture_avec_reste_a_recouvrer_et_lignes_au_detail():
    facture = emise(prix="1000000", aujourd_hui=date(2026, 7, 1))
    billing.enregistrer_reglement(
        facture, compte_finances(), montant=Decimal("400000"), mode=ModePaiement.WAVE,
        date_reglement=date(2026, 7, 5),
    )
    api = _api(Role.FINANCES)

    liste = api.get(reverse("api:facture-list")).data["results"][0]
    detail = api.get(reverse("api:facture-detail", args=[facture.pk])).data

    assert liste["numero"] == facture.numero and "lignes" not in liste
    assert Decimal(detail["montant_ttc"]) == Decimal("1180000")
    assert Decimal(detail["montant_regle"]) == Decimal("400000")
    assert Decimal(detail["reste_a_recouvrer"]) == Decimal("780000")
    assert detail["echue"] is True and detail["statut"] == "PARTIELLEMENT_PAYEE"
    assert len(detail["lignes"]) == 1 and Decimal(detail["lignes"][0]["montant_ht"]) == Decimal("1000000")


def test_factures_filtrees_par_statut_echeance_et_texte():
    echue = emise(aujourd_hui=date(2026, 7, 1))
    a_jour = emise(aujourd_hui=date.today())
    brouillon()
    api = _api(Role.DIRECTION)
    url = reverse("api:facture-list")

    assert [f["id"] for f in api.get(url, {"echues": "true"}).data["results"]] == [echue.pk]
    assert {f["id"] for f in api.get(url, {"statut": "EMISE"}).data["results"]} == {echue.pk, a_jour.pk}
    assert [f["id"] for f in api.get(url, {"q": a_jour.numero.lower()}).data["results"]] == [a_jour.pk]
    assert len(api.get(url, {"echues": "false"}).data["results"]) == 3


def test_la_liste_des_factures_est_a_requetes_constantes(django_assert_max_num_queries):
    for _ in range(10):
        emise()
    api = _api(Role.FINANCES)

    with django_assert_max_num_queries(6):
        assert api.get(reverse("api:facture-list")).status_code == 200


# --- documentation ---


def test_la_documentation_est_reservee_a_l_admin_et_a_la_direction_connectes():
    def acces(role=None):
        http = HttpClient()
        if role:
            http.force_login(UserFactory(role=role))
        return http.get(reverse("api:schema")).status_code

    assert acces(Role.ADMIN) == 200 and acces(Role.DIRECTION) == 200
    assert acces(Role.CHAUFFEUR) == 403 and acces(Role.FINANCES) == 403
    assert acces() == 403


def test_le_schema_openapi_decrit_les_ressources_sans_erreur():
    http = HttpClient()
    http.force_login(UserFactory(role=Role.ADMIN))

    reponse = http.get(reverse("api:schema"), {"format": "json"})

    chemins = reponse.json()["paths"]
    for attendu in ("/api/v1/missions/", "/api/v1/factures/{id}/", "/api/v1/auth/token/", "/api/v1/moi/"):
        assert attendu in chemins, attendu
    assert "code_expediteur" not in reponse.content.decode()
    assert http.get(reverse("api:docs")).status_code == 200


# --- traduction des erreurs métier ---


def test_les_erreurs_metier_deviennent_des_reponses_http_claires():
    from rest_framework.response import Response  # noqa: F401

    from apps.api.exceptions import gestionnaire_erreurs
    from apps.billing.exceptions import ActionFactureNonAutorisee
    from apps.fuel.exceptions import SaisieSuspecte
    from apps.missions.exceptions import CodeInvalide

    refus = gestionnaire_erreurs(CodeInvalide("Code incorrect."), {})
    droit = gestionnaire_erreurs(ActionFactureNonAutorisee("Interdit."), {})
    suspecte = gestionnaire_erreurs(SaisieSuspecte(Decimal("70.5"), Decimal("51"), Decimal("30")), {})

    assert (refus.status_code, refus.data) == (400, {"code": "code_invalide", "detail": "Code incorrect."})
    assert droit.status_code == 403 and droit.data["code"] == "action_facture_non_autorisee"
    assert suspecte.status_code == 409 and suspecte.data["consommation"] == "51"
    assert "confirmer=true" in suspecte.data["confirmer"]
    assert gestionnaire_erreurs(ValueError("autre"), {}) is None  # les autres erreurs restent gérées par DRF
