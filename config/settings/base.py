"""
Settings communs à tous les environnements (dev/test/prod).

Stack : Django 5.2.x, DRF 3.15+, PostgreSQL 16+ (SQLite en dev/démo).
Réf. cahier-des-charges.md §4 (Spécifications Techniques).
"""

from datetime import timedelta
from pathlib import Path

import environ

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
    "corsheaders",
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

# Sessions desktop : 30 min d'inactivité (cahier-des-charges.md:285). Chaque
# requête prolonge la session ; l'API mobile (15 min) aura sa propre durée JWT.
SESSION_COOKIE_AGE = 30 * 60
SESSION_SAVE_EVERY_REQUEST = True

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
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

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
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
