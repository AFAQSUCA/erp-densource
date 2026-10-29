"""Exercice 7 — Les missions annulées du mois au tableau de bord (formation/exercices/07-missions-annulees-tableau-de-bord).

À copier dans apps/dashboard/tests/ puis : python -m pytest apps/dashboard/tests/test_exercice_07.py -q --no-cov
"""

from datetime import date, datetime, timedelta

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.dashboard import services
from apps.missions import services as missions_services
from apps.missions.models import StatutMission
from apps.missions.tests.factories import MissionFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _sans_cache():
    cache.clear()


def _annulee(le: date):
    moment = timezone.make_aware(datetime(le.year, le.month, le.day, 10, 0))
    return MissionFactory(statut=StatutMission.ANNULEE, date_annulation=moment, motif_annulation="Client")


def test_le_compte_vient_du_service_des_missions():
    jour = date(2026, 10, 15)
    _annulee(date(2026, 10, 2))
    _annulee(date(2026, 10, 14))
    _annulee(date(2026, 9, 30))  # le mois précédent ne compte pas
    MissionFactory(statut=StatutMission.PLANIFIEE)

    assert missions_services.missions_annulees_entre(date(2026, 10, 1), jour) == 2


def test_le_bloc_exploitation_donne_les_annulees_du_mois():
    aujourd_hui = timezone.localdate()
    _annulee(aujourd_hui)
    _annulee(aujourd_hui.replace(day=1) - timedelta(days=1))  # dernier jour du mois précédent

    assert services.exploitation()["missions_annulees_du_mois"] == 1


def test_la_direction_voit_l_indicateur_sur_sa_page_d_accueil(client):
    _annulee(timezone.localdate())
    client.force_login(UserFactory(role=Role.DIRECTION))

    page = client.get(reverse("home")).content.decode()

    assert "Annulées ce mois" in page


def test_le_parc_auto_ne_voit_pas_les_indicateurs_de_missions(client):
    client.force_login(UserFactory(role=Role.PARCAUTO))

    assert "Annulées ce mois" not in client.get(reverse("home")).content.decode()
