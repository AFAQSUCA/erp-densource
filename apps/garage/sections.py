"""Blocs du garage : ceux qu'il expose, et celui qu'il ajoute à la fiche d'un camion.

- ``DETAIL_OR`` : blocs ajoutés à la fiche d'un OR par des apps situées en dessous
  (``inventory`` y ajoute les pièces utilisées et le coût total). Fournisseurs
  appelés avec ``(ordre, utilisateur)``.
- :func:`section_maintenance` : bloc « Maintenance » de la fiche d'un camion
  (historique des OR, ouverture d'un OR, immobilisation, remise en service).
"""

from apps.core.sections import RegistreSections
from apps.fleet.models import StatutVehicule

from . import permissions, services

DETAIL_OR = RegistreSections()


def section_maintenance(vehicule, utilisateur):
    role = utilisateur.role_effectif
    if role not in permissions.CONSULTATION:
        return None
    peut_modifier = role in permissions.MODIFICATION
    statut = vehicule.statut
    return {
        "template": "garage/_maintenance_vehicule.html",
        "contexte": {
            "ordres": list(services.ordres_du_vehicule(vehicule)),
            "peut_modifier": peut_modifier,
            "peut_immobiliser": peut_modifier
            and statut != StatutVehicule.IMMOBILISE,
            "peut_mettre_hors_service": peut_modifier
            and statut != StatutVehicule.HORS_SERVICE,
            "peut_remettre_en_service": peut_modifier
            and statut in (StatutVehicule.IMMOBILISE, StatutVehicule.HORS_SERVICE),
        },
    }
