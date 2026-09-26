"""R3 — Modification d'une mission (avenant-separation-des-taches.md) : DIRECTION et ADMIN
seulement, tant que le colis n'est pas encore récupéré ; changer un lieu régénère les codes,
changer camion/chauffeur revérifie leur disponibilité."""

from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.drivers.models import StatutChauffeur
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.models import StatutVehicule
from apps.fleet.tests.factories import VehiculeFactory
from apps.missions import services
from apps.missions.exceptions import AffectationImpossible, MissionError, TransitionMissionInterdite
from apps.missions.models import Mission, StatutMission

from .test_services import _affectee, _creer, _en_cours, _livree, _planifiee, _recuperee

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    utilisateur = UserFactory(role=role)
    client.force_login(utilisateur)
    return utilisateur


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


def _champs(mission, **surcharges):
    donnees = dict(
        lieu_chargement=mission.lieu_chargement,
        lieu_livraison=mission.lieu_livraison,
        nature_marchandise=mission.nature_marchandise,
        poids_t=mission.poids_t,
        prix_convenu=mission.prix_convenu,
        date_depart_prevue=mission.date_depart_prevue,
    )
    donnees.update(surcharges)
    return donnees


def _poste(mission, **surcharges):
    """``_champs`` prête pour un POST HTTP (le client de test n'encode pas ``None``)."""
    donnees = _champs(mission, **surcharges)
    if donnees.get("date_depart_prevue") is None:
        donnees["date_depart_prevue"] = ""
    return donnees


# --- service : statuts modifiables ---


@pytest.mark.parametrize("fabrique", [_creer, _planifiee, _affectee, _en_cours])
def test_modifiable_jusqu_a_en_cours_depart(fabrique):
    mission = fabrique()

    modifiee = services.modifier_mission(mission, **_champs(mission, nature_marchandise="Sable"))

    assert modifiee.nature_marchandise == "Sable"


@pytest.mark.parametrize("fabrique", [_recuperee, _livree])
def test_plus_modifiable_a_partir_de_colis_recupere(fabrique):
    mission = fabrique()

    with pytest.raises(TransitionMissionInterdite):
        services.modifier_mission(mission, **_champs(mission, nature_marchandise="Sable"))


# --- validations ---


def test_poids_et_prix_restent_valides():
    mission = _creer()

    with pytest.raises(MissionError, match="poids"):
        services.modifier_mission(mission, **_champs(mission, poids_t=Decimal("0")))
    with pytest.raises(MissionError, match="négatif"):
        services.modifier_mission(mission, **_champs(mission, prix_convenu=Decimal("-1")))


def test_le_prix_convenu_est_bien_modifiable():
    mission = _creer()

    modifiee = services.modifier_mission(mission, **_champs(mission, prix_convenu=Decimal("999000")))

    assert modifiee.prix_convenu == Decimal("999000")


# --- lieu → codes régénérés ---


def test_changer_un_lieu_regenere_les_deux_codes():
    mission = _creer()
    ancien_expediteur, ancien_destinataire = mission.code_expediteur, mission.code_destinataire

    modifiee = services.modifier_mission(mission, **_champs(mission, lieu_livraison="Korhogo"))

    assert modifiee.code_expediteur != ancien_expediteur
    assert modifiee.code_destinataire != ancien_destinataire
    assert modifiee.code_expediteur != modifiee.code_destinataire


def test_ne_pas_changer_le_lieu_garde_les_memes_codes():
    mission = _creer()
    code = mission.code_expediteur

    modifiee = services.modifier_mission(mission, **_champs(mission, nature_marchandise="Sable"))

    assert modifiee.code_expediteur == code


# --- camion / chauffeur ---


def test_reaffecter_camion_et_chauffeur_sur_une_mission_affectee():
    mission = _affectee()
    nouveau_vehicule, nouveau_chauffeur = VehiculeFactory(), ChauffeurFactory()

    modifiee = services.modifier_mission(
        mission, **_champs(mission), vehicule=nouveau_vehicule, chauffeur=nouveau_chauffeur
    )

    assert (modifiee.vehicule, modifiee.chauffeur) == (nouveau_vehicule, nouveau_chauffeur)


def test_reaffecter_revalide_la_disponibilite():
    mission = _affectee()

    with pytest.raises(AffectationImpossible, match="camion"):
        services.modifier_mission(
            mission, **_champs(mission),
            vehicule=VehiculeFactory(statut=StatutVehicule.EN_MAINTENANCE), chauffeur=ChauffeurFactory(),
        )


def test_reaffecter_refuse_un_camion_deja_reserve_par_une_autre_mission():
    vehicule = VehiculeFactory()
    _affectee(vehicule=vehicule)
    mission = _affectee()

    with pytest.raises(AffectationImpossible, match="déjà réservé"):
        services.modifier_mission(
            mission, **_champs(mission), vehicule=vehicule, chauffeur=ChauffeurFactory()
        )


def test_ne_pas_changer_camion_ni_chauffeur_ne_revalide_rien():
    """Le camion actuel n'est pas « disponible » au sens strict une fois affecté ailleurs (une autre
    mission) : mais tant qu'on ne le change pas, aucune revérification n'a lieu."""
    mission = _affectee()
    vehicule, chauffeur = mission.vehicule, mission.chauffeur

    modifiee = services.modifier_mission(mission, **_champs(mission), vehicule=vehicule, chauffeur=chauffeur)

    assert (modifiee.vehicule, modifiee.chauffeur) == (vehicule, chauffeur)


def test_reaffecter_impossible_apres_le_depart():
    mission = _en_cours()

    with pytest.raises(TransitionMissionInterdite, match="avant le départ"):
        services.modifier_mission(
            mission, **_champs(mission), vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory()
        )


def test_reaffecter_impossible_avant_l_affectation():
    mission = _planifiee()

    with pytest.raises(TransitionMissionInterdite, match="avant le départ"):
        services.modifier_mission(
            mission, **_champs(mission), vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory()
        )


def test_camion_et_chauffeur_se_changent_ensemble():
    mission = _affectee()

    with pytest.raises(MissionError, match="ensemble"):
        services.modifier_mission(mission, **_champs(mission), vehicule=VehiculeFactory())


# --- audit ---


def test_la_modification_est_tracee_dans_l_audit():
    from apps.audit.models import ActionChoices, AuditLog

    mission = _creer()

    services.modifier_mission(mission, **_champs(mission, nature_marchandise="Sable"))

    entree = AuditLog.objects.filter(entite="Mission", entite_id=mission.pk, action=ActionChoices.UPDATE).latest("date_heure")
    assert entree.nouvelle_valeur.get("nature_marchandise") == "Sable"
    assert "code_expediteur" not in (entree.ancienne_valeur or {})  # codes exclus de l'audit


# --- permissions ---


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION])
def test_admin_et_direction_modifient(client, role):
    _connecte(client, role)
    mission = _creer()

    reponse = client.post(
        reverse("missions:modifier", args=[mission.pk]),
        _poste(mission, nature_marchandise="Sable"),
        follow=True,
    )

    mission.refresh_from_db()
    assert mission.nature_marchandise == "Sable"
    assert any("modifiée" in m for m in _messages(reponse))


@pytest.mark.parametrize("role", [Role.CHARGE_CLIENTELE, Role.PARCAUTO, Role.FINANCES, Role.RH])
def test_les_autres_roles_ne_modifient_pas(client, role):
    _connecte(client, role)
    mission = _creer()

    for methode, args in ((client.get, ()), (client.post, (_poste(mission),))):
        reponse = methode(reverse("missions:modifier", args=[mission.pk]), *args)
        assert reponse.status_code == 403


def test_le_lien_modifier_n_apparait_que_pour_les_bons_roles_et_statuts(client):
    mission = _recuperee()

    _connecte(client, Role.DIRECTION)
    page = client.get(reverse("missions:detail", args=[mission.pk])).content.decode()
    assert reverse("missions:modifier", args=[mission.pk]) not in page  # plus modifiable

    autre = _creer()
    page = client.get(reverse("missions:detail", args=[autre.pk])).content.decode()
    assert reverse("missions:modifier", args=[autre.pk]) in page

    _connecte(client, Role.CHARGE_CLIENTELE)
    page = client.get(reverse("missions:detail", args=[autre.pk])).content.decode()
    assert reverse("missions:modifier", args=[autre.pk]) not in page  # pas le bon rôle


# --- écran ---


def test_le_formulaire_est_prerempli(client):
    _connecte(client, Role.DIRECTION)
    mission = _creer()

    reponse = client.get(reverse("missions:modifier", args=[mission.pk]))

    assert reponse.context["form"].initial["nature_marchandise"] == mission.nature_marchandise
    assert "vehicule" not in reponse.context["form"].fields  # pas encore affectée


def test_le_formulaire_propose_camion_et_chauffeur_une_fois_affectee(client):
    _connecte(client, Role.DIRECTION)
    mission = _affectee()

    reponse = client.get(reverse("missions:modifier", args=[mission.pk]))

    assert "vehicule" in reponse.context["form"].fields
    assert reponse.context["form"].initial["vehicule"] == mission.vehicule_id


def test_acceder_a_l_ecran_sur_une_mission_non_modifiable_renvoie_a_la_fiche(client):
    _connecte(client, Role.DIRECTION)
    mission = _livree()

    reponse = client.get(reverse("missions:modifier", args=[mission.pk]), follow=True)

    assert reponse.redirect_chain[-1][0] == reverse("missions:detail", args=[mission.pk])
    assert any("n'est plus modifiable" in m for m in _messages(reponse))


def test_une_erreur_metier_reste_sur_le_formulaire(client):
    _connecte(client, Role.DIRECTION)
    mission = _creer()

    reponse = client.post(
        reverse("missions:modifier", args=[mission.pk]), _poste(mission, poids_t="0"),
    )

    assert reponse.status_code == 200
    assert "strictement positif" in reponse.content.decode()
    mission.refresh_from_db()
    assert mission.poids_t != Decimal("0")


def test_le_client_n_est_pas_modifiable(client):
    """Aucun champ « client » sur l'écran : il n'apparaît nulle part dans le formulaire."""
    _connecte(client, Role.DIRECTION)
    mission = _creer()

    reponse = client.get(reverse("missions:modifier", args=[mission.pk]))

    assert "client" not in reponse.context["form"].fields
