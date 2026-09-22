"""Les tâches Celery ne sont que de minces relais : elles délèguent à `services` et `taches`.

En test, `CELERY_TASK_ALWAYS_EAGER` fait exécuter `.delay()` immédiatement (config/settings/base.py) :
pas besoin d'un vrai courtier Redis pour ces tests.
"""

import pytest

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.notifications import tasks
from apps.notifications.models import Notification
from apps.notifications.services import notifier

pytestmark = pytest.mark.django_db


def test_executer_taches_quotidiennes_delegue_a_la_fonction_idempotente(monkeypatch):
    appels = []
    monkeypatch.setattr(tasks.taches, "executer_taches_quotidiennes", lambda: appels.append(1) or {"documents vehicules": 0})

    resultat = tasks.executer_taches_quotidiennes()

    assert resultat == {"documents vehicules": 0}
    assert appels == [1]


def test_envoyer_email_notification_delegue_au_service(monkeypatch):
    appels = []
    monkeypatch.setattr(tasks.services, "envoyer_email", lambda pk: appels.append(pk))

    tasks.envoyer_email_notification(42)

    assert appels == [42]


def test_notifier_declenche_la_tache_par_e_mail_apres_commit(
    settings, django_capture_on_commit_callbacks, monkeypatch
):
    """Intégration : notifier() -> on_commit -> tâche Celery (eager) -> envoi réel."""
    settings.NOTIFICATIONS_EMAIL = True
    destinataire = UserFactory(role=Role.RH, email="rh@example.com")
    appels = []
    monkeypatch.setattr(tasks.services, "envoyer_email", lambda pk: appels.append(pk))

    with django_capture_on_commit_callbacks(execute=True):
        creees = notifier([destinataire], categorie="CONGE", titre="Essai tâche")

    notification = Notification.objects.get(pk=creees[0].pk)
    assert appels == [notification.pk]
