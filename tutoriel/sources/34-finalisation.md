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

{{RESTANTS}}

{{PYTEST}}

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

{{RESULTAT_FINAL}}

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
