## Ce que vous allez faire

Vérifier que le projet est **complet et cohérent**, comprendre ce qu'il reste pour une **mise en production**, et savoir
**comparer votre travail** avec le projet de référence.

## Étape 1 — Le README

Le dernier fichier du projet : le `README.md`, qui décrit l'application, ses commandes et son avancement.

{{RESTANTS}}

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
