## Ce que vous allez construire

**`drivers`** : les **chauffeurs**. Un chauffeur est d'abord un employé (une fiche `Personnel` de `hr`) auquel
on ajoute ce qui est propre au métier : le **permis**, la **visite médicale** et un **statut de disponibilité**
(Disponible, En mission, En congé, Suspendu, Inactif).

Trois comportements automatiques à repérer :

| Comportement | Où |
|---|---|
| Recruter quelqu'un au poste « Chauffeur » **crée sa fiche chauffeur** tout seul | `signals.py` |
| Un congé qui **commence** met le chauffeur « En congé » ; à la fin, il redevient disponible | `signals.py` |
| **Alerte 30 jours avant** l'expiration du permis ou de la visite médicale | `services.py` (`chauffeurs_a_renouveler`) |

## Prérequis

- Chapitres 1 à 5 terminés.

## Notions Django de ce chapitre

- **`OneToOneField`** : une relation « un pour un » : une fiche chauffeur ↔ une fiche personnel. C'est le
  moyen Django de « prolonger » une table sans la modifier.
- **Signal `post_save` sur le modèle d'une autre app** : `drivers` écoute `hr`. Le sens des dépendances est
  respecté : `hr` ne sait rien de `drivers`.
- **`@receiver(post_save, sender=Personnel)`** : la fonction est appelée après chaque enregistrement d'un
  `Personnel`. Le paramètre `raw` est vrai lors du chargement de données brutes (à ignorer).
- **Propriétés** (`@property`) : `chauffeur.nom` lit le nom depuis la fiche personnel, sans le dupliquer.
- **`get_or_create`** : « récupère ou crée » : rend l'opération rejouable sans doublon.

## Étape 1 — Créer l'application

```bash
mkdir -p apps/drivers/tests
```

{{VIDES}}

## Étape 2 — Modèle, exceptions et services

{{FICHIER apps/drivers/models.py}}

- **Pas de doublon d'identité.** Le matricule, le nom et le prénom ne sont *pas* recopiés : ce sont des
  propriétés qui lisent la fiche `Personnel`. Une seule source de vérité.
- **`CategoriePermis`** : C ou E (poids lourds). `categories_permis` est une liste stockée en JSON ;
  le `clean()` du modèle refuse toute catégorie autre que C ou E.
- **Dates d'expiration** du permis et de la visite médicale : facultatives (`null=True`), car on peut
  recruter un chauffeur avant d'avoir ses papiers ; l'alerte à 30 jours ne concerne que les dates renseignées.

{{FICHIER apps/drivers/exceptions.py}}

{{FICHIER apps/drivers/services.py}}

Lisez en particulier :

- **`assurer_fiche_chauffeur`** : crée la fiche si elle manque (utilisée par le signal ; rejouable).
- **`mettre_en_mission` / `rappeler_de_mission`**, **`mettre_en_conge` / `rappeler_de_conge`** : les
  changements d'état automatiques. `missions` et `hr` s'en serviront.
- **`changer_statut_manuel`** : on ne peut suspendre, désactiver ou réactiver qu'à la main ; « En mission » et
  « En congé » sont **posés par le système** et refusés ici (`StatutNonModifiable`).
- **`chauffeur_de(utilisateur)`** : retrouve la fiche chauffeur d'un compte : c'est ce qui permet à l'espace
  mobile de n'afficher que *ses* missions (chapitre 27).
- **`etat_echeances`** utilise `etat_echeance` du chapitre 2 pour dire « valide / à renouveler / expiré ».

{{FICHIER apps/drivers/signals.py}}

Les deux abonnements sont la raison d'être de ce fichier. Notez le commentaire : c'est **`drivers` qui écoute
`hr`**, pas l'inverse.

{{FICHIER apps/drivers/permissions.py}}

## Étape 3 — Administration, démarrage et tests

{{FICHIER apps/drivers/admin.py}}

{{FICHIER apps/drivers/apps.py}}

Important : `ready()` doit **importer `signals`** pour que les abonnements existent. C'est l'usage standard
de Django.

{{FICHIER apps/drivers/tests/factories.py}}

{{RESTANTS}}

Ce chapitre présente aussi quatre fichiers de tests de `hr` (`test_conges.py`, `test_droits_conges.py`,
`test_recrutement.py`, `test_comptes_demo.py`) : ils ont besoin des chauffeurs pour s'exécuter (par exemple
« un chauffeur en congé passe au statut En congé »).

## Étape 4 — Déclarer l'application et migrer

{{CONFIG}}

```bash
python manage.py makemigrations drivers
python manage.py migrate
```

**Résultat attendu :** `Create model Chauffeur`, puis `Applying drivers.0001_initial... OK`.

## Vérifier le chapitre

```bash
python manage.py check
```

{{PYTEST}}

**Créez maintenant vos comptes d'essai** (un par rôle) et vérifiez que la fiche chauffeur s'est créée
toute seule :

```bash
python manage.py creer_comptes_demo
python manage.py shell -c "from apps.drivers.models import Chauffeur; print(list(Chauffeur.objects.values_list('personnel__matricule', 'statut')))"
```

**Résultat attendu :** la première commande affiche un **mot de passe généré** et la liste des 7 comptes
(`demo_direction`, `demo_admin`, `demo_rh`, `demo_charge`, `demo_parcauto`, `demo_finances`,
`demo_chauffeur`). **Notez ce mot de passe** : vous en aurez besoin pour vous connecter. La seconde
affiche **une** fiche chauffeur au statut `DISPONIBLE` (celle de `demo_chauffeur`), créée par le signal.

## Ce qu'il faut retenir

- **Prolonger** une table plutôt que la dupliquer : `OneToOneField` + propriétés.
- Un **signal** permet à une app « du dessous » de réagir à une app « du dessus » sans la modifier.
- Certains états sont **posés par le système** et interdits à la saisie manuelle.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 6 : app drivers (fiche chauffeur, permis, visite médicale, statuts, alertes 30 jours)"
```
