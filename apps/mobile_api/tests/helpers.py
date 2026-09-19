"""Aides de test de l'espace chauffeur."""

from decimal import Decimal

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.customers.tests.factories import ClientFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.garage.models import CODES_CHECKLIST
from apps.missions.models import StatutMission
from apps.missions.tests.factories import MissionFactory

CODE_EXPEDITEUR = "ABCD2345"
CODE_DESTINATAIRE = "WXYZ6789"


def chauffeur_avec_compte(**surcharges):
    """Chauffeur dont la fiche du personnel est rattachée à un compte de rôle CHAUFFEUR."""
    fiche = ChauffeurFactory(**surcharges)
    compte = UserFactory(role=Role.CHAUFFEUR)
    fiche.personnel.utilisateur = compte
    fiche.personnel.save()
    return fiche, compte


def mission_de(chauffeur, statut=StatutMission.AFFECTEE, **surcharges):
    donnees = dict(
        statut=statut, chauffeur=chauffeur, vehicule=VehiculeFactory(), client=ClientFactory(),
        code_expediteur=CODE_EXPEDITEUR, code_destinataire=CODE_DESTINATAIRE,
        prix_convenu=Decimal("850000"),
    )
    donnees.update(surcharges)
    return MissionFactory(**donnees)


def checklist_ok(**ko):
    """Réponses de check-list : tout est OK, sauf les points donnés (code → remarque)."""
    return [
        {"code": c, "ok": c not in ko, "remarque": ko.get(c, "")} for c in CODES_CHECKLIST
    ]
