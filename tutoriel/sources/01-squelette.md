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

{{VIDES}}

## Étape 2 — Les dépendances

Créez les trois fichiers `requirements`. Le principe : `base.txt` liste ce qui sert toujours ; `dev.txt` et
`prod.txt` commencent par `-r base.txt` (« inclure base ») puis ajoutent leurs propres besoins.

{{FICHIER requirements/base.txt}}

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

{{FICHIER requirements/dev.txt}}

`pytest` lance les tests, `pytest-django` le branche sur Django, `pytest-cov` mesure la couverture,
`factory_boy` fabrique des objets de test (chapitre 3).

{{FICHIER requirements/prod.txt}}

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

{{FICHIER .gitignore}}

Ce fichier dit à Git **ce qu'il ne doit jamais versionner** : l'environnement virtuel (`.venv/`), la base de
développement (`db.sqlite3`), les secrets (`.env`), les fichiers générés (`__pycache__/`, `staticfiles/`).

{{FICHIER .env.example}}

`.env.example` est un **modèle** qu'on commite ; le vrai `.env` reste local. Copiez-le :

```bash
cp .env.example .env
```

> Sous PowerShell : `Copy-Item .env.example .env`. Pour un vrai usage, remplacez `SECRET_KEY` par une
> longue valeur aléatoire (`python -c "import secrets; print(secrets.token_urlsafe(60))"`).

## Étape 4 — Le point d'entrée : `manage.py` et les serveurs

{{FICHIER manage.py}}

`os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')` : par défaut, on utilise les
réglages de développement.

{{FICHIER config/wsgi.py}}

{{FICHIER config/asgi.py}}

`wsgi.py` et `asgi.py` sont les portes d'entrée que les serveurs de production (Gunicorn, Uvicorn)
utilisent. Vous n'y touchez jamais, mais Django en a besoin.

## Étape 5 — Les réglages

`settings/base.py` est le fichier le plus long du chapitre. Comme il évolue tout au long du tutoriel
(chaque nouvelle application doit y être déclarée), **voici sa version à ce stade** ; les chapitres suivants
ne montrent que les lignes à ajouter.

{{CONFIG}}

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

{{FICHIER config/settings/dev.py}}

En développement : base **SQLite** (un simple fichier `db.sqlite3`), cache en mémoire, e-mails affichés dans
la console.

{{FICHIER config/settings/test.py}}

Pour les tests : mots de passe hachés **en MD5** (rapide ; jamais en production), aucune double
authentification imposée (les tests qui la vérifient la réactivent), plafonds de limitation très hauts.

{{FICHIER config/settings/prod.py}}

En production : HTTPS obligatoire, cookies sécurisés, base PostgreSQL et Redis fournis par l'environnement.
Ce fichier n'est pas utilisé dans ce tutoriel (voir « Aller plus loin », chapitre 29).

## Étape 6 — Les adresses et la configuration des tests

Le fichier `config/urls.py` est la **table des adresses** du site. Il grossira à chaque écran ajouté ; voici
son état actuel (il figure dans le bloc précédent). La ligne `favicon.ico` redirige le
navigateur vers l'icône du site.

{{FICHIER pytest.ini}}

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
