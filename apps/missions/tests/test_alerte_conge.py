"""Alerte N1 : le chauffeur qui demande un congé a une mission prévue sur la période.

Cahier-des-charges.md:219-221. Bloc fourni par ``missions`` à la fiche d'un congé.
"""

from datetime import date, datetime
from datetime import timezone as dt_timezone

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.hr import services
from apps.hr.tests.factories import PersonnelFactory
from apps.missions.models import StatutMission

from .factories import MissionFactory

pytestmark = pytest.mark.django_db

MAINTENANT = datetime(2026, 9, 1, 8, 0, tzinfo=dt_timezone.utc)
DEBUT, FIN = date(2026, 10, 5), date(2026, 10, 9)


@pytest.fixture
def cas():
    compte_sup = UserFactory(role=Role.PARCAUTO)
    superieur = PersonnelFactory(utilisateur=compte_sup)
    fiche = ChauffeurFactory(personnel=PersonnelFactory(poste="Chauffeur", superieur=superieur))
    conge = services.demander_conge(
        fiche.personnel, date_debut=DEBUT, date_fin=FIN, motif="Repos", maintenant=MAINTENANT
    )
    return conge, fiche, compte_sup


def _page(client, compte, conge):
    client.force_login(compte)
    return client.get(reverse("hr:conges_detail", args=[conge.pk])).content.decode()


def test_le_validateur_est_prevenu_d_une_mission_sur_la_periode(client, cas):
    conge, fiche, compte_sup = cas
    mission = MissionFactory(
        chauffeur=fiche, statut=StatutMission.PLANIFIEE, date_depart_prevue=date(2026, 10, 7)
    )

    texte = _page(client, compte_sup, conge)

    assert "1 mission prévue pendant cette période" in texte
    assert mission.numero in texte


def test_le_lien_vers_la_mission_est_reserve_aux_roles_qui_y_ont_acces(client, cas):
    conge, fiche, compte_sup = cas
    mission = MissionFactory(
        chauffeur=fiche, statut=StatutMission.PLANIFIEE, date_depart_prevue=date(2026, 10, 7)
    )
    lien = reverse("missions:detail", args=[mission.pk])

    # Retour réunion : le Parc Auto affecte les missions, donc les consulte désormais aussi.
    assert lien in _page(client, compte_sup, conge)
    assert lien in _page(client, UserFactory(role=Role.DIRECTION), conge)
    assert lien not in _page(client, UserFactory(role=Role.RH), conge)


@pytest.mark.parametrize(
    "surcharges",
    [
        {"date_depart_prevue": date(2026, 10, 12)},  # après la période
        {"date_depart_prevue": date(2026, 10, 2)},  # avant la période
        {"date_depart_prevue": None},  # pas de date : non détectable
        {"date_depart_prevue": date(2026, 10, 7), "statut": StatutMission.CLOTUREE},
        {"date_depart_prevue": date(2026, 10, 7), "statut": StatutMission.BROUILLON},
    ],
)
def test_aucune_alerte_hors_periode_ou_hors_mission_active(client, cas, surcharges):
    conge, fiche, compte_sup = cas
    donnees = {"statut": StatutMission.PLANIFIEE, **surcharges}
    if donnees["statut"] == StatutMission.CLOTUREE:
        donnees["vehicule"] = VehiculeFactory()  # une mission clôturée a un camion
    MissionFactory(chauffeur=fiche, **donnees)

    assert "mission prévue" not in _page(client, compte_sup, conge)


def test_la_mission_d_un_autre_chauffeur_ne_declenche_pas_d_alerte(client, cas):
    conge, fiche, compte_sup = cas
    autre = ChauffeurFactory()
    MissionFactory(
        chauffeur=autre, statut=StatutMission.PLANIFIEE, date_depart_prevue=date(2026, 10, 7)
    )

    assert "mission prévue" not in _page(client, compte_sup, conge)


def test_plus_d_alerte_une_fois_le_conge_decide(client, cas):
    conge, fiche, compte_sup = cas
    MissionFactory(
        chauffeur=fiche, statut=StatutMission.PLANIFIEE, date_depart_prevue=date(2026, 10, 7)
    )
    services.refuser(conge, compte_sup, commentaire="Mission prévue")

    assert "mission prévue pendant" not in _page(client, compte_sup, conge)


def test_la_section_missions_du_client_est_reservee_aux_roles_des_missions():
    from apps.customers.tests.factories import ClientFactory
    from apps.missions import sections

    fiche = ClientFactory()

    assert sections.section_missions_client(fiche, UserFactory(role=Role.RH)) is None
    assert sections.section_missions_client(fiche, UserFactory(role=Role.DIRECTION)) is not None
