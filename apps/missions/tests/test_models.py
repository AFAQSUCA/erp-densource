from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.missions.models import StatutMission

from .factories import MissionFactory

pytestmark = pytest.mark.django_db


def test_mission_affectee_sans_camion_ni_chauffeur_refusee_par_la_base():
    with pytest.raises(IntegrityError), transaction.atomic():
        MissionFactory(statut=StatutMission.AFFECTEE)


def test_brouillon_et_planifiee_n_exigent_pas_de_camion():
    MissionFactory(statut=StatutMission.BROUILLON)
    MissionFactory(statut=StatutMission.PLANIFIEE)


def test_poids_nul_refuse_par_la_base():
    with pytest.raises(IntegrityError), transaction.atomic():
        MissionFactory(poids_t=Decimal("0"))


def test_prix_negatif_refuse_par_la_base():
    with pytest.raises(IntegrityError), transaction.atomic():
        MissionFactory(prix_convenu=Decimal("-1"))


def test_km_arrivee_inferieur_au_depart_refuse_par_la_base():
    with pytest.raises(IntegrityError), transaction.atomic():
        MissionFactory(km_depart=1000, km_arrivee=999)


def test_numero_unique():
    MissionFactory(numero="MIS-2026-0001")

    with pytest.raises(IntegrityError), transaction.atomic():
        MissionFactory(numero="MIS-2026-0001")


def test_est_en_cours_couvre_les_deux_etapes():
    assert MissionFactory.build(statut=StatutMission.EN_COURS_DEPART).est_en_cours
    assert MissionFactory.build(statut=StatutMission.EN_COURS_COLIS_RECUPERE).est_en_cours
    assert not MissionFactory.build(statut=StatutMission.LIVREE).est_en_cours
