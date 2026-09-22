"""Tâches Celery de l'application (étape 7 lot 2, ADR-004 architecture.md:493-497).

En développement et en test, ``CELERY_TASK_ALWAYS_EAGER`` fait exécuter ces tâches immédiatement,
dans le même processus : `.delay()` se comporte comme un appel de fonction normal. Rien ne change
donc pour les tests existants du module.
"""

from __future__ import annotations

from celery import shared_task

from . import services, taches


@shared_task
def envoyer_email_notification(notification_id: int) -> None:
    """Envoie par e-mail la notification déjà créée — hors du chemin critique de la requête."""
    services.envoyer_email(notification_id)


@shared_task
def executer_taches_quotidiennes() -> dict[str, int]:
    """Planifiée chaque jour par celery beat (voir CELERY_BEAT_SCHEDULE) ; idempotente, comme la
    commande `taches_quotidiennes` qui appelle la même fonction (cron de secours sans Celery)."""
    return taches.executer_taches_quotidiennes()
