"""Blocs ajoutés par ``missions`` aux fiches d'autres apps.

- ``hr.sections.DETAIL_CONGE`` : alerte du validateur quand le chauffeur qui demande un
  congé a une mission prévue pendant la période (cahier-des-charges.md:219-221). Seules
  les missions planifiées, affectées ou en cours, dotées d'une date de départ prévue,
  peuvent être détectées.
- ``customers.sections.DETAIL_CLIENT`` : missions récentes du client.
"""

from apps.hr.models import StatutConge

from . import permissions, services
from .models import Mission


def section_alerte_conge(conge, utilisateur):
    if conge.statut not in (StatutConge.DEMANDE, StatutConge.VALIDATION_N1):
        return None
    missions = list(
        services.missions_du_personnel_sur_periode(
            conge.employe_id, conge.date_debut, conge.date_fin
        )
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
