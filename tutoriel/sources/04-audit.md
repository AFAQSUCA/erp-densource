## Ce que vous allez construire

**`audit`** : le **journal d'audit**, la mémoire inaltérable de l'ERP. Chaque connexion, chaque création,
modification, suppression ou validation y laisse une trace : **qui**, **quand**, **depuis quelle adresse**,
**quoi**, **avec quelles valeurs avant et après**.

Trois idées à retenir :

| Idée | Réalisation |
|---|---|
| **Le journal ne peut pas être modifié ni effacé** | `AuditLog.save()` refuse toute modification, `delete()` est interdit, l'administration est en lecture seule |
| **Tracer un modèle coûte une ligne** | `audit_model(MonModele, module="…")` dans l'`apps.py` de chaque app |
| **Les secrets n'y entrent jamais** | `audit_model(..., exclure=("code_expediteur",))` retire des champs du journal |

## Prérequis

- Chapitre 3 terminé, `python manage.py migrate` fait (la table `accounts_user` existe).

## Notions Django de ce chapitre

- **Signaux `pre_save` / `post_save`** : Django les émet juste avant et juste après chaque `save()` d'un
  modèle. On s'y abonne pour capturer l'état **avant** puis **après** une modification.
- **`sender=Modele`** : limite l'abonnement à un seul modèle.
- **`weak=False`** : sans cela, Django garde l'abonné par référence *faible* et une fonction définie dans
  une autre fonction peut être ramassée par le ramasse-miettes : l'abonnement disparaîtrait.
- **`dispatch_uid`** : un identifiant qui empêche d'abonner deux fois la même fonction.
- **`JSONField`** : une colonne qui stocke du JSON (les valeurs avant/après sont des dictionnaires).
- **Administration en lecture seule** : on retire les droits d'ajout, de modification et de suppression.

## Étape 1 — Créer l'application

```bash
mkdir -p apps/audit/tests
```

{{VIDES}}

## Étape 2 — Le modèle du journal

{{FICHIER apps/audit/models.py}}

Points clés :

- **14 champs** : date, utilisateur (et son nom recopié : si le compte disparaît, la trace reste
  lisible), rôle, action, module, entité, identifiant de l'entité, valeurs avant/après, adresse IP,
  navigateur, statut (succès/échec).
- **`save()` lève une erreur** si la ligne existe déjà (`self.pk is not None`) : impossible de réécrire
  l'histoire. **`delete()`** est interdit.
- **`on_delete=SET_NULL`** sur l'utilisateur : supprimer un compte n'efface pas ses traces.
- Deux **index** accélèrent les recherches courantes (par entité, par utilisateur et date).

## Étape 3 — Le service et le branchement automatique

{{FICHIER apps/audit/services.py}}

`log_action` est **l'unique porte d'entrée** pour écrire dans le journal. Elle extrait toute seule l'adresse
IP et le navigateur de la requête courante.

{{FICHIER apps/audit/registry.py}}

C'est le cœur du système. `audit_model(Vehicule, module="PARC_AUTO")` branche deux fonctions sur le modèle :

1. **`capturer_avant`** (`pre_save`) : relit la ligne en base et en garde une photo (`_audit_avant`).
2. **`journaliser`** (`post_save`) : compare la photo « avant » à l'état « après ». Si rien n'a changé, elle
   n'écrit **rien**. Sinon elle écrit une ligne `CREATE`, `UPDATE` ou `DELETE` (une suppression logique
   est reconnue à `is_deleted` qui passe à vrai) avec **seulement les champs modifiés**.

`get_current_user()` et `get_current_request()` viennent du middleware du chapitre 2 : c'est ce qui permet de
savoir *qui* a modifié, même depuis un service qui ne reçoit pas la requête.

{{FICHIER apps/audit/signals.py}}

L'app `audit` s'abonne ici aux événements des autres : connexion réussie, déconnexion, connexion échouée
(fournis par Django) et `mfa_evenement` (notre signal du chapitre 3). Remarquez que c'est `audit` qui importe
`accounts`, pas l'inverse : `accounts` ne sait pas que le journal existe.

## Étape 4 — Administration et démarrage

{{FICHIER apps/audit/admin.py}}

Dans l'administration, le journal est en **lecture seule pour tout le monde** (même l'ADMIN). Il se lit
depuis `/admin/audit/auditlog/`. Seuls un superutilisateur, un ADMIN ou une DIRECTION peuvent le *voir* ; la
DIRECTION doit en plus avoir l'accès à l'administration (case « statut équipe » cochée sur son compte).

{{FICHIER apps/audit/apps.py}}

## Étape 5 — README et test

{{RESTANTS}}

## Étape 6 — Déclarer l'application et migrer

{{CONFIG}}

```bash
python manage.py makemigrations audit
python manage.py migrate
```

**Résultat attendu :** `Create model AuditLog`, puis `Applying audit.0001_initial... OK`.

## Vérifier le chapitre

```bash
python manage.py check
```

{{PYTEST}}

**Essai réel.** Le journal se remplit tout seul dès qu'un modèle est branché. Ouvrez le shell, créez un
utilisateur et regardez si la connexion échouée est tracée :

```bash
python manage.py shell -c "from apps.audit.services import log_action; from apps.audit.models import AuditLog, ActionChoices; e = log_action(action=ActionChoices.LOGIN, module='AUTH', entite='User'); print(e.date_heure is not None, AuditLog.objects.count())"
```

**Résultat attendu :** `True 1`. Essayez ensuite `e.delete()` dans un shell interactif : l'erreur
`AuditLog est append-only : suppression interdite.` apparaît.

> **Nettoyage.** Cette ligne d'essai restera dans votre journal de développement : c'est normal, on ne peut pas
> l'effacer (c'est le but !). Si vous voulez repartir d'une base propre, supprimez `db.sqlite3` et relancez
> `python manage.py migrate`.

## Ce qu'il faut retenir

- Un journal d'audit **se protège lui-même** : il n'existe aucune fonction pour le modifier.
- Le **branchement par signaux** rend la traçabilité automatique : les développeurs des autres apps n'écrivent
  jamais dans le journal à la main.
- **Dépendances à sens unique** : `audit` connaît `accounts`, jamais l'inverse.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 4 : app audit (journal inaltérable, audit automatique des modèles)"
```
