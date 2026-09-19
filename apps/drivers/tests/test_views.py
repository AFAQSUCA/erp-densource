"""Écrans des chauffeurs : accès par rôle, liste, fiche, modification, statut."""

from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.drivers.models import StatutChauffeur

from .factories import ChauffeurFactory

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    utilisateur = UserFactory(role=role)
    client.force_login(utilisateur)
    return utilisateur


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


def _donnees(**surcharges):
    donnees = {
        "telephone": "+2250701020304",
        "contact_urgence": "Awa - 0700000000",
        "numero_permis": "PC-555",
        "categories_permis": ["C", "E"],
        "date_expiration_permis": "2029-05-01",
        "date_expiration_visite_medicale": "2027-05-01",
    }
    donnees.update(surcharges)
    return donnees


# --- accès par rôle ---


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.RH])
def test_les_chauffeurs_sont_accessibles_a_la_direction_a_la_rh_et_a_l_admin(client, role):
    _connecte(client, role)

    assert client.get(reverse("drivers:liste")).status_code == 200


@pytest.mark.parametrize(
    "role", [Role.PARCAUTO, Role.FINANCES, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR]
)
def test_les_chauffeurs_sont_interdits_aux_autres_roles(client, role):
    _connecte(client, role)
    fiche = ChauffeurFactory()

    assert client.get(reverse("drivers:liste")).status_code == 403
    assert client.get(reverse("drivers:detail", args=[fiche.pk])).status_code == 403
    assert client.get(reverse("drivers:modifier", args=[fiche.pk])).status_code == 403
    assert client.post(reverse("drivers:statut", args=[fiche.pk]), {"statut": "SUSPENDU"}).status_code == 403
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE


def test_un_visiteur_non_connecte_est_renvoye_vers_la_connexion(client):
    reponse = client.get(reverse("drivers:liste"))

    assert reponse.status_code == 302
    assert reponse.url.startswith(reverse("accounts:login"))


def test_le_menu_chauffeurs_est_visible_de_la_rh_mais_pas_du_parc_auto(client):
    _connecte(client, Role.RH)
    assert 'href="/chauffeurs/"' in client.get(reverse("home")).content.decode()

    autre = Client()
    _connecte(autre, Role.PARCAUTO)
    assert 'href="/chauffeurs/"' not in autre.get(reverse("home")).content.decode()


# --- liste ---


def test_la_liste_affiche_les_chauffeurs_avec_leur_statut(client):
    _connecte(client, Role.DIRECTION)
    ChauffeurFactory(personnel__nom="Traoré", personnel__prenom="Moussa", telephone="0700112233")

    contenu = client.get(reverse("drivers:liste")).content.decode()

    assert "Moussa Traoré" in contenu
    assert "0700112233" in contenu
    assert "Disponible" in contenu


def test_la_liste_vide_affiche_un_message(client):
    _connecte(client, Role.DIRECTION)

    assert "Aucun chauffeur trouvé" in client.get(reverse("drivers:liste")).content.decode()


def test_la_liste_filtre_par_statut_et_recherche(client):
    _connecte(client, Role.RH)
    libre = ChauffeurFactory(personnel__nom="Adou")
    ChauffeurFactory(personnel__nom="Bamba", statut=StatutChauffeur.SUSPENDU)

    par_statut = client.get(reverse("drivers:liste"), {"statut": "DISPONIBLE"})
    par_texte = client.get(reverse("drivers:liste"), {"q": "adou"})

    assert [l["chauffeur"] for l in par_statut.context["lignes"]] == [libre]
    assert [l["chauffeur"] for l in par_texte.context["lignes"]] == [libre]


def test_la_liste_signale_et_filtre_les_echeances_proches(client):
    _connecte(client, Role.DIRECTION)
    aujourdhui = timezone.localdate()
    alerte = ChauffeurFactory(
        personnel__nom="Alerte", date_expiration_permis=aujourdhui + timedelta(days=10)
    )
    ChauffeurFactory(
        personnel__nom="Tranquille",
        date_expiration_permis=aujourdhui + timedelta(days=900),
        date_expiration_visite_medicale=aujourdhui + timedelta(days=900),
    )

    complet = client.get(reverse("drivers:liste"))
    filtre = client.get(reverse("drivers:liste"), {"alerte": "1"})

    assert "À renouveler" in complet.content.decode()
    assert [l["chauffeur"] for l in filtre.context["lignes"]] == [alerte]


def test_la_liste_est_paginee_par_20(client):
    _connecte(client, Role.DIRECTION)
    for _ in range(21):
        ChauffeurFactory()

    page2 = client.get(reverse("drivers:liste"), {"page": 2})

    assert len(page2.context["lignes"]) == 1


def test_la_liste_n_effectue_pas_une_requete_par_chauffeur(client, django_assert_max_num_queries):
    _connecte(client, Role.DIRECTION)
    for _ in range(15):
        ChauffeurFactory()

    with django_assert_max_num_queries(10):
        client.get(reverse("drivers:liste"))


def test_les_donnees_saisies_sont_echappees_contre_le_xss(client):
    _connecte(client, Role.DIRECTION)
    ChauffeurFactory(telephone="<script>alert(1)</script>")

    contenu = client.get(reverse("drivers:liste")).content.decode()

    assert "<script>alert(1)</script>" not in contenu
    assert "&lt;script&gt;" in contenu


# --- fiche ---


def test_la_fiche_affiche_l_identite_les_contacts_et_les_echeances(client):
    _connecte(client, Role.DIRECTION)
    aujourdhui = timezone.localdate()
    fiche = ChauffeurFactory(
        personnel__nom="Traoré",
        personnel__prenom="Moussa",
        personnel__matricule="CH-007",
        telephone="0700112233",
        contact_urgence="Fatou 0701",
        numero_permis="PC-42",
        categories_permis=["C", "E"],
        date_expiration_permis=aujourdhui - timedelta(days=5),
        date_expiration_visite_medicale=aujourdhui + timedelta(days=12),
    )

    reponse = client.get(reverse("drivers:detail", args=[fiche.pk]))
    contenu = reponse.content.decode()

    for attendu in ("Moussa Traoré", "CH-007", "0700112233", "Fatou 0701", "PC-42", "C, E"):
        assert attendu in contenu, attendu
    assert "Expiré" in contenu and "depuis 5 j" in contenu
    assert "À renouveler" in contenu and "dans 12 j" in contenu


def test_la_fiche_signale_les_informations_manquantes(client):
    _connecte(client, Role.DIRECTION)
    fiche = ChauffeurFactory()

    contenu = client.get(reverse("drivers:detail", args=[fiche.pk])).content.decode()

    assert "Non renseigné" in contenu and "Non renseignées" in contenu


def test_la_fiche_d_un_chauffeur_inconnu_est_introuvable(client):
    _connecte(client, Role.DIRECTION)

    assert client.get(reverse("drivers:detail", args=[999999])).status_code == 404


def test_la_fiche_propose_le_changement_de_statut_sauf_en_mission_ou_en_conge(client):
    _connecte(client, Role.DIRECTION)
    libre = ChauffeurFactory()
    en_mission = ChauffeurFactory(statut=StatutChauffeur.EN_MISSION)

    page_libre = client.get(reverse("drivers:detail", args=[libre.pk])).content.decode()
    page_mission = client.get(reverse("drivers:detail", args=[en_mission.pk])).content.decode()

    assert reverse("drivers:statut", args=[libre.pk]) in page_libre
    assert reverse("drivers:statut", args=[en_mission.pk]) not in page_mission
    assert "géré automatiquement" in page_mission


# --- modification ---


def test_le_formulaire_de_modification_est_prerempli(client):
    _connecte(client, Role.RH)
    fiche = ChauffeurFactory(telephone="0700112233", categories_permis=["C"])

    reponse = client.get(reverse("drivers:modifier", args=[fiche.pk]))

    assert reponse.context["form"].initial["telephone"] == "0700112233"
    assert reponse.context["form"].initial["categories_permis"] == ["C"]
    assert fiche.personnel.matricule in reponse.content.decode()


def test_modifier_une_fiche(client):
    _connecte(client, Role.RH)
    fiche = ChauffeurFactory()

    reponse = client.post(reverse("drivers:modifier", args=[fiche.pk]), _donnees(), follow=True)

    fiche.refresh_from_db()
    assert reponse.redirect_chain[-1][0] == reverse("drivers:detail", args=[fiche.pk])
    assert fiche.numero_permis == "PC-555"
    assert fiche.categories_permis == ["C", "E"]
    assert str(fiche.date_expiration_permis) == "2029-05-01"
    assert any("mise à jour" in m for m in _messages(reponse))


def test_modifier_avec_une_categorie_inconnue_est_refuse_par_le_formulaire(client):
    _connecte(client, Role.RH)
    fiche = ChauffeurFactory()

    reponse = client.post(
        reverse("drivers:modifier", args=[fiche.pk]), _donnees(categories_permis=["C", "Z"])
    )

    fiche.refresh_from_db()
    assert reponse.status_code == 200
    assert reponse.context["form"].errors
    assert fiche.categories_permis == []


def test_modifier_avec_une_date_invalide_est_refuse(client):
    _connecte(client, Role.RH)
    fiche = ChauffeurFactory()

    reponse = client.post(
        reverse("drivers:modifier", args=[fiche.pk]), _donnees(date_expiration_permis="31/02/2029")
    )

    assert reponse.context["form"].errors
    fiche.refresh_from_db()
    assert fiche.numero_permis == ""


def test_modifier_un_chauffeur_inconnu_est_introuvable(client):
    _connecte(client, Role.RH)

    assert client.get(reverse("drivers:modifier", args=[999999])).status_code == 404


# --- statut ---


def test_suspendre_puis_reactiver_un_chauffeur(client):
    _connecte(client, Role.DIRECTION)
    fiche = ChauffeurFactory()

    reponse = client.post(reverse("drivers:statut", args=[fiche.pk]), {"statut": "SUSPENDU"}, follow=True)
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.SUSPENDU
    assert any("Suspendu" in m for m in _messages(reponse))

    client.post(reverse("drivers:statut", args=[fiche.pk]), {"statut": "DISPONIBLE"})
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE


def test_changer_le_statut_d_un_chauffeur_en_mission_est_refuse(client):
    _connecte(client, Role.DIRECTION)
    fiche = ChauffeurFactory(statut=StatutChauffeur.EN_MISSION)

    reponse = client.post(reverse("drivers:statut", args=[fiche.pk]), {"statut": "SUSPENDU"}, follow=True)

    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.EN_MISSION
    assert any("missions et les congés" in m for m in _messages(reponse))


@pytest.mark.parametrize("cible", ["EN_MISSION", "EN_CONGE", "VOLANT", ""])
def test_un_statut_non_manuel_est_refuse_par_le_formulaire(client, cible):
    _connecte(client, Role.DIRECTION)
    fiche = ChauffeurFactory()

    client.post(reverse("drivers:statut", args=[fiche.pk]), {"statut": cible})

    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE


def test_le_changement_de_statut_refuse_le_get(client):
    _connecte(client, Role.DIRECTION)
    fiche = ChauffeurFactory()

    assert client.get(reverse("drivers:statut", args=[fiche.pk])).status_code == 405


def test_un_chauffeur_suspendu_ne_peut_plus_etre_affecte_a_une_mission():
    """Lien avec les missions : l'affectation exige un chauffeur « Disponible »."""
    from apps.fleet.tests.factories import VehiculeFactory
    from apps.missions import services as missions_services
    from apps.missions.exceptions import AffectationImpossible
    from apps.missions.tests.test_services import _planifiee
    from apps.drivers import services

    fiche = ChauffeurFactory()
    services.changer_statut_manuel(fiche, StatutChauffeur.SUSPENDU)

    with pytest.raises(AffectationImpossible, match="chauffeur"):
        missions_services.affecter_mission(
            _planifiee(), vehicule=VehiculeFactory(), chauffeur=fiche
        )


def test_les_formulaires_des_chauffeurs_sont_proteges_par_csrf():
    client = Client(enforce_csrf_checks=True)
    client.force_login(UserFactory(role=Role.DIRECTION))
    fiche = ChauffeurFactory()

    assert client.post(reverse("drivers:modifier", args=[fiche.pk]), _donnees()).status_code == 403
    assert client.post(reverse("drivers:statut", args=[fiche.pk]), {"statut": "SUSPENDU"}).status_code == 403
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE and fiche.numero_permis == ""
