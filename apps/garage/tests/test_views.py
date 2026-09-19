"""Écrans du garage : accès par rôle, OR, blocs dans la fiche d'un camion."""

from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.fleet.models import StatutVehicule
from apps.fleet.tests.factories import VehiculeFactory
from apps.garage import services
from apps.garage.models import LieuReparation, OrdreReparation, StatutOr, TypeOr
from apps.missions.tests.test_services import _affectee

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    utilisateur = UserFactory(role=role)
    client.force_login(utilisateur)
    return utilisateur


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


def _ouvrir(camion=None, **surcharges):
    donnees = dict(type_or=TypeOr.CURATIF, lieu=LieuReparation.INTERNE, motif="Fuite d'huile")
    donnees.update(surcharges)
    return services.ouvrir_or(camion or VehiculeFactory(), **donnees)


def _statut(camion):
    camion.refresh_from_db()
    return camion.statut


# --- accès par rôle ---


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.PARCAUTO])
def test_le_garage_est_consultable_par_le_parc_auto_la_direction_et_l_admin(client, role):
    _connecte(client, role)
    ordre = _ouvrir()

    assert client.get(reverse("garage:liste")).status_code == 200
    assert client.get(reverse("garage:detail", args=[ordre.pk])).status_code == 200


@pytest.mark.parametrize("role", [Role.RH, Role.FINANCES, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR])
def test_le_garage_est_interdit_aux_autres_roles(client, role):
    _connecte(client, role)
    ordre = _ouvrir()

    assert client.get(reverse("garage:liste")).status_code == 403
    assert client.get(reverse("garage:detail", args=[ordre.pk])).status_code == 403
    assert client.get(reverse("garage:creer")).status_code == 403


def test_la_direction_est_en_lecture_seule_sur_le_garage(client):
    _connecte(client, Role.DIRECTION)
    camion = VehiculeFactory()
    ordre = _ouvrir()

    assert client.get(reverse("garage:creer")).status_code == 403
    assert client.post(reverse("garage:cloturer", args=[ordre.pk]), {"cout_main_oeuvre": "0"}).status_code == 403
    assert client.post(reverse("garage:immobiliser", args=[camion.pk])).status_code == 403
    ordre.refresh_from_db()
    assert ordre.statut == StatutOr.OUVERT
    assert _statut(camion) == StatutVehicule.DISPONIBLE


def test_un_visiteur_non_connecte_est_renvoye_vers_la_connexion(client):
    reponse = client.get(reverse("garage:liste"))

    assert reponse.status_code == 302
    assert reponse.url.startswith(reverse("accounts:login"))


def test_le_menu_garage_est_visible_du_parc_auto_pas_de_la_rh(client):
    _connecte(client, Role.PARCAUTO)
    assert 'href="/garage/"' in client.get(reverse("home")).content.decode()

    autre = Client()
    _connecte(autre, Role.RH)
    assert 'href="/garage/"' not in autre.get(reverse("home")).content.decode()


# --- liste ---


def test_la_liste_affiche_les_ordres(client):
    _connecte(client, Role.PARCAUTO)
    ordre = _ouvrir(VehiculeFactory(immatriculation="7777 GH 01"), motif="Freins")

    contenu = client.get(reverse("garage:liste")).content.decode()

    assert ordre.numero in contenu and "7777 GH 01" in contenu and "Freins" in contenu
    assert "Ouvert" in contenu


def test_la_liste_vide_affiche_un_message(client):
    _connecte(client, Role.PARCAUTO)

    assert "Aucun ordre de réparation trouvé" in client.get(reverse("garage:liste")).content.decode()


def test_la_liste_filtre(client):
    _connecte(client, Role.PARCAUTO)
    cible = _ouvrir(type_or=TypeOr.PNEUMATIQUES, lieu=LieuReparation.EXTERNE, motif="Crevaison")
    autre = _ouvrir()
    services.cloturer_or(autre)

    par_type = client.get(reverse("garage:liste"), {"type": "PNEUMATIQUES"})
    par_statut = client.get(reverse("garage:liste"), {"statut": "CLOTURE"})
    par_texte = client.get(reverse("garage:liste"), {"q": "crevaison"})

    assert list(par_type.context["ordres"]) == [cible]
    assert list(par_statut.context["ordres"]) == [autre]
    assert list(par_texte.context["ordres"]) == [cible]


def test_la_liste_est_paginee_par_20(client):
    _connecte(client, Role.PARCAUTO)
    for _ in range(21):
        _ouvrir()

    assert len(client.get(reverse("garage:liste"), {"page": 2}).context["ordres"]) == 1


def test_la_liste_n_effectue_pas_une_requete_par_ordre(client, django_assert_max_num_queries):
    _connecte(client, Role.PARCAUTO)
    for _ in range(15):
        _ouvrir()

    with django_assert_max_num_queries(10):
        client.get(reverse("garage:liste"))


def test_le_motif_saisi_est_echappe_contre_le_xss(client):
    _connecte(client, Role.PARCAUTO)
    ordre = _ouvrir(motif="<script>alert(1)</script>")

    for url in (reverse("garage:liste"), reverse("garage:detail", args=[ordre.pk])):
        contenu = client.get(url).content.decode()
        assert "<script>alert(1)</script>" not in contenu
        assert "&lt;script&gt;" in contenu


# --- fiche d'un OR ---


def test_la_fiche_affiche_l_intervention_et_le_camion(client):
    _connecte(client, Role.DIRECTION)
    camion = VehiculeFactory(immatriculation="4444 KL 01")
    ordre = _ouvrir(camion, lieu=LieuReparation.EXTERNE, motif="Bruit moteur")

    contenu = client.get(reverse("garage:detail", args=[ordre.pk])).content.decode()

    assert ordre.numero in contenu and "4444 KL 01" in contenu
    assert "Prestataire externe" in contenu and "Bruit moteur" in contenu
    assert reverse("fleet:detail", args=[camion.pk]) in contenu
    assert "En maintenance" in contenu  # statut actuel du camion


def test_la_fiche_d_un_or_inconnu_est_introuvable(client):
    _connecte(client, Role.PARCAUTO)

    assert client.get(reverse("garage:detail", args=[999999])).status_code == 404


def test_la_fiche_propose_la_cloture_au_parc_auto_seulement_tant_que_l_or_est_ouvert(client):
    ordre = _ouvrir()
    _connecte(client, Role.PARCAUTO)
    assert reverse("garage:cloturer", args=[ordre.pk]) in client.get(
        reverse("garage:detail", args=[ordre.pk])
    ).content.decode()

    direction = Client()
    _connecte(direction, Role.DIRECTION)
    assert reverse("garage:cloturer", args=[ordre.pk]) not in direction.get(
        reverse("garage:detail", args=[ordre.pk])
    ).content.decode()

    services.cloturer_or(ordre)
    assert reverse("garage:cloturer", args=[ordre.pk]) not in client.get(
        reverse("garage:detail", args=[ordre.pk])
    ).content.decode()


# --- ouverture ---


def test_le_formulaire_d_ouverture_s_affiche_et_se_prerempli_depuis_un_camion(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()

    reponse = client.get(reverse("garage:creer"), {"vehicule": camion.pk})

    assert reponse.status_code == 200
    assert reponse.context["form"].initial["vehicule"] == camion.pk


def test_un_parametre_vehicule_invalide_est_ignore(client):
    _connecte(client, Role.PARCAUTO)

    reponse = client.get(reverse("garage:creer"), {"vehicule": "abc"})

    assert reponse.status_code == 200 and reponse.context["form"].initial == {}


def test_ouvrir_un_or(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()

    reponse = client.post(
        reverse("garage:creer"),
        {"vehicule": camion.pk, "type_or": "PREVENTIF", "lieu": "INTERNE", "motif": "Vidange"},
        follow=True,
    )

    ordre = OrdreReparation.objects.get()
    assert reponse.redirect_chain[-1][0] == reverse("garage:detail", args=[ordre.pk])
    assert (ordre.type_or, ordre.lieu, ordre.motif) == ("PREVENTIF", "INTERNE", "Vidange")
    assert _statut(camion) == StatutVehicule.EN_MAINTENANCE
    assert any(ordre.numero in m and "En maintenance" in m for m in _messages(reponse))


def test_ouvrir_un_or_sur_un_camion_en_mission_signale_une_panne(client):
    _connecte(client, Role.PARCAUTO)
    camion = _affectee().vehicule

    client.post(
        reverse("garage:creer"),
        {"vehicule": camion.pk, "type_or": "CURATIF", "lieu": "EXTERNE", "motif": "Panne"},
    )

    assert _statut(camion) == StatutVehicule.EN_MAINTENANCE


@pytest.mark.parametrize(
    "champ", [{"motif": ""}, {"type_or": "PEINTURE"}, {"lieu": "MAISON"}, {"vehicule": ""}]
)
def test_ouvrir_avec_des_donnees_invalides_est_refuse(client, champ):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()
    donnees = {"vehicule": camion.pk, "type_or": "CURATIF", "lieu": "INTERNE", "motif": "x"}
    donnees.update(champ)

    reponse = client.post(reverse("garage:creer"), donnees)

    assert reponse.status_code == 200 and reponse.context["form"].errors
    assert OrdreReparation.objects.count() == 0
    assert _statut(camion) == StatutVehicule.DISPONIBLE


# --- clôture ---


def test_cloturer_un_or_recalcule_le_statut_du_camion(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()
    ordre = _ouvrir(camion)

    reponse = client.post(
        reverse("garage:cloturer", args=[ordre.pk]), {"cout_main_oeuvre": "45000"}, follow=True
    )

    ordre.refresh_from_db()
    assert ordre.statut == StatutOr.CLOTURE and ordre.cout_main_oeuvre == Decimal("45000.00")
    assert _statut(camion) == StatutVehicule.DISPONIBLE
    assert any("Disponible" in m for m in _messages(reponse))


def test_cloturer_un_or_d_un_camion_reserve_le_repasse_en_mission(client):
    _connecte(client, Role.PARCAUTO)
    camion = _affectee().vehicule
    ordre = _ouvrir(camion)

    client.post(reverse("garage:cloturer", args=[ordre.pk]), {"cout_main_oeuvre": "0"})

    assert _statut(camion) == StatutVehicule.EN_MISSION


def test_cloturer_avec_une_main_d_oeuvre_negative_est_refuse(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()
    ordre = _ouvrir(camion)

    client.post(reverse("garage:cloturer", args=[ordre.pk]), {"cout_main_oeuvre": "-5"})

    ordre.refresh_from_db()
    assert ordre.statut == StatutOr.OUVERT
    assert _statut(camion) == StatutVehicule.EN_MAINTENANCE


def test_cloturer_deux_fois_affiche_l_erreur(client):
    _connecte(client, Role.PARCAUTO)
    ordre = _ouvrir()
    services.cloturer_or(ordre)

    reponse = client.post(
        reverse("garage:cloturer", args=[ordre.pk]), {"cout_main_oeuvre": "0"}, follow=True
    )

    assert any("déjà clôturé" in m for m in _messages(reponse))


def test_la_cloture_refuse_le_get_et_un_or_inconnu(client):
    _connecte(client, Role.PARCAUTO)
    ordre = _ouvrir()

    assert client.get(reverse("garage:cloturer", args=[ordre.pk])).status_code == 405
    assert client.post(reverse("garage:cloturer", args=[999999]), {"cout_main_oeuvre": "0"}).status_code == 404


# --- statut des camions ---


def test_immobiliser_puis_remettre_en_service_par_les_ecrans(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()

    reponse = client.post(reverse("garage:immobiliser", args=[camion.pk]), follow=True)
    assert _statut(camion) == StatutVehicule.IMMOBILISE
    assert reponse.redirect_chain[-1][0] == reverse("fleet:detail", args=[camion.pk])
    assert any("Immobilisé" in m for m in _messages(reponse))

    client.post(reverse("garage:remise_en_service", args=[camion.pk]))
    assert _statut(camion) == StatutVehicule.DISPONIBLE


def test_mettre_hors_service_par_l_ecran(client):
    _connecte(client, Role.ADMIN)
    camion = VehiculeFactory()

    client.post(reverse("garage:hors_service", args=[camion.pk]))

    assert _statut(camion) == StatutVehicule.HORS_SERVICE


def test_immobiliser_un_camion_reserve_affiche_l_erreur(client):
    _connecte(client, Role.PARCAUTO)
    camion = _affectee().vehicule

    reponse = client.post(reverse("garage:immobiliser", args=[camion.pk]), follow=True)

    assert any("ouvrez un OR" in m for m in _messages(reponse))
    assert _statut(camion) == StatutVehicule.DISPONIBLE


def test_remettre_en_service_un_camion_disponible_affiche_l_erreur(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()

    reponse = client.post(reverse("garage:remise_en_service", args=[camion.pk]), follow=True)

    assert any("immobilisé ou hors service" in m for m in _messages(reponse))


def test_les_actions_de_statut_refusent_le_get_et_un_camion_inconnu(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()

    assert client.get(reverse("garage:immobiliser", args=[camion.pk])).status_code == 405
    assert client.post(reverse("garage:immobiliser", args=[999999])).status_code == 404


# --- bloc « Maintenance » dans la fiche d'un camion ---


def test_la_fiche_du_camion_affiche_le_bloc_maintenance_et_l_historique(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()
    ordre = _ouvrir(camion)

    contenu = client.get(reverse("fleet:detail", args=[camion.pk])).content.decode()

    assert "Maintenance" in contenu and ordre.numero in contenu
    assert f"{reverse('garage:creer')}?vehicule={camion.pk}" in contenu
    assert reverse("garage:immobiliser", args=[camion.pk]) in contenu
    assert reverse("garage:remise_en_service", args=[camion.pk]) not in contenu


def test_le_bloc_propose_la_remise_en_service_d_un_camion_immobilise(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory(statut=StatutVehicule.IMMOBILISE)

    contenu = client.get(reverse("fleet:detail", args=[camion.pk])).content.decode()

    assert reverse("garage:remise_en_service", args=[camion.pk]) in contenu
    assert reverse("garage:immobiliser", args=[camion.pk]) not in contenu


def test_la_direction_voit_l_historique_sans_les_boutons(client):
    _connecte(client, Role.DIRECTION)
    camion = VehiculeFactory()
    ordre = _ouvrir(camion)

    contenu = client.get(reverse("fleet:detail", args=[camion.pk])).content.decode()

    assert ordre.numero in contenu
    assert reverse("garage:immobiliser", args=[camion.pk]) not in contenu
    assert f"{reverse('garage:creer')}?vehicule=" not in contenu


def test_les_formulaires_du_garage_sont_proteges_par_csrf():
    client = Client(enforce_csrf_checks=True)
    client.force_login(UserFactory(role=Role.PARCAUTO))
    camion = VehiculeFactory()

    assert client.post(reverse("garage:immobiliser", args=[camion.pk])).status_code == 403
    assert client.post(reverse("garage:creer"), {"vehicule": camion.pk}).status_code == 403
    assert _statut(camion) == StatutVehicule.DISPONIBLE


# --- gardes des blocs (défense en profondeur) ---


@pytest.mark.parametrize("role", [Role.RH, Role.FINANCES, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR])
def test_le_bloc_maintenance_n_est_jamais_fourni_aux_roles_sans_acces(role):
    from types import SimpleNamespace

    from apps.garage import sections

    camion = VehiculeFactory()

    assert sections.section_maintenance(camion, SimpleNamespace(role_effectif=role)) is None
