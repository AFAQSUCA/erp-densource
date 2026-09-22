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

# Cache Redis partagé entre les processus (compteurs anti force brute, indicateurs du tableau de
# bord — cahier-des-charges.md:291). Backend natif de Django (depuis la 4.0) : seul le client
# `redis` est nécessaire, pas de dépendance `django-redis` supplémentaire.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL"),
    }
}

# Tâches asynchrones réelles (étape 7 lot 2) : un processus `celery worker` (et `celery beat` pour
# la planification) doit tourner à côté de l'application — voir README « Lancer en production ».
CELERY_TASK_ALWAYS_EAGER = False
CELERY_BROKER_URL = env("REDIS_URL")

# HTTPS/TLS obligatoire + en-têtes de sécurité — cahier-des-charges.md:270-281.
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
