# Chapitre 29 — Finalisation, vérifications et déploiement

> 1 fichier(s) dans ce chapitre, 132 lignes de code.

## Ce que vous allez faire

Vérifier que le projet est **complet et cohérent**, comprendre ce qu'il reste pour une **mise en production**, et savoir
**comparer votre travail** avec le projet de référence.

## Étape 1 — Le README

Le dernier fichier du projet : le `README.md`, qui décrit l'application, ses commandes et son avancement.

#### `README.md`

*131 lignes* — ERP DEN Source Group

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
- `requirements/` : dépendances par environnement

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
- [x] Étape 4 — Finance (facturation, règlements, dépenses, trésorerie) : sans écritures comptables ni rapprochement bancaire (voir apps/billing/README.md)
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

## Sécurité de la connexion

- **Double authentification** obligatoire pour l'ADMIN et la DIRECTION : à la première connexion, scanner le
  QR code avec une application d'authentification et noter les 10 codes de secours. Téléphone perdu :
  `python manage.py reinitialiser_mfa <identifiant>`.
- **Interface sans CDN** : styles, icônes et Alpine.js sont servis par l'application (`static/`). Après un
  changement de classes Tailwind : `cd frontend && npm install && npm run build`.
- Variables : `TRUSTED_PROXY_COUNT` (1 derrière Nginx), `CSP_REPORT_ONLY` (mise au point de la CSP).
````

## Étape 2 — Les vérifications d'ensemble

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

**Résultat attendu :** `1786 passed` (tous les tests du projet).
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

## Étape 3 — Créer votre premier vrai administrateur

Les comptes `demo_*` ne servent qu'au développement (la commande qui les crée **refuse de tourner** hors
développement). Pour un vrai compte :

```bash
python manage.py createsuperuser
```

Un superutilisateur agit comme **ADMIN** (`role_effectif`). À sa première connexion, la **double authentification**
lui sera demandée : activez-la **immédiatement** (un mot de passe volé avant l'activation permettrait à un tiers
d'enrôler son propre téléphone).

## Étape 4 — Comparer avec le projet de référence

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
| **Métier** | `hr`, `drivers`, `customers`, `fleet`, `missions`, `garage`, `inventory`, `fuel`, `billing`, `finance` |
| **Pilotage** | `notifications`, `dashboard` |
| **Terrain** | `mobile_api` (PWA du chauffeur, codes QR) |
| **Ouverture** | `api` (REST, JWT + MFA, documentation) |

## Ce qui n'est pas dans ce tutoriel : la mise en production

Volontairement, ce tutoriel s'arrête au **développement** : base SQLite, un seul processus. Une mise en
production demande encore (les « lots 2 et 3 » de l'étape 7 du cahier des charges) :

- **PostgreSQL** à la place de SQLite : pour les verrous de ligne effectifs, la recherche sans accents native et les
  performances. La recherche `filtrer_par_texte` a une branche PostgreSQL (`LOWER(TRANSLATE(...))`) écrite mais
  **non testée** sur cette base ;
- **Redis** pour le cache partagé (compteurs anti force brute, tableau de bord) et **Celery** pour lancer
  `taches_quotidiennes` chaque jour et envoyer les e-mails en arrière-plan ;
- **Docker, Gunicorn et Nginx** : HTTPS (avec `SECURE_PROXY_SSL_HEADER`), en-têtes, **limitation de débit au niveau
  du serveur**, `collectstatic` ;
- **Sauvegardes chiffrées et testées**, **supervision** (Sentry) ;
- `config/settings/prod.py` existe déjà (chapitre 1) mais **n'a pas été exercé** : il attend ces briques.

Sont aussi **hors périmètre**, sur décision du client : le **mode hors ligne** du chauffeur (saisie sans réseau,
synchronisation différée), les **écritures comptables** et le **rapprochement bancaire**, l'envoi de SMS et de
notifications push, les photos d'incident.

## Aller plus loin

- Ajoutez un **écran d'administration des utilisateurs** dans l'interface (aujourd'hui : l'administration
  Django).
- Écrivez un **nouveau module** en suivant le plan : `models.py` → `services.py` → `tests` → `views.py`
  → `templates`. Le meilleur exercice : un module « Contrats clients » (renouvellement à 30 jours) sur le
  modèle de `fleet`.
- Relisez le code avec le [parcours d'apprentissage](../GUIDE-PARCOURS.md) et le
  [guide de l'interface](../GUIDE-INTERFACE.md) du dépôt de référence.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 29 : README, vérifications d'ensemble"
```

Bravo : vous avez reconstruit l'ERP DEN Source Group de A à Z.

---

[← Chapitre 28](28-api.md) · [Sommaire](README.md)
