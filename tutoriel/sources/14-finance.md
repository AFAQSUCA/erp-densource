## Ce que vous allez construire

**`finance`** : la **trésorerie** et les **indicateurs financiers**. Cette app est une **couche au-dessus** de
`billing` : elle lit ce que les autres ont enregistré et en tire des chiffres.

**La trésorerie = ce qui a réellement bougé.** Trois sources :

| Source | Sens |
|---|---|
| **Règlements** reçus (`billing`) | entrées |
| **Dépenses** payées (`billing`) | sorties |
| **Mouvements manuels** (`finance`) : solde d'ouverture, apport, frais bancaires, retrait | entrées ou sorties |

Le **compte** (Banque, Caisse, Mobile Money) se **déduit du mode de paiement** : virement et chèque → banque,
espèces → caisse, Wave / Orange Money / MTN → mobile money.

**Les indicateurs du mois** :

- **CA facturé** = total **HT** des factures émises ; **encaissé** = règlements du mois ;
- **charges** = dépenses saisies **+** carburant (litres × prix des pleins) **+** coût des OR clôturés
  (main-d'œuvre et pièces au PUMP). Les trois composantes restent visibles séparément ;
- **marge nette** = CA HT − charges ; **créances** = reste à recouvrer (dont échu) ; **trésorerie** = solde.

> Les **charges** (vue économique) et la **trésorerie** (vue réelle) ne sont volontairement **pas les mêmes
> chiffres**. Le rapprochement bancaire et les écritures comptables ne sont pas gérés (décision du client).

## Prérequis

- Chapitres 1 à 13 terminés.

## Notions Django de ce chapitre

- **Une app « de lecture »** : `finance` réutilise les services de `billing`, `fuel` et `inventory`
  **sans les dupliquer** : la règle du carburant reste dans `fuel`, le PUMP dans `inventory`.
- **Agrégation SQL** avec `Sum` et `values_list(...).annotate(...)` : le total est calculé par la base, pas
  par une boucle Python.
- **`order_by()` vide** pour neutraliser un tri par défaut qui fausserait un regroupement (`GROUP BY`).
- **Annulation logique d'un mouvement** (avec motif) : on n'efface pas un mouvement de trésorerie.
- **Dictionnaires de résultats** : les services renvoient des dictionnaires prêts à afficher (soldes,
  indicateurs).

## Étape 1 — Créer l'application

```bash
mkdir -p apps/finance/tests
```

{{VIDES}}

## Étape 2 — Modèle et services

{{FICHIER apps/finance/models.py}}

Un seul modèle : `MouvementManuel`. Tout le reste de la trésorerie vient des modèles de `billing`.

{{FICHIER apps/finance/services.py}}

À lire :

1. **`_compte`** : traduit un mode de paiement en compte grâce à `COMPTE_DU_MODE`.
2. **`enregistrer_mouvement`** / **`annuler_mouvement`** : contrôlent le rôle (`billing.permissions.SAISIE`), le
   montant (strictement positif) et le motif d'annulation.
3. **`soldes_par_compte`** : additionne règlements, soustrait dépenses, applique les mouvements manuels, et
   ajoute le **total**.
4. **`synthese_periode`** : entrées, sorties et variation sur une période.
5. **`charges`** et **`indicateurs`** : les chiffres du mois, en appelant `fuel.cout_carburant` et
   `inventory.cout_des_or_clotures`.

{{FICHIER apps/finance/permissions.py}}

Elle **réutilise** celles de `billing` : mêmes droits, écrits une seule fois.

{{FICHIER apps/finance/apps.py}}

{{RESTANTS}}

## Étape 3 — Déclarer l'application et migrer

{{CONFIG}}

```bash
python manage.py makemigrations finance
python manage.py migrate
```

**Résultat attendu :** `Create model MouvementManuel`, puis `Applying finance.0001_initial... OK`.

## Vérifier le chapitre

```bash
python manage.py check
```

{{PYTEST}}

Essai dans le shell (base sans règlement ni dépense) :

```bash
python manage.py shell -c "from apps.finance import services as s; t = s.soldes_par_compte(); print(sorted(t), t['total'])"
```

**Résultat attendu :** `['BANQUE', 'CAISSE', 'MOBILE_MONEY', 'total'] 0`.

## Ce qu'il faut retenir

- Une app qui **agrège** doit **appeler** les services des autres, pas recopier leurs règles.
- Ne pas confondre **économique** (charges, marge) et **réel** (trésorerie) : deux vérités, deux chiffres.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 14 : app finance (trésorerie par compte, indicateurs du mois)"
```
