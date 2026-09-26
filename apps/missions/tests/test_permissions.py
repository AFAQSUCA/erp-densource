from types import SimpleNamespace

import pytest

from apps.accounts.models import Role
from apps.missions import permissions
from apps.missions.models import StatutMission

from .factories import MissionFactory


def _utilisateur(role):
    return SimpleNamespace(role_effectif=role)


@pytest.mark.parametrize(
    ("statut", "role", "attendues"),
    [
        (StatutMission.BROUILLON, Role.CHARGE_CLIENTELE, {"planifier"}),
        (StatutMission.BROUILLON, Role.DIRECTION, {"planifier"}),
        (StatutMission.PLANIFIEE, Role.CHARGE_CLIENTELE, set()),
        (StatutMission.PLANIFIEE, Role.DIRECTION, {"affecter"}),
        # Retour réunion : c'est le Parc Auto qui affecte les missions après leur création.
        (StatutMission.PLANIFIEE, Role.PARCAUTO, {"affecter"}),
        (StatutMission.AFFECTEE, Role.DIRECTION, {"demarrer"}),
        (StatutMission.AFFECTEE, Role.CHARGE_CLIENTELE, set()),
        (StatutMission.AFFECTEE, Role.PARCAUTO, set()),
        (StatutMission.EN_COURS_DEPART, Role.ADMIN, {"recuperation"}),
        # Retour réunion : la DIRECTION a la même largeur que l'ADMIN, y compris ici.
        (StatutMission.EN_COURS_DEPART, Role.DIRECTION, {"recuperation"}),
        (StatutMission.EN_COURS_DEPART, Role.CHARGE_CLIENTELE, set()),
        (StatutMission.EN_COURS_COLIS_RECUPERE, Role.ADMIN, {"livraison"}),
        (StatutMission.EN_COURS_COLIS_RECUPERE, Role.DIRECTION, {"livraison"}),
        (StatutMission.LIVREE, Role.DIRECTION, {"cloturer"}),
        (StatutMission.LIVREE, Role.CHARGE_CLIENTELE, set()),
        (StatutMission.CLOTUREE, Role.ADMIN, set()),
        (StatutMission.BROUILLON, Role.RH, set()),
    ],
)
def test_actions_disponibles_selon_statut_et_role(statut, role, attendues):
    mission = MissionFactory.build(statut=statut)

    actions = permissions.actions_disponibles(_utilisateur(role), mission)

    assert {nom for nom, permise in actions.items() if permise} == attendues


def test_un_role_sans_droit_sur_les_codes_n_en_voit_aucun():
    mission = MissionFactory.build(statut=StatutMission.BROUILLON)

    codes = permissions.codes_visibles(_utilisateur(Role.PARCAUTO), mission)

    assert codes == {"expediteur": None, "destinataire": None}


def test_le_parc_auto_consulte_les_missions_sans_voir_les_codes():
    """Retour réunion : le Parc Auto affecte les missions, donc les consulte, mais les codes
    expéditeur/destinataire restent réservés à ceux qui gèrent la relation client (VOIR_CODES)."""
    assert Role.PARCAUTO in permissions.CONSULTATION
    assert Role.PARCAUTO not in permissions.VOIR_CODES
