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
