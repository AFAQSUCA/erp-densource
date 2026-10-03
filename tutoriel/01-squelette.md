# Chapitre 1 — Le squelette du projet

> 31 fichier(s) dans ce chapitre, 2558 lignes de code.

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
    # Les navigateurs (et l'administration Django) réclament /favicon.ico : on renvoie vers l'icône du site.
    path("favicon.ico", RedirectView.as_view(url=settings.STATIC_URL + "img/favicon.png", permanent=True)),
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

Il reste les autres fichiers du squelette : Docker, Celery, les guides de déploiement et les avenants du dépôt.

#### `.dockerignore`

*17 lignes*

```text
.venv/
__pycache__/
*.pyc
db.sqlite3
test_db.sqlite3
.env
.git/
.pytest_cache/
htmlcov/
.coverage
node_modules/
staticfiles/
media/
tutoriel/
outils/
GUIDE-*.md
Presentation-ERP-DEN-Source.*
```

#### `Dockerfile`

*38 lignes*

```text
# Image de production — étape 7 lot 3 (architecture.md §6 « Vue déploiement »).
#
# Les styles, icônes et Alpine.js sont déjà compilés et versionnés dans static/ (frontend/README.md) :
# Node n'est pas nécessaire ici, une seule étape suffit.

FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libpq5 : bibliothèque cliente PostgreSQL utilisée par psycopg au démarrage (le wheel « binary »
# embarque le nécessaire à l'installation, mais la garder explicite évite une surprise si le wheel
# venait à manquer pour une architecture donnée).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/ requirements/
RUN pip install -r requirements/prod.txt

COPY . .

# Compte non privilégié : l'application n'a besoin d'écrire que staticfiles/ et media/ (montés en
# volumes par docker-compose.yml). Les créer ici, avant le premier montage du volume : Docker
# reprend alors les droits de ce dossier pour initialiser le volume (sinon, root).
RUN useradd --create-home --uid 1000 django \
    && mkdir -p staticfiles media \
    && chown -R django:django /app
USER django

EXPOSE 8000

ENTRYPOINT ["ops/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--config", "ops/gunicorn.conf.py"]
```

#### `GUIDE-DEPLOIEMENT.md`

*311 lignes* — Déployer l'ERP DEN Source Group

````markdown
# Déployer l'ERP DEN Source Group

Guide du déploiement sur un **serveur Linux unique avec Docker Compose** — le choix retenu pour ce
projet (cahier-des-charges.md §4 « Conteneurisation », architecture.md §6 « Vue déploiement »). Pas
de réplique de base, pas de cluster Redis, pas de CDN : un seul serveur, suffisant pour le volume
visé, que les mêmes fichiers (`docker-compose.yml`) laissent la porte ouverte à faire évoluer plus
tard sans réécrire l'application.

Ce que ce fichier décrit a été **testé en local** (voir « Ce qui a été vérifié » en bas de page) :
la pile complète (application, Celery, Nginx, PostgreSQL, Redis) démarre et sert de vraies pages à
travers Nginx, exactement comme en production — seul un vrai domaine et un vrai certificat TLS
manquent à l'essai local.

## 1. Ce qui tourne

```
Internet ──► Nginx (80/443) ──► Gunicorn (web, 3 workers) ──► PostgreSQL
                 │                      │                         ▲
                 │                      └──► Celery worker ───────┤
                 ├── /static/, /media/       Celery beat ─────────┘
                 │   (disque, pas Gunicorn)        │
                 ├── /ws/ ──► Daphne (realtime) ───┤  suivi des missions en direct
                 │                                 │
                 └────────────────────────────► Redis (cache + file Celery + messages WebSocket)
```

7 conteneurs (`docker-compose.yml`) : `nginx`, `web` (Gunicorn), `realtime` (Daphne : les WebSocket du suivi
des missions en direct), `celery_worker`, `celery_beat`, `db` (PostgreSQL), `redis`. Quatre construisent une image
(`web`, `realtime`, `celery_worker`, `celery_beat` partagent la même, définie par `Dockerfile`) ; `db`, `redis` et
`nginx` sont des images officielles telles quelles. Gunicorn sert les pages, Daphne ne tient que les WebSocket :
quand une mission change, `web` le signale dans Redis et `realtime` le pousse aux navigateurs connectés.

## 2. Choisir un serveur, à moindre coût

Pas besoin d'un gros serveur : `docker-compose.yml` fait tourner nginx, l'application, Celery,
PostgreSQL et Redis confortablement sur **2 Go de RAM**. Les niveaux « toujours gratuits » des
grands fournisseurs cloud (Oracle Cloud notamment) ne sont pas ouverts à l'inscription depuis tous
les pays ; plutôt que de perdre du temps à contourner ça, un petit VPS payant revient à
2 000-4 000 FCFA/mois (3-5 €) — à comparer aux 200 000 FCFA/mois prévus au cahier des charges pour
l'exploitation réelle, c'est un coût marginal pour un pilote ou une démo, et **rien dans ce dépôt
n'a besoin de changer** pour en profiter : ce sont les mêmes commandes, plus bas, sur n'importe quel
Linux avec Docker.

Quelques fournisseurs qui acceptent les paiements internationaux (carte, parfois PayPal) et ont des
centres en Europe — plus proches d'Abidjan qu'un serveur américain, donc une meilleure latence :

| Fournisseur | Offre indicative | Note |
|---|---|---|
| **Contabo** | ~4-5 €/mois, 8 Go de RAM | Très généreux pour le prix |
| **OVH** (VPS) | ~4-6 €/mois, 2 Go de RAM | Société française, présente en Afrique |
| **DigitalOcean** | ~6 $/mois, 1 Go de RAM | Documentation abondante, simple à prendre en main |
| **Hetzner** | ~4-5 €/mois, 4 Go de RAM | Très bon rapport prix/performance (Europe uniquement) |

Prendre l'offre la plus petite (1-2 Go de RAM) avec **Ubuntu 22.04 ou 24.04 LTS** suffit.

## 3. Prérequis sur le serveur

- Un serveur Linux (Debian/Ubuntu conviennent) avec **Docker** et le plugin **Docker Compose**
  installés (`docker compose version`) — une fois le VPS créé :

  ```bash
  curl -fsSL https://get.docker.com | sh   # script officiel Docker, installe aussi le plugin Compose
  ```

- Un **nom de domaine** pointé (DNS, enregistrement A) vers l'adresse IP du serveur — nécessaire
  pour obtenir un certificat HTTPS (étape 8). Pas besoin d'en acheter un pour démarrer :
  [DuckDNS](https://www.duckdns.org) donne gratuitement un sous-domaine (`mon-erp.duckdns.org`)
  qui fonctionne tout aussi bien avec Let's Encrypt qu'un domaine payant.
- Les ports **80** et **443** ouverts (pare-feu du serveur / du fournisseur cloud — souvent une
  « security list » ou un « firewall » à configurer dans le tableau de bord du fournisseur, en plus
  du pare-feu du système : `ufw allow 80,443/tcp` sous Ubuntu).
- Git, pour récupérer le dépôt.

## 4. Préparer le serveur

```bash
git clone <url-du-dépôt> erp-densource
cd erp-densource
cp .env.example .env
```

Éditer `.env` et renseigner au minimum (voir les commentaires du fichier) :

| Variable | Valeur |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` |
| `SECRET_KEY` | une valeur longue et aléatoire — jamais celle de `.env.example` ; générer avec `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `ALLOWED_HOSTS` | le domaine, ex. `erp.densourcegroup.ci` |
| `CSRF_TRUSTED_ORIGINS` | `https://` + le même domaine |
| `POSTGRES_PASSWORD` | un mot de passe long, différent de celui de `.env.example` |
| `TRUSTED_PROXY_COUNT` | `1` (Nginx est l'unique proxy devant l'application) |
| `SAUVEGARDE_PASSPHRASE` | une phrase de passe longue, **à conserver ailleurs que sur ce serveur** (étape 9) |

`DATABASE_URL` et `REDIS_URL` n'ont **pas** à être renseignées dans `.env` pour ces quatre services :
`docker-compose.yml` les fixe lui-même vers `db` et `redis` (les noms des conteneurs). Elles ne
servent, en valeur `localhost`, que pour un test depuis la machine hors conteneur (étape 7 lot 2).

## 5. Démarrer

```bash
docker compose up -d --build
```

Au premier démarrage, `web` collecte les fichiers statiques et applique les migrations avant de
lancer Gunicorn (`ops/entrypoint.sh`) ; `celery_worker` et `celery_beat` attendent que `web` soit en
bonne santé (les migrations sont donc déjà passées) avant de démarrer.

```bash
docker compose ps                 # les 7 services doivent être « healthy » ou « running »
docker compose logs -f web        # suivre le démarrage
curl -I http://localhost/connexion/   # doit répondre 301 (redirigé vers https, tant que le 4 n'est pas fait)
```

Créer le premier compte administrateur :

```bash
docker compose exec web python manage.py createsuperuser
```

## 6. Comptes de démonstration

**Ne jamais lancer `creer_comptes_demo` en production** (la commande refuse de tourner si
`DEBUG=False` — apps/hr/management/commands/creer_comptes_demo.py) : ces comptes sont réservés au
développement.

## 7. Vérifier avant la mise en service réelle

Avant que les vrais utilisateurs n'arrivent, il est légitime de saisir quelques fiches réalistes
(personnel, un client, une mission…) pour parcourir les écrans une dernière fois sur ce serveur.

1. Créez le premier compte administrateur si ce n'est pas déjà fait (étape 5), activez sa MFA.
2. Saisissez quelques fiches à la main (recrutement, import Excel du personnel, un client, une
   mission…) et vérifiez les écrans qui comptent pour vous.
3. **Avant la mise en service réelle, repartez d'une base vide** plutôt que de supprimer les
   fiches une par une : la suppression est *logique* (`BaseModel.delete`, cahier-des-charges.md
   « jamais de suppression physique ») — les lignes resteraient en base, et les numéros déjà
   attribués (matricule, missions…) ne redescendraient pas à 1. Le plus sûr est d'effacer le
   volume de la base et de repartir d'une migration propre :

   ```bash
   docker compose down
   docker volume rm erp-densource_db_data
   docker compose up -d --build
   docker compose exec web python manage.py createsuperuser
   ```

   (Adapter le nom du volume si le dossier du projet ne s'appelle pas `erp-densource` —
   `docker volume ls | grep db_data` l'affiche.) Le compte administrateur doit être recréé après
   ce nettoyage : lui aussi a été effacé.

## 8. Activer HTTPS (Let's Encrypt, certbot)

Tant que ce qui suit n'est pas fait, Nginx répond en HTTP (port 80) et `SECURE_SSL_REDIRECT`
(config/settings/prod.py) redirige chaque page vers `https://…`, qui n'existe pas encore : c'est
attendu, à corriger maintenant.

1. **Obtenir un certificat** (le domaine doit déjà pointer vers ce serveur — le défi HTTP-01 le
   vérifie) :

   ```bash
   mkdir -p certs
   docker run --rm \
     -v "$(pwd)/certs:/etc/letsencrypt" \
     -v erp-densource_certbot_www:/var/www/certbot \
     certbot/certbot certonly --webroot -w /var/www/certbot \
     -d erp.densourcegroup.ci --email vous@densourcegroup.ci --agree-tos --no-eff-email
   ```

   (Remplacer le nom du volume par celui qu'affiche `docker volume ls | grep certbot_www` si le
   dossier du projet ne s'appelle pas `erp-densource`.)

2. **Ajouter le bloc HTTPS** dans `nginx/nginx.conf`, à la suite du bloc `server { listen 80; … }` :

   ```nginx
   server {
       listen 443 ssl;
       server_name erp.densourcegroup.ci;

       ssl_certificate     /etc/nginx/certs/live/erp.densourcegroup.ci/fullchain.pem;
       ssl_certificate_key /etc/nginx/certs/live/erp.densourcegroup.ci/privkey.pem;

       location /static/ { alias /app/staticfiles/; expires 30d; access_log off; }
       location /media/  { alias /app/media/;       expires 7d;  access_log off; }
       location / {
           proxy_pass http://django;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

   Et changer, dans le bloc `listen 80`, la `location /` pour ne plus proxyer mais rediriger (le défi
   `/.well-known/acme-challenge/` reste, lui, en HTTP) :

   ```nginx
   location / {
       return 301 https://$host$request_uri;
   }
   ```

3. **Décommenter**, dans `docker-compose.yml`, le port `443:443` et le volume `./certs:…` du service
   `nginx`, puis :

   ```bash
   docker compose up -d
   ```

4. **Renouvellement** : les certificats Let's Encrypt expirent après 90 jours. Programmer, dans la
   crontab du serveur (`crontab -e`), un renouvellement mensuel :

   ```cron
   0 3 1 * * cd /chemin/vers/erp-densource && docker run --rm -v "$(pwd)/certs:/etc/letsencrypt" -v erp-densource_certbot_www:/var/www/certbot certbot/certbot renew --webroot -w /var/www/certbot && docker compose restart nginx
   ```

## 9. Sauvegardes chiffrées (`ops/sauvegarde.sh`)

Sauvegarde quotidienne, chiffrée avec `SAUVEGARDE_PASSPHRASE` (GPG, symétrique), à copier vers un
stockage **hors de ce serveur** (cahier-des-charges.md « sauvegardes chiffrées et testées »,
« offsite ») :

```cron
0 2 * * * cd /chemin/vers/erp-densource && set -a && . ./.env && set +a && DATABASE_URL="postgres://erp_densource:${POSTGRES_PASSWORD}@localhost:5432/erp_densource" ops/sauvegarde.sh /chemin/vers/sauvegardes
```

(`pg_dump`/`gpg` doivent être installés sur l'hôte — `apt install postgresql-client gnupg` — ou lancés
dans un conteneur éphémère `postgres:16` avec les mêmes volumes réseau.)

### Tester une restauration (mensuel)

**Jamais sur la base de production.** Créer une base à part et y restaurer la dernière sauvegarde :

```bash
docker compose exec db createdb -U erp_densource erp_densource_essai_restauration
DATABASE_URL="postgres://erp_densource:${POSTGRES_PASSWORD}@localhost:5432/erp_densource_essai_restauration" \
  ops/restauration.sh /chemin/vers/sauvegardes/<fichier>.dump.gpg
docker compose exec db dropdb -U erp_densource erp_densource_essai_restauration   # nettoyage
```

Une restauration qui échoue silencieusement est pire qu'une absence de sauvegarde : ce test mensuel
est ce qui distingue les deux.

## 10. Supervision (Sentry)

Facultatif, mais recommandé (cahier-des-charges.md « Monitoring Sentry »). Créer un projet Django
sur [sentry.io](https://sentry.io) (ou une instance auto-hébergée), copier son DSN dans `.env` :

```
SENTRY_DSN=https://…@…ingest.sentry.io/…
```

Puis `docker compose up -d` (redémarre `web`, `celery_worker`, `celery_beat` avec Sentry actif —
config/settings/prod.py). Sans `SENTRY_DSN`, rien ne change : Sentry reste inactif.

*Prometheus/Grafana* (également cité au cahier des charges) n'est volontairement pas installé : pour
un serveur unique, deux conteneurs de plus pour un tableau de bord de métriques n'apportent pas
encore assez, face à Sentry qui couvre déjà les erreurs. À ajouter si le volume le justifie.

## 11. Mettre à jour l'application

```bash
git pull
docker compose up -d --build
```

Les migrations et `collectstatic` se rejouent automatiquement au démarrage de `web`
(`ops/entrypoint.sh`) ; `celery_worker`/`celery_beat` attendent que `web` soit de nouveau en bonne
santé avant de redémarrer.

**Une fois, après la mise à jour qui introduit la comptabilisation automatique des dépenses du parc auto**
(carburant, pièces, main-d'œuvre des OR) : reprendre l'historique déjà enregistré n'est pas automatique
(voir `apps/finance/README.md`). Vérifier d'abord si un « solde d'ouverture » a été saisi en trésorerie et à
quelle date, puis :
```bash
docker compose exec web python manage.py comptabiliser_historique_parc_auto --dry-run
docker compose exec web python manage.py comptabiliser_historique_parc_auto [--depuis AAAA-MM-JJ]
```

## 12. Dépannage

| Symptôme | Piste |
|---|---|
| `web` ne devient jamais « healthy » | `docker compose logs web` — souvent une variable de `.env` manquante (`SECRET_KEY`, `ALLOWED_HOSTS`…) |
| Nginx répond 502 | `web` n'a pas encore fini de démarrer, ou a planté — voir ses journaux |
| Boucle de redirection HTTPS | `X-Forwarded-Proto` n'arrive pas jusqu'à Django : vérifier que la requête passe bien par Nginx (pas directement sur le port 8000 de `web`) |
| `celery_worker` ne traite rien | `docker compose logs celery_worker` : le plus souvent `REDIS_URL` injoignable |
| Fiche mission sans voyant « En direct » (« Suivi en direct indisponible ») | `docker compose logs realtime` : conteneur arrêté ? Vérifier aussi que le bloc `location /ws/` est bien dans le serveur 443 de `nginx/nginx.conf`, et que `ALLOWED_HOSTS` contient le domaine (l'origine de la page est contrôlée) |
| Le voyant « En direct » clignote (Reconnexion…) et `docker compose logs realtime` affiche `Timeout reading from redis` | Le délai de lecture Redis est inférieur à l'attente bloquante de `channels-redis` (5 s) : vérifier `socket_timeout` dans `CHANNEL_LAYERS` (config/settings/prod.py, 15 s) — `redis-py` >= 8 impose sinon 5 s par défaut |
| Page de connexion sans styles | `collectstatic` n'a pas tourné, ou le volume `static_data` n'est pas monté dans `nginx` |

---

## Ce qui a été vérifié

Testé en local avec `docker compose up -d --build` (domaine `localhost`, sans certificat réel) :
- les 7 services démarrent et `web` devient « healthy » (migrations + `collectstatic` appliqués) ;
- la page de connexion est servie par **Nginx**, pas directement par Gunicorn (styles chargés
  depuis `/static/`, non `web:8000`) ;
- `SECURE_SSL_REDIRECT` redirige correctement en HTTP simple (pas de boucle) et laisse passer une
  requête dont `X-Forwarded-Proto` vaut `https` (simulation du TLS terminé par Nginx) ;
- `celery_worker` et `celery_beat` démarrent, se connectent à Redis et exécutent une tâche réelle ;
- le suivi des missions en direct traverse Nginx (TLS) : une WebSocket ouverte par un compte du bureau reçoit
  le changement d'état d'une mission confirmé par le chauffeur depuis une autre session (`web` → Redis →
  `realtime` → navigateur) ; sans cookie de session, la connexion est refusée (403) ;
- une sauvegarde chiffrée (`ops/sauvegarde.sh`) puis sa restauration (`ops/restauration.sh`) dans
  une base à part ont réellement été jouées contre le PostgreSQL du `docker-compose.yml`.

Non testés ici faute de domaine réel : l'obtention d'un certificat Let's Encrypt (étape 8.1) et son
renouvellement automatique (étape 8.4) — les commandes sont standard (image officielle
`certbot/certbot`, mode webroot) mais n'ont pas pu être rejouées sans nom de domaine public.
````

#### `avenant-comptabilite-autonomie.md`

*257 lignes* — Avenant — Autonomie complète du comptable dans l'ERP

```markdown
# Avenant — Autonomie complète du comptable dans l'ERP

Complète `avenant-comptabilite-syscohada.md` (qui a livré le moteur de comptabilité en partie
double, 6 phases, toutes fusionnées). Cet avenant est né d'un test en conditions réelles : je me
suis connecté avec le rôle FINANCES et j'ai exécuté les tâches qu'un comptable ferait vraiment
(facturation, encaissement, dépenses, trésorerie, écritures manuelles, rapports). Deux constats :
un bug réel (les brouillons non validés faussaient déjà les rapports officiels), et plusieurs
tâches qu'un comptable ne peut aujourd'hui pas faire seul dans l'ERP.

Décision confirmée par l'entreprise : l'ERP doit devenir complet pour un usage **100% autonome**
de comptable — à l'exception du contrôle Finances/Direction (préparation/validation des écritures
manuelles), qui reste volontairement en place (séparation des tâches, pas un manque).

Chaque lot est livré, testé, documenté et fusionné séparément (même principe que les phases de
`avenant-comptabilite-syscohada.md`).

| Lot | Contenu | Statut |
|---|---|---|
| A | Rapports comptables : exclure les brouillons non validés (bug trouvé en testant) | ✅ Fusionnée (PR #25) |
| B | Export / impression des rapports comptables (grand livre, balance, bilan, compte de résultat) | ✅ Fusionnée (PR #31) |
| C | Comptabilisation automatique des dépenses manuelles (péages, entretien, frais admin, autre) | ✅ Fusionnée (PR #32) |
| D | TVA déductible réelle sur les dépenses | ✅ Fusionnée (PR #33) |
| E | Déclaration TVA (synthèse collectée / déductible) | ✅ Fusionnée (PR #34) |
| F | Écran de gestion du plan comptable | ✅ Fusionnée (PR #35) |
| G | Rapprochement bancaire | **✅ Ce lot** — voir ci-dessous |

## Lot A — Rapports comptables : exclure les brouillons non validés

Trouvé en testant : `grand_livre`, `balance`, `compte_de_resultat` et `bilan`
(`apps/accounting/services.py`) ne filtraient jamais sur `statut=VALIDEE`. Un brouillon
d'opération diverse — créé mais pas encore approuvé par la DIRECTION — apparaissait déjà dans les
états financiers officiels. Démontré en direct : créer un brouillon a immédiatement changé le
résultat net affiché.

**Correctif** : les 4 fonctions filtrent désormais sur `ecriture__statut=VALIDEE`. 4 tests ajoutés
(un par rapport), suite complète verte. Détails : PR #25.

## Lot B — Export / impression des rapports comptables

Aucun des 4 rapports (grand livre, balance, bilan, compte de résultat) n'avait de version
imprimable, alors que tout le reste de l'ERP en a une (factures, journal d'audit, tableau de
bord, trésorerie) — un comptable ne pouvait pas sortir un bilan pour une banque ou un commissaire
aux comptes.

**Implémentation** : même mécanisme que partout ailleurs dans l'ERP (`apps/core/rapports.py`,
impression navigateur via CSS, pas de génération PDF côté serveur) — 4 nouvelles vues
(`GrandLivreImprimerView`, `BalanceImprimerView`, `BilanImprimerView`,
`CompteDeResultatImprimerView`, `apps/accounting/views.py`), 4 routes `.../imprimer/`, 4 gabarits
`accounting/*_print.html` réutilisant `rapports/_style_impression.html` +
`_entete_impression.html` + `_pied_impression.html`, bouton « Imprimer » ajouté sur les 4 écrans
existants (même style que `finance.tresorerie`).

**Vérifié manuellement** (navigateur, `demo_finances`) : les 4 versions imprimables affichent
exactement les mêmes chiffres que les écrans en ligne, avec l'en-tête entreprise et le pied
« Généré le / par ».

**Implémentation** : `apps.accounting.views.GrandLivreImprimerView` /
`BalanceImprimerView` / `BilanImprimerView` / `CompteDeResultatImprimerView`,
`apps/accounting/templates/accounting/grand_livre_print.html` /
`balance_print.html` / `bilan_print.html` / `compte_resultat_print.html`.

## Lot C — Comptabilisation automatique des dépenses manuelles

Trouvé en testant : une dépense saisie à la main (péages, entretien, frais administratifs, autre
— `billing.services.enregistrer_depense`) apparaissait bien en trésorerie mais ne générait
**aucune écriture comptable**. Seules les 4 catégories automatiques (carburant, pièces,
main-d'œuvre des OR, frais de mission) étaient comptabilisées depuis la Phase 3
(`avenant-comptabilite-syscohada.md` § P4, « limite de périmètre »). Concrètement : la
comptabilité prenait du retard sur la trésorerie sans que rien ne l'alerte.

**Mapping retenu** (`apps/accounting/constants.py::CATEGORIE_DEPENSE_VERS_COMPTE`), à valider par
un expert-comptable comme le reste du plan comptable de départ :
- Péages → 628100 (Frais de mission et déplacements — même nature que les frais de route)
- Entretien → 624100 (Entretien, réparations — même compte que la main-d'œuvre des OR)
- Frais administratifs et Autre → 658000 (Charges diverses de gestion courante)

**Implémentation** : `apps.billing.services.enregistrer_depense` émet désormais
`billing.signals.depense_a_comptabiliser` après création de la `Depense` (même signal que les
dépenses automatiques, `@transaction.atomic` : une dépense dont l'écriture ne s'équilibre pas est
annulée plutôt que de laisser une sortie d'argent non comptée). Côté `accounting`, aucun nouveau
code : `services.comptabiliser_une_depense_automatique` était déjà générique par catégorie, elle
gère maintenant les 8 catégories au lieu de 4. `comptabiliser_historique_depenses` reprend
désormais toutes les dépenses (plus seulement celles avec une `origine` automatique).

**Vérifié manuellement** (navigateur, `demo_finances`) : rattrapage des dépenses manuelles
existantes dans la base de dev via la commande (`4 dépense(s) comptabilisée(s)`), balance
correctement mouvementée sur 624100/628100/658000 ; une nouvelle dépense « Péages » saisie en
direct génère immédiatement son écriture (journal Caisse, visible dans le grand livre du compte
628100) sans action supplémentaire.

**Implémentation** : `apps.accounting.constants.CATEGORIE_DEPENSE_VERS_COMPTE`,
`apps.billing.services.enregistrer_depense`,
`apps.accounting.management.commands.comptabiliser_historique_depenses`.

## Lot D — TVA déductible réelle sur les dépenses

Jusqu'ici, une dépense n'avait qu'un montant unique traité comme une charge TTC sans TVA
récupérable — même les dépenses automatiques (carburant, pièces…) chargeaient le compte de charge
pour le montant plein. Le compte 445200 « État, TVA déductible » du plan comptable seedé n'était
jamais mouvementé.

**Décisions confirmées avec l'entreprise** :
- Toutes les catégories peuvent porter de la TVA déductible, au cas par cas (pas systématique :
  un fournisseur informel ou non assujetti ne la facture pas).
- Taux par défaut 18 % (aligné sur les ventes), mais l'utilisateur saisit le montant de TVA
  directement depuis sa pièce justificative plutôt qu'un taux — plus fidèle à ce qui est écrit sur
  un vrai reçu (HT / TVA / TTC).

**Modèle** (`billing.models.Depense`) : nouveau champ `montant_tva` (FCFA, défaut 0, facultatif).
`montant` reste le TTC payé ; `montant_ht` est une propriété calculée (`montant - montant_tva`).
Contraintes DB : `montant_tva >= 0` et `montant_tva < montant` (une TVA ne peut jamais égaler ou
dépasser le TTC). Les dépenses existantes gardent `montant_tva = 0` (aucune TVA reconstituée a
posteriori sur l'historique).

**Écriture comptable** (`accounting.services.comptabiliser_une_depense_automatique`) : quand
`montant_tva > 0`, l'écriture passe à 3 lignes — débit du compte de charge au HT, débit du compte
445200 pour la TVA déductible, crédit de la trésorerie au TTC (toujours équilibrée). Quand
`montant_tva = 0` (cas par défaut, y compris toutes les dépenses automatiques pour l'instant —
leurs apps sources ne capturent pas encore la TVA à la source), le comportement est inchangé : une
seule ligne de charge au montant plein.

**Écran** (`/facturation/depenses/nouvelle/`) : nouveau champ « dont TVA déductible (FCFA) »,
facultatif, avec l'aide « ex. 18 % : montant TTC × 18 ÷ 118 » ; affiché aussi dans la liste des
dépenses (« dont X TVA déd. » sous le montant) quand non nul.

**Limite de périmètre (pas un oubli)** : seule la saisie manuelle expose le champ TVA pour
l'instant. Les 4 catégories automatiques (carburant, pièces, main-d'œuvre des OR, frais de
mission) restent à TVA = 0 tant que leurs apps sources (`fuel`, `inventory`, `garage`, `missions`)
ne capturent pas elles-mêmes une ventilation HT/TVA — un chantier séparé, plus large (il toucherait
4 apps et leurs formulaires), pas nécessaire pour que le moteur comptable gère déjà la TVA
déductible correctement partout où elle est saisie.

**Vérifié manuellement** (navigateur, `demo_finances`) : péage à 11 800 FCFA TTC dont 1 800 FCFA de
TVA saisi en direct → écriture à 3 lignes (628100 débit 10 000, 445200 débit 1 800, 571000 crédit
11 800), balance équilibrée, compte de résultat n'inclut pas la TVA déductible dans les charges
(c'est un compte d'actif, pas une charge).

**Implémentation** : `billing.models.Depense.montant_tva`/`montant_ht`,
`billing.services.enregistrer_depense`, `billing.forms.DepenseForm`,
`accounting.constants.COMPTE_TVA_DEDUCTIBLE`,
`accounting.services.comptabiliser_une_depense_automatique`.

## Lot E — Déclaration TVA

Dernier maillon manquant côté TVA : une fois la TVA déductible réelle en place (Lot D), rien ne
calculait « TVA collectée − TVA déductible » pour une période — un comptable devait le faire à la
main à partir de la balance, en repérant lui-même les comptes 443300 et 445200.

**Service** (`accounting.services.declaration_tva(*, debut, fin)`) : agrège les mouvements
VALIDEE des deux comptes sur la période, renvoie `tva_collectee`, `tva_deductible` et
`tva_nette` (positive = à reverser au Trésor Public, négative = crédit de TVA reportable sur la
période suivante). Contrairement à la balance ou au grand livre, une déclaration porte toujours
sur une période bornée : le mois en cours par défaut si aucune date n'est choisie (cycle de
déclaration usuel en Côte d'Ivoire), ou le mois complet de la seule date fournie si une seule
borne est donnée.

**Écran** (`/comptabilite/declaration-tva/`, formulaire de période, accessible depuis le menu
« Rapports comptables ») + version imprimable (`.../imprimer/`, même mécanisme que les autres
rapports — Lot B).

**Vérifié manuellement** (navigateur, `demo_finances`) : sur l'année 2026 complète, TVA collectée
216 000 FCFA (identique à la ligne 443300 de la balance), TVA déductible 1 800 FCFA (identique à
la ligne 445200), TVA nette à payer 214 200 FCFA ; sur le mois en cours (aucune vente, une
dépense facturée), correctement affiché comme un crédit de TVA reportable négatif.

**Implémentation** : `accounting.services.declaration_tva`,
`accounting.views.DeclarationTvaView` / `DeclarationTvaImprimerView`,
`accounting/templates/accounting/declaration_tva.html` / `declaration_tva_print.html`.

## Lot F — Écran de gestion du plan comptable

Le plan comptable (`accounting.Compte`) n'était consultable et modifiable que depuis l'admin
Django, réservé à l'ADMIN — alors que le plan de départ est explicitement marqué « à valider par
un expert-comptable » dans le code depuis la Phase 1 : le comptable qui doit le corriger n'y avait
pas accès.

**Décisions de conception** (pas de question business ouverte, choix techniques directs, cohérents
avec le reste de l'app) :
- Même largeur de rôle que la saisie d'écritures manuelles (`GESTION_PLAN_COMPTABLE` = ADMIN,
  DIRECTION, FINANCES, RH) — ce n'est pas une transaction financière nécessitant un contrôle
  Direction a posteriori, seulement le paramétrage du référentiel.
- Le numéro et la nature d'un compte ne se modifient plus une fois créés (`services.creer_compte`
  vs `services.modifier_compte`) : changer la nature d'un compte après coup reclasserait
  silencieusement toutes ses écritures passées dans le bilan/compte de résultat.
- Un compte ne se supprime jamais (comme documenté depuis la Phase 1) : seule la désactivation
  (`actif=False`) est possible, empêchant son usage dans une nouvelle écriture
  (`passer_ecriture` refuse déjà un compte inactif) sans perdre son historique.

**Écran** (`/comptabilite/plan-comptable/`, menu « Plan comptable ») : liste triée par numéro avec
nature et statut, bouton « Nouveau compte » et lien « Modifier » par ligne pour les rôles
autorisés.

**Vérifié manuellement** (navigateur, `demo_finances`) : création d'un compte 626000 « Péages et
parkings » (Charge), immédiatement disponible dans les formulaires d'opération diverse ; puis
modification de son libellé, conservée après rechargement de la liste.

**Implémentation** : `accounting.services.creer_compte` / `modifier_compte`,
`accounting.permissions.GESTION_PLAN_COMPTABLE`, `accounting.exceptions.CompteDejaExistant`,
`accounting.views.PlanComptableListView` / `CompteCreateView` / `CompteModifierView`,
`accounting/templates/accounting/plan_comptable_list.html` / `compte_form.html` /
`compte_modifier_form.html`.

## Lot G — Rapprochement bancaire

Dernier écart trouvé en testant : rien dans l'ERP ne confrontait le relevé réel de la banque aux
mouvements de trésorerie enregistrés. Un comptable ne pouvait pas s'assurer que la banque était
d'accord avec le solde affiché ; en cas d'écart (frais bancaires prélevés directement, virement non
enregistré...), rien ne l'aurait signalé.

**Décisions confirmées avec l'entreprise** :
- Saisie manuelle ligne par ligne du relevé bancaire — pas d'import de fichier (aucun format de
  relevé n'est imposé par la banque actuelle, et l'import serait un chantier séparé si le besoin
  se confirme).
- Suggestion automatique de rapprochement (même sens et même montant que la ligne saisie, mouvement
  le plus proche en date en premier) avec pointage manuel confirmé par l'utilisateur — jamais de
  pointage automatique silencieux.
- Un écart qui persiste après pointage se corrige par l'opération diverse déjà existante
  (`apps/accounting/README.md`), pas par un nouveau mécanisme de correction.

**Modèle** (`finance.models.LigneReleve`) : une ligne du relevé saisie à la main (date, libellé,
montant, sens, référence facultative) ; `pointee`, `mouvement_origine` et `mouvement_id`
restent vides tant qu'elle n'est pas associée à un mouvement de trésorerie précis. Le
rapprochement ne concerne que le compte Banque (Virement, Chèque) — jamais la Caisse ni le Mobile
Money, cohérent avec `apps.billing.models.COMPTE_DU_MODE`.

**Service** (`finance.services`) : `saisir_ligne_releve` (mêmes droits que toute saisie
trésorerie, `billing.permissions.SAISIE`) ; `suggestions_pointage` (mouvements Banque non encore
pointés, même sens et montant, triés par proximité de date) ; `pointer_ligne_releve` /
`depointer_ligne_releve` (un mouvement ne peut être pointé que sur une seule ligne à la fois) ;
`rapprochement_bancaire(*, debut, fin)` calcule le solde du relevé, le solde des mouvements Banque
déjà enregistrés, l'écart entre les deux, et le détail de chaque côté non encore pointé.

**Écran** (`/finances/rapprochement/`, menu « Rapprochement bancaire ») : les trois totaux
(solde relevé, solde comptable, écart — en rouge si non nul), formulaire de saisie d'une ligne,
lignes non pointées avec leurs suggestions et un bouton « Associer » par suggestion, mouvements
Banque non pointés, et la liste complète des lignes de la période avec un bouton « Dépointer » en
cas d'erreur.

**Vérifié manuellement** (navigateur, `demo_finances`) : avec un règlement Cimaf de 916 000 FCFA
et un apport de 1 500 000 FCFA déjà en trésorerie, écart initial de -2 416 000 FCFA (aucune ligne
de relevé saisie) ; saisie d'une ligne « Virement Cimaf » de 916 000 FCFA → suggestion automatique
du règlement correspondant, écart ramené à -1 500 000 FCFA ; « Associer » → ligne pointée, sortie
des listes « non pointées » des deux côtés ; « Dépointer » → pointage annulé, suggestion réapparaît,
écart revient à -1 500 000 FCFA.

**Implémentation** : `finance.models.LigneReleve`, `finance.services.saisir_ligne_releve` /
`suggestions_pointage` / `pointer_ligne_releve` / `depointer_ligne_releve` /
`rapprochement_bancaire`, `finance.forms.LigneReleveForm` / `PeriodeRapprochementForm` /
`PointerLigneReleveForm`, `finance.views.RapprochementBancaireView` / `LigneReleveCreateView` /
`LigneRelevePointerView` / `LigneReleveDepointerView`,
`finance/templates/finance/rapprochement.html`.

---

Les 7 lots sont désormais fusionnés : l'ERP est complet pour un usage autonome de comptable, à
l'exception volontaire du contrôle Finances/Direction sur les écritures manuelles (séparation des
tâches, confirmée comme devant rester en place dès l'ouverture de cet avenant).
```

#### `avenant-comptabilite-syscohada.md`

*356 lignes* — Avenant — Comptabilité en partie double (SYSCOHADA révisé)

```markdown
# Avenant — Comptabilité en partie double (SYSCOHADA révisé)

Complète cahier-des-charges.md : la seule exigence déjà écrite sur ce sujet est « Une facture
émise génère la créance client et l'écriture comptable équilibrée » (cahier-des-charges.md:340).
Tout le reste (plan comptable, journaux, grand livre, bilan, compte de résultat, exercice
comptable et clôture) est un chantier neuf, demandé par l'entreprise : la comptabilité légale est
aujourd'hui tenue par un cabinet externe, mais l'entreprise compte l'internaliser dans quelques
mois — l'ERP doit devenir la source de vérité comptable, pas un simple export.

Référentiel retenu : **SYSCOHADA révisé, système normal** (pas le système minimal de trésorerie :
`billing.Facture` gère déjà des créances clients en droits constatés, incompatible avec l'esprit
du SMT ; un bilan et un compte de résultat au sens SYSCOHADA sont explicitement demandés).

Comme les règles R1-R8 de `avenant-separation-des-taches.md`, chaque phase est livrée par lot
indépendant, testée (≥ 70 % sur les services), documentée, fusionnée séparément.

| Phase | Contenu | Statut |
|---|---|---|
| P1 | Fondations : plan comptable, moteur d'écritures, écriture de facture validée | ✅ Fusionnée |
| P2 | Encaissements (règlements clients) | ✅ Fusionnée |
| P3 | Dépenses automatiques du parc auto/missions (carburant, pièces, main-d'œuvre, frais de mission, ordre de décaissement) | ✅ Fusionnée |
| P4 | Saisie manuelle (mouvements de trésorerie, opérations diverses) — brouillon → validation DIRECTION | ✅ Fusionnée |
| P5 | Exercice comptable et clôture (DIRECTION, contrôle strict) | ✅ Fusionnée |
| P6 | Rapports : grand livre, balance, bilan, compte de résultat | **✅ Ce lot** — voir ci-dessous |

## P1 — Fondations : plan comptable, moteur d'écritures, écriture de facture

**Position dans le graphe de dépendances** (architecture.md) : nouvelle app `accounting`, dépend
de `billing` (lit `Facture`, `CompteTresorerie`) ; aucune autre app ne dépend d'`accounting` — les
rapports de la P6 restent des écrans internes à l'app, aucune intégration au `dashboard`.

**Modèles** (`apps/accounting/models.py`) :
- `Compte` : plan comptable (numéro, libellé, nature ACTIF/PASSIF/CHARGE/PRODUIT, actif). Table de
  référence, jamais soft-supprimée (comme `core.CompteurNumero`).
- `EcritureComptable` (`BaseModel`) : en-tête (numéro `JOURNAL-AAAA-XXXX` via
  `core.services.prochain_numero`, journal, date, libellé, pièce justificative, origine générique
  `(origine, origine_id)` pour l'idempotence, statut BROUILLON/VALIDEE). Une écriture `VALIDEE` ne
  se modifie ni ne se supprime : seule une contre-passation la corrige (non livrée en P1).
- `LigneEcriture` : ligne débit ou crédit, append-only (comme `inventory.MouvementStock`), montant
  strictement positif, rattachement générique optionnel à un tiers (`tiers_type`/`tiers_id`, ex.
  un client pour le compte 411).
- 5 journaux auxiliaires SYSCOHADA (`Journal`) : Achats (ACH), Ventes (VTE), Banque (BQ), Caisse
  (CAI), Opérations diverses (OD). Seul VTE est utilisé en P1.

**Moteur** (`apps/accounting/services.py::passer_ecriture`) : garantit lui-même l'équilibre
(jamais l'appelant) — au moins 2 lignes, montants strictement positifs, comptes existants et
actifs, total débit == total crédit (sinon `EcritureNonEquilibree`). Idempotent par
`(origine, origine_id)` : rejouer le même événement source renvoie l'écriture déjà comptabilisée.
`@transaction.atomic`, `statut=VALIDEE` directement (aucune écriture automatique ne passe par un
brouillon).

**Déclencheur** : `apps.billing.signals.facture_a_comptabiliser`, ajouté à côté de
`facture_validee` — émis en `send()` **brut** (pas `emettre()`/`send_robust`, contrairement aux
signaux existants de `billing`) : une écriture qui échoue à s'équilibrer annule la validation de
la facture plutôt que d'être silencieusement absente du grand livre. Souscrit dans
`apps/accounting/receivers.py`, qui appelle `services.comptabiliser_facture_validee(facture)` :
débite le client (411, montant TTC, rattaché au tiers), crédite les ventes (706, montant HT) et la
TVA collectée (4433, si le taux n'est pas nul).

**Permissions** (`apps/accounting/permissions.py`) : `CONSULTATION` (ADMIN, DIRECTION, FINANCES,
RH) — lecture seule, aucune saisie manuelle avant la P4. Cohérent avec le reste du projet : la RH
fait tout ce que fait la FINANCES, la DIRECTION a la même largeur que l'ADMIN.

**Audit** : `Compte`, `EcritureComptable`, `LigneEcriture` journalisés (module `COMPTABILITE`).

**Écrans** : aucun écran dédié en P1 (inspection via l'admin Django) — les écrans de grand
livre/balance/bilan viennent avec la P6, quand il y aura assez de lots comptabilisés pour qu'un
écran soit utile.

**Reprise de l'historique** : `python manage.py comptabiliser_historique_factures [--depuis
AAAA-MM-JJ] [--dry-run]`, même principe que
`finance.comptabiliser_historique_parc_auto` — comptabilise les factures déjà validées avant la
mise en service de ce lot.

**Plan comptable de départ** (`migrations/0002_plan_comptable_seed.py`) : liste de travail
(Clients 411, Ventes transport 706, TVA collectée 4433, Banque/Caisse/Mobile Money 521/571/5219,
Carburant 6051, Pièces 6058, Entretien 6241, Frais de mission 6281, Frais bancaires 631, Charges
diverses 658, Capital 101, Compte de l'exploitant 108, Résultat 120, Fournisseurs 401, TVA
déductible 4452) — **à valider par un expert-comptable avant mise en production** ; aucun cabinet
externe n'a été consulté à ce stade. Seuls 411, 706, 4433 et les 3 comptes de trésorerie sont
mobilisés par le code de la P1, le reste est seedé pour éviter une migration de données fragmentée
aux phases suivantes.

**Limites connues (assumées pour ce lot)** :
- Les pièces détachées restent comptabilisées en charge à l'achat (comportement déjà en place
  côté `finance.receivers`, cf. « Les pièces sont comptées à l'achat, pas à leur sortie de stock
  ») plutôt qu'en vraie entrée de stock (classe 3) suivie d'une sortie en charge — décision
  confirmée avec l'entreprise, pas une omission.
- Aucune récupération de TVA déductible réelle : `billing.Depense` n'a pas de champ HT/TVA
  séparé, les charges seront comptabilisées TTC (le compte 4452 reste à 0 tant que ce n'est pas
  traité).
- Les comptes Mobile Money des 3 opérateurs (Wave, Orange Money, MTN) restent fusionnés en un
  seul compte 5219, comme `billing.CompteTresorerie.MOBILE_MONEY` aujourd'hui.
- Classes 2 (immobilisations, camions) et 8 (hors activités ordinaires) hors périmètre : aucun
  événement de l'ERP ne produit aujourd'hui un achat d'immobilisation ou une charge exceptionnelle.
- Pas d'exercice comptable ni de clôture en P1 (arrive en P5) : aucune écriture n'est encore
  verrouillée par période.

**Implémentation** : `apps.accounting.services.passer_ecriture`,
`apps.accounting.services.comptabiliser_facture_validee`, `apps.accounting.receivers`,
signal `apps.billing.signals.facture_a_comptabiliser`. Détails : `apps/accounting/README.md`.

## P2 — Encaissements (règlements clients)

**Aucun nouveau modèle** : réutilise le moteur et le plan comptable de la P1 tels quels.

**Service** (`apps/accounting/services.py::comptabiliser_un_reglement`) : débite le compte de
trésorerie déduit du mode de paiement du règlement (`billing.models.COMPTE_DU_MODE` puis
`constants.COMPTE_TRESORERIE_VERS_COMPTE` — banque 521, caisse 571, mobile money 5219), crédite
le client (411, rattaché au tiers) — solde la créance. Journal déduit du même compte de
trésorerie (`constants.COMPTE_TRESORERIE_VERS_JOURNAL`) : Banque (BQ) ou Caisse (CAI) ; le mobile
money, dématérialisé, est rattaché à la Banque faute de journal auxiliaire dédié dans les 5
journaux SYSCOHADA standards.

**Déclencheur** : `apps.billing.signals.reglement_a_comptabiliser`, ajouté à côté de
`reglement_enregistre` — même principe que `facture_a_comptabiliser` (P1) : émis en `send()`
**brut**, un échec d'équilibrage annule l'enregistrement du règlement plutôt que de laisser un
encaissement non tracé.

**Permissions, audit, écrans** : inchangés (voir P1) — aucune nouvelle app-permission, aucun
nouvel écran.

**Reprise de l'historique** : `python manage.py comptabiliser_historique_reglements [--depuis
AAAA-MM-JJ] [--dry-run]`, même gabarit que `comptabiliser_historique_factures` (P1).

**Limite connue** : l'annulation d'un règlement (`billing.services.annuler_reglement`) n'émet
aucun signal et ne génère aucune contre-passation — l'écriture d'origine reste en l'état,
orpheline de son règlement annulé. La contre-passation d'une écriture arrive avec une phase
future, une fois le mécanisme de correction (par écriture inverse plutôt que par édition) posé
pour l'ensemble du chantier plutôt que traité au cas par cas.

**Implémentation** : `apps.accounting.services.comptabiliser_un_reglement`,
`apps.accounting.receivers.comptabiliser_un_reglement_recu`, signal
`apps.billing.signals.reglement_a_comptabiliser`. Détails : `apps/accounting/README.md`.

## P3 — Dépenses automatiques du parc auto/missions + reclassement de mode

**Aucun nouveau modèle** : réutilise le moteur et le plan comptable de la P1 tels quels. Les 5
origines (`OrigineDepense` : PLEIN, ACHAT_STOCK, MAIN_OEUVRE_OR, FRAIS_MISSION,
ORDRE_DECAISSEMENT) convergent toutes vers le même point d'entrée, déjà en place :
`billing.services.comptabiliser_depense_automatique` — un seul récepteur suffit donc, pas cinq.
Seules 4 catégories sont concernées (`billing.models.CATEGORIES_AUTOMATIQUES` : CARBURANT,
PIECES, MAINTENANCE, FRAIS_MISSION — vérifié que `DemandeDepense.categorie`, pour un ordre de
décaissement manuel, est lui-même restreint à `CARBURANT`/`PIECES`/`MAINTENANCE` par
`finance.demandes._exiger_categorie_automatique`, jamais `FRAIS_ADMIN`/`PEAGES`/`ENTRETIEN`/`AUTRE`) ;
ces 4 catégories manuelles arrivent avec la P4.

**Service** (`apps/accounting/services.py::comptabiliser_une_depense_automatique`) : débite la
charge selon la catégorie (`constants.CATEGORIE_DEPENSE_VERS_COMPTE` : Carburant 6051, Pièces
6058, Main-d'œuvre 6241, Frais de mission 6281), crédite la trésorerie selon le mode de paiement
(même mapping que la P2). Pour 4 des 5 origines (tout sauf l'ordre de décaissement), le mode est
**provisoire** : `comptabiliser_depense_automatique` par défaut sur Espèces (Caisse), corrigé
ensuite par la Finance via `billing.services.changer_mode_depense`. L'ordre de décaissement, lui,
connaît son mode réel dès l'exécution (`finance.demandes.executer_ordre` le passe directement) :
pas de provisoire pour cette origine.

**Reclassement de mode** (`apps/accounting/services.py::reclasser_mode_depense`) : quand la
Finance corrige le mode d'une dépense provisoire, une écriture de reclassement (journal
Opérations diverses) débite le nouveau compte de trésorerie et crédite l'ancien — jamais d'édition
de l'écriture d'origine (append-only). Aucune écriture si l'ancien et le nouveau mode partagent le
même compte de trésorerie (ex. virement → chèque, tous deux Banque).

**Déclencheurs** :
- `apps.billing.signals.depense_a_comptabiliser`, émis dans
  `comptabiliser_depense_automatique` **uniquement à la création réelle** de la `Depense` (pas
  quand le `get_or_create` retombe sur l'existante) — évite un double signal au rejeu d'une source.
- `apps.billing.signals.depense_mode_a_reclasser`, émis par `changer_mode_depense` (désormais
  `@transaction.atomic`, ne l'était pas avant ce lot) **uniquement si le mode change vraiment**.

Les deux en `send()` **brut** : un échec d'équilibrage annule l'opération d'origine (la
comptabilisation de la dépense, ou sa correction de mode).

**Permissions, audit, écrans** : inchangés (voir P1).

**Reprise de l'historique** : `python manage.py comptabiliser_historique_depenses [--depuis
AAAA-MM-JJ] [--dry-run]`, même gabarit que les commandes des P1/P2 — ne reprend que les dépenses
automatiques (`Depense.est_automatique`), pas la saisie manuelle (P4).

**Limite connue** : le reclassement de mode n'est pas idempotent (pas d'`origine`/`origine_id` sur
son écriture) — une correction rejouée deux fois (double clic, retry réseau) créerait deux
reclassements. Accepté pour cette phase : c'est une action manuelle rare de la Finance, pas un
événement automatique rejouable par construction comme les 3 autres signaux.

**Implémentation** : `apps.accounting.services.comptabiliser_une_depense_automatique`,
`apps.accounting.services.reclasser_mode_depense`, `apps.accounting.receivers`, signaux
`apps.billing.signals.depense_a_comptabiliser` et `depense_mode_a_reclasser`. Détails :
`apps/accounting/README.md`.

## P4 — Saisie manuelle (mouvements de trésorerie, opérations diverses)

Deux volets tranchés avec l'utilisateur avant implémentation (aucune décision unilatérale sur une
règle métier ambiguë) :

**1. `finance.MouvementManuel` gagne un champ structuré.** Contrairement aux événements des P1-P3,
un mouvement manuel (solde d'ouverture, apport, retrait, frais bancaires…) n'avait qu'un libellé
libre : impossible d'en déduire automatiquement le compte de contrepartie. Nouveau champ
`nature` (`finance.models.NatureMouvement` : SOLDE_OUVERTURE, APPORT, RETRAIT, FRAIS_BANCAIRE,
AUTRE — migration `finance/migrations/0003_mouvementmanuel_nature.py`, défaut `AUTRE` pour les
lignes déjà existantes). Mapping vers le plan comptable
(`accounting.constants.NATURE_MOUVEMENT_VERS_COMPTE`) : SOLDE_OUVERTURE/APPORT → 101000 Capital,
RETRAIT → 108000 Compte de l'exploitant, FRAIS_BANCAIRE → 631000, AUTRE → 658000.

**Service** (`apps/accounting/services.py::comptabiliser_un_mouvement_manuel`) : une entrée débite
la trésorerie et crédite la contrepartie ; une sortie fait l'inverse. Déclencheur :
`apps.finance.signals.mouvement_a_comptabiliser` (nouveau, `send()` brut), émis par
`finance.services.enregistrer_mouvement`. **Ce signal vit dans `finance`, pas `billing`** :
`MouvementManuel` est un modèle `finance`, et le graphe de dépendances gagne l'arête `FIN → ACCT`
(`architecture.md`) pour que `accounting` puisse lire `finance.models.NatureMouvement`.

**Limite connue** (même principe que l'annulation d'un règlement, P2) : l'annulation d'un
mouvement (`annuler_mouvement`) n'émet aucun signal, aucune contre-passation.

**Limite de périmètre, résolue depuis** : les dépenses manuelles de `billing.Depense` (catégories
PEAGES, ENTRETIEN, FRAIS_ADMIN, AUTRE) sont restées hors périmètre jusqu'à ce lot — voir
`avenant-comptabilite-autonomie.md` § Lot C, qui les comptabilise désormais au même titre que les
dépenses automatiques.

**2. Écran de saisie manuelle d'opérations diverses (journal OD).** Premier écran web de l'app
`accounting` — sans lui, la saisie manuelle serait inutilisable en pratique. Cycle de vie calqué
sur celui de `Facture` : `BROUILLON` (numéro vide, lignes ajoutées/retirées librement) →
`VALIDEE` (numéro attribué, verrouillée) — jamais de brouillon abandonné qui laisse un trou de
numérotation.

**Modèles** : aucun changement de schéma dans `accounting` — seul le comportement de
`EcritureComptable.delete()` et `LigneEcriture.delete()` est assoupli (suppression permise tant
que l'écriture est encore `BROUILLON`, verrouillée dès `VALIDEE`, comme documenté en P1).

**Services** (`apps/accounting/services.py`) :
- `creer_ecriture_manuelle(acteur, *, date_ecriture, libelle)` → `BROUILLON`, journal OD, pas de
  numéro.
- `ajouter_ligne_manuelle(ecriture, acteur, *, compte, sens, montant, libelle="")` /
  `supprimer_ligne_manuelle(ligne, acteur)` — uniquement sur un brouillon.
- `abandonner_ecriture_manuelle(ecriture, acteur)` — soft delete, uniquement sur un brouillon (pas
  de contre-passation nécessaire, aucun numéro n'a encore été attribué).
- `valider_ecriture_manuelle(ecriture, acteur)` — vérifie l'équilibre (au moins 2 lignes, débit ==
  crédit, la même règle que `passer_ecriture`), attribue le numéro, verrouille. **Contrôle
  strict** (`acteur.role`, jamais `role_effectif`) : réservé à la DIRECTION, comme
  `Facture.valider` — ni l'ADMIN ni un superutilisateur ne valident à sa place.

**Permissions** (`apps/accounting/permissions.py`) : `SAISIE_OD` (ADMIN, DIRECTION, FINANCES, RH —
créer, ajouter/retirer une ligne, abandonner) ; `VALIDATION_OD` (DIRECTION seule, strict).

**Écrans** (`apps/accounting/views.py`, `urls.py`, `templates/accounting/`, montés sous
`/comptabilite/`) : liste des écritures OD, formulaire de création (date + libellé), fiche
(lignes, totaux débit/crédit, indicateur d'équilibre, formulaire d'ajout de ligne, bouton
Valider réservé à la DIRECTION sur une écriture équilibrée, bouton Abandonner). Menu :
« Opérations diverses », rôles `CONSULTATION`.

**Vérifié manuellement** (navigateur, `demo_finances`) : création d'un brouillon, ajout de deux
lignes, calcul des totaux et détection d'équilibre en direct, conformes à ce que testent les
tests automatisés.

**Implémentation** : `apps.accounting.services.creer_ecriture_manuelle` /
`ajouter_ligne_manuelle` / `supprimer_ligne_manuelle` / `valider_ecriture_manuelle` /
`abandonner_ecriture_manuelle` / `comptabiliser_un_mouvement_manuel`, `apps.accounting.views`,
`apps.accounting.permissions.SAISIE_OD` / `VALIDATION_OD`, signal
`apps.finance.signals.mouvement_a_comptabiliser`, migration
`apps/finance/migrations/0003_mouvementmanuel_nature.py`. Détails : `apps/accounting/README.md`.

## P5 — Exercice comptable et clôture

**Modèle** (`apps/accounting/models.py`) : `ExerciceComptable` (`BaseModel`) — `annee` (unique),
`date_debut`/`date_fin` (année civile par défaut : le cahier des charges ne précise pas de date de
clôture fiscale propre à l'entreprise, hypothèse à confirmer avec l'expert-comptable), `statut`
(`OUVERT`/`CLOTURE`), `cloture_par`, `date_cloture`. Auto-créé `OUVERT` au passage de la première
écriture de son année (`services.exercice_pour`, même principe que
`core.services.prochain_numero` : aucun geste explicite n'est requis pour « ouvrir » une nouvelle
année). Jamais supprimé, jamais rouvert une fois clôturé.

**Verrouillage** (`services._exiger_exercice_ouvert`) : appelé par `passer_ecriture` (écritures
automatiques), `creer_ecriture_manuelle` et `valider_ecriture_manuelle` (saisie manuelle, cette
dernière en seconde ligne de défense contre une clôture concurrente — en pratique la clôture est
déjà bloquée tant qu'un brouillon existe dans la période, voir ci-dessous). Toute date tombant
dans un exercice `CLOTURE` lève `ExerciceCloture` : l'opération d'origine est annulée, comme pour
un déséquilibre.

**Service** (`apps/accounting/services.py::cloturer_exercice`) : refusé si l'exercice est déjà
clôturé, ou s'il reste des écritures manuelles en `BROUILLON` datées dans sa période (à valider ou
abandonner d'abord — jamais clôturer une année à l'insu d'une saisie en attente). Contrôle
**strict** (`acteur.role`) : réservé à la DIRECTION, comme `Facture.valider` — jamais l'ADMIN ni
un superutilisateur à sa place.

**Permissions** (`apps/accounting/permissions.py`) : `CLOTURE_EXERCICE` (DIRECTION seule, strict).
Consultation de la liste : `CONSULTATION` (inchangé).

**Écran** (`/comptabilite/exercices/`) : liste des exercices (année, période, statut, clôturé par
qui et quand), bouton « Clôturer » visible seulement à la DIRECTION sur un exercice `OUVERT`.
Vérifié manuellement dans le navigateur (`demo_finances` : la liste s'affiche, le bouton
« Clôturer » n'apparaît pas pour ce rôle — conforme à ce que testent les tests automatisés).

**Limite connue** : une fois clôturé, un exercice ne se rouvre jamais — une correction après
clôture attendra la phase de contre-passation générale (déjà signalée comme limite connue depuis
la P1), pas un mécanisme de réouverture dédié.

**Implémentation** : `apps.accounting.models.ExerciceComptable`,
`apps.accounting.services.exercice_pour` / `cloturer_exercice`,
`apps.accounting.permissions.CLOTURE_EXERCICE`, `apps.accounting.views.ExerciceListView` /
`ExerciceCloturerView`. Détails : `apps/accounting/README.md`.

## P6 — Rapports : grand livre, balance, bilan, compte de résultat

Dernier lot de la feuille de route : aucun nouveau modèle, aucun nouveau signal — uniquement de la
lecture sur les écritures déjà comptabilisées par les P1-P5.

**Services** (`apps/accounting/services.py`) :
- `grand_livre_avec_solde(compte, *, debut=None, fin=None)` : lignes du compte triées par date,
  chacune enrichie d'un solde cumulé (débit − crédit, cumulé ligne après ligne dans l'ordre
  chronologique) — la lecture brute non enrichie (`grand_livre`, P1) reste disponible pour les
  usages internes/tests qui n'ont pas besoin du solde.
- `balance(*, debut=None, fin=None)` : agrège tous les comptes mouvementés sur la période (total
  débit, total crédit, solde débiteur ou créditeur selon lequel des deux totaux l'emporte), via
  `_agreger_par_compte`.
- `compte_de_resultat(exercice)` : produits et charges **strictement dans `[date_debut, date_fin]`
  de l'exercice** — les comptes de charge/produit sont par nature des compteurs de période, remis
  à zéro à chaque exercice.
- `bilan(exercice)` : actif et passif **cumulés depuis l'origine jusqu'à `date_fin`**, sans borne de
  date basse — contrairement au compte de résultat, les comptes de bilan (trésorerie, créances,
  capital…) portent un solde qui survit d'un exercice à l'autre.

**Limite connue (documentée dans l'écran du bilan lui-même)** : le résultat net de l'exercice est
**calculé à la volée** par `compte_de_resultat` et simplement ajouté au passif du bilan
(`total_passif_avec_resultat`) pour l'équilibrer à l'affichage — il n'existe **aucune écriture de
clôture** qui transfère réellement ce résultat dans le compte 120000 "Résultat de l'exercice" au
moment de `cloturer_exercice` (P5). Une clôture comptable complète (contre-passation des comptes de
classe 6/7 vers le 120000) est un chantier à part, non demandé pour ce lot — le bilan reste donc une
photo cohérente mais pas une écriture posée dans le grand livre.

**Permissions** : inchangées, `CONSULTATION` (voir P1) — ces 4 écrans sont uniquement de la
lecture, aucune saisie.

**Écrans** (`apps/accounting/views.py`, `forms.py`, `templates/accounting/`, montés sous
`/comptabilite/`) :
- `/comptabilite/grand-livre/` : formulaire compte (obligatoire) + période (facultative) ;
  n'affiche de tableau qu'une fois un compte choisi.
- `/comptabilite/balance/` : formulaire période (facultative) ; tableau de tous les comptes
  mouvementés avec leurs totaux et soldes, plus une ligne de total général.
- `/comptabilite/bilan/` et `/comptabilite/compte-de-resultat/` : sélecteur d'exercice (le plus
  récent par défaut, `?exercice=AAAA` pour changer), partagé par les deux écrans via
  `_RapportExerciceView`.
- Menu : « Rapports comptables » pointe vers la balance ; les 3 autres rapports se rejoignent
  depuis le même sous-menu (`_nav_rapports.html`).

**Vérifié manuellement** (navigateur, `demo_finances`) : les 4 écrans affichent des montants
cohérents entre eux sur les mêmes données (le résultat net du compte de résultat correspond
exactement à celui ajouté au passif du bilan), le filtre par compte du grand livre calcule le bon
solde cumulé, la balance totalise correctement débit/crédit.

**Implémentation** : `apps.accounting.services.grand_livre_avec_solde` / `balance` /
`compte_de_resultat` / `bilan`, `apps.accounting.forms.PeriodeForm` / `GrandLivreForm`,
`apps.accounting.views.GrandLivreView` / `BalanceView` / `BilanView` / `CompteDeResultatView`.
Détails : `apps/accounting/README.md`.

**Ceci clôt la feuille de route des 6 phases.** Les limites connues documentées phase par phase
restent ouvertes (contre-passation générale, TVA déductible réelle, dépenses manuelles hors
périmètre, clôture comptable posée dans le grand livre) : à traiter dans un futur avenant si
l'entreprise en confirme le besoin une fois la comptabilité internalisée.
```

#### `avenant-separation-des-taches.md`

*332 lignes* — Avenant — règles de gestion basées sur la séparation des tâches

````markdown
# Avenant — règles de gestion basées sur la séparation des tâches

Complète cahier-des-charges.md : celui qui demande une dépense ou fixe un prix n'est jamais
celui qui la valide. Chaque règle (R1 à R7) est livrée par lot indépendant, testée (≥ 70 % sur
les services), documentée dans le README de son app, puis fusionnée séparément.

| Règle | Contenu | Statut |
|---|---|---|
| R1 | Validation des prix et devis | Fusionnée dans R5 (seuil DIRECTION à 500 000 FCFA TTC) |
| R2 | Dépenses du parc auto (pré-approbation + enveloppe) | ✅ Fusionnée |
| R3 | Modification d'une mission | ✅ Fusionnée |
| R4 | Prévision de trésorerie des missions | ✅ Fusionnée |
| R5 | Facture proforma (devis) | ✅ Fusionnée |
| R6 | Mission créée depuis une proforma acceptée | ✅ Fusionnée |
| R7 | Congés : 26 jours ouvrés + report | ✅ Fusionnée |
| R8 | Retours de réunion : largeur DIRECTION, RH = FINANCES, affectation Parc Auto, copilote | **✅ Ce lot** — voir ci-dessous |

Les 7 règles historiques sont fusionnées ; R8 (retours de réunion, ci-dessous) les complète.

## R2 — Dépenses du parc auto pré-approuvées

**Séparation des tâches.** Le **Parc Auto** demande, la **DIRECTION** valide (jamais l'ADMIN à sa
place — contrôle strict, comme pour la validation d'une facture), la **FINANCES** exécute le
paiement. Deux circuits distincts, réconciliés avec le mécanisme déjà livré (une session plus tôt)
qui comptabilise automatiquement un plein, un achat de pièces ou la main-d'œuvre d'un OR clôturé,
sans aucune approbation préalable :

1. **Manuelle** : pour un achat ou une réparation non routinière (pièce commandée à un fournisseur
   externe, réparation chez un prestataire externe), le Parc Auto soumet une `DemandeDepense`
   *avant* tout engagement.
2. **Dépassement d'enveloppe** : pour le flux automatique déjà en place (carburant, pièces,
   main-d'œuvre), la DIRECTION peut fixer une `EnveloppeDepense` — un plafond mensuel par
   catégorie, globalement ou par camion. Tant qu'on reste dans l'enveloppe, **rien ne change** :
   c'est aussi le comportement par défaut, sans enveloppe définie (illimité, comme avant R2). La
   dépense qui fait franchir le plafond reste comptabilisée (l'argent est déjà sorti — un plein ne
   se refuse pas après coup) mais ouvre une demande a posteriori qui bloque la dépense automatique
   *suivante* de cette catégorie tant que la DIRECTION ne l'a pas décidée. Volontairement plus
   restreint que `billing.CATEGORIES_AUTOMATIQUES` (qui inclut aussi `FRAIS_MISSION`, R4) : une
   constante dédiée `finance.demandes.CATEGORIES_PARC_AUTO` scope l'enveloppe aux 3 catégories
   d'origine — un frais de mission a déjà sa propre double validation, il ne passe pas en plus par
   une enveloppe.

**Modèles** (`apps/finance/models.py`, cohérent avec `MouvementManuel` déjà là et
`finance/receivers.py` qui dépend déjà de `garage`/`inventory`/`fuel` — le graphe de dépendance des
apps, architecture.md:95-163, place `finance` sous `billing`, seul endroit qui peut connaître les
deux à la fois) :
- `EnveloppeDepense` : `categorie`, `vehicule` (vide = globale, sinon prioritaire sur la globale),
  `annee`/`mois`, `montant_plafond`, `valide_par` (DIRECTION). Une seule par (catégorie, camion, mois).
- `DemandeDepense` (`DEM-AAAA-XXXX`) : `categorie`, `vehicule`, `origine` (`MANUELLE` /
  `DEPASSEMENT_ENVELOPPE`), `montant_estime`, `motif`, `fournisseur`, `piece_jointe` (`FileField`),
  `statut` (`SOUMISE` → `VALIDEE` / `REFUSEE`), `demandeur`, `valide_par`, `date_decision`,
  `motif_refus`.
- `OrdreDecaissement` (`ODC-AAAA-XXXX`, uniquement pour l'origine `MANUELLE` — un dépassement
  d'enveloppe n'en génère pas, la dépense existe déjà) : `demande` (1-1), `montant_valide`, `statut`
  (`A_EXECUTER` → `EXECUTE`, ou `EN_ATTENTE_REVALIDATION` en cas de dépassement), `mode_paiement`,
  `justificatif` (`FileField`), `montant_reel`, `execute_par`, `depense` (la `billing.Depense`
  résultante, origine `ORDRE_DECAISSEMENT`).
- `billing.Depense` gagne un champ `vehicule` (facultatif) : sert au suivi par enveloppe (un plein
  ou une main-d'œuvre d'OR est déjà lié à un camion ; un achat de pièces reste sans camion, comme
  aujourd'hui — un achat de stock n'est pas encore affecté à un véhicule précis).

**Machine à états** :
- Manuelle : `soumettre_demande` (Parc Auto) → `SOUMISE` → `valider_demande` (DIRECTION, génère
  l'`OrdreDecaissement`) ou `refuser_demande` (motif obligatoire) → `executer_ordre` (FINANCES :
  mode, montant réel, justificatif) → `EXECUTE`, dépense créée.
- Dépassement d'enveloppe : ouverte automatiquement par
  `finance.demandes.comptabiliser_avec_controle_enveloppe` (appelée par `finance.receivers` à la
  place de `billing.comptabiliser_depense_automatique`) → `SOUMISE` → `valider_demande` ou
  `refuser_demande` — les deux débloquent le mécanisme automatique (le refus n'est qu'un constat de
  désaccord, il ne fige pas la flotte) ; aucun ordre généré.
- **Dépassement de plus de 10 %** à l'exécution (manuelle) : bloqué, l'ordre passe en
  `EN_ATTENTE_REVALIDATION` — un état qui doit **survivre** à l'erreur renvoyée à l'écran
  (`executer_ordre` n'a donc pas de `@transaction.atomic` sur toute sa longueur, seulement sur le
  bloc qui écrit cet état ; sans cette précaution, l'erreur lève une exception qui annule aussi la
  mise en attente qu'on veut pourtant garder — repéré par un test qui vérifiait l'état après coup).
  La DIRECTION revalide (`revalider_ordre`, nouveau montant) avant que la Finance ne retente.

**Permissions** (`finance.permissions`) : `DEMANDE_SAISIE` (ADMIN, PARCAUTO) ; `DEMANDE_VALIDATION`
(DIRECTION seule, strict) ; `ORDRE_EXECUTION` (FINANCES seule, strict) ; `ENVELOPPE_VALIDATION`
(DIRECTION seule, strict) ; `DEMANDE_CONSULTATION` (ADMIN, DIRECTION, PARCAUTO, FINANCES).

**Notifications** (catégorie `DEMANDE_DEPENSE`) : soumission (manuelle ou dépassement) → DIRECTION ;
décision → le demandeur (ou le Parc Auto pour un dépassement, sans demandeur nommé) ; ordre à
exécuter → FINANCES ; dépassement de 10 % → DIRECTION.

**Audit** : les trois modèles sont journalisés (module `FINANCES`).

**Écrans** : `/finances/demandes/` (liste + « Nouvelle demande » pour le Parc Auto), fiche par
demande (décision, exécution, revalidation selon le rôle et l'état), `/finances/enveloppes/`
(DIRECTION, liste + formulaire).

## R3 — Modification d'une mission

**Ajoute à** cahier-des-charges.md Module 5 (Missions & Trajets), après le cycle de vie
(cahier-des-charges.md:132-134).

- Une mission peut être modifiée (lieux, marchandise, poids, prix convenu, date de départ prévue)
  tant qu'elle n'a pas dépassé le statut **« Colis récupéré »**.
- Modification réservée à **DIRECTION et ADMIN** (plus restreint que la création, ouverte aussi au
  chargé clientèle).
- Changer le camion ou le chauffeur revérifie leur disponibilité (mêmes contrôles qu'à
  l'affectation initiale) — possible uniquement sur une mission déjà **Affectée**, avant le départ.
- Changer un lieu de chargement ou de livraison régénère les deux codes secrets (expéditeur,
  destinataire) : l'ancien code, et son QR, ne servent plus.
- Le client n'est pas modifiable.
- Chaque modification est tracée dans le journal d'audit (ancienne/nouvelle valeur), au même titre
  que le reste du cycle de vie de la mission.

**Implémentation** : `apps.missions.services.modifier_mission`, `permissions.MODIFICATION`,
écran `/missions/<id>/modifier/`. Détails : `apps/missions/README.md` § Modification.

**Limite connue** : une mission créée depuis un devis accepté (R6) reste modifiable comme une
autre — son prix n'est pas verrouillé du fait d'avoir été accepté par le client sur le devis.

## R4 — Prévision de trésorerie des missions

**Séparation des tâches.** Celui qui déclare ou planifie un frais n'est jamais celui qui le valide :
le **Parc Auto** planifie une avance de route ou une dépense prévue, la **Finance** seule la confirme ;
le **chauffeur** déclare un imprévu (panne, incident) depuis l'espace mobile, le **Parc Auto** le valide
en premier, la **Finance** en second (double validation, jamais en une fois ni par l'auteur).

**Modèle** `missions.FraisMission` (`BaseModel`) :
- `mission` (FK, obligatoire), `type_frais` (`AVANCE_ROUTE` / `DEPENSE_PREVUE` / `IMPREVU` /
  `ENCAISSEMENT`), `montant`, `description`, `justificatif` (`FileField` — obligatoire pour un
  imprévu, stocké sur `MEDIA_ROOT`) ;
- `statut` (`PREVU` → `CONFIRME` / `REJETE`), `motif_rejet` ;
- `chauffeur` (rempli pour un imprévu déclaré depuis le mobile), `saisi_par` (le Parc Auto qui a
  planifié une avance/dépense prévue) ;
- `valide_parcauto_par`/`date_validation_parcauto`, `valide_finances_par`/`date_validation_finances`.

**État et validation** (`missions.terrain`) :
- **Avance de route** / **dépense prévue** : `planifier_frais` (Parc Auto) → `PREVU` →
  `valider_finances` (Finance seule) → `CONFIRME`.
- **Imprévu** : `declarer_imprevu` (chauffeur, preuve obligatoire) → `PREVU` → `valider_parcauto`
  (Parc Auto, première validation, reste `PREVU`) → `valider_finances` (Finance, refuse tant que le
  Parc Auto n'est pas passé) → `CONFIRME`.
- **Encaissement** : `creer_encaissement`, créé directement `CONFIRME` — jamais de validation, jamais
  saisi à la main (reflet automatique d'un règlement, voir plus bas).
- `rejeter` : le Parc Auto tant qu'un imprévu attend encore sa validation, la Finance dans tous les
  autres cas (motif obligatoire).
- Contrôle **strict** (`acteur.role`, jamais `role_effectif`) : ni l'ADMIN ni un superutilisateur ne
  valident à la place du Parc Auto ou de la Finance — même logique que la validation d'une facture.

**Seule une ligne `CONFIRME` représente un mouvement de trésorerie réel.** `missions` et `billing`
s'ignorent l'un l'autre (graphe de dépendance, architecture.md:95-163 : `missions` est au-dessus de
`billing`/`finance`, il ne doit rien en importer) — c'est `finance.receivers`, seule app en dessous des
deux, qui relie :
- `missions.signals.frais_mission_confirme` (avance/dépense prévue/imprévu confirmé, `send` non
  protégé comme `garage.or_cloture` : si la dépense ne peut pas s'écrire, la confirmation est annulée)
  → `billing.comptabiliser_depense_automatique` (catégorie `FRAIS_MISSION`, liée à la mission) ;
- `billing.signals.reglement_enregistre` (`send_robust` : un échec ici ne bloque jamais un règlement)
  → `missions.terrain.creer_encaissement` (aucune dépense ni règlement supplémentaire, seulement le
  reflet pour la vue « Frais de mission »).

**Déclencheur** : signal `mission_affectee` (émis par `affecter_mission`) → notifie la FINANCES
(mouvement de caisse probable). Notifications supplémentaires : imprévu déclaré → Parc Auto ;
imprévu validé par le Parc Auto → Finance ; ligne rejetée → son auteur (catégorie `FRAIS_MISSION`).

**Permissions** (`missions.permissions`) : `FRAIS_CONSULTATION` (ADMIN, DIRECTION, PARCAUTO, FINANCES —
écran séparé de la fiche mission, le chargé clientèle n'y a pas accès, comme il ne voit pas le prix
convenu côté chauffeur) ; `FRAIS_SAISIE_PREVISION` (ADMIN, PARCAUTO) ; `FRAIS_VALIDATION_PARCAUTO`
(PARCAUTO seul) ; `FRAIS_VALIDATION_FINANCES` (FINANCES seule).

**Écrans** : `/missions/frais/` (lignes en attente, toutes missions), `/missions/<id>/frais/`
(planification, validation, rejet), `/missions/<id>/frais/imprimer/` (rapport de mission : lignes et
totaux). Côté mobile (`/chauffeur/imprevu/` et `POST /api/v1/mobile/imprevus/`) : formulaire tactile
avec upload de preuve, mêmes règles que le signalement d'un incident (mission du chauffeur uniquement).

## R5 — Facture proforma (et R1 fusionnée)

**Séparation des tâches.** Le **chargé clientèle** fixe le trajet et le prix d'un devis ; il
n'est jamais celui qui le valide. La **FINANCES** valide toujours le prix ; la **DIRECTION**
valide en plus quand le montant TTC dépasse `SEUIL_VALIDATION_DIRECTION` (500 000 FCFA — c'est la
fusion de R1, qui demandait exactement cette règle pour « la validation des prix et devis »).

**Modèle** `apps.billing.models.Proforma` (`BaseModel`) :
- `numero` (`PRO-AAAA-XXXX`, attribué à la validation finale seulement — comme `Facture`, pour
  qu'un devis abandonné ou contesté ne laisse aucun trou de numérotation) ;
- `client`, `lieu_chargement`, `lieu_livraison`, `nature_marchandise`, `poids_t`,
  `date_depart_souhaitee` (indicatif) : les mêmes champs qu'une `Mission`, plutôt que des lignes
  comme `Facture` — R6 les recopie tels quels dans la mission créée ;
- `prix_convenu` (HT), `taux_tva`, `motif_exoneration`, `montant_ht`/`montant_tva`/`montant_ttc`
  (mêmes 3 niveaux de TVA et même arrondi au franc qu'une facture) ;
- `motif_contre_proposition`, `motif_refus_client` ;
- `date_envoi`, `date_validite` (envoi + 30 jours) ;
- `cree_par`, `valide_par_finances`/`date_validation_finances`,
  `valide_par_direction`/`date_validation_direction`.

Pas de modèle séparé pour l'historique des versions : la section « Historique » de la fiche lit
directement `audit_log` (`apps.audit.services.historique`), qui journalise déjà chaque
modification (auteur, date, champs changés) — un modèle dédié aurait dupliqué cette information.

**État** (`StatutProforma`) :

```
BROUILLON → SOUMISE ⇄ CONTRE_PROPOSEE
              │
              ├─ (TTC ≤ seuil) FINANCES valide ──────────────► VALIDEE
              └─ (TTC > seuil) FINANCES valide → EN_ATTENTE_DIRECTION → DIRECTION valide → VALIDEE

VALIDEE → ENVOYEE_CLIENT → ACCEPTEE / REFUSEE / EXPIREE (tâche quotidienne, 30 jours sans réponse)
ACCEPTEE → CONVERTIE (R6 : la mission est créée)
```

Le devis reste modifiable (trajet, marchandise, poids, prix, TVA) tant qu'il est `BROUILLON` ou
`CONTRE_PROPOSEE`. Une contre-proposition renvoie systématiquement vers le chargé clientèle
plutôt que vers un refus définitif : il ajuste puis resoumet (comme `Facture.refuser`, mais avec
un état dédié qui distingue explicitement « à revoir » de « brouillon jamais soumis »).

**Permissions** (`PROFORMA_*` dans `apps/billing/permissions.py`) :
- `PROFORMA_CONSULTATION` : ADMIN, DIRECTION, FINANCES, CHARGE_CLIENTELE ;
- `PROFORMA_SAISIE` (créer, modifier, abandonner, soumettre, envoyer au client, décision client) :
  ADMIN, CHARGE_CLIENTELE ;
- `PROFORMA_VALIDATION_FINANCES` : FINANCES seul (contrôle **strict** : un ADMIN ou un
  superutilisateur ne valide pas, comme pour une facture) ;
- `PROFORMA_VALIDATION_DIRECTION` : DIRECTION seule, même contrôle strict.

**Notifications** (`apps.notifications.receivers`, catégorie `PROFORMA`) : devis soumis → FINANCES ;
devis en attente (seuil dépassé) → DIRECTION ; devis validé, contre-proposé ou expiré → son
auteur. Tâche quotidienne `expirer_proformas` ajoutée à
`notifications.taches.executer_taches_quotidiennes` (compteur `proformas_expirees`).

**Audit** : `Proforma` est journalisé (module `FINANCES`, comme `Facture`) — chaque création,
contre-proposition, validation et changement de statut est tracée avec l'auteur et l'horodatage.

## R6 — Mission créée depuis une proforma acceptée

Une fois le devis `ACCEPTEE`, l'acteur qui pourrait créer une mission à la main (rôle
`missions.permissions.CREATION` : ADMIN, DIRECTION, CHARGE_CLIENTELE) déclenche
« Créer la mission » depuis la fiche du devis
(`POST /facturation/devis/<id>/creer-mission/`) :

- `billing.services.convertir_en_mission(proforma)` recopie tel quel le trajet, la marchandise, le
  poids et le **prix HT** du devis dans une nouvelle `Mission` (via `missions.services.creer_mission`,
  au statut `BROUILLON`, comme une mission créée à la main) — la facture recalculera la TVA plus
  tard, avec le taux du client en vigueur ce jour-là, jamais celui figé sur le devis ;
- le devis passe à `CONVERTIE` (même fonction) ;
- **1 devis = 1 mission** est garanti au niveau base par `Mission.proforma`
  (`OneToOneField(billing.Proforma, on_delete=PROTECT)`), pas seulement par le contrôle de
  statut : deux tentatives concurrentes ne peuvent pas produire deux missions.

Refusé (`TransitionFactureInterdite`) si le devis n'est pas `ACCEPTEE` — y compris s'il l'a déjà
été converti une première fois. Orchestré côté `billing` et non `missions` : le graphe de
dépendance des apps (architecture.md:95-163) interdit à `missions` (Exploitation) de dépendre de
`billing` (Finance) — l'inverse est permis, `billing` appelle donc `missions.services.creer_mission`
plutôt que l'inverse.

**Limite connue** : une mission créée ainsi reste modifiable comme n'importe quelle autre (R3) —
rien n'empêche aujourd'hui de changer son prix après coup, alors que le client a accepté un
montant précis sur le devis.

## R7 — Congés : 26 jours ouvrés, report du solde d'un congé en cours

**Remplace, dans cahier-des-charges.md Module 11** (cahier-des-charges.md:219-221) :

- **Droit annuel : 26 jours ouvrés** (au lieu de 12 jours ouvrables) — avantage social au-delà du
  minimum légal ivoirien (2,2 jours ouvrables/mois ≈ 26,4 jours ouvrables/an). Décision confirmée
  explicitement par l'entreprise après vérification du calcul (26 jours **ouvrés**, lundi-vendredi,
  donne davantage de repos calendaire que le minimum légal en jours **ouvrables**, samedi compris).
- **Décompte en jours ouvrés** : du lundi au vendredi, hors jours fériés légaux (`JourFerie`). Le
  samedi ne compte plus (avant : « ouvrables », tous les jours sauf dimanche).
- **Annulation par la RH inchangée** : un congé approuvé annulé continue de restituer les jours à
  l'employé (règle non modifiée — l'entreprise n'a pas confirmé ce changement-là lors de la
  clarification).
- **Nouveau : report du solde d'un congé en cours.** Un bouton « Reporter » apparaît sur la ligne
  du tableau des congés de l'employé **actuellement en congé** (statut « En cours »). Il indique le
  jour où il reprend réellement le travail (avant la fin initialement prévue) et un motif. **Sans
  validation de la RH, la demande n'a aucun effet** : le congé continue normalement. La RH est
  notifiée (bouton « Confirmer le report ») ; une fois validée : le congé est raccourci à la
  nouvelle date de reprise, les jours ouvrés non pris sont reversés au solde de l'année, et le
  document d'autorisation (PDF) reflète le report (motif, date, jours reversés) — automatiquement,
  puisqu'il est régénéré à la demande à chaque téléchargement plutôt que stocké une fois pour
  toutes. Une seule demande de report à la fois par congé.
- **Nouveau : PDF « Autorisation de congé ».** Téléchargeable dès qu'un congé est approuvé (N2) :
  numéro, employé, dates, jours décomptés, validateurs N1/N2, solde restant de l'année, et la
  section report si applicable. Même en-tête (logo, couleurs de la marque) que le PDF des codes de
  mission.

**Implémentation** : `apps.hr.models.ReportConge`, `apps.hr.services.demander_report` /
`approuver_report` / `refuser_report`, écran `/rh/conges/<id>/reporter/`, PDF
`/rh/conges/<id>/autorisation.pdf` (`apps.hr.documents`). Détails : `apps/hr/README.md`.

## R8 — Retours d'une réunion entreprise (largeur DIRECTION, RH = FINANCES, affectation Parc Auto, copilote)

Quatre remarques de la direction, traitées ensemble car elles touchent toutes aux permissions par
rôle :

1. **La DIRECTION peut faire toutes les tâches** — interprété comme : la DIRECTION gagne la même
   largeur que l'ADMIN pour les actions de **préparation/saisie** dans toute l'application, mais ne
   **remplace jamais** un rôle exclusivement chargé d'une validation ou d'une exécution stricte
   (ex. la FINANCES reste seule à exécuter un ordre de décaissement, le Parc Auto seul à donner la
   première validation d'un imprévu). Concrètement, `Role.DIRECTION` a été ajouté à chaque ensemble
   de **saisie/modification** (jamais aux ensembles `*_VALIDATION`/`*_EXECUTION` à rôle unique et
   contrôle strict) : `billing.SAISIE`/`PROFORMA_SAISIE`, `finance.DEMANDE_SAISIE`,
   `customers.MODIFICATION`, `hr.PERSONNEL_MODIFICATION`, `fuel.MODIFICATION`,
   `garage.MODIFICATION`, `inventory.MODIFICATION`, `missions.FRAIS_SAISIE_PREVISION`,
   `missions.CODES_TERRAIN` (déjà présente dans `drivers.MODIFICATION`/`fleet.MODIFICATION`).
2. **La RH doit pouvoir faire tout ce que fait la FINANCES** — lu littéralement et sans réserve
   (contrairement au point 1) : `Role.RH` a été ajouté partout où `Role.FINANCES` apparaît,
   **y compris** les ensembles stricts à rôle unique (`billing.CONSULTATION`/`SAISIE`/
   `PROFORMA_CONSULTATION`/`PROFORMA_VALIDATION_FINANCES`, `finance.DEMANDE_CONSULTATION`/
   `ORDRE_EXECUTION`) et les notifications adressées à la FINANCES
   (`notifications.receivers`/`taches` : chaque `utilisateurs_du_role(Role.FINANCES)` devient
   `utilisateurs_du_role(Role.FINANCES, Role.RH)`).
3. **C'est le Parc Auto qui affecte les missions**, une fois créées par le chargé clientèle —
   `Role.PARCAUTO` ajouté à `missions.AFFECTATION` (et nécessairement à `missions.CONSULTATION`,
   pour voir les missions à affecter). Point de vigilance : `VOIR_CODES` (codes secrets
   expéditeur/destinataire) était défini comme un simple alias de `CONSULTATION`
   (`VOIR_CODES = CONSULTATION`) — laissé tel quel, le Parc Auto aurait hérité de la visibilité des
   codes, qui n'a rien à voir avec l'affectation. Corrigé en **décorrélant** `VOIR_CODES` en un
   ensemble explicite et indépendant (`{ADMIN, DIRECTION, CHARGE_CLIENTELE}`), qui ne bouge plus
   avec `CONSULTATION`.
4. **Certains voyages exigent un copilote**, assistant du chauffeur pendant le trajet — nouvelle
   entité `drivers.Copilote`, fonction/fiche **distincte** du chauffeur (jamais un chauffeur
   principal), même mécanisme que `Chauffeur` : extension 1-1 de `hr.Personnel` (poste
   « Copilote »), auto-création par signal, mêmes statuts de disponibilité (`StatutChauffeur`,
   y compris la synchronisation avec les congés). Aucune règle automatique ne décide qu'une mission
   exige un copilote : **décision humaine du Parc Auto au moment de l'affectation**, sur le même
   écran que le camion et le chauffeur (`Mission.copilote`, facultatif). `affecter_mission` vérifie
   sa disponibilité comme pour le chauffeur ; `demarrer_mission`/`livrer_mission` le mettent
   « En mission » / le libèrent en parallèle.

**Implémentation** : `apps/drivers/models.py` (`Copilote`), `apps/drivers/services.py` (section
copilotes), `apps/drivers/signals.py` (auto-création + synchronisation congés), `apps/missions/`
(`models.Mission.copilote`, `services.py` affectation/démarrage/livraison, `forms.AffectationForm`,
templates). Permissions détaillées ci-dessus, réparties dans le `permissions.py` de chaque app
concernée. Pas d'écran dédié pour gérer les fiches copilote (contrairement au chauffeur) : géré via
l'admin Django pour l'instant.

**Limite connue** : `missions.services.modifier_mission` (R3) ne permet pas encore de changer le
copilote d'une mission déjà affectée (seuls camion et chauffeur sont réaffectables) — seule
l'affectation initiale propose ce choix.
````

#### `config/__init__.py`

*3 lignes*

```python
from .celery import app as celery_app

__all__ = ("celery_app",)
```

#### `config/celery.py`

*19 lignes* — Application Celery : tâches asynchrones (étape 7 lot 2, ADR-004 architecture.md:493-497).

```python
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
```

#### `docker-compose.yml`

*140 lignes*

```text
## Étape 7, lots 2 et 3 (architecture.md §6 « Vue déploiement ») — même fichier pour les deux :
##
## - `db`, `redis` (lot 2) : peuvent tourner seuls pour tester `python manage.py runserver` sur la
##   machine contre de vrais PostgreSQL/Redis (voir .env.example, valeurs `localhost`).
## - `web`, `celery_worker`, `celery_beat`, `nginx` (lot 3) : l'application complète, dans les mêmes
##   conteneurs qu'en production. Nginx est le seul point d'entrée public (port 80) ; `db` et
##   `redis` ne publient leur port que sur 127.0.0.1, pour un débogage local, jamais sur Internet.
##
##     docker compose up -d --build   # démarrer (construit l'image applicative la 1re fois)
##     docker compose logs -f web     # suivre les journaux d'un service
##     docker compose down            # arrêter (les données restent dans les volumes)
##     docker compose down -v         # arrêter et tout effacer (base, cache, statiques, media)
##
## Variables lues dans `.env` (voir .env.example) : SECRET_KEY, ALLOWED_HOSTS, DATABASE_URL (mettre
## `@db` comme hôte, pas `@localhost`, quand `web`/`celery_*` tournent aussi dans docker-compose ;
## `environment:` ci-dessous l'impose déjà, `.env` n'a donc besoin que du mot de passe), etc.

services:
  db:
    image: postgres:16
    restart: unless-stopped
    environment:
      POSTGRES_DB: erp_densource
      POSTGRES_USER: erp_densource
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-erp_densource}
    ports:
      - "127.0.0.1:5432:5432"
    volumes:
      - db_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U erp_densource"]
      interval: 5s
      timeout: 5s
      retries: 10

  redis:
    image: redis:7
    restart: unless-stopped
    ports:
      - "127.0.0.1:6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 10

  web:
    build: .
    restart: unless-stopped
    env_file: .env
    environment:
      DJANGO_SETTINGS_MODULE: config.settings.prod
      DATABASE_URL: postgres://erp_densource:${POSTGRES_PASSWORD:-erp_densource}@db:5432/erp_densource
      REDIS_URL: redis://redis:6379/0
    volumes:
      - static_data:/app/staticfiles
      - media_data:/app/media
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      # Un en-tête Host explicite : sans lui, Django rejette la requête (400) dès que ALLOWED_HOSTS
      # ne contient pas « localhost » (c'est le cas dès qu'un vrai domaine est configuré, en
      # production). ${ALLOWED_HOSTS%%,*} prend le premier domaine de la liste.
      test: ["CMD-SHELL", "curl -fsS -H \"Host: $${ALLOWED_HOSTS%%,*}\" http://localhost:8000/connexion/ || exit 1"]
      interval: 15s
      timeout: 5s
      retries: 10
      start_period: 20s

  # Suivi des missions en direct (WebSocket) : même image que `web`, mais servie par Daphne (ASGI).
  # Nginx lui envoie les connexions /ws/ ; les pages restent servies par Gunicorn. Les changements de
  # mission sont diffusés par `web` dans Redis (couche de messages) puis poussés d'ici aux navigateurs.
  realtime:
    build: .
    restart: unless-stopped
    env_file: .env
    environment:
      DJANGO_SETTINGS_MODULE: config.settings.prod
      DATABASE_URL: postgres://erp_densource:${POSTGRES_PASSWORD:-erp_densource}@db:5432/erp_densource
      REDIS_URL: redis://redis:6379/0
    command: ["daphne", "-b", "0.0.0.0", "-p", "8001", "config.asgi:application"]
    depends_on:
      web:
        condition: service_healthy

  celery_worker:
    build: .
    restart: unless-stopped
    env_file: .env
    environment:
      DJANGO_SETTINGS_MODULE: config.settings.prod
      DATABASE_URL: postgres://erp_densource:${POSTGRES_PASSWORD:-erp_densource}@db:5432/erp_densource
      REDIS_URL: redis://redis:6379/0
    command: ["celery", "-A", "config", "worker", "-l", "info"]
    depends_on:
      # Attend `web` en bonne santé, pas seulement démarré : ses migrations (ops/entrypoint.sh)
      # doivent être appliquées avant qu'un worker n'interroge la base.
      web:
        condition: service_healthy

  celery_beat:
    build: .
    restart: unless-stopped
    env_file: .env
    environment:
      DJANGO_SETTINGS_MODULE: config.settings.prod
      DATABASE_URL: postgres://erp_densource:${POSTGRES_PASSWORD:-erp_densource}@db:5432/erp_densource
      REDIS_URL: redis://redis:6379/0
    command: ["celery", "-A", "config", "beat", "-l", "info"]
    depends_on:
      web:
        condition: service_healthy

  nginx:
    image: nginx:1.27-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - static_data:/app/staticfiles:ro
      - media_data:/app/media:ro
      - certbot_www:/var/www/certbot
      - ./certs:/etc/nginx/certs:ro
    depends_on:
      web:
        condition: service_healthy

volumes:
  db_data:
  redis_data:
  static_data:
  media_data:
  certbot_www:
```

#### `nginx/nginx.conf`

*105 lignes*

```text
# Reverse proxy devant Gunicorn (étape 7 lot 3) — cahier-des-charges.md:249, architecture.md §6.
#
# Sert directement /static/ et /media/ (fichiers déjà sur disque, volumes partagés avec le
# conteneur `web`) : Gunicorn ne voit que les requêtes applicatives, comme prévu par la vue
# déploiement (Nginx -> Gunicorn workers).
#
# TLS : certificat Let's Encrypt pour densource.tech (GUIDE-DEPLOIEMENT.md « Activer HTTPS »),
# monté depuis ./certs sur l'hôte (docker-compose.yml, service nginx). Le port 80 ne sert plus que
# le défi HTTP-01 (renouvellement) et redirige tout le reste vers HTTPS.

worker_processes auto;

events {
    worker_connections 1024;
}

http {
    include       mime.types;
    default_type  application/octet-stream;
    sendfile      on;
    server_tokens off;  # ne pas annoncer la version de Nginx

    gzip on;
    gzip_types text/css application/javascript application/json image/svg+xml;
    gzip_min_length 1024;

    client_max_body_size 10m;

    upstream django {
        server web:8000;
    }

    # Mise à niveau HTTP -> WebSocket (suivi des missions en direct) : « upgrade » seulement si le client
    # la demande, sinon la connexion se ferme normalement.
    map $http_upgrade $connection_upgrade {
        default upgrade;
        ""      close;
    }

    server {
        listen 80;
        server_name densource.tech www.densource.tech;

        # Défi HTTP-01 de Let's Encrypt (certbot, mode webroot) — voir GUIDE-DEPLOIEMENT.md
        # « Activer HTTPS », renouvellement mensuel. Le dossier est vide et sans effet le reste du
        # temps.
        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }

        location / {
            return 301 https://$host$request_uri;
        }
    }

    server {
        listen 443 ssl;
        server_name densource.tech www.densource.tech;

        ssl_certificate     /etc/nginx/certs/live/densource.tech/fullchain.pem;
        ssl_certificate_key /etc/nginx/certs/live/densource.tech/privkey.pem;

        location /static/ {
            alias /app/staticfiles/;
            expires 30d;
            access_log off;
        }

        location /media/ {
            alias /app/media/;
            expires 7d;
            access_log off;
        }

        # WebSocket du suivi des missions en direct : conteneur `realtime` (Daphne). Adresse résolue à
        # chaque connexion par le résolveur de Docker : Nginx démarre même si ce conteneur est absent ou
        # en train de redémarrer (sans cela, « host not found in upstream » l'empêcherait de démarrer).
        # Les pings de Daphne (toutes les 20 s) maintiennent la connexion ouverte malgré le délai de lecture.
        location /ws/ {
            resolver 127.0.0.11 valid=10s;
            set $realtime realtime:8001;
            proxy_pass http://$realtime;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection $connection_upgrade;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 3600s;
            proxy_send_timeout 3600s;
        }

        location / {
            proxy_pass http://django;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            # TRUSTED_PROXY_COUNT=1 (.env) : Django ne lit que la dernière adresse de cette liste
            # (apps/core/middleware.get_client_ip), jamais une valeur écrite par le client lui-même.
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_redirect off;
        }
    }
}
```

#### `ops/entrypoint.sh`

*15 lignes*

```text
#!/bin/sh
# Point d'entrée du conteneur applicatif (étape 7 lot 3) : préparé avant de lancer la commande
# reçue en argument (Gunicorn par défaut ; `celery worker` ou `celery beat` dans docker-compose.yml,
# qui n'ont besoin ni de collectstatic ni de migrer deux fois).
set -eu

if [ "${1:-}" = "gunicorn" ]; then
    echo "entrypoint : collecte des fichiers statiques"
    python manage.py collectstatic --noinput

    echo "entrypoint : migrations"
    python manage.py migrate --noinput
fi

exec "$@"
```

#### `ops/gunicorn.conf.py`

*19 lignes* — Réglages Gunicorn (étape 7 lot 3) — cahier-des-charges.md:249 « Serveur : Gunicorn / WSGI ».

```python
"""Réglages Gunicorn (étape 7 lot 3) — cahier-des-charges.md:249 « Serveur : Gunicorn / WSGI ».

Logs sur la sortie standard : c'est `docker compose logs` (ou tout collecteur de logs de conteneurs)
qui les récupère, pas de fichier à gérer dans l'image.
"""

import multiprocessing
import os

bind = "0.0.0.0:8000"

# 2×CPU + 1 (repère standard Gunicorn), plafonné à 5 pour rester raisonnable sur un petit serveur ;
# réglable directement par variable d'environnement si le matériel réel demande autre chose.
workers = int(os.environ.get("GUNICORN_WORKERS", min(multiprocessing.cpu_count() * 2 + 1, 5)))
threads = int(os.environ.get("GUNICORN_THREADS", 2))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 30))

accesslog = "-"
errorlog = "-"
```

#### `ops/restauration.sh`

*22 lignes*

```text
#!/bin/bash
# Restaure une sauvegarde chiffrée (ops/sauvegarde.sh) dans une base — pour l'essai mensuel exigé par
# le cahier des charges (« sauvegardes chiffrées et testées ») autant que pour un vrai incident.
#
# Usage :
#   DATABASE_URL=postgres://... SAUVEGARDE_PASSPHRASE=... ops/restauration.sh fichier.dump.gpg
#
# ATTENTION : restaure dans la base de DATABASE_URL, en écrasant son contenu (--clean). Pour l'essai
# mensuel, pointez DATABASE_URL vers une base à part (jamais la base de production) — voir
# GUIDE-DEPLOIEMENT.md « Tester une restauration ».
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL doit être défini (la base à restaurer, jamais la production pour un essai)}"
: "${SAUVEGARDE_PASSPHRASE:?SAUVEGARDE_PASSPHRASE doit être défini (phrase de passe de chiffrement)}"

FICHIER="${1:?Usage : ops/restauration.sh fichier.dump.gpg}"

echo "Restauration de $FICHIER vers $(echo "$DATABASE_URL" | sed -E 's#//[^@]+@#//***@#')"
gpg --batch --yes --decrypt --passphrase "$SAUVEGARDE_PASSPHRASE" "$FICHIER" \
    | pg_restore --clean --if-exists --no-owner --dbname "$DATABASE_URL"

echo "OK : restauration terminée."
```

#### `ops/sauvegarde.sh`

*37 lignes*

```text
#!/bin/bash
# Sauvegarde chiffrée de la base (cahier-des-charges.md:282 « Sauvegardes chiffrées et testées »).
#
# `pg_dump` (format personnalisé, compressé) chiffré au repos avec GPG (symétrique : une phrase de
# passe partagée, pas de gestion de clés). Le fichier produit ne sert à rien sans elle — à conserver
# hors du serveur (cahier-des-charges.md:294 « offsite »), par exemple copiée chaque nuit vers un
# stockage distinct.
#
# Usage :
#   DATABASE_URL=postgres://... SAUVEGARDE_PASSPHRASE=... ops/sauvegarde.sh [dossier de destination]
#
# Dans docker-compose.yml, un cron du serveur hôte peut lancer, chaque nuit :
#   docker compose exec -T db sh -c 'pg_dump "$DATABASE_URL"' | gpg ... > sauvegardes/AAAA-MM-JJ.sql.gpg
# ou, plus simple, appeler ce script directement sur l'hôte s'il a `pg_dump` et `gpg` installés et
# peut joindre le port 5432 exposé par le service `db`.
set -euo pipefail
# pipefail : sans lui, un `pg_dump` qui échoue laisserait quand même passer un fichier chiffré
# (vide ou tronqué) comme si tout s'était bien passé, `gpg` réussissant sur une entrée vide.

: "${DATABASE_URL:?DATABASE_URL doit être défini (postgres://utilisateur:motdepasse@hôte:5432/base)}"
: "${SAUVEGARDE_PASSPHRASE:?SAUVEGARDE_PASSPHRASE doit être défini (phrase de passe de chiffrement)}"

DESTINATION="${1:-.}"
HORODATAGE=$(date -u +%Y-%m-%dT%H-%M-%SZ)
FICHIER="$DESTINATION/erp_densource_$HORODATAGE.dump.gpg"

mkdir -p "$DESTINATION"

echo "Sauvegarde de la base vers $FICHIER"
pg_dump --format=custom "$DATABASE_URL" \
    | gpg --batch --yes --symmetric --cipher-algo AES256 --passphrase "$SAUVEGARDE_PASSPHRASE" \
    > "$FICHIER"

echo "Empreinte SHA-256 (à noter pour vérifier l'intégrité avant restauration) :"
sha256sum "$FICHIER"

echo "OK : $(du -h "$FICHIER" | cut -f1)"
```

#### `static/js/suivi-missions.js`

*143 lignes*

```javascript
// Suivi des missions en direct : ouvre la WebSocket du serveur et rafraîchit l'écran dès qu'une mission
// change (par exemple quand le chauffeur saisit ou scanne un code depuis son téléphone).
//
// Aucun code n'est écrit dans les pages (CSP stricte) ; le gabarit déclare son intention :
//   <div data-suivi-missions data-ws-chemin="/ws/missions/suivi/" data-mission-id="12">
//       data-mission-id : ne réagit qu'aux changements de cette mission (fiche) ; absent : toute
//       mission (liste).
//   <div data-suivi-zone="nom">   zone remplacée par la même zone de la page rechargée
//   #suivi-voyant [data-etat=connecte|reconnexion|hors_ligne], #suivi-annonce (lecteurs d'écran),
//   #suivi-bandeau + #suivi-actualiser (changement arrivé pendant une saisie).
//
// Le message reçu ne contient que « quelle mission, quel statut » : les données, elles, sont relues par
// une requête ordinaire, avec les droits de l'utilisateur. Rien de secret ne transite par la WebSocket.
(function () {
  "use strict";

  var racine = document.querySelector("[data-suivi-missions]");
  if (!racine || !("WebSocket" in window)) {
    return;
  }

  var chemin = racine.getAttribute("data-ws-chemin");
  var missionId = racine.getAttribute("data-mission-id");
  var voyant = document.getElementById("suivi-voyant");
  var annonce = document.getElementById("suivi-annonce");
  var bandeau = document.getElementById("suivi-bandeau");
  var bouton = document.getElementById("suivi-actualiser");

  var delai = 1000;      // attente avant de se reconnecter, doublée à chaque échec (15 s au plus)
  var echecs = 0;        // échecs de connexion consécutifs avant la toute première ouverture
  var dejaOuverte = false;
  var minuterie = null;

  function montrerEtat(etat) {
    if (!voyant) {
      return;
    }
    var pastilles = voyant.querySelectorAll("[data-etat]");
    for (var i = 0; i < pastilles.length; i++) {
      pastilles[i].classList.toggle("hidden", pastilles[i].getAttribute("data-etat") !== etat);
    }
  }

  function saisieEnCours(zone) {
    var actif = document.activeElement;
    return !!actif && zone.contains(actif) && /^(INPUT|SELECT|TEXTAREA)$/.test(actif.tagName);
  }

  // Relit la page et remplace les zones ; une zone où l'on est en train de saisir est laissée telle
  // quelle (on ne perd pas une saisie) et un bandeau propose d'actualiser.
  function actualiser() {
    fetch(window.location.href, { credentials: "same-origin", headers: { "X-Requested-With": "suivi" } })
      .then(function (reponse) {
        if (!reponse.ok || reponse.redirected) {
          window.location.reload(); // session expirée, page disparue : on laisse le serveur décider
          return null;
        }
        return reponse.text();
      })
      .then(function (html) {
        if (html === null) {
          return;
        }
        var page = new DOMParser().parseFromString(html, "text/html");
        var occupee = false;
        var zones = document.querySelectorAll("[data-suivi-zone]");
        for (var i = 0; i < zones.length; i++) {
          var nouvelle = page.querySelector('[data-suivi-zone="' + zones[i].getAttribute("data-suivi-zone") + '"]');
          if (!nouvelle) {
            continue;
          }
          if (saisieEnCours(zones[i])) {
            occupee = true;
          } else {
            zones[i].replaceWith(nouvelle);
          }
        }
        if (bandeau) {
          bandeau.classList.toggle("hidden", !occupee);
        }
      })
      .catch(function () {
        /* réseau coupé : la reconnexion et l'actualisation qui suit rattraperont le retard */
      });
  }

  function planifierActualisation() {
    window.clearTimeout(minuterie);
    minuterie = window.setTimeout(actualiser, 250); // regroupe des changements rapprochés
  }

  function annoncer(mission) {
    if (annonce) {
      annonce.textContent = "Mission " + mission.numero + " : " + mission.statut_libelle + ".";
    }
  }

  function connecter() {
    var protocole = window.location.protocol === "https:" ? "wss://" : "ws://";
    var socket = new WebSocket(protocole + window.location.host + chemin);

    socket.onopen = function () {
      delai = 1000;
      echecs = 0;
      montrerEtat("connecte");
      if (dejaOuverte) {
        planifierActualisation(); // reconnecté : rattrape ce qui a changé pendant la coupure
      }
      dejaOuverte = true;
    };

    socket.onmessage = function (evenement) {
      var mission;
      try {
        mission = JSON.parse(evenement.data);
      } catch (erreur) {
        return;
      }
      if (missionId && String(mission.id) !== missionId) {
        return;
      }
      annoncer(mission);
      planifierActualisation();
    };

    socket.onclose = function () {
      if (!dejaOuverte && ++echecs >= 4) {
        montrerEtat("hors_ligne"); // refusée (droits, MFA) ou serveur sans WebSocket : inutile d'insister
        return;
      }
      montrerEtat("reconnexion");
      window.setTimeout(connecter, delai);
      delai = Math.min(delai * 2, 15000);
    };
  }

  if (bouton) {
    bouton.addEventListener("click", function () {
      window.location.reload();
    });
  }
  connecter();
})();
```

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
