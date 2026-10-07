"""Environnement production — PostgreSQL, Redis (architecture.md:405).

Écrit pour le serveur Linux unique retenu pour le déploiement (docker-compose.yml, étape 7 lot 3) :
une base et un cache, pas de réplique ni de cluster. Les mêmes variables d'environnement
(DATABASE_URL, REDIS_URL) permettraient de pointer vers des services managés plus tard sans
changer ce fichier.

Sécurité : conventions.md §3 + cahier-des-charges.md §4 "Sécurité".
"""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import SECRET_KEY, env

DEBUG = False

# Refuser de démarrer avec la clé par défaut du dépôt (``base.py``) ou celle de ``.env.example`` : elle est
# publique, et c'est elle qui signe les sessions, les jetons de réinitialisation de mot de passe et les
# jetons de l'API mobile. Mieux vaut un conteneur qui s'arrête avec un message clair qu'un serveur qui
# tourne avec une clé que n'importe qui connaît (GUIDE-DEPLOIEMENT.md § 4).
if SECRET_KEY.startswith("django-insecure-") or SECRET_KEY == "change-me" or len(SECRET_KEY) < 32:
    raise ImproperlyConfigured(
        "SECRET_KEY absente, par défaut ou trop courte (32 caractères minimum) : en production, générez-en une "
        "avec « python -c \"import secrets; print(secrets.token_urlsafe(50))\" » et placez-la dans .env."
    )

# Fichiers statiques à noms versionnés (``tailwind.4f2a9c.css``) : Nginx les garde 30 jours en cache
# (nginx/nginx.conf). Sans cela, après un déploiement, les téléphones continuaient d'afficher l'ancien
# ``tailwind.css`` avec les nouveaux gabarits : une classe ajoutée depuis (``grid-cols-6``...) manquait et la
# barre de navigation du chauffeur s'empilait en colonne au milieu de l'écran. Le nom change quand le contenu
# change (``collectstatic``, lancé par ops/entrypoint.sh), donc le cache ne sert jamais un fichier périmé.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "apps.core.statiques.StockageStatiqueVersionne"},
}

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

# Couche de messages des WebSocket : Redis, partagé entre le conteneur `web` (gunicorn), qui diffuse un
# changement de mission, et le conteneur `realtime` (daphne), qui le pousse aux navigateurs connectés.
#
# ATTENTION au délai de lecture : `redis-py` >= 8 en impose un par défaut (5 s), alors que
# `channels-redis` attend un message en bloquant 5 s (BZPOPMIN). Sans réglage, le délai de lecture expire
# à chaque attente au repos : le consommateur meurt en « erreur interne » (code 1011) quelques secondes
# après la connexion et le navigateur se reconnecte en boucle. Le délai de lecture doit donc rester
# supérieur à l'attente bloquante ; le délai de connexion, lui, reste court (Redis injoignable : on
# échoue vite, la diffusion étant sans conséquence pour le métier — voir apps/missions/temps_reel.py).
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [{"address": env("REDIS_URL"), "socket_timeout": 15, "socket_connect_timeout": 3}],
        },
    }
}

# Tâches asynchrones réelles (étape 7 lot 2) : un processus `celery worker` (et `celery beat` pour
# la planification) doit tourner à côté de l'application — voir README « Lancer en production ».
CELERY_TASK_ALWAYS_EAGER = False
CELERY_BROKER_URL = env("REDIS_URL")

# Nginx envoie les fichiers téléversés sur ordre de Django (X-Accel-Redirect), après contrôle du rôle.
MEDIA_ACCEL_REDIRECT = True

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

# Envoi d'e-mails réel (notifications si NOTIFICATIONS_EMAIL=true, et surtout « mot de passe
# oublié » — étape 7, qui n'a pas d'autre canal). Sans ces variables, Django essaierait un serveur
# SMTP local inexistant et l'envoi échouerait silencieusement en production. Un hébergeur de
# domaine (dont Hostinger) fournit généralement un compte e-mail SMTP prêt à l'emploi.
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)

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
