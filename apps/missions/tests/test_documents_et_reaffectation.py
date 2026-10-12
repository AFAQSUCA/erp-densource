"""Audit M3-10 : un chauffeur au permis ou à la visite médicale expiré n'est pas affectable.
Audit M5-09 : réaffecter seulement le camion ou seulement le chauffeur marche, et une hausse du poids est
recontrôlée contre la capacité du camion conservé."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.models import DocumentReglementaire, TypeDocument
from apps.fleet.tests.factories import VehiculeEnRegleFactory, VehiculeFactory
from apps.missions import services
from apps.missions.exceptions import AffectationImpossible, DemarrageImpossible

from .test_modification import _champs
from .test_services import _affectee, _planifiee

pytestmark = pytest.mark.django_db

HIER = timezone.localdate() - timedelta(days=1)
DEMAIN = timezone.localdate() + timedelta(days=1)


# --- documents du chauffeur ---


def test_un_permis_expire_bloque_l_affectation():
    mission = _planifiee()
    chauffeur = ChauffeurFactory(date_expiration_permis=HIER)

    with pytest.raises(AffectationImpossible, match=r"permis de conduire \(expiré le"):
        services.affecter_mission(mission, vehicule=VehiculeEnRegleFactory(), chauffeur=chauffeur)


def test_une_visite_medicale_expiree_bloque_l_affectation():
    mission = _planifiee()
    chauffeur = ChauffeurFactory(date_expiration_visite_medicale=HIER)

    with pytest.raises(AffectationImpossible, match="visite médicale"):
        services.affecter_mission(mission, vehicule=VehiculeEnRegleFactory(), chauffeur=chauffeur)


def test_les_deux_documents_expires_sont_nommes():
    mission = _planifiee()
    chauffeur = ChauffeurFactory(date_expiration_permis=HIER, date_expiration_visite_medicale=HIER)

    with pytest.raises(AffectationImpossible, match="permis de conduire.* ; visite médicale"):
        services.affecter_mission(mission, vehicule=VehiculeEnRegleFactory(), chauffeur=chauffeur)


def test_l_expiration_aujourd_hui_ne_bloque_pas_encore():
    aujourd_hui = timezone.localdate()
    chauffeur = ChauffeurFactory(date_expiration_permis=aujourd_hui, date_expiration_visite_medicale=DEMAIN)

    mission = services.affecter_mission(_planifiee(), vehicule=VehiculeEnRegleFactory(), chauffeur=chauffeur)

    assert mission.chauffeur == chauffeur


# --- fiche permis incomplète : bloquante depuis la décision du 12/10/2026 (audit M5-04) ---


@pytest.mark.parametrize(
    ("champs", "message"),
    [
        ({"numero_permis": ""}, "n° de permis non renseigné"),
        ({"categories_permis": []}, "ni catégorie C ni catégorie E"),
        ({"date_expiration_permis": None}, "date d'expiration du permis non renseignée"),
        ({"date_expiration_visite_medicale": None}, "visite médicale non renseignée"),
    ],
)
def test_une_fiche_permis_incomplete_bloque_l_affectation(champs, message):
    chauffeur = ChauffeurFactory(**champs)

    with pytest.raises(AffectationImpossible, match=message):
        services.affecter_mission(_planifiee(), vehicule=VehiculeEnRegleFactory(), chauffeur=chauffeur)


@pytest.mark.parametrize("categories", [["C"], ["E"], ["C", "E"]])
def test_la_categorie_c_ou_e_suffit(categories):
    chauffeur = ChauffeurFactory(categories_permis=categories)

    mission = services.affecter_mission(_planifiee(), vehicule=VehiculeEnRegleFactory(), chauffeur=chauffeur)

    assert mission.chauffeur == chauffeur


def test_tous_les_manques_sont_nommes_ensemble():
    chauffeur = ChauffeurFactory(numero_permis="", date_expiration_visite_medicale=None)

    with pytest.raises(AffectationImpossible, match="n° de permis non renseigné ; visite médicale non renseignée"):
        services.affecter_mission(_planifiee(), vehicule=VehiculeEnRegleFactory(), chauffeur=chauffeur)


# --- documents du camion : bloquants s'ils sont expirés ou manquants (audit AUD-12) ---


def test_un_camion_sans_assurance_n_est_pas_affectable():
    camion = VehiculeEnRegleFactory()
    DocumentReglementaire.objects.filter(vehicule=camion, type_document=TypeDocument.ASSURANCE).delete()

    with pytest.raises(AffectationImpossible, match=r"ne peut pas rouler : assurance non enregistrée"):
        services.affecter_mission(_planifiee(), vehicule=camion, chauffeur=ChauffeurFactory())


def test_un_camion_a_la_visite_technique_expiree_n_est_pas_affectable():
    camion = VehiculeEnRegleFactory()
    DocumentReglementaire.objects.filter(vehicule=camion, type_document=TypeDocument.VISITE_TECHNIQUE).update(
        date_expiration=HIER
    )

    with pytest.raises(AffectationImpossible, match="visite technique expirée le"):
        services.affecter_mission(_planifiee(), vehicule=camion, chauffeur=ChauffeurFactory())


def test_un_camion_sans_aucun_document_les_nomme_tous():
    camion = VehiculeFactory()

    with pytest.raises(AffectationImpossible) as erreur:
        services.affecter_mission(_planifiee(), vehicule=camion, chauffeur=ChauffeurFactory())

    for libelle in ("carte grise", "assurance", "visite technique", "patente"):
        assert f"{libelle} non enregistrée" in str(erreur.value)


def test_un_document_du_camion_expire_depuis_l_affectation_bloque_le_depart():
    mission = _affectee()
    DocumentReglementaire.objects.filter(vehicule=mission.vehicule, type_document=TypeDocument.ASSURANCE).update(
        date_expiration=HIER
    )

    with pytest.raises(DemarrageImpossible, match="assurance expirée le"):
        services.demarrer_mission(mission)


def test_le_depart_est_refuse_si_un_document_a_expire_depuis_l_affectation():
    chauffeur = ChauffeurFactory(date_expiration_permis=DEMAIN)
    mission = _affectee(chauffeur=chauffeur)
    type(chauffeur).objects.filter(pk=chauffeur.pk).update(date_expiration_permis=HIER)

    with pytest.raises(DemarrageImpossible, match="permis de conduire"):
        services.demarrer_mission(mission)


def test_reaffecter_vers_un_chauffeur_au_permis_expire_est_refuse():
    mission = _affectee()

    with pytest.raises(AffectationImpossible, match="permis de conduire"):
        services.modifier_mission(
            mission, **_champs(mission), vehicule=mission.vehicule,
            chauffeur=ChauffeurFactory(date_expiration_permis=HIER),
        )


# --- réaffectation partielle ---


def test_changer_seulement_le_camion_garde_le_chauffeur():
    mission = _affectee()
    chauffeur, nouveau = mission.chauffeur, VehiculeEnRegleFactory()

    modifiee = services.modifier_mission(mission, **_champs(mission), vehicule=nouveau, chauffeur=chauffeur)

    assert (modifiee.vehicule, modifiee.chauffeur) == (nouveau, chauffeur)


def test_changer_seulement_le_chauffeur_garde_le_camion():
    mission = _affectee()
    vehicule, nouveau = mission.vehicule, ChauffeurFactory()

    modifiee = services.modifier_mission(mission, **_champs(mission), vehicule=vehicule, chauffeur=nouveau)

    assert (modifiee.vehicule, modifiee.chauffeur) == (vehicule, nouveau)


def test_une_hausse_du_poids_est_recontrolee_contre_le_camion_conserve():
    mission = _affectee()
    capacite = mission.vehicule.capacite_charge_t

    with pytest.raises(AffectationImpossible, match="capacité du camion"):
        services.modifier_mission(mission, **_champs(mission, poids_t=capacite + Decimal("1")))


def test_un_poids_dans_la_capacite_reste_accepte():
    mission = _affectee()

    modifiee = services.modifier_mission(
        mission, **_champs(mission, poids_t=mission.vehicule.capacite_charge_t)
    )

    assert modifiee.poids_t == mission.vehicule.capacite_charge_t
