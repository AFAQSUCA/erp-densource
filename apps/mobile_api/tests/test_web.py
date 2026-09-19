"""Espace mobile du chauffeur (PWA) : accès, parcours d'une mission, check-list, plein, incident."""

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.staticfiles import finders
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.garage.models import ChecklistVehicule, Incident
from apps.missions.models import StatutMission
from apps.mobile_api import services

from .helpers import CODE_DESTINATAIRE, CODE_EXPEDITEUR, chauffeur_avec_compte, mission_de

pytestmark = pytest.mark.django_db


@pytest.fixture
def chauffeur(client):
    fiche, compte = chauffeur_avec_compte()
    client.force_login(compte)
    return fiche, compte


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


PAGES = ["chauffeur:accueil", "chauffeur:missions", "chauffeur:plein", "chauffeur:incident"]


# --- accès ---


@pytest.mark.parametrize("nom", PAGES)
def test_les_pages_du_chauffeur_lui_sont_reservees(client, nom):
    fiche, compte = chauffeur_avec_compte()

    assert client.get(reverse(nom)).status_code == 302  # non connecté : page de connexion
    for role in (Role.ADMIN, Role.DIRECTION, Role.PARCAUTO, Role.RH, Role.FINANCES, Role.CHARGE_CLIENTELE):
        client.force_login(UserFactory(role=role))
        assert client.get(reverse(nom)).status_code == 403, (nom, role)
    client.force_login(UserFactory(role=Role.CHAUFFEUR))  # compte sans fiche du personnel
    assert client.get(reverse(nom)).status_code == 403
    client.force_login(compte)
    assert client.get(reverse(nom)).status_code == 200


def test_la_page_de_bureau_redirige_le_chauffeur_vers_son_espace(client, chauffeur):
    reponse = client.get(reverse("home"))

    assert reponse.status_code == 302 and reponse["Location"] == reverse("chauffeur:accueil")


def test_un_compte_chauffeur_sans_fiche_garde_la_page_d_explication(client):
    client.force_login(UserFactory(role=Role.CHAUFFEUR))

    reponse = client.get(reverse("home"))

    assert reponse.status_code == 200 and "espace mobile" in reponse.content.decode()


def test_la_session_du_chauffeur_dure_15_minutes_celle_du_bureau_30(client):
    compte = UserFactory(role=Role.CHAUFFEUR)
    bureau = UserFactory(role=Role.DIRECTION)

    client.post(reverse("accounts:login"), {"username": compte.username, "password": "Test-Passw0rd!"})
    assert client.session.get_expiry_age() == 15 * 60
    autre = Client()
    autre.post(reverse("accounts:login"), {"username": bureau.username, "password": "Test-Passw0rd!"})
    assert autre.session.get_expiry_age() == 30 * 60


# --- application installable ---


def test_le_manifeste_est_public_et_decrit_l_application(client):
    reponse = client.get(reverse("chauffeur:manifeste"))
    manifeste = json.loads(reponse.content)

    assert reponse.status_code == 200 and reponse["Content-Type"] == "application/manifest+json"
    assert manifeste["start_url"] == "/chauffeur/" == manifeste["scope"]
    assert manifeste["display"] == "standalone" and manifeste["theme_color"] == "#8b0319"
    assert {i["sizes"] for i in manifeste["icons"]} == {"192x192", "512x512"}
    for icone in manifeste["icons"]:  # les fichiers d'icônes existent bien dans les fichiers statiques
        assert finders.find(icone["src"].removeprefix("/static/")), icone["src"]


def test_le_service_worker_ne_met_en_cache_que_la_page_hors_connexion(client):
    reponse = client.get(reverse("chauffeur:sw"))
    texte = reponse.content.decode()

    assert reponse.status_code == 200 and reponse["Content-Type"].startswith("application/javascript")
    assert reponse["Service-Worker-Allowed"] == "/chauffeur/" and reponse["Cache-Control"] == "no-cache"
    assert reverse("chauffeur:hors_ligne") in texte
    assert 'mode === "navigate"' in texte and "/chauffeur/missions/" not in texte


def test_la_page_hors_connexion_est_publique_et_autonome(client):
    reponse = client.get(reverse("chauffeur:hors_ligne"))
    texte = reponse.content.decode()

    assert reponse.status_code == 200 and "hors connexion" in texte
    assert "cdn." not in texte  # doit s'afficher sans réseau : aucune ressource externe


def test_les_pages_declarent_le_manifeste_et_enregistrent_le_service_worker(client, chauffeur):
    texte = client.get(reverse("chauffeur:accueil")).content.decode()

    assert reverse("chauffeur:manifeste") in texte and reverse("chauffeur:sw") in texte
    assert 'name="theme-color"' in texte and "viewport-fit=cover" in texte
    assert 'aria-current="page"' in texte  # onglet actif de la navigation du bas


# --- accueil et missions ---


def test_l_accueil_montre_la_mission_du_jour_le_camion_et_les_chiffres(client, chauffeur):
    fiche, _ = chauffeur
    mission = mission_de(fiche, lieu_chargement="Abidjan", lieu_livraison="Bouaké")

    reponse = client.get(reverse("chauffeur:accueil"))
    texte = reponse.content.decode()

    assert reponse.context["mission_du_jour"] == mission
    assert "Prochaine mission" in texte and "Abidjan" in texte and "Bouaké" in texte
    assert mission.vehicule.immatriculation in texte
    assert "Faire la check-list du camion" in texte and "Saisir un plein" in texte


def test_l_accueil_sans_mission(client, chauffeur):
    texte = client.get(reverse("chauffeur:accueil")).content.decode()

    assert "Aucune mission ne vous est affectée" in texte and "Aucun camion affecté" in texte


def test_l_accueil_d_une_course_en_cours(client, chauffeur):
    fiche, _ = chauffeur
    mission_de(fiche, StatutMission.EN_COURS_DEPART, date_depart=timezone.now())

    texte = client.get(reverse("chauffeur:accueil")).content.decode()

    assert "Course en cours" in texte and "Faire la check-list" not in texte


def test_la_liste_ne_montre_que_mes_missions(client, chauffeur):
    fiche, _ = chauffeur
    a_moi = mission_de(fiche)
    autre = mission_de(ChauffeurFactory())

    texte = client.get(reverse("chauffeur:missions")).content.decode()

    assert a_moi.numero in texte and autre.numero not in texte


def test_la_fiche_d_une_mission_d_un_autre_chauffeur_est_un_404(client, chauffeur):
    autre = mission_de(ChauffeurFactory())

    assert client.get(reverse("chauffeur:mission", args=[autre.pk])).status_code == 404
    assert client.get(reverse("chauffeur:checklist", args=[autre.pk])).status_code == 404


def test_les_codes_secrets_et_le_prix_n_apparaissent_jamais_sur_l_ecran_du_chauffeur(client, chauffeur):
    fiche, _ = chauffeur
    mission = mission_de(fiche)

    for url in (reverse("chauffeur:accueil"), reverse("chauffeur:missions"), reverse("chauffeur:mission", args=[mission.pk])):
        texte = client.get(url).content.decode()
        assert CODE_EXPEDITEUR not in texte and CODE_DESTINATAIRE not in texte, url
        assert "850000" not in texte and "850 000" not in texte, url


def test_boutons_selon_le_statut_de_la_mission(client, chauffeur):
    fiche, _ = chauffeur
    affectee = mission_de(fiche)
    en_cours = mission_de(fiche, StatutMission.EN_COURS_DEPART)
    recuperee = mission_de(fiche, StatutMission.EN_COURS_COLIS_RECUPERE)

    a = client.get(reverse("chauffeur:mission", args=[affectee.pk])).content.decode()
    b = client.get(reverse("chauffeur:mission", args=[en_cours.pk])).content.decode()
    c = client.get(reverse("chauffeur:mission", args=[recuperee.pk])).content.decode()

    assert "Démarrer la mission" in a and "Check-list du camion" in a and "Confirmer la récupération" not in a
    assert "Confirmer la récupération" in b and "Démarrer la mission" not in b and "Scanner le QR" in b
    assert "Confirmer la livraison" in c and "Kilométrage à l" in c


# --- parcours d'une mission ---


def test_parcours_complet_par_les_ecrans(client, chauffeur):
    fiche, _ = chauffeur
    mission = mission_de(fiche)
    km = mission.vehicule.kilometrage

    r1 = client.post(reverse("chauffeur:demarrer", args=[mission.pk]), follow=True)
    r2 = client.post(reverse("chauffeur:recuperation", args=[mission.pk]), {"code": CODE_EXPEDITEUR.lower()}, follow=True)
    r3 = client.post(
        reverse("chauffeur:livraison", args=[mission.pk]), {"code": CODE_DESTINATAIRE, "km_arrivee": km + 350}, follow=True
    )

    mission.refresh_from_db()
    assert mission.statut == StatutMission.LIVREE and mission.km_arrivee == km + 350
    assert any("C'est parti" in m for m in _messages(r1))
    assert any("Colis récupéré" in m for m in _messages(r2))
    assert any("Livraison confirmée" in m for m in _messages(r3))


def test_un_code_faux_ou_une_etape_incorrecte_donne_un_message_sans_rien_changer(client, chauffeur):
    fiche, _ = chauffeur
    mission = mission_de(fiche)

    trop_tot = client.post(reverse("chauffeur:recuperation", args=[mission.pk]), {"code": CODE_EXPEDITEUR}, follow=True)
    client.post(reverse("chauffeur:demarrer", args=[mission.pk]))
    faux = client.post(reverse("chauffeur:recuperation", args=[mission.pk]), {"code": "FAUX0000"}, follow=True)

    mission.refresh_from_db()
    assert mission.statut == StatutMission.EN_COURS_DEPART
    assert _messages(trop_tot) and any("incorrect" in m.lower() for m in _messages(faux))


def test_champs_manquants_a_la_livraison(client, chauffeur):
    fiche, _ = chauffeur
    mission = mission_de(fiche, StatutMission.EN_COURS_COLIS_RECUPERE)

    reponse = client.post(reverse("chauffeur:livraison", args=[mission.pk]), {"code": CODE_DESTINATAIRE}, follow=True)

    mission.refresh_from_db()
    assert mission.statut == StatutMission.EN_COURS_COLIS_RECUPERE and _messages(reponse)


def test_agir_sur_la_mission_d_un_autre_donne_un_404_et_ne_change_rien(client, chauffeur):
    autre = mission_de(ChauffeurFactory())

    assert client.post(reverse("chauffeur:demarrer", args=[autre.pk])).status_code == 404
    assert client.post(reverse("chauffeur:recuperation", args=[autre.pk]), {"code": CODE_EXPEDITEUR}).status_code == 404
    assert client.post(reverse("chauffeur:livraison", args=[autre.pk]), {"code": "X", "km_arrivee": 1}).status_code == 404
    autre.refresh_from_db()
    assert autre.statut == StatutMission.AFFECTEE


def test_les_actions_de_mission_exigent_post_et_csrf():
    fiche, compte = chauffeur_avec_compte()
    mission = mission_de(fiche)
    http = Client(enforce_csrf_checks=True)
    http.force_login(compte)

    for nom in ("demarrer", "recuperation", "livraison"):
        url = reverse(f"chauffeur:{nom}", args=[mission.pk])
        assert http.get(url).status_code == 405, nom
        assert http.post(url, {"code": CODE_EXPEDITEUR}).status_code == 403, nom
    mission.refresh_from_db()
    assert mission.statut == StatutMission.AFFECTEE


# --- check-list ---


def _reponses_checklist(ko=None):
    from apps.garage.models import CODES_CHECKLIST

    donnees = {}
    for code in CODES_CHECKLIST:
        donnees[f"ok_{code}"] = "0" if ko and code in ko else "1"
        donnees[f"remarque_{code}"] = (ko or {}).get(code, "")
    return donnees


def test_la_page_de_checklist_liste_les_huit_points(client, chauffeur):
    fiche, _ = chauffeur
    mission = mission_de(fiche)

    texte = client.get(reverse("chauffeur:checklist", args=[mission.pk])).content.decode()

    for libelle in ("Pneus", "Freins", "Feux", "huile", "Extincteur"):
        assert libelle in texte
    assert texte.count('value="1"') == 8 and texte.count('value="0"') == 8


def test_checklist_tout_ok(client, chauffeur):
    fiche, _ = chauffeur
    mission = mission_de(fiche)

    reponse = client.post(reverse("chauffeur:checklist", args=[mission.pk]), _reponses_checklist(), follow=True)

    assert ChecklistVehicule.objects.get().nb_anomalies == 0
    assert any("tout est OK" in m for m in _messages(reponse))
    assert "Check-list du camion faite" in reponse.content.decode()


def test_checklist_avec_ko_previent_sans_bloquer(client, chauffeur):
    fiche, _ = chauffeur
    mission = mission_de(fiche)

    reponse = client.post(
        reverse("chauffeur:checklist", args=[mission.pk]), _reponses_checklist(ko={"FREINS": "Pédale molle"}), follow=True
    )

    assert ChecklistVehicule.objects.get().nb_anomalies == 1
    assert any("1 point(s) KO" in m and "vous pouvez partir" in m for m in _messages(reponse))
    assert client.post(reverse("chauffeur:demarrer", args=[mission.pk])).status_code == 302


def test_un_ko_sans_remarque_reste_sur_le_formulaire(client, chauffeur):
    fiche, _ = chauffeur
    mission = mission_de(fiche)

    reponse = client.post(reverse("chauffeur:checklist", args=[mission.pk]), _reponses_checklist(ko={"FREINS": ""}))

    assert reponse.status_code == 200 and "Précisez le problème pour" in reponse.content.decode()
    assert not ChecklistVehicule.objects.exists()


def test_une_checklist_incomplete_est_refusee_et_le_doublon_aussi(client, chauffeur):
    fiche, _ = chauffeur
    mission = mission_de(fiche)
    url = reverse("chauffeur:checklist", args=[mission.pk])
    incomplete = _reponses_checklist()
    del incomplete["ok_PNEUS"]

    assert client.post(url, incomplete).status_code == 200 and not ChecklistVehicule.objects.exists()
    client.post(url, _reponses_checklist())
    doublon = client.post(url, _reponses_checklist())
    assert doublon.status_code == 200 and "déjà remplie" in doublon.content.decode()


# --- plein ---


def _plein(**surcharges):
    donnees = {"station": "Total", "quantite_litres": "100", "prix_unitaire": "655", "km_compteur": "1000",
               "numero_ticket": "T-001", "date_plein": timezone.localdate().isoformat()}
    donnees.update(surcharges)
    return donnees


def test_la_page_plein_annonce_le_camion(client, chauffeur):
    fiche, _ = chauffeur
    mission = mission_de(fiche)

    texte = client.get(reverse("chauffeur:plein")).content.decode()

    assert f"Camion {mission.vehicule.immatriculation}" in texte


def test_saisie_d_un_plein_depuis_le_telephone(client, chauffeur):
    fiche, _ = chauffeur
    mission_de(fiche)

    reponse = client.post(reverse("chauffeur:plein"), _plein(), follow=True)

    assert reponse.redirect_chain[-1][0] == reverse("chauffeur:accueil")
    assert any("Premier plein enregistré" in m for m in _messages(reponse))
    assert services.pleins_du_chauffeur(fiche).count() == 1


def test_plein_sans_camion_ou_invalide_reste_sur_le_formulaire(client, chauffeur):
    fiche, _ = chauffeur

    sans_camion = client.post(reverse("chauffeur:plein"), _plein())
    mission_de(fiche)
    invalide = client.post(reverse("chauffeur:plein"), _plein(quantite_litres="-3", date_plein="2999-01-01"))

    assert sans_camion.status_code == 200 and "Aucun camion ne vous est affecté" in sans_camion.content.decode()
    assert invalide.status_code == 200 and services.pleins_du_chauffeur(fiche).count() == 0


def test_saisie_suspecte_avertit_puis_se_confirme(client, chauffeur):
    fiche, _ = chauffeur
    mission_de(fiche)
    aujourd_hui = timezone.localdate()
    for rang, (km, litres) in enumerate(((1000, "100"), (1400, "120"), (1800, "120"), (2200, "120")), start=1):
        services.saisir_plein(
            fiche, station="T", quantite_litres=Decimal(litres), prix_unitaire=Decimal("655"),
            km_compteur=km, numero_ticket=f"H-{rang}", date_plein=aujourd_hui - timedelta(days=10 - rang),
        )
    suspect = _plein(km_compteur="2600", quantite_litres="300", numero_ticket="S-1")

    avertie = client.post(reverse("chauffeur:plein"), suspect)
    texte = avertie.content.decode()
    assert avertie.status_code == 200 and "Vérifiez votre saisie" in texte
    assert "Confirmer : les valeurs sont exactes" in texte and 'name="confirmer"' in texte
    assert services.pleins_du_chauffeur(fiche).count() == 4  # rien d'enregistré

    confirmee = client.post(reverse("chauffeur:plein"), {**suspect, "confirmer": "1"}, follow=True)
    assert services.pleins_du_chauffeur(fiche).count() == 5
    assert any("Surconsommation" in m for m in _messages(confirmee))


# --- incident ---


def _incident(**surcharges):
    donnees = {"type_incident": "PANNE", "gravite": "MOYENNE", "description": "Moteur qui chauffe",
               "lieu": "Km 120", "mission": ""}
    donnees.update(surcharges)
    return donnees


def test_signalement_d_un_incident_depuis_le_telephone(client, chauffeur):
    fiche, _ = chauffeur
    mission = mission_de(fiche)

    reponse = client.post(reverse("chauffeur:incident"), _incident(mission=mission.pk), follow=True)

    incident = Incident.objects.get()
    assert incident.mission == mission and incident.vehicule == mission.vehicule and incident.chauffeur == fiche
    assert any("Parc Auto et la Direction sont prévenus" in m for m in _messages(reponse))


def test_incident_sans_mission_sur_le_camion_courant(client, chauffeur):
    fiche, _ = chauffeur
    habituel = VehiculeFactory(chauffeur_habituel=fiche)

    client.post(reverse("chauffeur:incident"), _incident())

    assert Incident.objects.get().vehicule == habituel


def test_la_mission_est_preselectionnee_depuis_la_fiche(client, chauffeur):
    fiche, _ = chauffeur
    mission = mission_de(fiche)

    reponse = client.get(reverse("chauffeur:incident"), {"mission": mission.pk})

    assert reponse.context["form"].initial["mission"] == str(mission.pk)
    assert f'value="{mission.pk}" selected' in reponse.content.decode()


def test_incident_invalide_ou_sur_la_mission_d_un_autre(client, chauffeur):
    fiche, _ = chauffeur
    autre = mission_de(ChauffeurFactory())

    vide = client.post(reverse("chauffeur:incident"), _incident(description=""))
    etrangere = client.post(reverse("chauffeur:incident"), _incident(mission=autre.pk))
    sans_camion = client.post(reverse("chauffeur:incident"), _incident())

    assert vide.status_code == 200 and etrangere.status_code == 200 and sans_camion.status_code == 200
    assert "Aucun camion ne vous est affecté" in sans_camion.content.decode()
    assert not Incident.objects.exists()


def test_les_textes_de_l_incident_sont_echappes(client, chauffeur):
    fiche, _ = chauffeur
    VehiculeFactory(chauffeur_habituel=fiche)
    client.post(reverse("chauffeur:incident"), _incident(description="<script>alert(1)</script>"))

    texte = client.get(reverse("chauffeur:incident")).content.decode()

    assert "<script>alert(1)</script>" not in texte and "&lt;script&gt;" in texte


def test_les_formulaires_du_chauffeur_exigent_le_csrf():
    fiche, compte = chauffeur_avec_compte()
    mission_de(fiche)
    http = Client(enforce_csrf_checks=True)
    http.force_login(compte)

    assert http.post(reverse("chauffeur:plein"), _plein()).status_code == 403
    assert http.post(reverse("chauffeur:incident"), _incident()).status_code == 403
    assert not Incident.objects.exists()
