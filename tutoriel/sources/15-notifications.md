## Ce que vous allez construire

**`notifications`** : prévenir **les bonnes personnes au bon moment**. C'est la dernière app « métier » ; elle
est tout en haut du graphe de dépendances : **elle connaît toutes les autres, aucune ne la connaît**. Comment
est-ce possible ? Les autres apps **émettent des signaux** (chapitres 5 à 13) et `notifications` **s'y abonne**.

| Événement | Qui est prévenu |
|---|---|
| congé déposé | le supérieur hiérarchique (N1), avec une alerte urgente s'il y a une mission prévue sur la période |
| congé validé N1 | la RH (N2) ; congé approuvé, refusé ou annulé → l'employé |
| stock au seuil | le Parc Auto |
| surconsommation, anomalie, saisie suspecte | le Parc Auto et la Direction |
| mission partie | le chargé de clientèle du client (à défaut, tous les chargés) |
| incident signalé | le Parc Auto et la Direction ; check-list avec point KO → le Parc Auto |
| facture soumise | la Direction ; validée → Finances et son auteur ; renvoyée → son auteur |
| facture échue (tâche du jour) | Finances et Direction, **une fois par facture** |

À cela s'ajoutent les **tâches du jour** (documents et permis à 30 jours puis expirés, rappels de validation de
congés en retard, passage des congés à « En cours » / « Terminé »), lancées par une commande.

## Prérequis

- Chapitres 1 à 14 terminés.

## Notions Django de ce chapitre

- **Abonnements par `@receiver`** dans un fichier `receivers.py`, branchés par `ready()` : c'est l'inverse
  des chapitres précédents où l'on *émettait*.
- **Clé d'unicité** (`cle_unicite`) : pour qu'un rappel quotidien ne soit **envoyé qu'une fois** à la même
  personne, on lui associe une clé (par exemple `facture-echue-12`) : si elle existe déjà, on ne recrée rien.
- **`Notification.all_objects`** (le manager qui voit aussi les lignes supprimées) : une notification
  supprimée ne doit pas être renvoyée.
- **Envoi d'e-mails optionnel** (`NOTIFICATIONS_EMAIL`) : un e-mail en échec est **journalisé** et ne bloque
  jamais l'opération métier.
- **Commande de gestion planifiable** : `taches_quotidiennes` sera lancée chaque jour (planificateur,
  cron…) ; elle est **rejouable** sans doublon.
- **Lien profond** : chaque notification porte l'adresse de l'écran concerné, résolue avec `reverse()`
  (la table d'adresses s'écrira aux chapitres 16 et suivants).

## Étape 1 — Créer l'application

```bash
mkdir -p apps/notifications/management/commands
```

{{VIDES}}

## Étape 2 — Modèle et service de base

{{FICHIER apps/notifications/models.py}}

Une `Notification` : destinataire, catégorie, niveau (Information, Attention, Urgent), titre, message, lien,
date de lecture, clé d'unicité.

{{FICHIER apps/notifications/services.py}}

- **`notifier(destinataires, ...)`** : crée **une notification par compte actif**, ignore les doublons, les
  valeurs vides et, si une `cle` est fournie, ce que la personne a déjà reçu.
- **`utilisateurs_du_role(*roles)`** : pratique pour cibler « tous les Parc Auto ».
- **`nombre_non_lues`**, **`marquer_lue`**, **`marquer_toutes_lues`** : pour la cloche de l'interface.

## Étape 3 — Les abonnements

{{FICHIER apps/notifications/receivers.py}}

C'est ici que se lit *qui est prévenu de quoi*. Repérez le motif : chaque fonction reçoit un événement
(`conge_soumis`, `alerte_consommation`, `mission_demarree`…), calcule les destinataires **avec les services
des autres apps** puis appelle `notifier`. Notez `send_robust` côté émetteur : si un récepteur plante, l'action
métier (un plein, un départ de mission) **n'échoue pas**.

## Étape 4 — Les tâches du jour

{{FICHIER apps/notifications/taches.py}}

Cinq tâches indépendantes, regroupées par `executer_taches_quotidiennes` :

1. **`alerter_documents_vehicules`** : documents à renouveler à 30 jours, puis expirés (une alerte à chaque
   changement d'état).
2. **`alerter_echeances_chauffeurs`** : permis et visite médicale.
3. **`relancer_validations_en_retard`** : rappel au validateur quand le délai (48 h pour le N1, 24 h pour le N2)
   est dépassé.
4. **`alerter_factures_echues`**.
5. Le passage des congés à « En cours » / « Terminé » (`hr.synchroniser_statuts_conges`).

{{FICHIER apps/notifications/management/commands/taches_quotidiennes.py}}

## Étape 5 — Administration, démarrage et README

{{FICHIER apps/notifications/admin.py}}

{{FICHIER apps/notifications/apps.py}}

{{RESTANTS}}

Les **tests** de `notifications` sont nombreux (récepteurs, tâches, écrans) : ils sont présentés dans les
chapitres où leurs dépendances existent (20, 23, 24, 25 et 26).

## Étape 6 — Déclarer l'application et migrer

{{CONFIG}}

```bash
python manage.py makemigrations notifications
python manage.py migrate
```

**Résultat attendu :** `Create model Notification`, puis `Applying notifications.0001_initial... OK`.

## Vérifier le chapitre

```bash
python manage.py check
```

**Essai 1 : une notification, et un rappel qui n'est envoyé qu'une fois** (avec le compte `demo_rh` du chapitre 6) :

```bash
python manage.py shell -c "from apps.accounts.models import User; from apps.notifications import services as s; u = User.objects.get(username='demo_rh'); s.notifier([u], categorie='CONGE', titre='Essai', cle='essai-1'); s.notifier([u], categorie='CONGE', titre='Essai', cle='essai-1'); print(s.nombre_non_lues(u))"
```

**Résultat attendu :** `1` (le second appel est ignoré grâce à la clé).

**Essai 2 : les tâches du jour.**

```bash
python manage.py taches_quotidiennes
```

**Résultat attendu :** six lignes de compteurs (`documents vehicules`, `echeances chauffeurs`,
`validations en retard`, `factures echues`, `conges demarres`, `conges termines`), toutes à `0` sur une base
qui ne contient encore rien d'échu.

## Ce qu'il faut retenir

- Le module qui **prévient** ne doit pas être connu de ceux qui **agissent** : les **signaux** inversent la
  dépendance.
- Une tâche répétée chaque jour doit être **idempotente** (rejouable sans effet en double) : d'où la clé
  d'unicité.
- Une erreur dans un **effet secondaire** (e-mail, notification) ne doit **jamais** annuler l'action principale.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 15 : app notifications (abonnements aux événements, tâches quotidiennes)"
```

> **Fin de la première phase.** Vous avez terminé le « cerveau » : toutes les règles métier existent et sont
> testées. Le chapitre suivant commence le « visage » : les écrans.
