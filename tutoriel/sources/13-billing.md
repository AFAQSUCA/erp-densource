## Ce que vous allez construire

**`billing`** : la **facturation**, les **règlements** et les **dépenses**. Une facture suit un circuit de
validation en deux mains : **FINANCES prépare, la DIRECTION valide**.

```text
Brouillon → À valider → Émise → Partiellement payée → Payée
```

| Règle | Détail |
|---|---|
| **Une facture par mission** | créée depuis une mission **livrée ou clôturée** ; elle reprend le prix convenu, la TVA et le délai de paiement du client |
| **TVA à 3 niveaux** | 18 % par défaut (système), le taux du client, puis ajustable sur la facture **tant qu'elle est en brouillon** ; à 0 %, motif obligatoire |
| **Numéro à la validation** | `FACT-<année>-0001` n'est attribué qu'à la **validation** : un brouillon abandonné ne laisse **aucun trou** dans la numérotation |
| **Montants gelés** | dès la validation : une facture émise ne se modifie ni ne se supprime |
| **Règlements** | par virement, chèque, espèces, Wave, Orange Money, MTN ; jamais plus que le **reste à recouvrer** ; un règlement erroné s'**annule** avec un motif |
| **Facture échue** | émise, non soldée, **échéance dépassée** |
| **Dépenses** | péages, entretien, frais administratifs, autre |

## Prérequis

- Chapitres 1 à 12 terminés.

## Notions Django de ce chapitre

- **Rôle strict** : `valider` exige `strict=True` : un ADMIN ou un superutilisateur ne peut **pas** valider ;
  seule la DIRECTION le peut. La règle est dans le service, **pas dans la vue**.
- **`Decimal` et arrondi au franc** : le FCFA n'a pas de centimes. `arrondir_franc` arrondit au franc entier
  (`ROUND_HALF_UP`) ; la TVA est calculée puis arrondie **une seule fois**.
- **Annotation SQL** : `_regle_annote` calcule dans la base le montant réglé de chaque facture pour trier et
  filtrer sans boucler en Python.
- **Contrainte d'unicité conditionnelle** : une seule facture par mission (hors factures supprimées).
- **`related_name="lignes"`** : `facture.lignes.all()` liste ses lignes.
- **Constantes dérivées** : `COMPTE_DU_MODE` associe chaque mode de paiement à un compte (Banque, Caisse,
  Mobile Money).
- **Signaux** : `facture_a_valider`, `facture_validee`, `facture_refusee` : `notifications` prévient les bonnes
  personnes.

## Étape 1 — Créer l'application

```bash
mkdir -p apps/billing/tests
```

{{VIDES}}

## Étape 2 — Modèles

{{FICHIER apps/billing/models.py}}

Cinq modèles autour de la facture : `Facture`, `LigneFacture`, `Reglement` (avec son statut d'annulation
logique), `Depense`, et les énumérations `ModePaiement`, `CompteTresorerie`, `StatutFacture`,
`CategorieDepense`. `STATUTS_EMIS` et `STATUTS_A_RECOUVRER` regroupent les statuts pour les filtres.

## Étape 3 — Règles métier

{{FICHIER apps/billing/exceptions.py}}

{{FICHIER apps/billing/permissions.py}}

Trois ensembles : `CONSULTATION` (ADMIN, DIRECTION, FINANCES), `SAISIE` (ADMIN, FINANCES : préparer, encaisser,
saisir) et `VALIDATION` (**DIRECTION seule**).

{{FICHIER apps/billing/services.py}}

À lire dans cet ordre :

1. **`creer_facture`** : contrôle le rôle, verrouille la mission, refuse une mission non livrée
   (`FactureNonFacturable`), reprend prix, TVA et délai du client.
2. **`ajouter_ligne`**, **`supprimer_ligne`**, **`modifier_conditions`** : possibles **seulement en brouillon**.
   `_recalculer` refait HT, TVA arrondie, TTC.
3. **`soumettre`** : Brouillon → À valider. **`refuser`** : la Direction renvoie en brouillon **avec un motif**.
4. **`valider`** : le cœur : rôle strict, numéro `FACT-AAAA-XXXX`, date d'émission, échéance = émission + délai de
   paiement du client, montants gelés, signal `facture_validee`.
5. **`enregistrer_reglement`** / **`annuler_reglement`** : refusés si la facture n'est pas émise, si le montant
   dépasse le reste à recouvrer, ou si la date est future ou antérieure à l'émission ; le **statut** (partiellement
   payée / payée) est recalculé par `_statut_selon_reste`.
6. **Lectures** : `creances`, `factures_echues`, `chiffre_affaires`, `encaissements`, `total_depenses`,
   `depenses_par_categorie`.

{{FICHIER apps/billing/signals.py}}

## Étape 4 — Démarrage et tests

{{FICHIER apps/billing/apps.py}}

Dans `ready()`, on branche l'audit (module `FINANCES`) sur les factures, les règlements et les dépenses, et on
déclare les entrées de menu « Facturation » et « Dépenses ».

{{FICHIER apps/billing/tests/helpers.py}}

Ce fichier n'est pas un test : c'est une **bibliothèque d'aides** (`mission_livree`, `direction`, `finances`,
`emise`…) que réutiliseront aussi les tests de la trésorerie (chapitre 14) et des notifications.

{{RESTANTS}}

## Étape 5 — Déclarer l'application et migrer

{{CONFIG}}

```bash
python manage.py makemigrations billing
python manage.py migrate
```

**Résultat attendu :** `Create model Facture`, `Create model LigneFacture`, `Create model Reglement`,
`Create model Depense`, les contraintes, puis `Applying billing.0001_initial... OK`.

## Vérifier le chapitre

```bash
python manage.py check
```

{{PYTEST}}

(Les tests d'écrans de `billing` sont présentés au chapitre 25.)

Essai dans le shell : l'arrondi au franc.

```bash
python manage.py shell -c "from decimal import Decimal; from apps.billing.services import arrondir_franc; print(arrondir_franc(Decimal('100530.5')), arrondir_franc(Decimal('100530.49')))"
```

**Résultat attendu :** `100531 100530`.

## Ce qu'il faut retenir

- Le **numéro attribué à la validation** évite les trous dans une numérotation légale.
- Les règles de **rôle** vivent dans les **services** : elles s'appliquent quel que soit le point d'entrée
  (interface, API, mobile).
- Après validation, **rien ne bouge plus** : la seule façon de corriger, c'est un nouveau document.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 13 : app billing (factures, TVA, règlements, dépenses)"
```
