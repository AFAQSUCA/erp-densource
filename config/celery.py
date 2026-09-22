"""Application Celery : tâches asynchrones (étape 7 lot 2, ADR-004 architecture.md:493-497).

En développement et en test, ``CELERY_TASK_ALWAYS_EAGER`` (config/settings/base.py) exécute chaque
tâche immédiatement, dans le même processus, sans courtier Redis : le comportement observé est
identique à un appel de fonction normal. En production, un vrai courtier (Redis) et un processus
``celery worker`` séparé sont nécessaires (voir README).
"""

from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("erp_den_source")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
