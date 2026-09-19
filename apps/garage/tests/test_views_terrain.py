"""Écrans du Parc Auto : incidents et check-lists signalés par les chauffeurs."""

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.garage import terrain
from apps.garage.models import CODES_CHECKLIST, GraviteIncident, Incident, StatutIncident, TypeIncident
from apps.missions.models import StatutMission
from apps.missions.tests.factories import MissionFactory

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    compte = UserFactory(role=role)
    client.force_login(compte)
    return compte


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


def _incident(**surcharges):
    chauffeur = ChauffeurFactory()
    mission = MissionFactory(statut=StatutMission.AFFECTEE, vehicule=VehiculeFactory(), chauffeur=chauffeur)
    donnees = dict(
        chauffeur=chauffeur, mission=mission, type_incident=TypeIncident.PANNE,
        gravite=GraviteIncident.MOYENNE, description="Moteur qui chauffe", lieu="Bouaké",
    )
    donnees.update(surcharges)
    return terrain.declarer_incident(**donnees)


def _checklist(anomalie=False):
    chauffeur = ChauffeurFactory()
    mission = MissionFactory(statut=StatutMission.AFFECTEE, vehicule=VehiculeFactory(), chauffeur=chauffeur)
    resultats = [{"code": c, "ok": True, "remarque": ""} for c in CODES_CHECKLIST]
    if anomalie:
        resultats[1].update(ok=False, remarque="Frein spongieux")
    return terrain.enregistrer_checklist(chauffeur=chauffeur, mission=mission, resultats=resultats)


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.PARCAUTO])
def test_incidents_et_checklists_sont_visibles_par_admin_direction_et_parc_auto(client, role):
    _connecte(client, role)
    incident = _incident()

    for url in (reverse("garage:incidents"), reverse("garage:incident", args=[incident.pk]),
                reverse("garage:checklists")):
        assert client.get(url).status_code == 200, url


@pytest.mark.parametrize("role", [Role.RH, Role.FINANCES, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR])
def test_incidents_et_checklists_sont_interdits_aux_autres_roles(client, role):
    _connecte(client, role)
    incident = _incident()

    for url in (reverse("garage:incidents"), reverse("garage:incident", args=[incident.pk]),
                reverse("garage:checklists")):
        assert client.get(url).status_code == 403, url


def test_la_liste_des_incidents_se_filtre_et_compte_ceux_a_traiter(client):
    _connecte(client, Role.PARCAUTO)
    grave = _incident(description="Crevaison pneu avant", gravite=GraviteIncident.GRAVE)
    _incident(description="Feu cassé")
    url = reverse("garage:incidents")

    assert client.get(url).context["a_traiter"] == 2
    assert [i.pk for i in client.get(url, {"q": "crevaison"}).context["incidents"]] == [grave.pk]
    assert [i.pk for i in client.get(url, {"gravite": "GRAVE"}).context["incidents"]] == [grave.pk]
    assert len(client.get(url, {"statut": "CLOS"}).context["incidents"]) == 0
    assert len(client.get(url, {"statut": "???", "page": "abc"}).context["incidents"]) == 2


def test_liste_vide_des_incidents(client):
    _connecte(client, Role.PARCAUTO)

    assert "Aucun incident" in client.get(reverse("garage:incidents")).content.decode()


def test_la_fiche_propose_le_traitement_au_parc_auto_pas_a_la_direction(client):
    incident = _incident()
    url = reverse("garage:incident", args=[incident.pk])

    _connecte(client, Role.PARCAUTO)
    texte = client.get(url).content.decode()
    assert "Ouvrir un OR" in texte and "Prendre en compte" in texte and "Clore l'incident" in texte
    assert f"{reverse('garage:creer')}?vehicule={incident.vehicule.pk}" in texte

    _connecte(client, Role.DIRECTION)
    assert "Prendre en compte" not in client.get(url).content.decode()


def test_prendre_en_compte_puis_clore(client):
    _connecte(client, Role.PARCAUTO)
    incident = _incident()
    url = reverse("garage:incident_traiter", args=[incident.pk])

    reponse = client.post(url, {"action": "prendre", "note": "On s'en occupe"}, follow=True)
    incident.refresh_from_db()
    assert incident.statut == StatutIncident.PRIS_EN_COMPTE
    assert any("pris en compte" in m for m in _messages(reponse))

    client.post(url, {"action": "clore", "note": " "}, follow=True)
    incident.refresh_from_db()
    assert incident.statut == StatutIncident.PRIS_EN_COMPTE  # motif vide : rien ne change

    reponse = client.post(url, {"action": "clore", "note": "Courroie remplacée"}, follow=True)
    incident.refresh_from_db()
    assert incident.statut == StatutIncident.CLOS and "Courroie remplacée" in reponse.content.decode()
    assert "Prendre en compte" not in reponse.content.decode()


def test_un_incident_clos_ne_se_retraite_pas(client):
    _connecte(client, Role.PARCAUTO)
    incident = _incident()
    url = reverse("garage:incident_traiter", args=[incident.pk])
    client.post(url, {"action": "clore", "note": "Fausse alerte"})

    reponse = client.post(url, {"action": "clore", "note": "Encore"}, follow=True)

    assert any("déjà clos" in m for m in _messages(reponse))


def test_la_direction_ne_peut_pas_traiter_meme_en_postant(client):
    _connecte(client, Role.DIRECTION)
    incident = _incident()

    assert client.post(reverse("garage:incident_traiter", args=[incident.pk]),
                       {"action": "clore", "note": "x"}).status_code == 403
    incident.refresh_from_db()
    assert incident.statut == StatutIncident.SIGNALE


def test_action_inconnue_ou_incident_inexistant(client):
    _connecte(client, Role.PARCAUTO)
    incident = _incident()

    client.post(reverse("garage:incident_traiter", args=[incident.pk]), {"action": "supprimer"})
    assert Incident.objects.get(pk=incident.pk).statut == StatutIncident.SIGNALE
    assert client.post(reverse("garage:incident_traiter", args=[999]), {"action": "prendre"}).status_code == 404
    assert client.get(reverse("garage:incident", args=[999])).status_code == 404


def test_traitement_en_post_avec_csrf_seulement():
    incident = _incident()
    http = Client(enforce_csrf_checks=True)
    http.force_login(UserFactory(role=Role.PARCAUTO))
    url = reverse("garage:incident_traiter", args=[incident.pk])

    assert http.get(url).status_code == 405
    assert http.post(url, {"action": "prendre"}).status_code == 403


def test_les_textes_de_l_incident_sont_echappes(client):
    _connecte(client, Role.PARCAUTO)
    incident = _incident(description="<script>alert(1)</script>", lieu="<img src=x onerror=alert(2)>")

    for url in (reverse("garage:incidents"), reverse("garage:incident", args=[incident.pk])):
        texte = client.get(url).content.decode()
        assert "<script>alert(1)</script>" not in texte and "<img src=x" not in texte, url


def test_la_liste_des_checklists_montre_les_points_ko_et_se_filtre(client):
    _connecte(client, Role.PARCAUTO)
    _checklist()
    avec_ko = _checklist(anomalie=True)
    url = reverse("garage:checklists")

    reponse = client.get(url)
    assert len(reponse.context["checklists"]) == 2
    assert "Frein spongieux" in reponse.content.decode() and "Tout est OK" in reponse.content.decode()
    assert [c.pk for c in client.get(url, {"anomalies": "on"}).context["checklists"]] == [avec_ko.pk]
    assert len(client.get(url, {"q": avec_ko.mission.numero}).context["checklists"]) == 1


def test_le_menu_du_parc_auto_propose_les_incidents(client):
    _connecte(client, Role.PARCAUTO)

    assert 'href="/garage/incidents/"' in client.get(reverse("home")).content.decode()


def test_les_listes_du_terrain_sont_a_requetes_constantes(client, django_assert_max_num_queries):
    _connecte(client, Role.PARCAUTO)
    for _ in range(12):
        _incident()
        _checklist(anomalie=True)

    with django_assert_max_num_queries(12):
        assert client.get(reverse("garage:incidents")).status_code == 200
    with django_assert_max_num_queries(12):
        assert client.get(reverse("garage:checklists")).status_code == 200
