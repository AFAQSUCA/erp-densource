"""Environnement CI/CD — PostgreSQL éphémère si dispo, sinon SQLite (architecture.md:403)."""

from .base import *  # noqa: F401,F403
from .base import BASE_DIR, env

DEBUG = False

DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'test_db.sqlite3'}")
}

# Hachage rapide pour accélérer les tests — pas utilisé en prod.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Pas de cache dans les tests (indicateurs toujours recalculés) ; e-mails activés par test.
DASHBOARD_CACHE_SECONDS = 0
NOTIFICATIONS_EMAIL = False

# CELERY_TASK_ALWAYS_EAGER reste à True (config/settings/base.py) : les tâches (envoi d'e-mail,
# taches_quotidiennes) s'exécutent immédiatement, sans courtier Redis à démarrer pour les tests.

# Les compteurs de limitation de débit ne doivent pas s'accumuler d'un test à l'autre : plafonds
# très hauts par défaut ; les tests de limitation les abaissent eux-mêmes.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {"user": "100000/min", "connexion": "100000/min"},
}

# Les milliers de tests qui connectent un ADMIN ou une DIRECTION avec force_login n'ont pas à passer
# la double authentification ; les tests de la MFA la réactivent explicitement.
MFA_ENFORCED = False
