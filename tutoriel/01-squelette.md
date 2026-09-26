# Chapitre 1 — Le squelette du projet

> 29 fichier(s) dans ce chapitre, 1941 lignes de code.

## Ce que vous allez construire

Le **squelette** : les fichiers qui n'appartiennent à aucun domaine métier mais sans lesquels rien ne
démarre : la liste des bibliothèques, les réglages (`settings`), le point d'entrée `manage.py`, la
configuration des tests et les règles Git. À la fin du chapitre, `python manage.py check` s'exécute sans
erreur : Django « tourne à vide ».

## Prérequis

- Le [chapitre 0](00-prerequis.md) : dossier `erp-densource`, Git initialisé, environnement virtuel **activé**.

## Notions Django de ce chapitre

- **Projet Django** : le dossier de réglages (`config/`) qui relie les applications. On ne le confond pas
  avec une *application* (`apps/fleet/`…), qui est un domaine métier.
- **`manage.py`** : la « télécommande » du projet. Toute commande Django passe par lui
  (`runserver`, `migrate`, `test`…). Il charge un fichier de réglages choisi par la variable
  `DJANGO_SETTINGS_MODULE`.
- **Réglages en couches** : `base.py` contient ce qui est vrai partout ; `dev.py`, `test.py`, `prod.py`
  ajoutent ce qui change selon l'environnement (base de données, cache, sécurité).
- **`.env`** : un fichier local (jamais commité) où vivent les *secrets* (clé secrète, mot de passe de la
  base). Le code les lit avec la bibliothèque `django-environ`.

## Étape 1 — Créer l'arborescence

```bash
mkdir -p apps config/settings requirements
```

Les fichiers vides `__init__.py` transforment un dossier en **paquet Python** (importable avec `import`) :

#### Fichiers vides à créer

Ces fichiers n'ont aucun contenu ; ils servent à faire de leur dossier un *paquet Python* (sans eux, `import apps.xxx` échouerait). Créez d'abord les dossiers, puis les fichiers :

```bash
mkdir -p apps config\settings
touch apps/__init__.py
touch config/settings/__init__.py
```

> Sous PowerShell, `mkdir -p` s'écrit `New-Item -ItemType Directory -Force <dossier>` et `touch fichier` s'écrit `New-Item -ItemType File -Force fichier`. Vous pouvez aussi créer ces fichiers avec votre éditeur.

## Étape 2 — Les dépendances

Créez les trois fichiers `requirements`. Le principe : `base.txt` liste ce qui sert toujours ; `dev.txt` et
`prod.txt` commencent par `-r base.txt` (« inclure base ») puis ajoutent leurs propres besoins.

#### `requirements/base.txt`

*27 lignes*

```text
Django>=5.2,<5.3
djangorestframework>=3.15
django-environ>=0.11

# Étape 6 — API REST et espace mobile chauffeur (cahier-des-charges.md:250-252)
djangorestframework-simplejwt>=5.3   # JWT court + refresh pour l'API mobile
django-filter>=24                    # filtres des listes de l'API
drf-spectacular>=0.27                # documentation OpenAPI
django-cors-headers>=4.3             # CORS restreint aux domaines connus
qrcode>=7.4                          # codes QR des missions
Pillow>=10                           # images PNG des codes QR et icônes de l'application
argon2-cffi>=23                      # hachage Argon2 des mots de passe (recommandé par le CDC)
pyotp>=2.9                           # codes TOTP de la double authentification
drf-spectacular-sidecar>=2024.1       # Swagger UI servi localement (pas de script tiers sur une session ADMIN)

# Étape 7 lot 2 — PostgreSQL, cache et tâches asynchrones (cahier-des-charges.md:247-251, ADR-002, ADR-004)
psycopg[binary]>=3.2                 # pilote PostgreSQL (dev : optionnel, activé via DATABASE_URL ; prod : requis)
redis>=5                             # client Redis, utilisé par le cache natif de Django et par Celery
celery>=5.4                          # tâches planifiées (taches_quotidiennes) et envoi d'e-mail en arrière-plan

openpyxl>=3.1                        # import/export Excel (.xlsx) — apps/hr : recrutement en masse du personnel

# Documents et temps réel des missions (apps/missions)
reportlab>=4.2                       # PDF des codes de mission — pur Python, aucune bibliothèque système à ajouter à l'image
channels>=4.1                        # WebSocket : suivi des missions en direct (apps/missions/consumers.py)
channels-redis>=4.2                  # couche de messages Redis : gunicorn diffuse, daphne pousse aux navigateurs
daphne>=4.1                          # serveur ASGI des WebSocket ; en développement, il remplace aussi `runserver`
```

Ce que chaque bibliothèque apporte (vous les rencontrerez toutes) :

| Bibliothèque | Rôle |
|---|---|
| **Django** | le framework : base de données, URL, vues, gabarits, administration, sécurité |
| **djangorestframework** (DRF) | l'API REST (chapitre 28) |
| **django-environ** | lire le fichier `.env` |
| **djangorestframework-simplejwt** | jetons JWT courts pour l'API mobile |
| **django-filter** | filtres des listes de l'API |
| **drf-spectacular** (+ sidecar) | documentation interactive de l'API (Swagger), servie localement |
| **django-cors-headers** | autoriser certains domaines à appeler l'API |
| **qrcode**, **Pillow** | fabriquer les images des codes QR des missions |
| **argon2-cffi** | hachage Argon2 des mots de passe |
| **pyotp** | codes à 6 chiffres de la double authentification |

#### `requirements/dev.txt`

*7 lignes*

```text
-r base.txt

# Tests — conventions.md §7 (pytest --cov=apps, factory_boy).
pytest>=8
pytest-django>=4.9
pytest-cov>=5
factory_boy>=3.3
```

`pytest` lance les tests, `pytest-django` le branche sur Django, `pytest-cov` mesure la couverture,
`factory_boy` fabrique des objets de test (chapitre 3).

#### `requirements/prod.txt`

*8 lignes*

```text
-r base.txt

# psycopg, redis et celery sont dans base.txt (étape 7 lot 2) : dev et test s'en servent aussi
# (DATABASE_URL, tests rejoués sur PostgreSQL, Celery en exécution immédiate).

# Étape 7 lot 3 — serveur applicatif et supervision (architecture.md §10 ADR-002, §8 Observabilité)
gunicorn>=23                         # serveur WSGI derrière Nginx
sentry-sdk>=2                        # erreurs et exceptions ; inactif tant que SENTRY_DSN n'est pas défini
```

Installez tout d'un coup (cela prend une à deux minutes) :

```bash
python -m pip install --upgrade pip
pip install -r requirements/dev.txt
```

**Vérifier :**

```bash
python -c "import django, rest_framework, pytest, pyotp, qrcode; print('Django', django.get_version())"
```

**Résultat attendu :** `Django 5.2.x` (un numéro de correctif à partir de 5.2.0, sans avertissement).

## Étape 3 — Règles Git et secrets

#### `.gitignore`

*25 lignes*

```bash
.venv/
__pycache__/
*.pyc
*.pyo
db.sqlite3
test_db.sqlite3
.env
media/
staticfiles/
*.log
.pytest_cache/
htmlcov/
.coverage
.vscode/
.idea/
.claude/

COMPTES-ESSAI.md
donnees_locales*.json

# Fichiers verrou temporaires d'Office (Word, PowerPoint ouverts)
~$*

# Certificats TLS (clés privées Let's Encrypt, GUIDE-DEPLOIEMENT.md) : jamais commités
certs/
```

Ce fichier dit à Git **ce qu'il ne doit jamais versionner** : l'environnement virtuel (`.venv/`), la base de
développement (`db.sqlite3`), les secrets (`.env`), les fichiers générés (`__pycache__/`, `staticfiles/`).

#### `.env.example`

*49 lignes*

```bash
# Copier en .env (jamais commité) — conventions.md §3 "Secrets via .env"

DJANGO_SETTINGS_MODULE=config.settings.dev
SECRET_KEY=change-me
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Prod uniquement (PostgreSQL — architecture.md ADR-002)
# DATABASE_URL=postgres://user:password@host:5432/erp_densource
# REDIS_URL=redis://host:6379/0
# CORS_ALLOWED_ORIGINS=https://app.densourcegroup.com

# Tester en local contre le PostgreSQL/Redis de docker-compose.yml (étape 7 lot 2) : `docker compose up -d`
# puis, par exemple pour rejouer les tests sur une vraie base :
# DATABASE_URL=postgres://erp_densource:erp_densource@localhost:5432/erp_densource
# REDIS_URL=redis://localhost:6379/0
# CELERY_TASK_ALWAYS_EAGER=false   # avec un `celery worker` lancé à côté ; sinon garder à true (défaut)

# Sécurité (étape 7)
# Nombre de proxys de confiance devant l'application (0 en dev, 1 derrière Nginx) : sert à lire la vraie
# adresse du client dans X-Forwarded-For (anti force brute, journal d'audit).
# TRUSTED_PROXY_COUNT=1
# true = la CSP signale sans bloquer (mise au point uniquement)
# CSP_REPORT_ONLY=false

# Déploiement docker-compose (étape 7 lot 3 — voir GUIDE-DEPLOIEMENT.md)
# DJANGO_SETTINGS_MODULE=config.settings.prod
# ALLOWED_HOSTS=erp.densourcegroup.ci
# CSRF_TRUSTED_ORIGINS=https://erp.densourcegroup.ci
# POSTGRES_PASSWORD=change-moi-en-un-mot-de-passe-long   # lu par db, web, celery_worker, celery_beat
# TRUSTED_PROXY_COUNT=1                                  # Nginx est le seul proxy devant l'application

# Supervision (facultatif : inactif tant que SENTRY_DSN n'est pas défini)
# SENTRY_DSN=https://…@…ingest.sentry.io/…
# SENTRY_ENVIRONMENT=production
# SENTRY_TRACES_SAMPLE_RATE=0

# Sauvegardes chiffrées (ops/sauvegarde.sh, ops/restauration.sh)
# SAUVEGARDE_PASSPHRASE=change-moi-en-une-phrase-de-passe-longue

# E-mail réel (prod uniquement) : notifications (si NOTIFICATIONS_EMAIL=true) et « mot de passe
# oublié », qui en dépend entièrement. Un hébergeur de domaine (Hostinger compris) fournit souvent
# un compte e-mail SMTP prêt à l'emploi pour le domaine.
# EMAIL_HOST=smtp.hostinger.com
# EMAIL_PORT=587
# EMAIL_HOST_USER=noreply@densourcegroup.ci
# EMAIL_HOST_PASSWORD=change-moi
# EMAIL_USE_TLS=true
# NOTIFICATIONS_EMAIL=true
```

`.env.example` est un **modèle** qu'on commite ; le vrai `.env` reste local. Copiez-le :

```bash
cp .env.example .env
```

> Sous PowerShell : `Copy-Item .env.example .env`. Pour un vrai usage, remplacez `SECRET_KEY` par une
> longue valeur aléatoire (`python -c "import secrets; print(secrets.token_urlsafe(60))"`).

## Étape 4 — Le point d'entrée : `manage.py` et les serveurs

#### `manage.py`

*22 lignes* — Django's command-line utility for administrative tasks.

```python
#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
```

`os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')` : par défaut, on utilise les
réglages de développement.

#### `config/wsgi.py`

*16 lignes* — WSGI config for config project.

```python
"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')

application = get_wsgi_application()
```

#### `config/asgi.py`

*29 lignes* — Configuration ASGI : HTTP (Django) et WebSocket (suivi des missions en direct).

```python
"""
Configuration ASGI : HTTP (Django) et WebSocket (suivi des missions en direct).

En production, gunicorn (WSGI) sert les pages ; ce module n'est lancé que par le conteneur `realtime`
(daphne), auquel Nginx envoie les connexions ``/ws/``. En développement, `runserver` (daphne) sert
tout à la fois.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')

# Doit précéder l'import des consommateurs : il initialise le registre des applications Django.
application_http = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from apps.missions.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter({
    "http": application_http,
    # L'origine de la page doit figurer dans ALLOWED_HOSTS (sans cela, n'importe quel site pourrait
    # ouvrir une WebSocket avec la session de l'utilisateur) ; la session identifie la personne.
    "websocket": AllowedHostsOriginValidator(AuthMiddlewareStack(URLRouter(websocket_urlpatterns))),
})
```

`wsgi.py` et `asgi.py` sont les portes d'entrée que les serveurs de production (Gunicorn, Uvicorn)
utilisent. Vous n'y touchez jamais, mais Django en a besoin.

## Étape 5 — Les réglages

`settings/base.py` est le fichier le plus long du chapitre. Comme il évolue tout au long du tutoriel
(chaque nouvelle application doit y être déclarée), **voici sa version à ce stade** ; les chapitres suivants
ne montrent que les lignes à ajouter.

#### `config/settings/base.py` — état au chapitre 1

*Ce fichier évolue au fil du tutoriel : voici sa version à ce stade. Les chapitres suivants n'en montrent que les ajouts.*

```python
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
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# 7 rôles, RBAC simple — cahier-des-charges.md:44-55, architecture.md:534.

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
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
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

```

#### `config/urls.py` — état au chapitre 1

*Ce fichier évolue au fil du tutoriel : voici sa version à ce stade. Les chapitres suivants n'en montrent que les ajouts.*

```python
"""Routes du projet.

Chaque app expose ses écrans dans son propre ``urls.py`` (espace de noms =
nom de l'app) ; ce fichier ne fait que les monter.
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView


urlpatterns = [
    path("imprimer/", DashboardImprimerView.as_view(), name="home_imprimer"),
    # Les navigateurs (et l'administration Django) réclament /favicon.ico : on renvoie vers l'icône du site.
    path("favicon.ico", RedirectView.as_view(url=settings.STATIC_URL + "img/favicon.png", permanent=True)),
    path("audit/", include("apps.audit.urls")),
    path("admin/", admin.site.urls),
]

```

Les blocs à repérer dans `base.py` :

| Bloc | Rôle |
|---|---|
| `env = environ.Env(...)`, `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` | lecture des secrets dans `.env` |
| `DJANGO_APPS`, `THIRD_PARTY_APPS`, `LOCAL_APPS` | les applications installées ; on ajoutera les nôtres une par une |
| `MIDDLEWARE` | code exécuté sur **chaque requête** (sécurité, sessions, CSRF…) |
| `TEMPLATES` | où chercher les gabarits HTML |
| `PASSWORD_HASHERS`, `AUTH_PASSWORD_VALIDATORS` | Argon2 et règles de mot de passe (10 caractères minimum) |
| `LANGUAGE_CODE = "fr"`, `TIME_ZONE = "Africa/Abidjan"` | langue et fuseau horaire |
| `REST_FRAMEWORK`, `SIMPLE_JWT`, `SPECTACULAR_SETTINGS`, `CORS_…` | l'API (utilisés au chapitre 28) |
| `MFA_…`, `LOGIN_MAX_ECHECS_…` | double authentification et anti force brute (chapitre 3) |
| `CSP`, `PERMISSIONS_POLICY` | politique de sécurité du contenu (chapitre 16) |

> **Pourquoi des lignes « à venir » dans des réglages qui ne servent pas encore ?** Les blocs API et
> sécurité sont écrits une fois pour toutes ici, parce qu'ils ne dépendent d'aucune de nos applications.
> Seules les lignes qui *nomment* une de nos applications (`apps.core`, `apps.accounts`…) sont ajoutées au
> fil des chapitres : c'est ce que montre le bloc ci-dessus.

Les trois autres environnements :

#### `config/settings/dev.py`

*26 lignes* — Environnement développeur — SQLite, LocMem cache (architecture.md:402).

```python
"""Environnement développeur — SQLite, LocMem cache (architecture.md:402)."""

from .base import *  # noqa: F401,F403
from .base import BASE_DIR, env

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Les e-mails de notification s'affichent dans la console du serveur.
NOTIFICATIONS_EMAIL = True
```

En développement : base **SQLite** (un simple fichier `db.sqlite3`), cache en mémoire, e-mails affichés dans
la console.

#### `config/settings/test.py`

*41 lignes* — Environnement CI/CD — PostgreSQL éphémère si dispo, sinon SQLite (architecture.md:403).

```python
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
```

Pour les tests : mots de passe hachés **en MD5** (rapide ; jamais en production), aucune double
authentification imposée (les tests qui la vérifient la réactivent), plafonds de limitation très hauts.

#### `config/settings/prod.py`

*107 lignes* — Environnement production — PostgreSQL, Redis (architecture.md:405).

```python
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
```

En production : HTTPS obligatoire, cookies sécurisés, base PostgreSQL et Redis fournis par l'environnement.
Ce fichier n'est pas utilisé dans ce tutoriel (voir « Aller plus loin », chapitre 29).

## Étape 6 — Les adresses et la configuration des tests

Le fichier `config/urls.py` est la **table des adresses** du site. Il grossira à chaque écran ajouté ; voici
son état actuel (il figure dans le bloc précédent). La ligne `favicon.ico` redirige le
navigateur vers l'icône du site.

#### `pytest.ini`

*6 lignes*

```ini
[pytest]
DJANGO_SETTINGS_MODULE = config.settings.test
python_files = test_*.py
testpaths = apps
markers =
    gabarit_reel: le test veut le vrai chargeur de gabarits (pas le simulacre par défaut des tests de sections)
```

`pytest.ini` dit à pytest d'utiliser les réglages `config.settings.test`, de chercher les fichiers
`test_*.py` dans `apps/`, et déclare un *marqueur* utilisé par un test du chapitre 2.

## Vérifier le chapitre

```bash
python manage.py check
```

**Résultat attendu :** `System check identified no issues (0 silenced).`

```bash
python manage.py --version
```

**Résultat attendu :** `5.2.x`.

> **Si `check` échoue avec `ModuleNotFoundError`** : une bibliothèque manque (`pip install -r
> requirements/dev.txt`) ou l'environnement virtuel n'est pas activé. **Avec `ImproperlyConfigured`** : une
> ligne de `base.py` a été mal recopiée.

## Ce qu'il faut retenir

- Un projet Django, c'est des **réglages** + une **liste d'applications** + une **table d'adresses**.
- Les secrets ne sont jamais dans le code : ils vivent dans `.env`, ignoré par Git.
- Trois environnements (`dev`, `test`, `prod`) partagent un socle commun (`base`).

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 1 : squelette du projet (réglages, dépendances, configuration des tests)"
```

---

[← Chapitre 0](00-prerequis.md) · [Sommaire](README.md) · [Chapitre 2 →](02-core.md)
