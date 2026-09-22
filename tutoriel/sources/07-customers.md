## Ce que vous allez construire

**`customers`** : le **portefeuille clients** et leur **historique commercial**.

| Élément | Règle |
|---|---|
| `Client` | raison sociale, n° de contribuable (NCC/NIF, unique), contact, adresse, **chargé de clientèle attitré** |
| **TVA** | **18 % par défaut** ; à **0 %**, un **motif d'exonération** est obligatoire (export, ONG, convention, autre) |
| **Délai de paiement** | 30 jours par défaut, réglable de 1 à 365 jours ; il servira à calculer l'échéance des factures |
| `Interaction` | l'historique : appel, mail, réunion, demande de devis, **réclamation** |

## Prérequis

- Chapitres 1 à 6 terminés.

## Notions Django de ce chapitre

- **`CheckConstraint` avec `Q`** : une règle vérifiée par la base : « si le taux de TVA est 0, le motif
  d'exonération n'est pas vide » (`client_tva_zero_requiert_motif`). Le service la contrôle aussi, pour
  donner un message clair *avant* que la base ne refuse.
- **`DecimalField`** : pour l'argent et les taux, **jamais `float`** (les flottants s'arrondissent mal).
- **Unicité et suppression logique** : un NCC/NIF reste unique **même parmi les clients supprimés**
  (sinon on pourrait recréer un doublon d'un ancien client).
- **`**champs`** : une fonction qui accepte un nombre variable d'arguments nommés ; ici `creer_client`
  applique des valeurs par défaut avec `setdefault`.
- **Registre `sections`** : comme pour `hr`, `customers` expose un bloc que `missions` remplira (les missions
  d'un client s'affichent sur sa fiche).

## Étape 1 — Créer l'application

```bash
mkdir -p apps/customers/tests
```

{{VIDES}}

## Étape 2 — Modèles et règles

{{FICHIER apps/customers/models.py}}

Repérez les trois `CheckConstraint` : la TVA à zéro exige un motif, le taux reste entre 0 et 100, le délai
de paiement entre 1 et 365 jours.

{{FICHIER apps/customers/exceptions.py}}

{{FICHIER apps/customers/services.py}}

- **`_controler`** rassemble tous les contrôles communs à la création et à la modification (TVA, unicité du
  NCC/NIF, chargé de clientèle valide, motif effacé si la TVA redevient positive). Il **transforme une
  violation de règle en `ClientError`** avec un message lisible.
- **`enregistrer_interaction`** refuse un résumé vide et une date **dans le futur**.
- **`rechercher_clients`** utilise `filtrer_par_texte` du chapitre 2 : « traore » trouve « Traoré ».
- **`reclamations_recentes`** alimentera le tableau de bord clientèle.

{{FICHIER apps/customers/permissions.py}}

Le CDC donne la **gestion** des clients à l'ADMIN et au CHARGE_CLIENTELE, et la **lecture seule** à la
DIRECTION. La RH, le Parc Auto, les Finances et le chauffeur n'y ont pas accès.

{{FICHIER apps/customers/sections.py}}

## Étape 3 — Administration, démarrage et fabrique de test

{{FICHIER apps/customers/admin.py}}

{{FICHIER apps/customers/apps.py}}

{{RESTANTS}}

## Étape 4 — Déclarer l'application et migrer

{{CONFIG}}

```bash
python manage.py makemigrations customers
python manage.py migrate
```

**Résultat attendu :** `Create model Client`, `Create model Interaction`, `Add constraint …`, puis
`Applying customers.0001_initial... OK`.

## Vérifier le chapitre

Les tests de `customers` (formulaires, écrans) sont présentés avec les écrans au chapitre 19 ; pour l'instant on
vérifie à la main, dans le shell :

```bash
python manage.py check
python manage.py shell -c "from apps.customers import services as s; c = s.creer_client(raison_sociale='Cimaf CI', ncc_nif='CI-0001', contact_principal='M. Kouassi', telephone='0700000000', adresse='Abidjan'); print(c.raison_sociale, c.taux_tva, c.delai_paiement_jours)"
```

**Résultat attendu :** `Cimaf CI 18.00 30` (TVA à 18 % et délai à 30 jours **par défaut**).

Vérifiez maintenant que la base protège la règle de TVA, même si on contourne le service :

```bash
python manage.py shell -c "from apps.customers.models import Client; Client.objects.create(raison_sociale='ONG', ncc_nif='CI-0002', contact_principal='x', telephone='1', adresse='a', taux_tva=0)"
```

**Résultat attendu :** une erreur qui se termine par `CHECK constraint failed: client_tva_zero_requiert_motif`
(`IntegrityError`).

## Ce qu'il faut retenir

- Une règle importante se protège **deux fois** : dans le service (message clair) et dans la base
  (contrainte), pour qu'aucun chemin de code ne puisse la contourner.
- **Ne jamais utiliser `float`** pour de l'argent : `DecimalField` / `Decimal`.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 7 : app customers (portefeuille clients, TVA, délai de paiement, historique)"
```
