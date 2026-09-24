"""
Settings communs à tous les environnements (dev/test/prod).

Stack : Django 5.2.x, DRF 3.15+, PostgreSQL 16+ (SQLite en dev/démo).
Réf. cahier-des-charges.md §4 (Spécifications Techniques).
"""

from datetime import timedelta
from pathlib import Path

import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="django-insecure-change-me-in-env")

DEBUG = env.bool("DEBUG", default=False)

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])


# Application definition
# Apps métier listées en cahier-des-charges.md:259-261 (17 apps).
# Ajoutées au fur et à mesure des phases (voir architecture.md §3).

DJANGO_APPS = [
    "daphne",  # en premier : `runserver` devient ASGI (WebSocket du suivi des missions), comme en production
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",  # révocation des refresh tokens (déconnexion)
    "django_filters",
    "drf_spectacular",
    "drf_spectacular_sidecar",  # fichiers de Swagger UI servis par l'application
    "corsheaders",
    "channels",
]

LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.audit",
    "apps.hr",
    "apps.drivers",
    "apps.customers",
    "apps.fleet",
    "apps.missions",
    "apps.garage",
    "apps.inventory",
    "apps.fuel",
    "apps.billing",
    "apps.finance",
    "apps.notifications",
    "apps.dashboard",
    "apps.api",
    "apps.mobile_api",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# 7 rôles, RBAC simple — cahier-des-charges.md:44-55, architecture.md:534.
AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "accounts:login"

# WebSocket : suivi des missions en direct (apps/missions/consumers.py). En développement et en test,
# couche en mémoire (un seul processus) ; la production (prod.py) passe par Redis, partagé entre gunicorn
# (qui diffuse les changements) et daphne (qui les pousse aux navigateurs).
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

# Sessions desktop : 30 min d'inactivité (cahier-des-charges.md:285). Chaque
# requête prolonge la session ; l'API mobile (15 min) aura sa propre durée JWT.
SESSION_COOKIE_AGE = 30 * 60
SESSION_SAVE_EVERY_REQUEST = True

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.MFARequiseMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.CurrentRequestMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.accounts.context_processors.menu",
                "apps.notifications.context_processors.notifications",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Mots de passe : Argon2 (recommandé, cahier-des-charges.md:273). PBKDF2 reste accepté : un ancien
# hachage est converti en Argon2 à la prochaine connexion de la personne.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalisation — conventions.md §11 : langue par défaut fr.
LANGUAGE_CODE = "fr"
TIME_ZONE = "Africa/Abidjan"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Tables BDD `app_modele` : conventions.md §1. BigAutoField requis pour
# cohérence avec audit_log.id (BIGINT) — cahier-des-charges.md:60.
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Pagination obligatoire sur toutes les listes — conventions.md §5.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.api.exceptions.gestionnaire_erreurs",
    # Limitation de débit (anti force brute) : la connexion est limitée à part et plus strictement.
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"user": "300/min", "connexion": "10/min"},
}

# JWT : accès de 15 minutes (cahier-des-charges.md:285), refresh de 7 jours renouvelé à chaque usage
# et révoqué à la déconnexion.
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "ERP DEN Source Group : API",
    "DESCRIPTION": (
        "API REST versionnée. `/api/v1/` : lecture des principales ressources selon le rôle. "
        "`/api/v1/mobile/` : espace chauffeur (missions, codes QR, plein, check-list, incident)."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "REDOC_DIST": "SIDECAR",
}

# CORS restreint aux domaines connus (cahier-des-charges.md:277), et seulement pour l'API.
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_URLS_REGEX = r"^/api/.*$"

# Session de l'espace mobile chauffeur : 15 minutes d'inactivité (cahier-des-charges.md:285).
SESSION_COOKIE_AGE_MOBILE = 15 * 60


# Notifications (étape 5) : toujours enregistrées dans l'application ; l'envoi par e-mail
# est facultatif et se règle par l'environnement. SMS et notifications push (Twilio,
# Firebase) demandent des comptes externes et ne sont pas branchés.
NOTIFICATIONS_EMAIL = env.bool("NOTIFICATIONS_EMAIL", default=False)
NOTIFICATIONS_URL_BASE = env("NOTIFICATIONS_URL_BASE", default="http://localhost:8000")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="ERP DEN Source Group <noreply@densourcegroup.ci>")

# Durée (secondes) de mise en cache des indicateurs du tableau de bord ; 0 = pas de cache.
# Avec Redis en production (CACHES), le cache est partagé entre les processus.
DASHBOARD_CACHE_SECONDS = env.int("DASHBOARD_CACHE_SECONDS", default=60)

# Mentions de l'émetteur sur la facture imprimable (à renseigner par l'environnement).
ENTREPRISE_NOM = env("ENTREPRISE_NOM", default="DEN Source Group")
ENTREPRISE_ADRESSE = env("ENTREPRISE_ADRESSE", default="")
ENTREPRISE_NCC = env("ENTREPRISE_NCC", default="")


# --- Tâches asynchrones (étape 7 lot 2, ADR-004 architecture.md:493-497) ---

# Par défaut (dev, test) : chaque tâche s'exécute immédiatement, dans le même processus, sans
# courtier — même comportement qu'un appel de fonction. La production (config/settings/prod.py)
# désactive ce mode : un vrai courtier Redis et un processus « celery worker » deviennent nécessaires.
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=True)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_TIMEZONE = TIME_ZONE
# Planification (celery beat, prod uniquement) : reprend la même tâche que la commande manuelle
# `taches_quotidiennes` (cron de secours) — les deux appellent la fonction idempotente sous-jacente.
CELERY_BEAT_SCHEDULE = {
    "taches-quotidiennes": {
        "task": "apps.notifications.tasks.executer_taches_quotidiennes",
        "schedule": crontab(hour=5, minute=0),
    },
}


# --- Sécurité applicative (étape 7) ---

# Nombre de proxys de confiance devant l'application (0 = aucun : l'adresse vue est celle du
# client). Derrière Nginx, mettre 1 : on lit alors l'adresse ajoutée par ce proxy dans
# X-Forwarded-For, jamais une valeur écrite par le client (anti-usurpation, cf. core.middleware).
TRUSTED_PROXY_COUNT = env.int("TRUSTED_PROXY_COUNT", default=0)
REST_FRAMEWORK["NUM_PROXIES"] = TRUSTED_PROXY_COUNT

# Double authentification obligatoire pour l'ADMIN et la DIRECTION (cahier-des-charges.md:276).
MFA_ENFORCED = True
MFA_ROLES = ("ADMIN", "DIRECTION")
MFA_ISSUER = "DEN Source ERP"
MFA_MAX_ECHECS = 5  # codes faux tolérés ...
MFA_FENETRE = 10 * 60  # ... par fenêtre de 10 minutes, puis blocage jusqu'à la fin de la fenêtre

# Anti force brute sur la connexion : par couple (adresse, identifiant) puis par adresse.
LOGIN_MAX_ECHECS_COMPTE = 5
LOGIN_MAX_ECHECS_ADRESSE = 20
LOGIN_FENETRE = 15 * 60

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# Politique de sécurité du contenu (CSP) : le navigateur n'exécute que les scripts et ne charge que les
# ressources venant de l'application elle-même (cahier-des-charges.md:280). Les styles, icônes et Alpine.js
# sont locaux (frontend/), aucune page ne contient de script écrit en ligne.
# Deux réserves assumées : « 'unsafe-eval' » pour Alpine.js (il évalue les expressions des attributs x-… ;
# sa variante sans eval demanderait de réécrire les écrans) et « 'unsafe-inline' » pour les styles (attributs style).
CSP_REPORT_ONLY = env.bool("CSP_REPORT_ONLY", default=False)  # true : signale sans bloquer (mise au point)
CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-eval'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self'",
    "media-src 'self'",
    "manifest-src 'self'",
    "worker-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])
# Documentation Swagger (ADMIN et DIRECTION) : la page contient un petit script d'initialisation.
CSP_DOCS = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "frame-ancestors 'none'",
])
# La caméra reste permise pour l'application elle-même : le chauffeur scanne les codes QR.
PERMISSIONS_POLICY = "camera=(self), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()"
