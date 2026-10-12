"""Ce que la sortie d'un employé (hr.sorties) change aux missions — avenant-sortie-personnel.md.

``missions`` écoute ``hr`` (et non l'inverse) pour respecter le sens des dépendances d'architecture.md.
"""

from django.dispatch import receiver

from apps.hr import signals as hr_signals
from apps.hr.exceptions import SortieImpossible

from . import services


@receiver(hr_signals.sortie_a_verifier)
def refuser_la_sortie_pendant_une_mission(sender, sortie, **kwargs):
    """Un camion sur la route ne se réaffecte pas : la sortie attend la livraison (la tâche du jour réessaie)."""
    numeros = list(services.missions_en_route_du_personnel(sortie.employe_id).values_list("numero", flat=True))
    if numeros:
        employe = sortie.employe
        raise SortieImpossible(
            f"{employe.prenom} {employe.nom} est sur la route (mission{'s' if len(numeros) > 1 else ''} "
            f"{', '.join(numeros)}) : la sortie s'appliquera une fois la mission livrée."
        )


@receiver(hr_signals.sortie_appliquee)
def liberer_les_missions_du_partant(sender, sortie, **kwargs):
    employe = sortie.employe
    return services.liberer_missions_du_partant(
        sortie.employe_id,
        motif=f"Sortie de {employe.prenom} {employe.nom} le {sortie.date_sortie:%d/%m/%Y}",
    )
