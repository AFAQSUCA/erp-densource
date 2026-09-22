## Ce que vous allez construire

**`accounts`** : les utilisateurs, leurs **sept rôles** et tout ce qui protège la connexion.

| Élément | À quoi il sert |
|---|---|
| `User` et `Role` | l'utilisateur de l'ERP et son rôle : ADMIN, DIRECTION, RH, CHARGE_CLIENTELE, PARCAUTO, FINANCES, CHAUFFEUR |
| `RoleRequiredMixin` | la **garde** de toutes les vues : refuse l'accès si le rôle n'est pas autorisé |
| `navigation` | le **menu** de gauche, différent selon le rôle, alimenté par un registre |
| `throttle` | **anti force brute** : après trop d'échecs, la connexion est bloquée quelques minutes |
| `mfa` | **double authentification** (application d'authentification + codes de secours), obligatoire pour l'ADMIN et la DIRECTION |
| `middleware` | la **porte** qui refuse tout tant que la double authentification n'est pas passée |

## Prérequis

- Chapitres 1 et 2 terminés (`python -m pytest apps/core -q` est vert).
- Une application d'authentification sur le téléphone n'est pas nécessaire ici ; elle servira au chapitre 16.

## Notions Django de ce chapitre

- **Modèle utilisateur personnalisé** : Django fournit un `User` par défaut. Ici on le remplace par le nôtre
  (avec un champ `role`) grâce au réglage `AUTH_USER_MODEL`. **Il faut le faire avant la première
  migration** : changer plus tard est très pénible. C'est pourquoi on n'a pas encore lancé `migrate`.
- **`AbstractUser`** : la classe de Django qu'on prolonge (elle apporte identifiant, mot de passe haché,
  nom, e-mail, `is_active`, `is_staff`…).
- **Mixin** : une petite classe qui ajoute un comportement à une vue par héritage multiple
  (`class MaVue(RoleRequiredMixin, ListView)`).
- **Décorateur `@receiver`** : abonne une fonction à un **signal** (ici, l'échec d'une connexion).
- **Signal personnalisé** : `Signal()` crée une annonce à laquelle d'autres apps s'abonneront. C'est ainsi
  que `audit` (chapitre 4) sera prévenu sans que `accounts` l'importe.
- **Commande de gestion** : un script lancé par `python manage.py <nom>` (dossier
  `management/commands/`).
- **Fabrique de test (`factory_boy`)** : une classe qui fabrique des objets de test valides en une ligne
  (`UserFactory(role="RH")`).

## Étape 1 — Créer l'application

```bash
mkdir -p apps/accounts/tests apps/accounts/management/commands
```

{{VIDES}}

## Étape 2 — Le modèle utilisateur

{{FICHIER apps/accounts/models.py}}

À retenir :

- **`Role`** est une énumération (`TextChoices`) : la valeur stockée en base (`"ADMIN"`) et le libellé
  affiché (« Administrateur »).
- **`role_effectif`** : un *superutilisateur* Django (créé par `createsuperuser`, sans rôle) agit comme
  ADMIN. Sans cela, le premier compte créé ne verrait aucun écran.
- **`AppareilMFA`** : l'application d'authentification d'un utilisateur (un seul par compte). Le champ
  `dernier_pas` mémorise le dernier code accepté pour qu'**un code ne serve qu'une fois** (anti-rejeu).
- **`CodeSecours`** : on ne garde **jamais** un code de secours en clair, seulement son *empreinte*
  SHA-256. Si la base fuitait, les codes resteraient inutilisables.

## Étape 3 — Les droits et le menu

{{FICHIER apps/accounts/permissions.py}}

Ces classes servent à l'**API** (chapitre 28) : `IsAdmin`, `IsDirection`… décident si un rôle a accès à une
route.

{{FICHIER apps/accounts/mixins.py}}

C'est **le** fichier de sécurité de l'interface web : toute vue qui hérite de `RoleRequiredMixin` et déclare
`roles = ...` refuse (erreur 403) tout utilisateur d'un autre rôle. Masquer un bouton dans le HTML ne protège
rien ; c'est cette garde, **côté serveur**, qui protège.

{{FICHIER apps/accounts/navigation.py}}

Le menu est un **registre** : chaque app (au démarrage, dans son `apps.py`) déclare ses entrées avec
`enregistrer(EntreeMenu(...))`. `accounts` n'importe donc aucune app métier. Une entrée dont l'écran
n'existe pas encore est simplement ignorée : c'est ce qui permet de construire l'interface écran par écran.

## Étape 4 — Anti force brute et double authentification

{{FICHIER apps/accounts/signals.py}}

Deux abonnements aux signaux de connexion de Django : chaque **échec** alimente le compteur anti force
brute ; chaque **nouvelle connexion** oublie la vérification MFA de la session précédente.

`mfa_evenement` est notre propre signal : chaque étape de la double authentification l'émet, et l'app
`audit` (chapitre suivant) l'écoutera pour tout inscrire au journal.

{{FICHIER apps/accounts/throttle.py}}

Le principe : un compteur dans le **cache** (par couple adresse + identifiant, puis par adresse seule).
Une fois le plafond atteint (5 échecs pour un compte, 20 pour une adresse, sur 15 minutes), l'accès reste
refusé **même avec le bon mot de passe** : on ne vérifie même plus. Le message ne révèle pas si le
compte existe.

{{FICHIER apps/accounts/mfa.py}}

La double authentification en quelques mots :

1. À l'activation, on génère un **secret** aléatoire que l'utilisateur scanne (QR code) dans son
   application (Google Authenticator, Microsoft Authenticator…).
2. L'application affiche toutes les 30 secondes un **code à 6 chiffres** calculé à partir du secret et de
   l'heure (norme TOTP). Le serveur recalcule le même code et compare, en **temps constant**
   (`secrets.compare_digest`).
3. Un code déjà utilisé est refusé (`dernier_pas`). Un décalage d'horloge d'un intervalle est toléré.
4. On donne **10 codes de secours** à usage unique, au cas où le téléphone serait perdu.

{{FICHIER apps/accounts/middleware.py}}

La **porte** : à chaque requête, si l'utilisateur est un ADMIN ou une DIRECTION dont la session n'est pas
« vérifiée », on le renvoie vers la saisie du code. C'est un **refus par défaut** : il couvre aussi
l'administration et la documentation de l'API, sans que chaque vue y pense. Les appels d'API avec un jeton
(JWT) ne passent pas ici : la MFA y est contrôlée à l'émission du jeton (chapitre 28).

## Étape 5 — Administration, démarrage et commande de secours

{{FICHIER apps/accounts/admin.py}}

L'**administration Django** (`/admin/`) est une interface générée automatiquement. Ici on lui apprend à
lister les utilisateurs, à réinitialiser la MFA d'un compte (téléphone perdu), et on redirige sa page de
connexion vers celle du site, pour que l'anti force brute et la MFA s'appliquent partout.

{{FICHIER apps/accounts/apps.py}}

{{FICHIER apps/accounts/management/commands/reinitialiser_mfa.py}}

Une **commande de gestion** : `python manage.py reinitialiser_mfa <identifiant>`. Utile quand plus aucun
administrateur ne peut réinitialiser la MFA depuis l'interface.

## Étape 6 — Tests et fabriques

{{FICHIER apps/accounts/tests/factories.py}}

`UserFactory` fabrique un utilisateur valide en une ligne : `UserFactory(role=Role.RH)`. On s'en servira
dans des centaines de tests.

{{FICHIER apps/accounts/tests/helpers_mfa.py}}

{{RESTANTS}}

## Étape 7 — Déclarer l'application dans les réglages

{{CONFIG}}

Trois modifications : `"apps.accounts"` dans `LOCAL_APPS`, **`AUTH_USER_MODEL`** (le point crucial) et la
porte MFA dans `MIDDLEWARE` (juste après `AuthenticationMiddleware`, car elle a besoin de savoir qui est
connecté).

## Étape 8 — Migrations : cette fois, on migre

```bash
python manage.py makemigrations accounts
python manage.py migrate
```

**Résultat attendu :** `makemigrations` liste `Create model User`, `Create model AppareilMFA`,
`Create model CodeSecours` ; `migrate` applique une vingtaine de migrations (`contenttypes`, `auth`,
`admin`, `sessions`, `core`, `accounts`…) et se termine par `OK`. Un fichier `db.sqlite3` apparaît à la
racine : c'est votre base de développement.

> **Si `migrate` échoue avec `InconsistentMigrationHistory`** : une migration a été lancée avec le
> `User` par défaut. Supprimez `db.sqlite3` et relancez `python manage.py migrate` (aucune donnée à perdre
> à ce stade).

## Vérifier le chapitre

```bash
python manage.py check
```

{{PYTEST}}

Les tests de connexion, de MFA et de menu par rôle **ouvrent des pages** et seront présentés plus tard
(chapitres 16 et suivants), quand les écrans existeront.

Petit essai dans le shell : créer un utilisateur et lire son rôle effectif.

```bash
python manage.py shell -c "from apps.accounts.models import User; u = User.objects.create_user('essai', password='Essai-de-mot-de-passe-1', role='RH'); print(u, u.role_effectif, u.check_password('Essai-de-mot-de-passe-1')); u.delete()"
```

**Résultat attendu :** `essai RH True`.

## Ce qu'il faut retenir

- Le **rôle** est un champ de l'utilisateur ; la **garde** est un mixin de vue ; le **menu** est un registre.
- La sécurité d'une connexion se pense en couches : mot de passe (Argon2), limitation d'essais, double
  authentification, session courte.
- Deux apps peuvent collaborer par **signal** sans s'importer.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 3 : app accounts (utilisateurs, 7 rôles, garde d'accès, menu, MFA, anti force brute)"
```
