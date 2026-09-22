## Ce que vous allez construire

**`core`**, le socle : ce qui est utilisé par *toutes* les autres applications et qui ne dépend d'aucune.
On y trouve :

| Élément | À quoi il sert |
|---|---|
| `BaseModel` | classe mère de tous les modèles métier : dates de création/modification et **suppression logique** |
| `prochain_numero` | distribue des numéros `MIS-2026-0001`, `FACT-2026-0001`… sans doublon |
| `etat_echeance` | dit si un document est valide, à renouveler (30 jours avant) ou expiré |
| `filtrer_par_texte` | recherche qui ignore accents et majuscules (« traore » trouve « Traoré ») |
| `nombre`, `pourcentage_signe` | affichage des nombres à la française |
| `RegistreSections` | un mécanisme pour qu'une fiche affiche des blocs fournis par d'autres apps |
| middlewares | mémoriser la requête courante (pour l'audit) et ajouter les en-têtes de sécurité |

## Prérequis

- Chapitre 1 terminé : `python manage.py check` répond « no issues ».

## Notions Django de ce chapitre

- **Modèle** : une classe Python qui décrit une **table** de la base ; chaque attribut est une **colonne**.
  Django génère le SQL (c'est l'**ORM**).
- **Modèle abstrait** (`class Meta: abstract = True`) : un modèle qui n'a *pas* de table ; il sert de
  modèle mère. Les colonnes qu'il déclare sont copiées dans chaque modèle enfant.
- **Manager** (`objects`) : le point d'entrée des requêtes (`Modele.objects.filter(...)`). On peut en
  définir un qui filtre d'office (ici : ne pas montrer les lignes « supprimées »).
- **Migration** : un fichier qui décrit comment faire évoluer la base pour suivre les modèles.
  `makemigrations` l'écrit, `migrate` l'applique.
- **Signal** : une annonce (« la connexion à la base vient d'être créée ») à laquelle une fonction peut
  s'abonner.
- **`AppConfig.ready()`** : code exécuté **une fois au démarrage** de Django.
- **Middleware** : une classe qui voit **chaque requête** avant et après la vue.
- **Test avec pytest** : une fonction `test_…` avec des `assert` ; le marqueur
  `pytest.mark.django_db` autorise l'accès à la base ; chaque test travaille sur une base vide, annulée à la fin.

## Étape 1 — Créer l'application

```bash
mkdir -p apps/core/tests
```

{{VIDES}}

> **`apps/core/tests/__init__.py` vide** : sans ce fichier, pytest ne saurait pas que `tests` est un
> paquet et les `import` relatifs entre tests échoueraient.

## Étape 2 — Les constantes et le modèle de base

{{FICHIER apps/core/constants.py}}

Une constante partagée : **30 jours** avant l'expiration d'un document, une alerte préventive part.

{{FICHIER apps/core/models.py}}

À retenir dans ce fichier :

- **Suppression logique.** `delete()` ne supprime rien : il pose `is_deleted = True`, la date et l'auteur.
  Sur des données sensibles (factures, missions, personnel), on ne détruit jamais une ligne : on peut
  ainsi toujours retrouver l'historique.
- **Deux managers.** `objects = ActiveManager()` **cache** les lignes supprimées (c'est ce qu'utilise
  presque tout le code) ; `all_objects` les montre toutes.
- **`CompteurNumero`** : une table technique : pour chaque couple (préfixe, année), le dernier numéro
  attribué. Sa contrainte d'unicité (`UniqueConstraint`) est posée **dans la base** : même si un bug
  du code l'oubliait, la base refuserait un doublon.
- `auto_now_add=True` (posé une fois à la création) et `auto_now=True` (mis à jour à chaque `save()`).

{{FICHIER apps/core/services.py}}

`prochain_numero` est le premier vrai **service** du projet (une fonction qui porte une règle métier).
Deux détails importants :

- `@transaction.atomic` : tout se passe dans une transaction, « tout ou rien ».
- `select_for_update()` : **verrouille la ligne** du compteur pendant l'opération, pour que deux personnes
  qui créent une mission au même instant n'obtiennent pas le même numéro. (SQLite, qu'on utilise en
  développement, ignore ce verrou ; il est effectif avec PostgreSQL en production.)

`etat_echeance` est une **fonction pure** : mêmes entrées, même sortie, aucun accès à la base. Elle
est donc très simple à tester (voir `test_echeance.py`).

## Étape 3 — Recherche, formats et blocs d'affichage

{{FICHIER apps/core/search.py}}

Pourquoi ne pas simplement écrire `nom__icontains="traore"` ? Parce que ce filtre ne trouve pas
« Traoré » (accent) et, sous SQLite, ne gère pas la casse des lettres accentuées. La solution : comparer
des textes **normalisés** (minuscules, sans accents) des deux côtés. Sous PostgreSQL on utilise
`LOWER(TRANSLATE(...))` ; sous SQLite on **enregistre une fonction SQL** `NORMALISER` à chaque
connexion (c'est le rôle de `apps.py`, plus bas).

{{FICHIER apps/core/formats.py}}

Pourquoi un module de formats ? Écrire `f"{valeur}"` afficherait « 1500.50 » (point anglais). Ici on
affiche « 1 500,5 ». Django tronque les décimales au lieu de les arrondir ; on arrondit donc d'abord
(demi supérieur).

{{FICHIER apps/core/sections.py}}

C'est un **registre**. Exemple concret : la fiche d'un camion (app `fleet`) veut afficher un bloc
« Maintenance » fourni par `garage`. Mais `fleet` ne doit pas *importer* `garage` (les dépendances vont
dans un seul sens). Alors `fleet` crée un `RegistreSections`, et `garage` y **enregistre** un fournisseur
au démarrage. La fiche affiche ce qui s'est inscrit, sans jamais connaître `garage`.

Les blocs dont le gabarit n'existe pas (encore) sont simplement ignorés.

## Étape 4 — Middlewares et formulaires

{{FICHIER apps/core/middleware.py}}

Trois éléments :

- **`CurrentRequestMiddleware`** garde la requête en cours dans une variable propre au fil d'exécution,
  pour que le journal d'audit sache **qui** a fait quoi, depuis **quelle adresse**.
- **`get_client_ip`** : l'adresse du client. Méfiance : l'en-tête `X-Forwarded-For` peut être écrit par
  n'importe quel client. On ne le lit que derrière un nombre déclaré de proxys de confiance
  (`TRUSTED_PROXY_COUNT`), sinon un attaquant pourrait falsifier son adresse et contourner les limites
  d'essais.
- **`SecurityHeadersMiddleware`** ajoute la politique de sécurité du contenu (CSP) et la politique des
  fonctions du navigateur (la caméra reste permise pour le scan des QR).

{{FICHIER apps/core/forms.py}}

Un tout petit mixin : il applique le même style Tailwind à tous les champs d'un formulaire.

## Étape 3 bis — Enregistrer l'application

{{FICHIER apps/core/apps.py}}

`ready()` s'exécute au démarrage : elle abonne `enregistrer_fonction_sqlite` au signal
`connection_created`, ce qui rend la fonction `NORMALISER` disponible dans SQLite.

{{FICHIER apps/core/admin.py}}

Rien à administrer pour l'instant (un modèle technique n'a pas d'écran).

## Étape 5 — Déclarer l'application dans les réglages

Modifiez `config/settings/base.py` :

{{CONFIG}}

Les deux lignes de `MIDDLEWARE` ajoutent nos deux middlewares ; `"apps.core"` déclare l'application.

## Étape 6 — Les fichiers restants (README et tests)

{{RESTANTS}}

Lisez les tests : ils **documentent** le comportement. Par exemple `test_numerotation.py` prouve que deux
appels donnent des numéros consécutifs, et que la numérotation repart à 1 chaque année.

## Étape 7 — Générer la migration

Django compare vos modèles à l'état précédent et écrit la migration :

```bash
python manage.py makemigrations core
```

**Résultat attendu :**

```text
Migrations for 'core':
  apps\core\migrations\0001_compteur_numero.py
    + Create model CompteurNumero
```

(Le nom du fichier peut différer légèrement : `0001_initial.py`. Cela n'a pas d'importance.)

> ⚠️ **Ne lancez pas encore `python manage.py migrate`.** Le modèle *utilisateur* de l'ERP sera créé au
> chapitre suivant. Django exige qu'il existe **avant** la toute première migration ; sinon la base
> se retrouve dans un état incohérent. Les tests, eux, utilisent une base temporaire : vous pouvez
> les lancer.

## Vérifier le chapitre

```bash
python manage.py check
```

{{PYTEST}}

Petits essais dans le shell (aucune base nécessaire) :

```bash
python manage.py shell -c "from apps.core.search import normaliser; print(normaliser('TRAORÉ Moussa'))"
python manage.py shell -c "from apps.core.formats import nombre, pourcentage_signe; print(nombre(1500.5, 1), pourcentage_signe(23.333))"
```

**Résultat attendu :** `traore moussa`, puis `1 500,5 +23,3` (avec des espaces insécables).

> **Si des tests échouent** avec `no such function: NORMALISER` : `apps.py` n'est pas pris en compte
> (vérifiez `"apps.core"` dans `LOCAL_APPS`). Avec `RuntimeError: Model class … doesn't declare an explicit
> app_label` : l'application n'est pas listée dans `INSTALLED_APPS`.

## Ce qu'il faut retenir

- Un **service** est une fonction qui porte une règle ; les vues ne font qu'appeler des services.
- La **suppression logique** est le comportement par défaut : on ne détruit pas les données sensibles.
- Un **registre** (sections) permet à deux apps de collaborer **sans s'importer**.
- Les **tests** sont la documentation exécutable : lisez-les avant le code.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 2 : app core (BaseModel, numérotation, recherche, formats, sections, middlewares)"
```
