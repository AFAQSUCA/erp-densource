"""Audit M3-10 : un chauffeur au permis ou à la visite médicale expiré n'est pas affectable.
Audit M5-09 : réaffecter seulement le camion ou seulement le chauffeur marche, et une hausse du poids est
recontrôlée contre la capacité du camion conservé."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
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
        services.affecter_mission(mission, vehicule=VehiculeFactory(), chauffeur=chauffeur)


def test_une_visite_medicale_expiree_bloque_l_affectation():
    mission = _planifiee()
    chauffeur = ChauffeurFactory(date_expiration_visite_medicale=HIER)

    with pytest.raises(AffectationImpossible, match="visite médicale"):
        services.affecter_mission(mission, vehicule=VehiculeFactory(), chauffeur=chauffeur)


def test_les_deux_documents_expires_sont_nommes():
    mission = _planifiee()
    chauffeur = ChauffeurFactory(date_expiration_permis=HIER, date_expiration_visite_medicale=HIER)

    with pytest.raises(AffectationImpossible, match="permis de conduire.* et visite médicale"):
        services.affecter_mission(mission, vehicule=VehiculeFactory(), chauffeur=chauffeur)


def test_l_expiration_aujourd_hui_ne_bloque_pas_encore_et_les_dates_absentes_non_plus():
    aujourd_hui = timezone.localdate()
    ok = ChauffeurFactory(date_expiration_permis=aujourd_hui, date_expiration_visite_medicale=DEMAIN)
    sans_date = ChauffeurFactory()  # dates non renseignées : signalées par l'alerte, pas bloquantes

    for chauffeur in (ok, sans_date):
        mission = services.affecter_mission(_planifiee(), vehicule=VehiculeFactory(), chauffeur=chauffeur)
        assert mission.chauffeur == chauffeur


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
    chauffeur, nouveau = mission.chauffeur, VehiculeFactory()

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
