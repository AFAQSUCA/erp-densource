"""Blocs ajoutés par ``missions`` aux fiches d'autres apps.

- ``hr.sections.DETAIL_CONGE`` : alerte du validateur quand le chauffeur qui demande un
  congé a une mission prévue pendant la période (cahier-des-charges.md:219-221). Seules
  les missions planifiées, affectées ou en cours, dotées d'une date de départ prévue,
  peuvent être détectées.
- ``customers.sections.DETAIL_CLIENT`` : missions récentes du client.
"""

from apps.hr.models import StatutConge

from . import permissions
from .models import Mission, StatutMission

STATUTS_A_SURVEILLER = (
    StatutMission.PLANIFIEE,
    StatutMission.AFFECTEE,
    StatutMission.EN_COURS_DEPART,
    StatutMission.EN_COURS_COLIS_RECUPERE,
)


def section_alerte_conge(conge, utilisateur):
    if conge.statut not in (StatutConge.DEMANDE, StatutConge.VALIDATION_N1):
        return None
    missions = list(
        Mission.objects.filter(
            chauffeur__personnel_id=conge.employe_id,
            statut__in=STATUTS_A_SURVEILLER,
            date_depart_prevue__range=(conge.date_debut, conge.date_fin),
        )
        .select_related("client")
        .order_by("date_depart_prevue")
    )
    if not missions:
        return None
    return {
        "template": "missions/_alerte_conge.html",
        "contexte": {
            "missions": missions,
            "peut_ouvrir": utilisateur.role_effectif in permissions.CONSULTATION,
        },
    }


def section_missions_client(client, utilisateur):
    if utilisateur.role_effectif not in permissions.CONSULTATION:
        return None
    missions = Mission.objects.filter(client=client)
    return {
        "template": "missions/_missions_client.html",
        "contexte": {
            "missions": list(missions.order_by("-created_at", "-pk")[:10]),
            "total": missions.count(),
        },
    }
