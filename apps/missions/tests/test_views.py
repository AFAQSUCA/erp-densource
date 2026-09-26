"""Écrans des missions : accès par rôle, affichage, actions du cycle de vie."""

from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.customers.tests.factories import ClientFactory
from apps.fleet.models import StatutVehicule
from apps.fleet.tests.factories import VehiculeFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.missions import services
from apps.missions.models import Mission, StatutMission

from .factories import MissionFactory
from .test_services import (
    _affectee,
    _creer,
    _en_cours,
    _livree,
    _planifiee,
    _recuperee,
)

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    utilisateur = UserFactory(role=role)
    client.force_login(utilisateur)
    return utilisateur


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


def _url(nom, mission):
    return reverse(f"missions:{nom}", args=[mission.pk])


# --- accès par rôle ---


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.CHARGE_CLIENTELE, Role.PARCAUTO])
def test_la_liste_est_accessible_aux_roles_de_gestion(client, role):
    # Retour réunion : le Parc Auto affecte les missions, donc les consulte désormais aussi.
    _connecte(client, role)

    assert client.get(reverse("missions:liste")).status_code == 200


@pytest.mark.parametrize("role", [Role.RH, Role.FINANCES, Role.CHAUFFEUR])
def test_la_liste_est_interdite_aux_autres_roles(client, role):
    _connecte(client, role)

    assert client.get(reverse("missions:liste")).status_code == 403


@pytest.mark.parametrize(
    "nom", ["liste", "creer"]
)
def test_un_visiteur_non_connecte_est_renvoye_vers_la_connexion(client, nom):
    reponse = client.get(reverse(f"missions:{nom}"))

    assert reponse.status_code == 302
    assert reponse.url.startswith(reverse("accounts:login"))


# --- liste ---


def test_la_liste_affiche_les_missions(client):
    _connecte(client, Role.DIRECTION)
    mission = _planifiee()

    contenu = client.get(reverse("missions:liste")).content.decode()

    assert mission.numero in contenu
    assert mission.client.raison_sociale in contenu
    assert "Planifiée" in contenu


def test_la_liste_vide_affiche_un_message(client):
    _connecte(client, Role.DIRECTION)

    assert "Aucune mission trouvée" in client.get(reverse("missions:liste")).content.decode()


def test_la_liste_filtre_par_statut(client):
    _connecte(client, Role.DIRECTION)
    brouillon, planifiee = _creer(), _planifiee()

    reponse = client.get(reverse("missions:liste"), {"statut": StatutMission.PLANIFIEE})

    assert list(reponse.context["missions"]) == [planifiee]
    assert brouillon.numero not in reponse.content.decode()


def test_la_liste_ignore_un_statut_inconnu(client):
    _connecte(client, Role.DIRECTION)
    _creer()

    reponse = client.get(reverse("missions:liste"), {"statut": "N_IMPORTE_QUOI"})

    assert len(reponse.context["missions"]) == 1


def test_la_liste_recherche_par_client_numero_ou_lieu(client):
    _connecte(client, Role.DIRECTION)
    cible = _creer(client=ClientFactory(raison_sociale="Cimaf Côte d'Ivoire"))
    _creer(lieu_livraison="Korhogo")

    par_client = client.get(reverse("missions:liste"), {"q": "cimaf"})
    par_numero = client.get(reverse("missions:liste"), {"q": cible.numero})
    par_lieu = client.get(reverse("missions:liste"), {"q": "korhogo"})

    assert list(par_client.context["missions"]) == [cible]
    assert list(par_numero.context["missions"]) == [cible]
    assert len(par_lieu.context["missions"]) == 1


def test_la_liste_est_paginee_par_20_et_conserve_les_filtres(client):
    _connecte(client, Role.DIRECTION)
    for _ in range(21):
        MissionFactory(statut=StatutMission.BROUILLON)

    page1 = client.get(reverse("missions:liste"), {"statut": "BROUILLON"})
    page2 = client.get(reverse("missions:liste"), {"statut": "BROUILLON", "page": 2})

    assert len(page1.context["missions"]) == 20
    assert len(page2.context["missions"]) == 1
    assert "statut=BROUILLON" in page1.content.decode()  # lien « Suivant »


def test_la_liste_n_effectue_pas_une_requete_par_mission(client, django_assert_max_num_queries):
    _connecte(client, Role.DIRECTION)
    for _ in range(15):
        MissionFactory()

    with django_assert_max_num_queries(10):
        client.get(reverse("missions:liste"))


def test_le_contenu_saisi_est_echappe_contre_le_xss(client):
    _connecte(client, Role.DIRECTION)
    _creer(lieu_chargement="<script>alert('xss')</script>")

    contenu = client.get(reverse("missions:liste")).content.decode()

    assert "<script>alert('xss')</script>" not in contenu
    assert "&lt;script&gt;" in contenu


# --- fiche ---


def test_la_fiche_affiche_le_detail(client):
    _connecte(client, Role.DIRECTION)
    mission = _affectee()

    contenu = client.get(_url("detail", mission)).content.decode()

    assert mission.numero in contenu
    assert mission.vehicule.immatriculation in contenu
    assert mission.chauffeur.personnel.nom in contenu


def test_la_fiche_d_une_mission_inconnue_est_introuvable(client):
    _connecte(client, Role.DIRECTION)

    assert client.get(reverse("missions:detail", args=[999999])).status_code == 404


def test_la_frise_marque_l_etape_courante(client):
    _connecte(client, Role.DIRECTION)
    mission = _en_cours()

    reponse = client.get(_url("detail", mission))

    etapes = reponse.context["etapes"]
    assert [e["etat"] for e in etapes] == [
        "faite", "faite", "faite", "courante", "a_venir", "a_venir", "a_venir",
    ]
    assert reponse.content.decode().count('aria-current="step"') == 1


@pytest.mark.parametrize(
    ("etape", "expediteur", "destinataire"),
    [
        (_creer, True, True),
        (_en_cours, True, True),
        (_recuperee, False, True),  # colis récupéré : le code expéditeur ne sert plus
        (_livree, False, False),  # livrée : plus aucun code utile
    ],
)
def test_les_codes_ne_s_affichent_que_tant_qu_ils_servent(client, etape, expediteur, destinataire):
    _connecte(client, Role.DIRECTION)
    mission = etape()

    contenu = client.get(_url("detail", mission)).content.decode()

    assert (mission.code_expediteur in contenu) is expediteur
    assert (mission.code_destinataire in contenu) is destinataire


# --- actions proposées selon rôle et statut ---


def test_le_charge_clientele_peut_planifier_un_brouillon_mais_pas_affecter(client):
    _connecte(client, Role.CHARGE_CLIENTELE)
    brouillon = _creer()
    planifiee = _planifiee()

    page_brouillon = client.get(_url("detail", brouillon)).content.decode()
    page_planifiee = client.get(_url("detail", planifiee)).content.decode()

    assert _url("planifier", brouillon) in page_brouillon
    assert _url("affecter", planifiee) not in page_planifiee
    assert "Aucune action disponible" in page_planifiee


def test_la_direction_voit_le_formulaire_d_affectation_avec_les_seuls_camions_disponibles(client):
    _connecte(client, Role.DIRECTION)
    mission = _planifiee()
    libre = VehiculeFactory(immatriculation="1111 AA 01")
    VehiculeFactory(immatriculation="2222 BB 01", statut=StatutVehicule.EN_MAINTENANCE)

    reponse = client.get(_url("detail", mission))
    contenu = reponse.content.decode()

    assert _url("affecter", mission) in contenu
    assert libre.immatriculation in contenu
    assert "2222 BB 01" not in contenu


@pytest.mark.parametrize(
    ("etape", "action_attendue"),
    [
        (_affectee, "demarrer"),
        (_livree, "cloturer"),
    ],
)
def test_la_direction_voit_l_action_de_l_etape(client, etape, action_attendue):
    _connecte(client, Role.DIRECTION)
    mission = etape()

    contenu = client.get(_url("detail", mission)).content.decode()

    assert _url(action_attendue, mission) in contenu


@pytest.mark.parametrize(
    ("etape", "action_attendue"), [(_en_cours, "recuperation"), (_recuperee, "livraison")]
)
def test_l_admin_voit_la_saisie_du_code_a_la_place_du_chauffeur(client, etape, action_attendue):
    _connecte(client, Role.ADMIN)
    mission = etape()

    contenu = client.get(_url("detail", mission)).content.decode()

    assert _url(action_attendue, mission) in contenu


@pytest.mark.parametrize(
    ("etape", "action"), [(_en_cours, "recuperation"), (_recuperee, "livraison")]
)
def test_seul_le_chargeur_clientele_voit_les_codes_sans_les_saisir(client, etape, action):
    """Le chargé clientèle voit les codes mais ne les saisit pas."""
    _connecte(client, Role.CHARGE_CLIENTELE)
    mission = etape()
    statut_avant = mission.statut
    code = mission.code_expediteur if action == "recuperation" else mission.code_destinataire

    contenu = client.get(_url("detail", mission)).content.decode()
    reponse = client.post(_url(action, mission), {"code": code, "km_arrivee": mission.km_depart + 10})

    assert _url(action, mission) not in contenu
    assert reponse.status_code == 403
    mission.refresh_from_db()
    assert mission.statut == statut_avant


@pytest.mark.parametrize(
    ("etape", "action_attendue"), [(_en_cours, "recuperation"), (_recuperee, "livraison")]
)
def test_la_direction_saisit_desormais_aussi_les_codes(client, etape, action_attendue):
    """Retour réunion : la DIRECTION a la même largeur que l'ADMIN (CODES_TERRAIN)."""
    _connecte(client, Role.DIRECTION)
    mission = etape()

    contenu = client.get(_url("detail", mission)).content.decode()

    assert _url(action_attendue, mission) in contenu


def test_une_mission_cloturee_n_a_plus_d_action(client):
    _connecte(client, Role.ADMIN)
    mission = services.cloturer_mission(_livree())

    contenu = client.get(_url("detail", mission)).content.decode()

    assert "Aucune action disponible" in contenu


# --- création ---


def test_le_formulaire_de_creation_s_affiche(client):
    _connecte(client, Role.CHARGE_CLIENTELE)

    reponse = client.get(reverse("missions:creer"))

    assert reponse.status_code == 200
    assert "Nouvelle mission" in reponse.content.decode()


def test_creer_une_mission_valide(client):
    _connecte(client, Role.CHARGE_CLIENTELE)
    societe = ClientFactory()

    reponse = client.post(
        reverse("missions:creer"),
        {
            "client": societe.pk,
            "lieu_chargement": "Abidjan, Port",
            "lieu_livraison": "Bouaké",
            "nature_marchandise": "Ciment",
            "poids_t": "18.50",
            "prix_convenu": "850000",
            "date_depart_prevue": "2026-10-12",
        },
        follow=True,
    )

    mission = Mission.objects.get()
    assert reponse.redirect_chain[-1][0] == _url("detail", mission)
    assert mission.statut == StatutMission.BROUILLON
    assert mission.poids_t == Decimal("18.50")
    assert str(mission.date_depart_prevue) == "2026-10-12"
    assert mission.numero in " ".join(_messages(reponse))


def test_creer_avec_un_poids_nul_affiche_l_erreur_sans_creer(client):
    _connecte(client, Role.DIRECTION)
    societe = ClientFactory()

    reponse = client.post(
        reverse("missions:creer"),
        {
            "client": societe.pk,
            "lieu_chargement": "Abidjan",
            "lieu_livraison": "Bouaké",
            "nature_marchandise": "Ciment",
            "poids_t": "0",
            "prix_convenu": "1000",
        },
    )

    assert reponse.status_code == 200
    assert reponse.context["form"].errors
    assert Mission.objects.count() == 0


def test_creer_sans_client_est_refuse(client):
    _connecte(client, Role.DIRECTION)

    reponse = client.post(reverse("missions:creer"), {"lieu_chargement": "x"})

    assert "client" in reponse.context["form"].errors
    assert Mission.objects.count() == 0


def test_la_creation_est_interdite_aux_autres_roles(client):
    _connecte(client, Role.RH)

    assert client.get(reverse("missions:creer")).status_code == 403
    assert client.post(reverse("missions:creer"), {}).status_code == 403


# --- actions du cycle de vie ---


def test_planifier(client):
    _connecte(client, Role.CHARGE_CLIENTELE)
    mission = _creer()

    reponse = client.post(_url("planifier", mission), follow=True)

    mission.refresh_from_db()
    assert mission.statut == StatutMission.PLANIFIEE
    assert reponse.redirect_chain[-1][0] == _url("detail", mission)
    assert any("planifiée" in m for m in _messages(reponse))


def test_une_action_refusee_par_le_service_affiche_l_erreur_sans_rien_changer(client):
    _connecte(client, Role.CHARGE_CLIENTELE)
    mission = _planifiee()

    reponse = client.post(_url("planifier", mission), follow=True)  # déjà planifiée

    mission.refresh_from_db()
    assert mission.statut == StatutMission.PLANIFIEE
    assert any("Impossible de planifier" in m for m in _messages(reponse))


def test_un_role_sans_droit_ne_peut_pas_agir_meme_par_post_direct(client):
    _connecte(client, Role.CHARGE_CLIENTELE)
    mission = _planifiee()
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()

    reponse = client.post(
        _url("affecter", mission), {"vehicule": camion.pk, "chauffeur": chauffeur.pk}
    )

    mission.refresh_from_db()
    assert reponse.status_code == 403
    assert mission.statut == StatutMission.PLANIFIEE


def test_affecter(client):
    _connecte(client, Role.DIRECTION)
    mission = _planifiee()
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()

    client.post(
        _url("affecter", mission), {"vehicule": camion.pk, "chauffeur": chauffeur.pk}
    )

    mission.refresh_from_db()
    assert mission.statut == StatutMission.AFFECTEE
    assert (mission.vehicule, mission.chauffeur) == (camion, chauffeur)


def test_affecter_un_camion_indisponible_est_refuse(client):
    _connecte(client, Role.DIRECTION)
    mission = _planifiee()
    en_panne = VehiculeFactory(statut=StatutVehicule.EN_MAINTENANCE)

    reponse = client.post(
        _url("affecter", mission),
        {"vehicule": en_panne.pk, "chauffeur": ChauffeurFactory().pk},
        follow=True,
    )

    mission.refresh_from_db()
    assert mission.statut == StatutMission.PLANIFIEE
    assert any(m for m in _messages(reponse))  # message d'erreur du formulaire


def test_affecter_une_charge_trop_lourde_affiche_l_erreur_du_service(client):
    _connecte(client, Role.DIRECTION)
    mission = _planifiee(poids_t=Decimal("30"))
    petit = VehiculeFactory(capacite_charge_t=Decimal("10"))

    reponse = client.post(
        _url("affecter", mission),
        {"vehicule": petit.pk, "chauffeur": ChauffeurFactory().pk},
        follow=True,
    )

    assert any("capacité" in m for m in _messages(reponse))
    mission.refresh_from_db()
    assert mission.statut == StatutMission.PLANIFIEE


def test_demarrer(client):
    _connecte(client, Role.DIRECTION)
    mission = _affectee()

    client.post(_url("demarrer", mission))

    mission.refresh_from_db()
    mission.vehicule.refresh_from_db()
    assert mission.statut == StatutMission.EN_COURS_DEPART
    assert mission.vehicule.statut == StatutVehicule.EN_MISSION


def test_recuperation_avec_un_mauvais_code_est_refusee(client):
    _connecte(client, Role.ADMIN)
    mission = _en_cours()

    reponse = client.post(_url("recuperation", mission), {"code": "AAAAAAAA"}, follow=True)

    mission.refresh_from_db()
    assert mission.statut == StatutMission.EN_COURS_DEPART
    assert "Code incorrect." in _messages(reponse)


def test_recuperation_avec_le_bon_code_meme_en_minuscules(client):
    _connecte(client, Role.ADMIN)
    mission = _en_cours()

    client.post(_url("recuperation", mission), {"code": mission.code_expediteur.lower()})

    mission.refresh_from_db()
    assert mission.statut == StatutMission.EN_COURS_COLIS_RECUPERE


def test_livraison(client):
    _connecte(client, Role.ADMIN)
    mission = _recuperee()

    client.post(
        _url("livraison", mission),
        {"code": mission.code_destinataire, "km_arrivee": mission.km_depart + 250},
    )

    mission.refresh_from_db()
    mission.vehicule.refresh_from_db()
    assert mission.statut == StatutMission.LIVREE
    assert mission.vehicule.kilometrage == mission.km_depart + 250
    assert mission.vehicule.statut == StatutVehicule.DISPONIBLE


def test_livraison_avec_un_km_incoherent_est_refusee(client):
    _connecte(client, Role.ADMIN)
    mission = _recuperee()

    reponse = client.post(
        _url("livraison", mission),
        {"code": mission.code_destinataire, "km_arrivee": mission.km_depart - 1},
        follow=True,
    )

    mission.refresh_from_db()
    assert mission.statut == StatutMission.EN_COURS_COLIS_RECUPERE
    assert any("kilométrage" in m.lower() for m in _messages(reponse))


def test_livraison_sans_km_est_refusee_par_le_formulaire(client):
    _connecte(client, Role.ADMIN)
    mission = _recuperee()

    client.post(_url("livraison", mission), {"code": mission.code_destinataire})

    mission.refresh_from_db()
    assert mission.statut == StatutMission.EN_COURS_COLIS_RECUPERE


def test_cloturer(client):
    _connecte(client, Role.DIRECTION)
    mission = _livree()

    client.post(_url("cloturer", mission))

    mission.refresh_from_db()
    assert mission.statut == StatutMission.CLOTUREE


def test_les_actions_refusent_le_get(client):
    _connecte(client, Role.DIRECTION)
    mission = _creer()

    assert client.get(_url("planifier", mission)).status_code == 405


def test_une_action_sur_une_mission_inconnue_est_introuvable(client):
    _connecte(client, Role.DIRECTION)

    assert client.post(reverse("missions:planifier", args=[999999])).status_code == 404


def test_les_actions_sont_protegees_par_csrf():
    client = Client(enforce_csrf_checks=True)
    client.force_login(UserFactory(role=Role.DIRECTION))
    mission = _creer()

    reponse = client.post(_url("planifier", mission))

    mission.refresh_from_db()
    assert reponse.status_code == 403
    assert mission.statut == StatutMission.BROUILLON


def test_un_parcours_complet_par_l_interface(client):
    """Brouillon → clôturée, uniquement par les écrans, avec les bons rôles (les codes : l'ADMIN)."""
    charge = Client()
    _connecte(charge, Role.CHARGE_CLIENTELE)
    direction = Client()
    _connecte(direction, Role.DIRECTION)
    admin = Client()
    _connecte(admin, Role.ADMIN)
    societe = ClientFactory()
    camion, chauffeur = VehiculeFactory(kilometrage=50000), ChauffeurFactory()

    charge.post(
        reverse("missions:creer"),
        {
            "client": societe.pk,
            "lieu_chargement": "Abidjan",
            "lieu_livraison": "Yamoussoukro",
            "nature_marchandise": "Riz",
            "poids_t": "12",
            "prix_convenu": "600000",
        },
    )
    mission = Mission.objects.get()
    charge.post(_url("planifier", mission))
    direction.post(
        _url("affecter", mission), {"vehicule": camion.pk, "chauffeur": chauffeur.pk}
    )
    direction.post(_url("demarrer", mission))
    mission.refresh_from_db()
    admin.post(_url("recuperation", mission), {"code": mission.code_expediteur})
    admin.post(
        _url("livraison", mission),
        {"code": mission.code_destinataire, "km_arrivee": 50240},
    )
    direction.post(_url("cloturer", mission))

    mission.refresh_from_db()
    camion.refresh_from_db()
    assert mission.statut == StatutMission.CLOTUREE
    assert camion.kilometrage == 50240 and camion.statut == StatutVehicule.DISPONIBLE


# --- suggestions de lieux ---


def test_le_formulaire_propose_les_lieux_deja_utilises(client):
    _connecte(client, Role.CHARGE_CLIENTELE)
    _creer(lieu_chargement="Abidjan", lieu_livraison="Korhogo")

    contenu = client.get(reverse("missions:creer")).content.decode()

    assert '<datalist id="lieux-missions">' in contenu
    assert '<option value="Korhogo">' in contenu
    assert '<option value="Abidjan">' in contenu
    assert contenu.count('list="lieux-missions"') == 2  # chargement et livraison
