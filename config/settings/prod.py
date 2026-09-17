"""Environnement production — PostgreSQL + réplique, Redis cluster (architecture.md:405).

Sécurité : conventions.md §3 + cahier-des-charges.md §4 "Sécurité".
"""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

DATABASES = {
    "default": env.db("DATABASE_URL"),
}

# NB: django-redis + django-cors-headers seront ajoutés au requirements
# lors des phases Notifications (Celery/Redis) et API — non installés
# tant que ces phases ne sont pas atteintes (pas de dépendance inutilisée).
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env("REDIS_URL"),
    }
}

# HTTPS/TLS obligatoire + en-têtes de sécurité — cahier-des-charges.md:270-281.
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Sessions 15 min mobile / 30 min desktop — cahier-des-charges.md:285.
# Valeur par défaut desktop ; l'API mobile applique sa propre durée JWT.
SESSION_COOKIE_AGE = 30 * 60

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
