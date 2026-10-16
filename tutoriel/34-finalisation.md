# Chapitre 34 — Finalisation, vérifications et déploiement

> 12 fichier(s) dans ce chapitre, 1540 lignes de code.

## Ce que vous allez faire

Vérifier que le projet est **complet et cohérent**, comprendre ce qu'il reste pour une **mise en production**, et savoir
**comparer votre travail** avec le projet de référence.

## Étape 1 — Récupérer les fichiers de référence

Les vérifications d'ensemble relisent des fichiers que ce tutoriel ne vous a pas fait écrire : `architecture.md` (le
schéma des dépendances entre apps, comparé au code) et les fichiers de **mise en production** (Docker, Nginx, scripts
de sauvegarde, versions figées des dépendances). Copiez-les depuis le dépôt de référence :

```bash
cp chemin/vers/reference/architecture.md chemin/vers/reference/Dockerfile chemin/vers/reference/.dockerignore chemin/vers/reference/docker-compose.yml .
cp chemin/vers/reference/requirements/prod.lock requirements/
cp -r chemin/vers/reference/nginx chemin/vers/reference/ops .
```

Leur rôle est expliqué dans `GUIDE-DEPLOIEMENT.md` : PDF préparés par le worker Celery (qui partage le dossier
`media/`), application servie derrière Cloudflare (vraie adresse du visiteur, cache des seuls fichiers statiques),
mesures lues par Prometheus, sauvegarde chiffrée de nuit.

## Étape 2 — Le README, les vérifications du projet complet et la recette navigateurs

Le `README.md` décrit l'application, ses commandes et son avancement. Les tests qui suivent vérifient le projet
**entier** : le schéma de `architecture.md`, la configuration de déploiement, les mesures pour Prometheus, Cloudflare,
les PDF en tâche de fond et les scripts de sauvegarde.

Le dossier `recette_navigateurs/` joue les scénarios de `RECETTE-NAVIGATEURS.md` dans de **vrais navigateurs**
(Chrome, Edge, Firefox et WebKit, le moteur de Safari), avec Playwright. Il ne fait pas partie de la suite habituelle
(`pytest.ini` ne lit que `apps/`) et demande d'installer les navigateurs :

```bash
python -m playwright install firefox webkit
python -m pytest recette_navigateurs -p no:cacheprovider
```

Le résultat, avec les versions testées, est écrit dans `recette_navigateurs/RESULTATS.md`.

#### Fichiers vides à créer

Ces fichiers n'ont aucun contenu ; ils servent à faire de leur dossier un *paquet Python* (sans eux, `import apps.xxx` échouerait). Créez d'abord les dossiers, puis les fichiers :

```bash
mkdir -p recette_navigateurs
touch recette_navigateurs/__init__.py
```

> Sous PowerShell, `mkdir -p` s'écrit `New-Item -ItemType Directory -Force <dossier>` et `touch fichier` s'écrit `New-Item -ItemType File -Force fichier`. Vous pouvez aussi créer ces fichiers avec votre éditeur.

#### `README.md`

*138 lignes* — ERP DEN Source Group

````markdown
# ERP DEN Source Group

Gestion intégrée transport & logistique — voir [cahier-des-charges.md](cahier-des-charges.md)
(source de vérité), [architecture.md](architecture.md), [conventions.md](conventions.md),
[glossaire-metier.md](glossaire-metier.md), [audit-checklist.md](audit-checklist.md).

## Démarrage (dev)

```bash
python -m venv .venv
./.venv/Scripts/pip install -r requirements/dev.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

## Interface web

Django Templates + Tailwind + Alpine.js + FontAwesome, chargés par CDN pour le
développement (à remplacer par un build avant la production). Les vues appellent
les `services.py` : aucune règle métier dans les vues.

```bash
python manage.py runserver   # puis http://localhost:8000
python manage.py createsuperuser   # un superutilisateur agit comme ADMIN
```

Modules disponibles : connexion / déconnexion, accueil, **missions** (liste, fiche,
création, cycle de vie complet), **flotte** (camions, fiche, documents réglementaires
avec alerte à 30 jours), **chauffeurs** (fiche, permis, visite médicale, suspension), **garage** (ordres de
réparation avec pièces et coût, immobilisation et remise en service des camions),
**stock** (articles, valeur au PUMP, entrées d'achat, ajustements, alerte de seuil, journal), **carburant** (pleins, alertes de surconsommation, analyse par
camion et par chauffeur), **clients** (portefeuille, fiche, TVA, historique commercial,
missions du client), **personnel** (fiche, recrutement, hiérarchie, jours de congé
exceptionnels) et **congés** (demande, validation N1 puis N2, annulation, alerte mission).
Le menu et les actions dépendent du rôle ; chaque
app déclare ses entrées de menu dans son `AppConfig.ready()`
(`apps/accounts/navigation.py`).

Identité visuelle : couleurs du logo DEN Source Group (bordeaux `#8B0319`, orange
`#F28A14`), définies sous les noms `marque` et `accent` dans la configuration Tailwind de
`templates/base.html`. Images dans `static/img/`.

## Structure

- `config/settings/` : `base.py` / `dev.py` / `test.py` / `prod.py`
- `apps/` : une app Django par domaine métier (cahier-des-charges.md:259-261)
- `requirements/` : dépendances par environnement ; `prod.lock` fige les versions exactes de la production
  (regénéré par `outils/verrouiller_dependances.py` après une mise à jour des paquets dans `.venv`)

## Avancement (phases CDC §5)

- [x] Étape 0 — Squelette Django (settings, apps vides core/accounts/audit)
- [x] Étape 1 — Fondations (BaseModel, User + rôles, AuditLog)
- [x] Étape 2a — Référentiels (hr, drivers, customers, fleet)
- [x] Étape 2b — Congés et recrutements (hr)
- [x] Étape 3 — Exploitation (missions, garage, inventory, fuel)
- [x] Interface web : connexion, mise en page, module missions
- [x] Interface web : flotte (camions, documents réglementaires)
- [x] Interface web : chauffeurs (fiche, permis, visite médicale, statut)
- [x] Interface web : garage (OR, pièces utilisées, immobilisation, remise en service)
- [x] Interface web : stock (articles, entrées, ajustements, journal, alerte de seuil)
- [x] Interface web : carburant (pleins, alertes, confirmation des saisies suspectes, analyse)
- [x] Interface web : clients (portefeuille, fiche, interactions)
- [x] Interface web : personnel, recrutement et congés (workflow 3 niveaux)
- [x] Étape 4 — Finance (facturation, règlements, dépenses, trésorerie, écritures comptables, rapprochement bancaire) (voir apps/billing/README.md)
- [x] Étape 5 — Pilotage (tableau de bord par rôle, notifications) : sans les indicateurs financiers (étape 4) ni Celery / SMS / push (voir apps/notifications/README.md)
- [x] Étape 6 — API (api/v1 en lecture seule, API et espace mobile du chauffeur, codes QR) : sans mode hors ligne (voir apps/mobile_api/README.md)
- [x] Étape 7 — Tests & déploiement, en 3 lots :
  - [x] Lot 1 — sécurité de l'application : Argon2, double authentification (TOTP), anti force brute, CSP, ressources locales (voir apps/accounts/README.md, frontend/README.md)
  - [x] Lot 2 — PostgreSQL, Redis, tâches planifiées (Celery) (voir apps/notifications/README.md)
  - [x] Lot 3 — Docker, Nginx, Gunicorn, sauvegardes chiffrées, Sentry (voir GUIDE-DEPLOIEMENT.md) : sans Prometheus/Grafana (décision : Sentry suffit à ce volume)

## Tableau de bord et notifications

La page d'accueil est le **tableau de bord** de chaque rôle (exploitation, centre d'alertes,
RH, clientèle). La **cloche** de l'en-tête compte les notifications non lues. Pour lancer les
alertes du jour (documents et permis à 30 jours, rappels de validation, statuts des congés) :

```bash
python manage.py taches_quotidiennes   # rejouable : aucune alerte en double
```

Les e-mails de notification s'affichent dans la console en développement ; en production,
réglez `NOTIFICATIONS_EMAIL=True`, `NOTIFICATIONS_URL_BASE` et l'envoi d'e-mails de Django.
Comptes d'essai : `python manage.py creer_comptes_demo`.

## Facturation et finances

`/facturation/` (factures, dépenses) et `/finances/` (trésorerie). Une facture se prépare depuis une
mission livrée (FINANCES), se valide par la DIRECTION (numéro `FACT-AAAA-XXXX`), puis s'encaisse par
acomptes et solde. Les indicateurs du mois (CA, encaissé, charges, marge, créances, trésorerie) et les
factures échues apparaissent au tableau de bord. Mentions de l'émetteur sur la facture imprimable :
`ENTREPRISE_NOM`, `ENTREPRISE_ADRESSE`, `ENTREPRISE_NCC`.

## API et espace chauffeur

- **API** : `/api/v1/` (JWT). Connexion : `POST /api/v1/auth/token/`. Documentation interactive pour
  l'ADMIN et la DIRECTION : `/api/v1/docs/`. Variable d'environnement : `CORS_ALLOWED_ORIGINS`.
- **Espace chauffeur** : `/chauffeur/`, à ouvrir sur un téléphone puis « Ajouter à l'écran d'accueil ».
  Un compte de rôle CHAUFFEUR arrive directement dessus après sa connexion.
- **Codes QR** : sur la fiche d'une mission, l'expéditeur et le destinataire disposent de leur code et
  de son QR ; le chauffeur le scanne pour confirmer la récupération puis la livraison.

## PostgreSQL, Redis et tâches planifiées

- **Base et cache en développement** : SQLite et un cache en mémoire (`LocMemCache`), sans rien à
  installer. La production (`config/settings/prod.py`) utilise PostgreSQL (`DATABASE_URL`) et un
  cache Redis natif (`REDIS_URL`, backend `django.core.cache.backends.redis.RedisCache` — aucune
  dépendance `django-redis`).
- **Tester en local contre de vrais services** : `docker-compose.yml` démarre un PostgreSQL et un
  Redis (`docker compose up -d`). Pointez `.env` dessus (voir `.env.example`) puis rejouez les
  tests : `python -m pytest -q --no-cov` — cela exerce aussi la recherche sans accents spécifique à
  PostgreSQL (`apps/core/search.py`), jamais testée sur SQLite.
- **Tâches planifiées (Celery)** : `taches_quotidiennes` et l'envoi d'e-mail de notification
  passent par Celery (`apps/notifications/tasks.py`). En développement et en test,
  `CELERY_TASK_ALWAYS_EAGER=True` (par défaut) les exécute immédiatement, sans courtier. En
  production, lancez un `celery worker` et un `celery beat` à côté de l'application :

  ```bash
  celery -A config worker -l info
  celery -A config beat -l info
  ```

- **PDF en tâche de fond** (audit TECH-70) : en production (`PDF_EN_TACHE_DE_FOND`, actif par défaut dans
  `config/settings/prod.py`), « Télécharger en PDF » confie la mise en page au worker et affiche une page
  « Préparation de votre PDF » qui lance le téléchargement dès que le fichier est prêt. Le worker doit donc partager
  le dossier `media/` avec l'application (volume `media_data` dans `docker-compose.yml`). Les fichiers sont réservés
  au demandeur et effacés au bout de 24 heures. Sans worker (développement), le PDF est rendu dans la requête.

## Sécurité de la connexion

- **Double authentification** obligatoire pour l'ADMIN et la DIRECTION : à la première connexion, scanner le
  QR code avec une application d'authentification et noter les 10 codes de secours. Téléphone perdu :
  `python manage.py reinitialiser_mfa <identifiant>`.
- **Interface sans CDN** : styles, icônes et Alpine.js sont servis par l'application (`static/`). Après un
  changement de classes Tailwind : `cd frontend && npm install && npm run build`.
- Variables : `TRUSTED_PROXY_COUNT` (1 derrière Nginx), `CSP_REPORT_ONLY` (mise au point de la CSP).
````

#### `recette_navigateurs/conftest.py`

*230 lignes* — Recette automatisée dans de vrais navigateurs (cahier-des-charges.md:300 ; audit TECH-74 à TECH-77).

```python
"""Recette automatisée dans de vrais navigateurs (cahier-des-charges.md:300 ; audit TECH-74 à TECH-77).

Lancement (hors de la suite habituelle, qui ne lit que ``apps/``) :

    python -m pytest recette_navigateurs -p no:cacheprovider

Prérequis : ``pip install playwright`` puis ``python -m playwright install firefox webkit`` ; Chrome et Edge sont
ceux installés sur le poste (canaux ``chrome`` et ``msedge`` de Playwright). Les scénarios suivent la fiche
``RECETTE-NAVIGATEURS.md`` (sections A à F) ; chacun tourne dans chaque navigateur, sur un serveur de test et une
base de test (jamais les données de démonstration). En fin de passage, ``recette_navigateurs/RESULTATS.md`` donne les
versions testées et le résultat de chaque scénario par navigateur.

Safari : Playwright fournit le moteur de Safari (WebKit) sur Windows, pas Safari lui-même ; la ligne Safari de la
matrice demande en plus la vérification sur un iPhone ou un Mac (section F de la fiche).
"""

from __future__ import annotations

import asyncio
import io
import os
import shutil
import sys
import tempfile
import warnings
from datetime import datetime
from pathlib import Path

import pytest
from django.test import Client
from playwright.sync_api import sync_playwright

# L'API synchrone de Playwright fait tourner une boucle d'événements dans le fil principal : Django y voit un contexte
# asynchrone et refuserait les requêtes en base des scénarios (créations de données, vérifications). Réglage prévu
# par Django pour ce cas (tests seulement).
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

ICI = Path(__file__).resolve().parent
CODE_QR = "ABCD2345"  # code expéditeur des missions de test (apps/mobile_api/tests/helpers.py)

NAVIGATEURS = {
    "chrome": ("chromium", {"channel": "chrome"}),
    "edge": ("chromium", {"channel": "msedge"}),
    "firefox": ("firefox", {}),
    "webkit": ("webkit", {}),
}
LIBELLES = {"chrome": "Chrome", "edge": "Edge", "firefox": "Firefox", "webkit": "WebKit (moteur de Safari)"}

VERSIONS: dict[str, str] = {}
RESULTATS: dict[tuple[str, str], str] = {}  # (scénario, navigateur) -> réussi / échoué / ignoré


def pytest_collection_modifyitems(items):
    """Un navigateur après l'autre (un seul lancement de chacun), dans l'ordre de la fiche."""
    ordre = list(NAVIGATEURS)
    items.sort(key=lambda item: ordre.index(item.callspec.params["navigateur"]) if hasattr(item, "callspec") else -1)


def _video_qr(dossier: Path) -> Path:
    """Vidéo Y4M d'un QR du code expéditeur : la « caméra » simulée de Chrome et Edge (section F3)."""
    import qrcode
    from PIL import Image

    largeur, hauteur = 640, 480
    fond = Image.new("RGB", (largeur, hauteur), "white")
    qr = qrcode.make(CODE_QR, box_size=10, border=4).convert("RGB")
    fond.paste(qr, ((largeur - qr.width) // 2, (hauteur - qr.height) // 2))
    y, cb, cr = fond.convert("YCbCr").split()
    demi = (largeur // 2, hauteur // 2)
    trame = y.tobytes() + cb.resize(demi).tobytes() + cr.resize(demi).tobytes()
    chemin = dossier / "qr.y4m"
    with chemin.open("wb") as video:
        video.write(f"YUV4MPEG2 W{largeur} H{hauteur} F10:1 Ip A1:1 C420jpeg\n".encode())
        for _ in range(10):
            video.write(b"FRAME\n" + trame)
    return chemin


def _lancer(type_navigateur, options):
    """Lance le navigateur. Sur certains postes Windows, le Firefox de Playwright refuse de démarrer depuis son
    dossier d'installation (« configuration côte-à-côte incorrecte », composant mozglue) mais démarre depuis une
    copie dans le dossier temporaire : on s'y replie."""
    try:
        return type_navigateur.launch(**options)
    except Exception:
        if type_navigateur.name != "firefox" or sys.platform != "win32" or "executable_path" in options:
            raise
        copie = Path(tempfile.gettempdir()) / "erp-recette-firefox"
        if not (copie / "firefox.exe").exists():
            shutil.copytree(Path(type_navigateur.executable_path).parent, copie, dirs_exist_ok=True)
        return type_navigateur.launch(executable_path=str(copie / "firefox.exe"), **options)


@pytest.fixture(scope="session")
def playwright_session():
    if sys.platform == "win32":
        # Daphne (WebSocket) impose à l'import une boucle d'événements « Selector », incapable de lancer le processus
        # de Playwright sous Windows : on rétablit la boucle « Proactor », celle par défaut de Windows.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session", params=list(NAVIGATEURS))
def navigateur(request, playwright_session, tmp_path_factory):
    nom = request.param
    moteur, options = NAVIGATEURS[nom]
    if moteur == "chromium":
        video = _video_qr(tmp_path_factory.mktemp("camera"))
        options = {**options, "args": [
            "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
            f"--use-file-for-fake-video-capture={video}",
        ]}
    elif moteur == "firefox":
        options = {**options, "firefox_user_prefs": {
            "media.navigator.streams.fake": True, "media.navigator.permission.disabled": True,
        }}
    try:
        navigateur = _lancer(getattr(playwright_session, moteur), options)
    except Exception as erreur:  # navigateur absent du poste
        pytest.skip(f"{LIBELLES[nom]} indisponible : {erreur}")
    VERSIONS[nom] = navigateur.version
    navigateur.nom = nom
    yield navigateur
    navigateur.close()


@pytest.fixture
def serveur(live_server, settings, tmp_path):
    from django.core.cache import cache

    settings.MEDIA_ROOT = tmp_path / "media"
    cache.clear()  # compteurs anti-abus (connexion, mot de passe oublié) : chaque scénario repart de zéro
    return live_server.url


@pytest.fixture
def ouvrir(navigateur, serveur, playwright_session):
    """``ouvrir(utilisateur=None, mobile=False)`` : une page neuve, connectée si un utilisateur est donné.

    Les erreurs JavaScript et les refus de la politique de sécurité (CSP) de la page sont relevés ; un scénario
    échoue s'il y en a (``verifier_console``).
    """
    contextes = []

    def _ouvrir(utilisateur=None, *, mobile=False):
        options = {"base_url": serveur, "accept_downloads": True, "locale": "fr-FR", "timezone_id": "Africa/Abidjan"}
        if mobile:
            # Téléphone : iPhone pour le moteur de Safari, Android pour Chrome et Edge ; Firefox n'émule pas de
            # téléphone (option « is_mobile » non prise en charge), seulement sa taille d'écran.
            appareil = {"webkit": "iPhone 14", "chrome": "Pixel 7", "edge": "Pixel 7"}.get(navigateur.nom)
            if appareil:
                description = dict(playwright_session.devices[appareil])
                description.pop("default_browser_type", None)
                options.update(description)
            else:
                options.update({"viewport": {"width": 412, "height": 915}, "has_touch": True})
        else:
            options["viewport"] = {"width": 1366, "height": 850}
        if navigateur.nom in ("chrome", "edge"):
            options["permissions"] = ["camera"]
        contexte = navigateur.new_context(**options)
        contextes.append(contexte)
        if utilisateur is not None:
            client = Client()
            client.force_login(utilisateur)
            contexte.add_cookies([{"name": "sessionid", "value": client.cookies["sessionid"].value, "url": serveur}])
        page = contexte.new_page()
        suivre_erreurs(page)
        return page

    yield _ouvrir
    for contexte in contextes:
        contexte.close()


def suivre_erreurs(page):
    """Relève les erreurs JavaScript, les messages d'erreur de la console et les réponses en erreur (avec leur
    adresse : la console de Chrome ne la donne pas toujours)."""
    page.erreurs = []
    page.on("pageerror", lambda e: page.erreurs.append(f"JavaScript : {e}"))
    page.on("console", lambda m: page.erreurs.append(f"Console : {m.text}")
            if m.type == "error" and not m.text.startswith("Failed to load resource") else None)
    page.on("response", lambda r: page.erreurs.append(f"HTTP {r.status} : {r.url}") if r.status >= 400 else None)


def verifier_console(page, *, sauf=()):
    """Aucune erreur JavaScript ni refus de la CSP. ``sauf`` : morceaux de messages attendus (ex. WebSocket, que le
    serveur de test ne sert pas)."""
    ignorees = ("WebSocket", "ws/missions", "favicon") + tuple(sauf)
    restantes = [e for e in page.erreurs if not any(morceau in e for morceau in ignorees)]
    assert not restantes, restantes


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    resultat = yield
    rapport = resultat.get_result()
    if not hasattr(item, "callspec") or "navigateur" not in item.callspec.params:
        return
    cle = (item.originalname, item.callspec.params["navigateur"])
    if rapport.when == "call" or (rapport.when == "setup" and not rapport.passed):
        RESULTATS[cle] = "ignoré" if rapport.skipped else ("réussi" if rapport.passed else "ÉCHOUÉ")
    elif rapport.when == "teardown" and rapport.failed:
        RESULTATS[cle] = "ÉCHOUÉ"


def pytest_sessionfinish(session):
    if not RESULTATS or os.environ.get("RECETTE_SANS_RAPPORT"):
        return
    scenarios = list(dict.fromkeys(nom for nom, _ in RESULTATS))
    noms = [n for n in NAVIGATEURS if any(cle[1] == n for cle in RESULTATS)]
    docstrings = {}
    for item in session.items:
        docstrings.setdefault(item.originalname, (item.function.__doc__ or "").strip().splitlines()[0])
    sortie = io.StringIO()
    sortie.write("# Résultats de la recette navigateurs automatisée\n\n")
    sortie.write(f"Passage du {datetime.now():%d/%m/%Y à %H:%M}, `python -m pytest recette_navigateurs` "
                 "(fiche `RECETTE-NAVIGATEURS.md`, audit TECH-74 à TECH-77). Fichier régénéré à chaque passage.\n\n")
    sortie.write("| Navigateur | Version |\n|---|---|\n")
    for nom in noms:
        sortie.write(f"| {LIBELLES[nom]} | {VERSIONS.get(nom, 'indisponible')} |\n")
    sortie.write("\n| Scénario | " + " | ".join(LIBELLES[n] for n in noms) + " |\n")
    sortie.write("|---|" + "---|" * len(noms) + "\n")
    for scenario in scenarios:
        cellules = [RESULTATS.get((scenario, n), "—") for n in noms]
        sortie.write(f"| {docstrings.get(scenario, scenario)} | " + " | ".join(cellules) + " |\n")
    (ICI / "RESULTATS.md").write_text(sortie.getvalue(), encoding="utf-8")
```

#### `recette_navigateurs/reglages_asgi.py`

*18 lignes* — Réglages du serveur ASGI de la recette du suivi en direct (scénario E1, ``test_temps_reel.py``).

```python
"""Réglages du serveur ASGI de la recette du suivi en direct (scénario E1, ``test_temps_reel.py``).

Ceux du développement (``runserver`` de Daphne : pages, fichiers statiques et WebSocket dans un seul processus),
mais sur une base jetable : jamais la base de démonstration.
"""

import os

from config.settings.dev import *  # noqa: F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ["RECETTE_BASE"],
    }
}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
NOTIFICATIONS_EMAIL = False
```

#### `recette_navigateurs/test_recette.py`

*412 lignes* — Scénarios de la fiche RECETTE-NAVIGATEURS.md, joués dans Chrome, Edge, Firefox et WebKit (audit TECH-74 à 77).

```python
"""Scénarios de la fiche RECETTE-NAVIGATEURS.md, joués dans Chrome, Edge, Firefox et WebKit (audit TECH-74 à 77).

Chaque test porte le numéro de la fiche (A1, B2...) dans la première ligne de sa documentation, reprise par
``RESULTATS.md``.
"""

from __future__ import annotations

import re
import time
from decimal import Decimal
from pathlib import Path

import pyotp
import pytest
from django.core import mail
from playwright.sync_api import expect

from apps.accounts.models import AppareilMFA, Role
from apps.accounts.tests.factories import UserFactory
from apps.billing.tests.helpers import emise
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeEnRegleFactory
from apps.fuel.models import Plein
from apps.hr.tests.factories import PersonnelFactory
from apps.missions.models import FraisMission, StatutMission
from apps.mobile_api.tests.helpers import CODE_EXPEDITEUR, chauffeur_avec_compte, mission_de
from apps.notifications.models import CategorieNotification
from apps.notifications.services import notifier

from .conftest import verifier_console

pytestmark = pytest.mark.django_db(transaction=True, serialized_rollback=True)

MOT_DE_PASSE = "Test-Passw0rd!"  # celui de UserFactory
MILLIERS = r"[\s  ]"


def _image_chargee(page, image):
    """Attend qu'une image soit chargée et non vide (une image cassée ferait échouer le scénario)."""
    expect(image).to_be_visible()
    page.wait_for_function("(img) => img.complete && img.naturalWidth > 0", arg=image.element_handle(), timeout=10000)


def _admin():
    return UserFactory(is_superuser=True, is_staff=True, first_name="Awa", last_name="Diallo")


# --- A. Connexion et sécurité ---


def test_a1_connexion(ouvrir):
    """A1 — Connexion, puis refus d'un mauvais mot de passe"""
    UserFactory(username="awa", role=Role.RH)
    page = ouvrir()
    page.goto("/")
    expect(page).to_have_url(re.compile(r"/connexion/"))
    page.fill("#id_username", "awa")
    page.fill("#id_password", "mauvais-mot-de-passe")
    page.click("button[type=submit]")
    expect(page.get_by_role("alert").first).to_be_visible()

    page.fill("#id_username", "awa")
    page.fill("#id_password", MOT_DE_PASSE)
    page.click("button[type=submit]")
    expect(page.get_by_role("button", name="Déconnexion")).to_be_visible()
    verifier_console(page)


def test_a2_double_authentification(ouvrir, settings):
    """A2 — Double authentification : QR affiché, code à 6 chiffres accepté"""
    settings.MFA_ENFORCED = True
    UserFactory(username="direction", role=Role.DIRECTION)
    page = ouvrir()
    page.goto("/connexion/")
    page.fill("#id_username", "direction")
    page.fill("#id_password", MOT_DE_PASSE)
    page.click("button[type=submit]")

    qr = page.get_by_role("img", name=re.compile("Code QR d'activation"))
    _image_chargee(page, qr)
    secret = AppareilMFA.objects.get(utilisateur__username="direction").secret
    page.fill("#id_code", pyotp.TOTP(secret).now())
    page.get_by_role("button", name="Activer").click()
    expect(page.get_by_text(re.compile("codes de secours", re.I)).first).to_be_visible()
    verifier_console(page)


def test_a3_mot_de_passe_oublie(ouvrir):
    """A3 — « Mot de passe oublié » : envoi et confirmation"""
    UserFactory(username="rh", email="rh@densourcegroup.ci", role=Role.RH)
    page = ouvrir()
    page.goto("/mot-de-passe/")
    page.fill("#id_email", "rh@densourcegroup.ci")
    page.click("button[type=submit]")
    expect(page.get_by_role("heading", name="E-mail envoyé")).to_be_visible()
    assert len(mail.outbox) == 1
    verifier_console(page)


def test_a4_expiration_de_session(ouvrir, settings):
    """A4 — La session expire après l'inactivité et ramène à la connexion"""
    settings.SESSION_COOKIE_AGE = 3
    UserFactory(username="rh", role=Role.RH)
    page = ouvrir()
    page.goto("/connexion/")
    page.fill("#id_username", "rh")
    page.fill("#id_password", MOT_DE_PASSE)
    page.click("button[type=submit]")
    expect(page.get_by_role("button", name="Déconnexion")).to_be_visible()

    time.sleep(4)
    page.reload()
    expect(page).to_have_url(re.compile(r"/connexion/"))


def test_a5_deconnexion(ouvrir):
    """A5 — Déconnexion : « Précédent » ne réaffiche pas une page protégée"""
    PersonnelFactory(nom="Secretnom")
    page = ouvrir(_admin())
    page.goto("/rh/personnel/")
    expect(page.get_by_text("Secretnom").first).to_be_visible()
    page.get_by_role("button", name="Déconnexion").click()
    expect(page).to_have_url(re.compile(r"/connexion/"))

    page.go_back()
    page.wait_for_load_state()
    expect(page.get_by_text("Secretnom")).to_have_count(0)
    verifier_console(page)


# --- B. Mise en page et navigation ---


def test_b1_menu_logo_et_icones(ouvrir):
    """B1 — Menu latéral, logo et icônes affichés"""
    page = ouvrir(_admin())
    page.goto("/")
    liens = page.locator("#navigation nav a")
    assert liens.count() >= 8
    for i in range(liens.count()):
        expect(liens.nth(i)).to_be_visible()
    _image_chargee(page, page.locator("#navigation img").first)
    page.evaluate("document.fonts.ready")
    assert page.evaluate(
        "[...document.fonts].some(f => /Font Awesome/i.test(f.family) && f.status === 'loaded')"
    ), "police d'icônes non chargée"
    largeur_icone = page.evaluate("document.querySelector('#navigation nav i').getBoundingClientRect().width")
    assert largeur_icone > 0
    with page.expect_navigation():
        liens.nth(1).click()
    assert page.locator("#navigation [aria-current=page]").count() == 1
    verifier_console(page)


def test_b2_menu_sur_petit_ecran(ouvrir):
    """B2 — Petit écran : le menu s'ouvre par « ☰ » et se ferme par Échap"""
    page = ouvrir(_admin())
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto("/")
    navigation = page.locator("#navigation")
    expect(navigation).not_to_be_in_viewport()
    page.get_by_role("button", name="Ouvrir le menu").click()
    expect(navigation).to_be_in_viewport()
    page.keyboard.press("Escape")
    expect(navigation).not_to_be_in_viewport()
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
    verifier_console(page)


def test_b3_pagination_et_recherche_sans_accents(ouvrir):
    """B3 — Pagination et recherche sans accents (« kone » trouve « Koné »)"""
    for i in range(24):
        PersonnelFactory(nom=f"Agent{i:02d}")
    PersonnelFactory(nom="Koné", prenom="Mariam")
    page = ouvrir(_admin())
    page.goto("/rh/personnel/")
    page.locator("a[href*='page=2']").first.click()
    expect(page).to_have_url(re.compile(r"page=2"))
    page.goto("/rh/personnel/?q=kone")
    expect(page.get_by_text("Koné").first).to_be_visible()
    expect(page.get_by_text("Agent00")).to_have_count(0)
    verifier_console(page)


def test_b4_notifications(ouvrir):
    """B4 — Cloche des notifications et « Tout marquer comme lu »"""
    utilisateur = _admin()
    notifier([utilisateur], categorie=CategorieNotification.MISSION, titre="Mission livrée")
    page = ouvrir(utilisateur)
    page.goto("/")
    cloche = page.locator("a[href='/notifications/']")
    expect(cloche).to_contain_text("1")
    cloche.click()
    expect(page.get_by_text("Mission livrée").first).to_be_visible()
    with page.expect_navigation():
        page.get_by_role("button", name="Tout marquer comme lu").click()
    expect(page.locator("a[href='/notifications/']")).not_to_contain_text("1")
    verifier_console(page)


def test_b5_tableau_de_bord(ouvrir):
    """B5 — Tableau de bord : indicateurs et graphiques sans débordement"""
    fiche, _ = chauffeur_avec_compte()
    mission_de(fiche)  # des données pour que les graphiques aient quelque chose à montrer
    emise()
    page = ouvrir(_admin())
    page.goto("/")
    page.wait_for_load_state("networkidle")
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
    assert page.locator("main [class*='viz-']").count() >= 1  # graphiques en HTML/CSS (apps/core/graphiques.py)
    verifier_console(page)


# --- C. Formulaires ---


def _formulaire_plein(page, vehicule, chauffeur, *, date_plein):
    page.goto("/carburant/nouveau/")
    page.select_option("#id_vehicule", str(vehicule.pk))
    page.select_option("#id_chauffeur", str(chauffeur.pk))
    page.fill("#id_date_plein", date_plein)
    page.fill("#id_station", "Total Plateau")
    page.fill("#id_quantite_litres", "100")
    page.fill("#id_prix_unitaire", "700")
    page.fill("#id_km_compteur", "1500")
    page.fill("#id_numero_ticket", "T-001")


def test_c1_c2_c3_formulaire_dates_montants_erreurs(ouvrir):
    """C1-C3 — Calendrier de date, montant en FCFA, erreurs affichées sans perdre la saisie"""
    vehicule, chauffeur = VehiculeEnRegleFactory(), ChauffeurFactory()
    page = ouvrir(UserFactory(role=Role.PARCAUTO))

    _formulaire_plein(page, vehicule, chauffeur, date_plein="2099-01-01")  # date future : refusée par le serveur
    page.get_by_role("button", name=re.compile("Enregistrer")).click()
    expect(page.get_by_text("ne peut pas être dans le futur")).to_be_visible()
    expect(page.locator("#id_station")).to_have_value("Total Plateau")

    page.fill("#id_date_plein", "2026-10-10")
    with page.expect_navigation():
        page.get_by_role("button", name=re.compile("Enregistrer")).click()
    plein = Plein.objects.get()
    assert plein.date_plein.isoformat() == "2026-10-10"
    page.goto("/carburant/")
    expect(page.locator("main")).to_contain_text(re.compile(f"70{MILLIERS}000"))
    verifier_console(page)


def test_c5_confirmation_avant_une_action(ouvrir):
    """C5 — Confirmation avant une action : « Annuler » n'enregistre rien"""
    fiche, _ = chauffeur_avec_compte()
    mission = mission_de(fiche)
    page = ouvrir(UserFactory(role=Role.CHARGE_CLIENTELE))
    page.goto(f"/missions/{mission.pk}/")
    page.get_by_role("button", name="Annuler la mission").click()
    page.fill("#motif-annulation", "Le client a retiré sa commande")

    page.once("dialog", lambda dialogue: dialogue.dismiss())
    page.get_by_role("button", name="Confirmer l'annulation").click()
    page.wait_for_timeout(500)
    mission.refresh_from_db()
    assert mission.statut == StatutMission.AFFECTEE

    page.once("dialog", lambda dialogue: dialogue.accept())
    page.get_by_role("button", name="Confirmer l'annulation").click()
    expect(page.get_by_text(re.compile("annulée")).first).to_be_visible()
    mission.refresh_from_db()
    assert mission.statut == StatutMission.ANNULEE
    verifier_console(page)


# --- D. Documents et exports ---


def test_d1_impression_d_une_facture(ouvrir):
    """D1 — Impression d'une facture : la page imprimée ne montre que la facture"""
    facture = emise()
    page = ouvrir(_admin())
    page.goto(f"/facturation/{facture.pk}/imprimer/")
    expect(page.get_by_text(facture.numero).first).to_be_visible()
    assert page.locator("#navigation").count() == 0
    bouton = page.locator("[data-imprimer]").first
    expect(bouton).to_be_visible()
    page.emulate_media(media="print")
    expect(bouton).to_be_hidden()
    verifier_console(page)


def test_d2_pdf_prepare_en_tache_de_fond(ouvrir, settings):
    """D2 — « Télécharger en PDF » : page d'attente puis téléchargement automatique"""
    settings.PDF_EN_TACHE_DE_FOND = True
    PersonnelFactory()
    page = ouvrir(_admin())
    page.goto("/rh/personnel/imprimer/")
    with page.expect_download(timeout=20000) as attente:
        page.get_by_role("link", name="Télécharger en PDF").click()
    fichier = attente.value
    assert fichier.suggested_filename.startswith("personnel-") and fichier.suggested_filename.endswith(".pdf")
    assert Path(fichier.path()).read_bytes().startswith(b"%PDF")


def test_d3_export_excel(ouvrir):
    """D3 — Export Excel : le fichier .xlsx se télécharge"""
    PersonnelFactory()
    page = ouvrir(_admin())
    page.goto("/rh/personnel/")
    with page.expect_download() as attente:
        page.locator("a[href*='/rh/personnel/excel/']").first.click()
    fichier = attente.value
    assert fichier.suggested_filename.endswith(".xlsx")
    assert Path(fichier.path()).read_bytes().startswith(b"PK")  # classeur = archive zip
    verifier_console(page)


def test_d4_pdf_des_codes_d_une_mission(ouvrir):
    """D4 — PDF des codes d'une mission et QR affichés"""
    fiche, _ = chauffeur_avec_compte()
    mission = mission_de(fiche)
    page = ouvrir(UserFactory(role=Role.CHARGE_CLIENTELE))
    page.goto(f"/missions/{mission.pk}/")
    _image_chargee(page, page.get_by_role("img", name=re.compile("Code QR de l'expéditeur")))
    with page.expect_download() as attente:
        page.get_by_role("link", name="Télécharger le PDF des codes").click()
    assert Path(attente.value.path()).read_bytes().startswith(b"%PDF")
    verifier_console(page)


# --- F. Espace chauffeur (téléphone) ---


def test_f1_espace_chauffeur_a_la_taille_du_telephone(ouvrir):
    """F1 — Espace chauffeur à la taille de l'écran, barre du bas sur une ligne"""
    fiche, compte = chauffeur_avec_compte()
    mission_de(fiche)
    page = ouvrir(compte, mobile=True)
    page.goto("/chauffeur/")
    page.wait_for_load_state("networkidle")
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
    barre = page.locator("nav").last
    expect(barre).to_be_visible()
    assert barre.bounding_box()["height"] < 100
    verifier_console(page)


def test_f2_installable_sur_l_ecran_d_accueil(ouvrir):
    """F2 — Installable : manifeste valide et service worker enregistré"""
    _, compte = chauffeur_avec_compte()
    page = ouvrir(compte, mobile=True)
    page.goto("/chauffeur/")
    adresse = page.evaluate("document.querySelector('link[rel=manifest]').href")
    manifeste = page.context.request.get(adresse).json()  # lu directement, sans passer par le service worker
    assert manifeste["name"] and manifeste["icons"] and manifeste["start_url"].startswith("/chauffeur/")
    enregistre = page.evaluate(
        "navigator.serviceWorker ? navigator.serviceWorker.ready.then(r => !!r.active) : false"
    )
    assert enregistre, "service worker non enregistré"
    verifier_console(page)


def test_f4_code_saisi_a_la_main(ouvrir):
    """F4 — Code de récupération saisi à la main (en minuscules) et accepté"""
    fiche, compte = chauffeur_avec_compte()
    mission = mission_de(fiche, statut=StatutMission.EN_COURS_DEPART)
    page = ouvrir(compte, mobile=True)
    page.goto(f"/chauffeur/missions/{mission.pk}/")
    page.fill("#id_code", CODE_EXPEDITEUR.lower())
    with page.expect_navigation():
        page.get_by_role("button", name="Confirmer la récupération").click()
    mission.refresh_from_db()
    assert mission.statut == StatutMission.EN_COURS_COLIS_RECUPERE
    verifier_console(page)


def test_f3_qr_scanne_par_la_camera(ouvrir, navigateur):
    """F3 — Caméra ouverte depuis l'espace chauffeur ; QR lu (Chrome, Edge : caméra simulée filmant un QR)"""
    if navigateur.nom == "webkit":
        pytest.skip("Pas de caméra simulée dans WebKit sous Windows : à vérifier sur un iPhone (fiche, F3)")
    fiche, compte = chauffeur_avec_compte()
    mission = mission_de(fiche, statut=StatutMission.EN_COURS_DEPART)
    page = ouvrir(compte, mobile=True)
    page.goto(f"/chauffeur/missions/{mission.pk}/")
    page.get_by_role("button", name="Scanner le QR").click()
    if navigateur.nom == "firefox":
        expect(page.locator("video")).to_be_visible()
        page.wait_for_function("document.querySelector('video').readyState >= 2", timeout=10000)
        page.get_by_role("button", name="Fermer la caméra").click()
    else:
        expect(page.locator("#id_code")).to_have_value(CODE_EXPEDITEUR, timeout=15000)
    expect(page.get_by_role("alert")).to_have_count(0)
    verifier_console(page)


def test_f5_imprevu_avec_photo(ouvrir, tmp_path):
    """F5 — Imprévu déclaré avec une photo"""
    from PIL import Image

    photo = tmp_path / "photo.jpg"
    Image.new("RGB", (64, 64), "orange").save(photo)
    fiche, compte = chauffeur_avec_compte()
    mission = mission_de(fiche, statut=StatutMission.EN_COURS_DEPART)
    page = ouvrir(compte, mobile=True)
    page.goto(f"/chauffeur/imprevu/?mission={mission.pk}")
    page.fill("#id_montant", "15000")
    page.fill("#id_description", "Crevaison, pneu remplacé")
    page.set_input_files("#id_justificatif", str(photo))
    with page.expect_navigation():
        page.locator("form button[type=submit]").last.click()
    frais = FraisMission.objects.get(mission=mission)
    assert frais.montant == Decimal("15000") and frais.justificatif
    verifier_console(page)

```

#### `recette_navigateurs/test_temps_reel.py`

*116 lignes* — Scénario E1 de la fiche RECETTE-NAVIGATEURS.md : le suivi des missions se met à jour sans recharger la page.

```python
"""Scénario E1 de la fiche RECETTE-NAVIGATEURS.md : le suivi des missions se met à jour sans recharger la page.

Le serveur de test de pytest ne sait pas servir de WebSocket : ce scénario lance à part le ``runserver`` de Daphne
(comme en développement) sur une base jetable préparée pour l'occasion (``reglages_asgi.py``).
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from playwright.sync_api import expect

from .conftest import NAVIGATEURS, suivre_erreurs, verifier_console

RACINE = Path(__file__).resolve().parent.parent
MOT_DE_PASSE = "Test-Passw0rd!"

# Un compte du bureau et une mission par navigateur (chacun annule la sienne), créés une fois au démarrage.
PREPARATION = """
import json
from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.mobile_api.tests.helpers import chauffeur_avec_compte, mission_de
UserFactory(username="suivi", role=Role.CHARGE_CLIENTELE)
missions = {}
for nom in NOMS:
    fiche, _ = chauffeur_avec_compte()
    mission = mission_de(fiche)
    missions[nom] = {"mission": mission.pk, "numero": mission.numero}
print("RESULTAT" + json.dumps(missions))
"""


def _port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def serveur_asgi(tmp_path_factory):
    dossier = tmp_path_factory.mktemp("asgi")
    env = {
        **os.environ, "DJANGO_SETTINGS_MODULE": "recette_navigateurs.reglages_asgi",
        "RECETTE_BASE": str(dossier / "recette.sqlite3"), "PYTHONIOENCODING": "utf-8",
    }
    env.pop("DJANGO_ALLOW_ASYNC_UNSAFE", None)
    manage = [sys.executable, str(RACINE / "manage.py")]
    subprocess.run([*manage, "migrate", "--noinput", "-v", "0"], cwd=RACINE, env=env, check=True)
    preparation = PREPARATION.replace("NOMS", repr(list(NAVIGATEURS)))
    sortie = subprocess.run(
        [*manage, "shell", "-c", preparation], cwd=RACINE, env=env, check=True, capture_output=True, text=True,
    ).stdout
    missions = json.loads(sortie.split("RESULTAT", 1)[1])
    port = _port_libre()
    processus = subprocess.Popen(
        [*manage, "runserver", "--noreload", f"127.0.0.1:{port}"], cwd=RACINE, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(120):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                break
            except OSError:
                time.sleep(0.5)
        else:
            pytest.fail("Le serveur ASGI de la recette n'a pas démarré")
        yield {"url": f"http://127.0.0.1:{port}", "missions": missions}
    finally:
        processus.terminate()
        processus.wait(timeout=10)


def test_e1_suivi_des_missions_en_direct(navigateur, serveur_asgi):
    """E1 — Suivi des missions : l'écran se met à jour seul quand une mission change"""
    mission = serveur_asgi["missions"][navigateur.nom]
    contexte = navigateur.new_context(base_url=serveur_asgi["url"], locale="fr-FR", viewport={"width": 1366, "height": 850})
    try:
        suivi = contexte.new_page()
        suivre_erreurs(suivi)
        suivi.goto("/connexion/")
        suivi.fill("#id_username", "suivi")
        suivi.fill("#id_password", MOT_DE_PASSE)
        suivi.click("button[type=submit]")
        expect(suivi.get_by_role("button", name="Déconnexion")).to_be_visible()

        suivi.goto("/missions/")
        expect(suivi.locator("#suivi-voyant [data-etat=connecte]")).to_be_visible(timeout=10000)
        ligne = suivi.locator("tr", has_text=mission["numero"])
        expect(ligne).not_to_contain_text("Annulée")

        # Un autre onglet (même session) annule la mission : le premier ne recharge rien lui-même.
        action = contexte.new_page()
        action.goto(f"/missions/{mission['mission']}/")
        action.get_by_role("button", name="Annuler la mission").click()
        action.fill("#motif-annulation", "Recette du suivi en direct")
        action.once("dialog", lambda dialogue: dialogue.accept())
        action.get_by_role("button", name="Confirmer l'annulation").click()
        expect(action.get_by_text(re.compile("annulée")).first).to_be_visible()

        expect(suivi.locator("#suivi-annonce")).to_contain_text("Annulée", timeout=10000)
        expect(suivi.locator("tr", has_text=mission["numero"])).to_contain_text("Annulée", timeout=10000)
        # Le runserver de Daphne sert mal la police d'icônes à Firefox (repli sur un .ttf absent) ; en production,
        # Nginx sert les fichiers statiques, et le scénario B1 vérifie leur chargement dans chaque navigateur.
        verifier_console(suivi, sauf=("downloadable font", "/webfonts/"))
    finally:
        contexte.close()
```

#### `apps/core/tests/test_architecture.py`

*58 lignes* — Le graphe des dépendances entre apps : sans cycle, et tel que le décrit architecture.md — audit AUD-20.

````python
"""Le graphe des dépendances entre apps : sans cycle, et tel que le décrit architecture.md — audit AUD-20.

Une dépendance = un import ``apps.<autre>`` hors tests et migrations. Le schéma du document (§ 3) ne trace pas les
flèches vers le socle (``core``, ``accounts``, ``audit``, ``parametres``), dont dépendent toutes les apps.
"""

import re
from pathlib import Path

RACINE = Path(__file__).resolve().parents[3]
SOCLE = {"core", "accounts", "audit", "parametres"}
NOEUDS = {  # nœud du schéma -> app
    "CORE": "core", "ACC": "accounts", "AUDIT": "audit", "PARAM": "parametres", "SAUV": "sauvegardes",
    "HR": "hr", "DRV": "drivers", "CUST": "customers", "FLEET": "fleet",
    "MISSION": "missions", "FUEL": "fuel", "GARAGE": "garage", "INV": "inventory",
    "BILL": "billing", "FIN": "finance", "ACCT": "accounting",
    "NOTIF": "notifications", "DASH": "dashboard", "IMPORT": "importation",
    "APIV1": "api", "MOBAPI": "mobile_api",
}


def dependances() -> dict[str, set[str]]:
    apps = {p.name for p in (RACINE / "apps").iterdir() if (p / "apps.py").exists()}
    graphe = {app: set() for app in apps}
    for app in apps:
        for fichier in (RACINE / "apps" / app).rglob("*.py"):
            if "tests" in fichier.parts or "migrations" in fichier.parts:
                continue
            for autre in re.findall(r"(?:from|import)\s+apps\.(\w+)", fichier.read_text(encoding="utf-8")):
                if autre != app and autre in apps:
                    graphe[app].add(autre)
    return graphe


def test_aucune_dependance_circulaire_entre_apps():
    graphe, etat = dependances(), {}

    def visiter(app, chemin):
        etat[app] = "en cours"
        for autre in graphe[app]:
            assert etat.get(autre) != "en cours", "cycle : " + " -> ".join([*chemin, app, autre])
            if autre not in etat:
                visiter(autre, [*chemin, app])
        etat[app] = "fait"

    for app in sorted(graphe):
        if app not in etat:
            visiter(app, [])


def test_le_schema_d_architecture_decrit_les_dependances_reelles():
    texte = (RACINE / "architecture.md").read_text(encoding="utf-8")
    schema = texte.split("## 3. VUE COMPOSANTS", 1)[1].split("```", 2)[1]
    documentees = {(NOEUDS[a], NOEUDS[b]) for a, b in re.findall(r"^\s*(\w+) --> (\w+)\s*$", schema, re.M)}
    reelles = {(dep, app) for app, deps in dependances().items() for dep in deps if dep not in SOCLE}

    assert not reelles - documentees, f"dépendances absentes du schéma : {sorted(reelles - documentees)}"
    assert not documentees - reelles, f"flèches du schéma sans import réel : {sorted(documentees - reelles)}"
````

#### `apps/core/tests/test_cloudflare.py`

*94 lignes* — Derrière Cloudflare (cahier-des-charges.md:295 « CDN Cloudflare » ; décision du 13/10/2026, audit TECH-71).

```python
"""Derrière Cloudflare (cahier-des-charges.md:295 « CDN Cloudflare » ; décision du 13/10/2026, audit TECH-71)."""

import ipaddress
import re
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.core.middleware import get_client_ip

NGINX = Path(settings.BASE_DIR) / "nginx"

# Liste officielle relevée le 13/10/2026 (https://www.cloudflare.com/ips/).
PLAGES_CLOUDFLARE = {
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22", "141.101.64.0/18", "108.162.192.0/18",
    "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22", "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
    "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22", "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32",
    "2405:b500::/32", "2405:8100::/32", "2a06:98c0::/29", "2c0f:f248::/32",
}


def _sans_commentaires(texte: str) -> str:
    return "\n".join(ligne.split("#")[0] for ligne in texte.splitlines())


def _configuration_nginx() -> str:
    return _sans_commentaires((NGINX / "nginx.conf").read_text(encoding="utf-8"))


def test_nginx_ne_croit_la_vraie_adresse_que_venant_de_cloudflare():
    conf = _sans_commentaires((NGINX / "cloudflare-ips.conf").read_text(encoding="utf-8"))
    plages = re.findall(r"set_real_ip_from\s+(\S+);", conf)

    assert set(plages) == PLAGES_CLOUDFLARE
    for plage in plages:
        reseau = ipaddress.ip_network(plage)  # plage valide
        assert reseau.is_global and reseau.prefixlen >= 13  # jamais 0.0.0.0/0 ni un réseau privé
    assert re.search(r"^\s*real_ip_header CF-Connecting-IP;", conf, re.M)
    assert "real_ip_recursive" not in conf  # on prend l'adresse donnée par Cloudflare, rien d'écrit par le client


def test_la_liste_est_incluse_avant_les_limites_et_embarquee_dans_l_image():
    conf = _configuration_nginx()
    http = conf.split("http {", 1)[1]

    assert http.index("include /etc/nginx/cloudflare-ips.conf;") < http.index("limit_req_zone")
    assert "COPY cloudflare-ips.conf /etc/nginx/cloudflare-ips.conf" in (NGINX / "Dockerfile").read_text(encoding="utf-8")


def test_seuls_les_fichiers_statiques_sont_publics_pour_le_cache():
    conf = _configuration_nginx()
    statiques = conf.split("location /static/ {", 1)[1].split("}", 1)[0]

    assert 'add_header Cache-Control "public, max-age=2592000, immutable";' in statiques
    assert conf.count("public") == 1


def test_le_defi_lets_encrypt_est_aussi_servi_en_https():
    https = _configuration_nginx().split("listen 443 ssl;", 1)[1]

    assert "location /.well-known/acme-challenge/ {" in https


def test_le_script_de_mise_a_jour_ne_remplace_la_liste_que_si_elle_est_valide():
    script = (NGINX / "maj-ips-cloudflare.sh").read_text(encoding="utf-8")

    assert "set -eu" in script and "https://www.cloudflare.com/ips-v4" in script and "https://www.cloudflare.com/ips-v6" in script
    assert "liste inattendue" in script and script.index("liste inattendue") < script.index('mv "${TEMP}" "${CIBLE}"')


@pytest.mark.django_db
def test_les_pages_de_l_application_ne_vont_jamais_dans_un_cache_partage(client):
    assert "private" in client.get(reverse("accounts:login"))["Cache-Control"]
    client.force_login(UserFactory(is_superuser=True))
    assert "private" in client.get(reverse("home"))["Cache-Control"]
    assert "private" in client.get(reverse("hr:personnel_imprimer"))["Cache-Control"]


@pytest.mark.django_db
def test_une_politique_de_cache_deja_posee_est_gardee(client):
    """Le service worker du chauffeur garde « no-cache » ; seules les réponses muettes reçoivent « private »."""
    assert client.get(reverse("chauffeur:sw"))["Cache-Control"] == "no-cache"


def test_l_adresse_transmise_par_nginx_est_celle_du_visiteur(rf, settings):
    """Nginx a remplacé l'adresse de Cloudflare par celle du visiteur et l'a ajoutée en fin de X-Forwarded-For :
    Django la lit avec TRUSTED_PROXY_COUNT=1, même si le visiteur a écrit une fausse adresse en tête de liste."""
    settings.TRUSTED_PROXY_COUNT = 1
    requete = rf.get("/", HTTP_X_FORWARDED_FOR="10.9.9.9, 41.202.1.7, 41.202.1.7", REMOTE_ADDR="172.18.0.5")

    assert get_client_ip(requete) == "41.202.1.7"
```

#### `apps/core/tests/test_deploiement.py`

*36 lignes* — Réglages de déploiement sûrs par défaut — audits TECH-47 et TECH-49.

```python
"""Réglages de déploiement sûrs par défaut — audits TECH-47 et TECH-49."""

from pathlib import Path

RACINE = Path(__file__).resolve().parents[3]


def test_les_points_d_entree_des_serveurs_partent_sur_la_production_par_defaut():
    for fichier in ("config/wsgi.py", "config/asgi.py", "config/celery.py"):
        texte = (RACINE / fichier).read_text(encoding="utf-8")
        assert "config.settings.prod" in texte and "config.settings.dev" not in texte, fichier


def test_les_secrets_ne_partent_pas_dans_l_image_docker():
    exclus = (RACINE / ".dockerignore").read_text(encoding="utf-8").split()

    for secret in ("certs/", "*.pem", "*.key", "COMPTES-ESSAI.md", ".env"):
        assert secret in exclus, secret


def test_le_verrou_couvre_chaque_paquet_de_production_et_l_image_l_utilise():
    """Audit TECH-84 : versions exactes figées, pour des constructions de l'image reproductibles."""
    import re

    verrou = {
        ligne.split("==")[0]
        for ligne in (RACINE / "requirements" / "prod.lock").read_text(encoding="utf-8").splitlines()
        if "==" in ligne and not ligne.startswith("#")
    }
    for fichier in ("base.txt", "prod.txt"):
        for ligne in (RACINE / "requirements" / fichier).read_text(encoding="utf-8").splitlines():
            ligne = ligne.split("#", 1)[0].strip()
            if ligne and not ligne.startswith("-r"):
                nom = re.split(r"[\[<>=!~ ]", ligne, maxsplit=1)[0].lower().replace("_", "-")
                assert nom in verrou, f"{nom} absent de requirements/prod.lock"
    assert "-c requirements/prod.lock" in (RACINE / "Dockerfile").read_text(encoding="utf-8")
```

#### `apps/core/tests/test_mesures.py`

*195 lignes* — Mesures techniques pour Prometheus (cahier-des-charges.md:256 ; décision du 13/10/2026, audit TECH-24).

```python
"""Mesures techniques pour Prometheus (cahier-des-charges.md:256 ; décision du 13/10/2026, audit TECH-24)."""

import re
from datetime import timedelta
from pathlib import Path
from unittest import mock

import pytest
import yaml
from django.conf import settings
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.core import mesures
from apps.sauvegardes import services as sauvegardes

pytestmark = pytest.mark.django_db

JETON = "jeton-de-test-0123456789"
RACINE = Path(settings.BASE_DIR)
# Une ligne de mesure : nom{étiquettes} valeur (format texte de Prometheus 0.0.4).
LIGNE = re.compile(r'^[a-zA-Z_:][a-zA-Z0-9_:]*(\{([a-zA-Z_][a-zA-Z0-9_]*="(\\.|[^"\\])*",?)*\})? -?[0-9.e+Inf]+$')


@pytest.fixture(autouse=True)
def _cache_vide(settings):
    settings.METRIQUES_JETON = JETON
    cache.clear()
    yield
    cache.clear()


def _lire(client, jeton=JETON):
    entetes = {"HTTP_AUTHORIZATION": f"Bearer {jeton}"} if jeton is not None else {}
    return client.get(mesures.CHEMIN, **entetes)


def _valeurs(texte: str) -> dict[str, float]:
    return {ligne.rsplit(" ", 1)[0]: float(ligne.rsplit(" ", 1)[1]) for ligne in texte.splitlines() if not ligne.startswith("#")}


def test_les_requetes_sont_comptees_par_ecran_methode_et_statut(client):
    client.get(reverse("accounts:login"))
    client.get(reverse("accounts:login"))
    client.post(reverse("accounts:login"), {"username": "personne", "password": "x"})
    client.get("/adresse-inconnue/")

    valeurs = _valeurs(_lire(client).content.decode())

    assert valeurs['erp_requetes_total{vue="accounts:login",methode="GET",statut="2xx"}'] == 2
    assert valeurs['erp_requetes_total{vue="accounts:login",methode="POST",statut="2xx"}'] == 1
    assert valeurs['erp_requetes_total{vue="aucune",methode="GET",statut="4xx"}'] == 1
    assert valeurs['erp_requete_duree_secondes_count'] == 4 and valeurs['erp_requete_duree_secondes_bucket{le="+Inf"}'] == 4
    assert valeurs['erp_vue_duree_secondes_total{vue="accounts:login"}'] > 0


def test_l_histogramme_est_cumulatif(client):
    for duree in (0.01, 0.3, 3, 30):
        mesures.enregistrer_requete("accounts:login", "GET", 200, duree)

    valeurs = _valeurs(_lire(client).content.decode())

    assert valeurs['erp_requete_duree_secondes_bucket{le="0.05"}'] == 1
    assert valeurs['erp_requete_duree_secondes_bucket{le="0.5"}'] == 2
    assert valeurs['erp_requete_duree_secondes_bucket{le="5"}'] == 3
    assert valeurs['erp_requete_duree_secondes_bucket{le="10"}'] == 3
    assert valeurs['erp_requete_duree_secondes_bucket{le="+Inf"}'] == 4
    assert valeurs["erp_requete_duree_secondes_sum"] == pytest.approx(33.31)


def test_les_erreurs_serveur_sont_classees_5xx():
    mesures.enregistrer_requete("accounts:login", "PATCH", 503, 0.1)

    assert 'erp_requetes_total{vue="accounts:login",methode="autre",statut="5xx"} 1' in mesures.exposition()


def test_le_format_est_lisible_par_prometheus(client):
    client.get(reverse("accounts:login"))

    reponse = _lire(client)

    assert reponse["Content-Type"] == "text/plain; version=0.0.4; charset=utf-8"
    assert reponse["Cache-Control"] == "no-store"
    noms_declares = set()
    for ligne in reponse.content.decode().splitlines():
        if ligne.startswith("# TYPE "):
            _, _, nom, sorte = ligne.split(" ")
            assert sorte in ("counter", "gauge", "histogram") and nom not in noms_declares
            noms_declares.add(nom)
        elif not ligne.startswith("# HELP "):
            assert LIGNE.match(ligne), ligne
    assert {"erp_requetes_total", "erp_requete_duree_secondes", "erp_base_de_donnees_disponible",
            "erp_cache_disponible", "erp_pdf_en_preparation"} <= noms_declares


def test_les_jauges_du_socle(client):
    valeurs = _valeurs(_lire(client).content.decode())

    assert valeurs["erp_base_de_donnees_disponible"] == 1 and valeurs["erp_cache_disponible"] == 1
    assert valeurs["erp_pdf_en_preparation"] == 0
    assert "erp_celery_file_attente" not in valeurs  # pas de courtier en test (tâches exécutées sur place)


def test_une_jauge_en_panne_est_omise_sans_casser_les_autres(client):
    mesures.enregistrer_jauge("erp_essai_en_panne", "Essai.", mock.Mock(side_effect=RuntimeError("panne")))
    try:
        texte = _lire(client).content.decode()
    finally:
        mesures._JAUGES[:] = [j for j in mesures._JAUGES if j[0] != "erp_essai_en_panne"]

    assert "erp_essai_en_panne" not in texte and "erp_base_de_donnees_disponible 1" in texte


def test_une_panne_du_cache_ne_bloque_aucune_requete(client):
    with mock.patch.object(mesures.cache, "incr", side_effect=ConnectionError("Redis arrêté")):
        assert client.get(reverse("accounts:login")).status_code == 200


def test_sans_le_bon_jeton_rien_n_est_publie(client):
    client.force_login(UserFactory(is_superuser=True))  # même connecté en administrateur

    assert _lire(client, jeton=None).status_code == 401
    assert _lire(client, jeton="faux").status_code == 401
    assert b"erp_" not in _lire(client, jeton="faux").content


def test_sans_jeton_configure_l_adresse_n_existe_pas(client, settings):
    settings.METRIQUES_JETON = ""

    assert _lire(client, jeton="").status_code == 404


def test_prometheus_lit_les_mesures_sans_nom_de_domaine_ni_https(client, settings):
    """Prometheus appelle web:8000 en HTTP : ni ALLOWED_HOSTS ni la redirection HTTPS ne doivent l'en empêcher."""
    settings.ALLOWED_HOSTS = ["erp.densourcegroup.ci"]
    settings.SECURE_SSL_REDIRECT = True

    reponse = client.get(mesures.CHEMIN, HTTP_HOST="web:8000", HTTP_AUTHORIZATION=f"Bearer {JETON}")

    assert reponse.status_code == 200 and b"erp_requetes_total" in reponse.content


def test_tous_les_ecrans_sont_connus():
    noms = mesures.noms_des_vues()

    assert "accounts:login" in noms and "home" in noms and "missions:detail" in noms
    assert noms[-2:] == (mesures.SANS_NOM, mesures.AUCUNE)


def test_age_de_la_derniere_sauvegarde(settings):
    maintenant = timezone.now()
    settings.SAUVEGARDES_SURVEILLEES = True
    with mock.patch.object(sauvegardes, "derniere_reussie", return_value={"fin": maintenant - timedelta(hours=3)}):
        assert sauvegardes.age_derniere_sauvegarde(maintenant=maintenant) == 3 * 3600
    with mock.patch.object(sauvegardes, "derniere_reussie", return_value=None):
        assert sauvegardes.age_derniere_sauvegarde() is None
    settings.SAUVEGARDES_SURVEILLEES = False
    assert sauvegardes.age_derniere_sauvegarde() is None


def test_la_jauge_de_sauvegarde_est_enregistree():
    assert "erp_sauvegarde_age_secondes" in [nom for nom, _, _ in mesures._JAUGES]


def test_le_middleware_passe_en_premier():
    assert settings.MIDDLEWARE[0] == "apps.core.mesures.MesuresMiddleware"


def test_nginx_refuse_les_mesures_depuis_internet():
    conf = (RACINE / "nginx/nginx.conf").read_text(encoding="utf-8")

    bloc = conf.split("location ^~ /metriques {", 1)[1].split("}", 1)[0]
    assert "return 404;" in bloc


def test_prometheus_est_configure_et_ses_alertes_portent_sur_des_mesures_publiees():
    compose = yaml.safe_load((RACINE / "docker-compose.yml").read_text(encoding="utf-8"))
    service = compose["services"]["prometheus"]
    assert service["ports"] == ["127.0.0.1:9090:9090"]  # jamais exposé sur Internet
    assert re.fullmatch(r"prom/prometheus:v\d+\.\d+\.\d+", service["image"])  # version figée
    assert "prometheus_data" in compose["volumes"]

    configuration = yaml.safe_load((RACINE / "ops/prometheus.yml").read_text(encoding="utf-8"))
    erp = next(job for job in configuration["scrape_configs"] if job["job_name"] == "erp")
    assert erp["metrics_path"] == mesures.CHEMIN and erp["static_configs"][0]["targets"] == ["web:8000"]
    assert erp["authorization"]["credentials_file"] == "/prometheus/jeton"
    assert "/prometheus/jeton" in " ".join(service["command"])

    alertes = yaml.safe_load((RACINE / "ops/prometheus-alertes.yml").read_text(encoding="utf-8"))
    expressions = " ".join(regle["expr"] for groupe in alertes["groups"] for regle in groupe["rules"])
    publiees = set(re.findall(r"^# TYPE (\S+)", mesures.exposition(), re.M)) | {"erp_celery_file_attente", "erp_sauvegarde_age_secondes", "up"}
    for nom in set(re.findall(r"\b(erp_[a-z_]+|up)\b", expressions)):
        assert re.sub(r"_(bucket|sum|count)$", "", nom) in publiees, nom
```

#### `apps/core/tests/test_pdf_tache_de_fond.py`

*184 lignes* — PDF préparés en tâche de fond par Celery (cahier-des-charges.md:294 ; décision du 13/10/2026, audit TECH-70).

```python
"""PDF préparés en tâche de fond par Celery (cahier-des-charges.md:294 ; décision du 13/10/2026, audit TECH-70)."""

import json
import os
from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.core import documents_pdf, pdf
from apps.core.models import DocumentPdf, StatutDocumentPdf
from apps.hr.tests.factories import PersonnelFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def en_tache_de_fond(settings, tmp_path):
    settings.PDF_EN_TACHE_DE_FOND = True
    settings.MEDIA_ROOT = tmp_path
    return settings


@pytest.fixture
def admin(client):
    utilisateur = UserFactory(is_superuser=True)
    client.force_login(utilisateur)
    return utilisateur


def _demander(client, capture, **parametres):
    """Clic sur « Télécharger en PDF » ; ``capture`` exécute la tâche confiée à Celery après la transaction."""
    with capture(execute=True):
        return client.get(reverse("hr:personnel_imprimer"), {"format": "pdf", **parametres})


def test_les_blocs_passent_par_json_sans_rien_perdre():
    blocs = [
        pdf.Section("Actif"),
        pdf.Texte("3 lignes", discret=True),
        pdf.Tableau(entetes=["Compte", "Solde"], lignes=[["411000", Decimal("1250.50")], ["521000", None]],
                    alignes_a_droite={1}, total=["Total", 1250], largeurs=[2, 1]),
        pdf.Rubriques([("Encaissé", "1 000 FCFA")]),
    ]

    relus = pdf.blocs_depuis_donnees(json.loads(json.dumps(pdf.blocs_vers_donnees(blocs))))

    assert relus[:2] == blocs[:2] and relus[3] == blocs[3]
    assert relus[2] == pdf.Tableau(entetes=["Compte", "Solde"], lignes=[["411000", "1250.50"], ["521000", None]],
                                   alignes_a_droite={1}, total=["Total", "1250"], largeurs=[2, 1])


def test_un_type_de_bloc_inconnu_est_refuse():
    with pytest.raises(KeyError):
        pdf.blocs_depuis_donnees([{"type": "Script", "texte": "x"}])


def test_sans_worker_le_pdf_est_rendu_dans_la_requete(client, admin, settings):
    settings.PDF_EN_TACHE_DE_FOND = False

    reponse = client.get(reverse("hr:personnel_imprimer"), {"format": "pdf"})

    assert reponse["Content-Type"] == "application/pdf" and not DocumentPdf.objects.exists()


def test_le_pdf_est_prepare_par_le_worker_puis_telecharge(client, admin, en_tache_de_fond, django_capture_on_commit_callbacks):
    PersonnelFactory(nom="Kone")

    reponse = _demander(client, django_capture_on_commit_callbacks, q="Kone")

    document = DocumentPdf.objects.get()
    assert reponse.status_code == 302 and reponse.url == reverse("document_pdf", args=[document.cle])
    assert document.statut == StatutDocumentPdf.PRET and document.parametres == {}  # données effacées
    assert document.url_retour == reverse("hr:personnel_imprimer") + "?q=Kone"  # sans format=pdf
    page = client.get(reponse.url).content.decode()
    assert "Votre PDF est prêt" in page and reverse("document_pdf_telecharger", args=[document.cle]) in page
    fichier = client.get(reverse("document_pdf_telecharger", args=[document.cle]))
    assert fichier["Content-Type"] == "application/pdf"
    assert fichier["Content-Disposition"].startswith('attachment; filename="personnel-20')
    assert b"".join(fichier.streaming_content).startswith(b"%PDF")


def test_la_page_se_recharge_tant_que_le_pdf_se_prepare(client, admin, en_tache_de_fond):
    with mock.patch("apps.core.tasks.generer_document_pdf.delay"):
        reponse = client.get(reverse("hr:personnel_imprimer"), {"format": "pdf"}, follow=True)

    page = reponse.content.decode()
    assert "Préparation de votre PDF" in page and 'http-equiv="refresh" content="2"' in page
    document = DocumentPdf.objects.get()
    assert client.get(reverse("document_pdf_telecharger", args=[document.cle])).status_code == 404


def test_un_worker_arrete_est_signale_au_lieu_d_attendre_sans_fin(client, admin):
    document = DocumentPdf.objects.create(demande_par=admin, titre="Personnel", nom_fichier="personnel.pdf")
    DocumentPdf.objects.filter(pk=document.pk).update(created_at=timezone.now() - timedelta(minutes=6))

    page = client.get(reverse("document_pdf", args=[document.cle])).content.decode()

    assert "semble arrêté" in page and "http-equiv" not in page


def test_un_echec_de_mise_en_page_est_annonce(client, admin, en_tache_de_fond, django_capture_on_commit_callbacks):
    with mock.patch.object(pdf, "generer_pdf", side_effect=ValueError("police absente")):
        reponse = _demander(client, django_capture_on_commit_callbacks)

    document = DocumentPdf.objects.get()
    assert document.statut == StatutDocumentPdf.ECHEC and "police absente" in document.erreur
    assert "n'a pas pu être fabriqué" in client.get(reponse.url).content.decode()


def test_seul_le_demandeur_voit_et_telecharge_son_pdf(client, admin, en_tache_de_fond, django_capture_on_commit_callbacks):
    _demander(client, django_capture_on_commit_callbacks)
    document = DocumentPdf.objects.get()

    client.force_login(UserFactory(is_superuser=True))  # même un autre administrateur

    assert client.get(reverse("document_pdf", args=[document.cle])).status_code == 404
    assert client.get(reverse("document_pdf_telecharger", args=[document.cle])).status_code == 404
    client.logout()
    assert client.get(reverse("document_pdf", args=[document.cle])).status_code == 302  # vers la connexion


def test_le_fichier_n_est_pas_servi_par_les_medias_proteges(client, admin, en_tache_de_fond, django_capture_on_commit_callbacks):
    _demander(client, django_capture_on_commit_callbacks)
    document = DocumentPdf.objects.get()

    assert client.get(reverse("media", args=[document.fichier.name])).status_code == 404


def test_derriere_nginx_le_fichier_part_par_x_accel_redirect(client, admin, en_tache_de_fond, django_capture_on_commit_callbacks):
    _demander(client, django_capture_on_commit_callbacks)
    document = DocumentPdf.objects.get()
    en_tache_de_fond.MEDIA_ACCEL_REDIRECT = True

    reponse = client.get(reverse("document_pdf_telecharger", args=[document.cle]))

    assert reponse["X-Accel-Redirect"] == f"/medias-internes/pdf-generes/{document.cle}.pdf"
    assert reponse["Cache-Control"] == "private, no-store"


def test_rejouer_la_tache_ne_refait_rien(admin, en_tache_de_fond):
    document = DocumentPdf.objects.create(
        demande_par=admin, titre="Vide", nom_fichier="vide.pdf", statut=StatutDocumentPdf.PRET,
    )

    with mock.patch.object(pdf, "generer_pdf") as generer:
        documents_pdf.preparer(document.pk)

    generer.assert_not_called()


def test_les_pdf_de_plus_d_un_jour_sont_effaces_avec_leur_fichier(client, admin, en_tache_de_fond, django_capture_on_commit_callbacks):
    _demander(client, django_capture_on_commit_callbacks)
    _demander(client, django_capture_on_commit_callbacks)
    ancien, recent = DocumentPdf.objects.order_by("pk")
    DocumentPdf.objects.filter(pk=ancien.pk).update(created_at=timezone.now() - timedelta(hours=25))
    chemin = ancien.fichier.path

    assert documents_pdf.purger() == 1

    assert list(DocumentPdf.objects.all()) == [recent]
    assert not os.path.exists(chemin)


def test_les_taches_quotidiennes_purgent_les_pdf():
    from apps.notifications.taches import executer_taches_quotidiennes

    assert executer_taches_quotidiennes()["pdf_purges"] == 0


def test_la_production_confie_les_pdf_au_worker():
    from pathlib import Path

    from django.conf import settings

    prod = (Path(settings.BASE_DIR) / "config/settings/prod.py").read_text(encoding="utf-8")
    compose = (Path(settings.BASE_DIR) / "docker-compose.yml").read_text(encoding="utf-8")
    assert 'PDF_EN_TACHE_DE_FOND = env.bool("PDF_EN_TACHE_DE_FOND", default=True)' in prod
    worker = compose.split("celery_worker:")[1].split("celery_beat:")[0]
    assert "media_data:/app/media" in worker  # sinon le worker écrirait dans un dossier que `web` ne voit pas
```

#### `apps/sauvegardes/tests/test_scripts.py`

*47 lignes* — Scripts de sauvegarde (ops/) : le mot de passe de la base ne doit jamais apparaître dans la liste des processus

```python
"""Scripts de sauvegarde (ops/) : le mot de passe de la base ne doit jamais apparaître dans la liste des processus
(audit AUD-18). Exécutés seulement si bash est disponible."""

import shutil
import subprocess
from pathlib import Path

import pytest
from django.conf import settings

BASH = shutil.which("bash")
FONCTIONS = Path(settings.BASE_DIR) / "ops" / "fonctions-sauvegarde.sh"

pytestmark = pytest.mark.skipif(BASH is None, reason="bash absent")


def _executer(script: str) -> list[str]:
    resultat = subprocess.run(
        [BASH, "-c", f". '{FONCTIONS.as_posix()}'\n{script}"], capture_output=True, text=True, check=True
    )
    return resultat.stdout.splitlines()


def test_le_mot_de_passe_quitte_l_url_pour_un_fichier_pgpass_prive():
    url, pgpass, droits = _executer(
        "preparer_connexion 'postgres://erp:p%40ss:w\\rd@db:5432/erp_densource'\n"
        'echo "$URL_SANS_MOT_DE_PASSE"; cat "$PGPASSFILE"; stat -c %a "$PGPASSFILE"; supprimer_temporaires'
    )

    assert url == "postgres://erp@db:5432/erp_densource"
    assert pgpass == "*:*:*:*:p@ss\\:w\\\\rd"  # %40 décodé ; « : » et « \\ » échappés (format .pgpass)
    assert droits == "600"


def test_une_url_sans_mot_de_passe_reste_telle_quelle():
    (url,) = _executer("preparer_connexion 'postgres://erp@db/erp'; echo \"$URL_SANS_MOT_DE_PASSE${PGPASSFILE:-}\"")

    assert url == "postgres://erp@db/erp"


def test_les_fichiers_temporaires_sont_supprimes():
    (restant,) = _executer(
        "SAUVEGARDE_PASSPHRASE=secret; preparer_phrase_de_passe; preparer_connexion 'postgres://a:b@h/d'\n"
        'supprimer_temporaires; ls "$SAUVEGARDE_PASSPHRASE_FILE" "$PGPASSFILE" 2>/dev/null | wc -l'
    )

    assert restant.strip() == "0"
```

```bash
python -m pytest apps/core/tests/test_architecture.py apps/core/tests/test_cloudflare.py apps/core/tests/test_deploiement.py apps/core/tests/test_mesures.py apps/core/tests/test_pdf_tache_de_fond.py apps/sauvegardes/tests/test_scripts.py -q --no-cov
```

**Résultat attendu :** `46 passed` (pour les 6 fichier(s) de tests présentés dans ce chapitre).

## Étape 3 — Les vérifications d'ensemble

**Aucune migration ne doit manquer** (les modèles et la base sont d'accord) :

```bash
python manage.py makemigrations --check --dry-run
```

**Résultat attendu :** `No changes detected`.

**Le contrôle Django** :

```bash
python manage.py check
```

**Résultat attendu :** `System check identified no issues (0 silenced).`

**Tous les tests** (environ une minute) :

```bash
python -m pytest -q --no-cov
```

**Résultat attendu :** `3415 passed` (tous les tests du projet).
**La couverture des tests** (quelle part du code est exécutée par les tests) :

```bash
python -m pytest -q --cov=apps --cov-report=term-missing:skip-covered
```

**Résultat attendu :** une ligne `TOTAL` proche de **99 %**. Les quelques lignes non couvertes sont listées : ce sont
des branches d'erreur rares (l'administration Django, quelques cas limites).

**La page de connexion et le tableau de bord :**

```bash
python manage.py runserver
```

Ouvrez **http://localhost:8000**, connectez-vous avec chacun des sept comptes d'essai et parcourez le menu de chacun.
Vous avez maintenant reconstruit **toute** l'application.

## Étape 4 — Créer votre premier vrai administrateur

Les comptes `demo_*` ne servent qu'au développement (la commande qui les crée **refuse de tourner** hors
développement). Pour un vrai compte :

```bash
python manage.py createsuperuser
```

Un superutilisateur agit comme **ADMIN** (`role_effectif`). À sa première connexion, la **double authentification**
lui sera demandée : activez-la **immédiatement** (un mot de passe volé avant l'activation permettrait à un tiers
d'enrôler son propre téléphone).

## Étape 5 — Comparer avec le projet de référence

Si vous avez le dépôt de référence, vous pouvez **comparer** vos fichiers, sans rien modifier :

```bash
git diff --no-index --stat chemin/vers/reference/apps apps
```

(Les fichiers de migration, générés par `makemigrations`, peuvent porter des noms différents : c'est normal, seuls
les modèles comptent.)

**Vous pouvez aussi faire rejouer ce tutoriel.** Les outils qui l'ont produit vivent dans le dossier `outils/` du
dépôt de référence :

| Commande | Effet |
|---|---|
| `python outils/generer_tutoriel.py` | régénère les chapitres à partir des sources et du code |
| `python outils/tester_tutoriel.py` | **reconstruit** le projet chapitre par chapitre dans un dossier vide et lance les commandes du tutoriel |
| `python outils/tester_tutoriel.py --source tutoriel` | idem, mais **à partir du code qui figure dans les chapitres** (et non du dépôt) : prouve que le tutoriel est exact |

## Ce que vous avez construit

| Domaine | Réalisation |
|---|---|
| **Socle** | `core` (suppression logique, numérotation, recherche, registres, sécurité HTTP) |
| **Sécurité** | `accounts` (7 rôles, garde, MFA, anti force brute, Argon2), `audit` (journal inaltérable), CSP, ressources locales |
| **Métier** | `hr`, `drivers`, `customers`, `fleet`, `missions`, `garage`, `inventory`, `fuel`, `billing`, `finance`, `accounting` |
| **Pilotage** | `notifications`, `dashboard` |
| **Terrain** | `mobile_api` (PWA du chauffeur, codes QR) |
| **Ouverture** | `api` (REST, JWT + MFA, documentation) |
| **Reprise de données** | `importation` (import Excel des données par l'administrateur) |

## Ce qui n'est pas dans ce tutoriel : la mise en production

Volontairement, ce tutoriel s'arrête au **développement** : base SQLite, un seul processus. Une mise en
production demande encore (les « lots 2 et 3 » de l'étape 7 du cahier des charges) :

- **PostgreSQL** à la place de SQLite : pour les verrous de ligne effectifs, la recherche sans accents native, les triggers
  des journaux append-only et les performances. Toute la suite de tests a été rejouée sur PostgreSQL (elle y a révélé un défaut de
  la recherche du journal d'audit, corrigé) ;
- **Redis** pour le cache partagé (compteurs anti force brute, tableau de bord) et **Celery** pour lancer
  `taches_quotidiennes` chaque jour et envoyer les e-mails en arrière-plan ;
- **Docker, Gunicorn et Nginx** : HTTPS (avec `SECURE_PROXY_SSL_HEADER`), en-têtes, **limitation de débit au niveau
  du serveur**, `collectstatic`. Sur un serveur neuf, Nginx démarre avec un **certificat provisoire** le temps que Let's Encrypt
  délivre le vrai (`nginx/preparer-https.sh`) ;
- **Sauvegardes chiffrées et testées** (phrase de passe par fichier, rotation, copie hors serveur), **supervision** (Sentry) ;
- `config/settings/prod.py` **refuse de démarrer** avec une `SECRET_KEY` par défaut ou trop courte, et `docker-compose.yml`
  n'a aucun mot de passe PostgreSQL par défaut.

Tout cela est décrit pas à pas dans `GUIDE-DEPLOIEMENT.md`, à la racine du dépôt de référence.

Sont aussi **hors périmètre**, sur décision du client : le **mode hors ligne** du chauffeur (saisie sans réseau,
synchronisation différée), l'envoi de SMS et de notifications push, les photos d'incident.

## Aller plus loin

- Ajoutez l'**import Excel** d'autres données (devis, stock de pièces…) sur le modèle de `importation`.
- Écrivez un **nouveau module** en suivant le plan : `models.py` → `services.py` → `tests` → `views.py`
  → `templates`. Le meilleur exercice : un module « Contrats clients » (renouvellement à 30 jours) sur le
  modèle de `fleet`.
- Relisez le code avec le [parcours d'apprentissage](../GUIDE-PARCOURS.md) et le
  [guide de l'interface](../GUIDE-INTERFACE.md) du dépôt de référence.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 33 : README, vérifications d'ensemble"
```

Bravo : vous avez reconstruit l'ERP DEN Source Group de A à Z.

---

[← Chapitre 33](33-importation.md) · [Sommaire](README.md)
