"""Environnement production — PostgreSQL, Redis (architecture.md:405).

Écrit pour le serveur Linux unique retenu pour le déploiement (docker-compose.yml, étape 7 lot 3) :
une base et un cache, pas de réplique ni de cluster. Les mêmes variables d'environnement
(DATABASE_URL, REDIS_URL) permettraient de pointer vers des services managés plus tard sans
changer ce fichier.

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

# Le TLS est terminé par Nginx (étape 7 lot 3) : Django lui-même ne reçoit que du HTTP, sur le
# réseau interne de docker-compose. Sans ce réglage, SECURE_SSL_REDIRECT le renverrait en boucle
# (il ne verrait jamais de requête « sécurisée »). Nginx doit poser `X-Forwarded-Proto` lui-même
# (nginx/nginx.conf) : un client ne peut pas écrire cet en-tête directement, TRUSTED_PROXY_COUNT
# proxys de confiance étant devant l'application (cf. apps/core/middleware.get_client_ip).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Domaines autorisés à soumettre un formulaire (schéma inclus) — nécessaire dès que le site est
# servi en HTTPS derrière un proxy (cahier-des-charges.md:270-281). Exemple :
# CSRF_TRUSTED_ORIGINS=https://erp.densourcegroup.ci
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])

# Supervision des erreurs (cahier-des-charges.md:297, architecture.md §8 « Observabilité »). Inactif
# tant que SENTRY_DSN n'est pas défini : un environnement de démonstration n'a pas besoin de compte
# Sentry pour démarrer. Prometheus/Grafana (mentionné au même endroit) n'est volontairement pas
# installé : un serveur unique n'en tire pas encore parti ; Sentry couvre déjà erreurs et exceptions.
SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=env("SENTRY_ENVIRONMENT", default="production"),
        integrations=[DjangoIntegration(), CeleryIntegration()],
        # Pas de traces de performance par défaut (coût, volumétrie) : seulement les erreurs.
        traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.0),
        send_default_pii=False,  # jamais de données personnelles envoyées à un tiers sans réglage explicite
    )
