## Ce que vous allez construire

Les **écrans de la facturation, des dépenses et de la trésorerie** : le circuit complet **FINANCES prépare, la
DIRECTION valide**.

| Écran | Adresse | Qui |
|---|---|---|
| Liste des factures (créances, échues, filtres) | `/facturation/` | ADMIN, DIRECTION, FINANCES |
| **Préparer** une facture depuis une mission livrée | `/facturation/nouvelle/` | ADMIN, FINANCES |
| **Fiche** d'une facture : lignes, conditions, **Soumettre**, **Valider et émettre** / **Renvoyer en brouillon**, règlements | `/facturation/<id>/` | selon le statut et le rôle |
| **Version imprimable** (à enregistrer en PDF) | `/facturation/<id>/imprimer/` | ADMIN, DIRECTION, FINANCES |
| Dépenses (liste, saisie) | `/facturation/depenses/` | consultation : ADMIN, DIRECTION, FINANCES ; saisie : ADMIN, FINANCES |
| **Trésorerie** : soldes par compte, journal, mouvements manuels | `/finances/` | idem |

## Prérequis

- Chapitres 1 à 24 terminés.

## Ce que ce chapitre apporte de nouveau

- **Une page à états multiples** : la fiche d'une facture n'affiche pas les mêmes boutons en brouillon, à
  valider, émise ou payée. La vue calcule `saisie`, `validation` et ce qui est possible ; **le service** contrôle
  en plus le rôle **strict** (un ADMIN ne peut pas valider).
- **Beaucoup d'actions en POST** (`_ActionFacture` puis `_Saisie`) : ajouter/supprimer une ligne, modifier les
  conditions, soumettre, abandonner, valider, refuser, ajouter/annuler un règlement.
- **Une page imprimable** : `facture_print.html` est une **page autonome** (elle n'hérite pas de `base.html`), avec sa
  feuille de style d'impression et un bouton `data-imprimer` (traité par `app.js`, sans code en ligne). Les
  mentions de l'émetteur viennent des réglages `ENTREPRISE_NOM`, `ENTREPRISE_ADRESSE`, `ENTREPRISE_NCC`.
- **Deux apps dans un chapitre** : `billing` et `finance` ont chacune leurs formulaires, vues et adresses ; les
  adresses sont montées séparément (`/facturation/` et `/finances/`).
- **Un motif** (`MotifForm`) : un refus, une annulation, un abandon exigent un **motif** saisi.

## Étape 1 — Formulaires

{{FICHIER apps/billing/forms.py}}

{{FICHIER apps/finance/forms.py}}

## Étape 2 — Vues et adresses

{{FICHIER apps/billing/views.py}}

Lisez `FactureDetailView.get_context_data` : c'est lui qui prépare, pour le gabarit, **ce que la personne a le droit
de faire** (`saisie`, `validation`) — jamais le gabarit.

{{FICHIER apps/finance/views.py}}

{{FICHIER apps/billing/urls.py}}

{{FICHIER apps/finance/urls.py}}

{{CONFIG}}

## Étape 3 — Gabarits

```bash
mkdir -p apps/billing/templates/billing apps/finance/templates/finance
```

{{FICHIER apps/billing/templates/billing/facture_list.html}}

{{FICHIER apps/billing/templates/billing/facture_form.html}}

{{FICHIER apps/billing/templates/billing/facture_detail.html}}

{{FICHIER apps/billing/templates/billing/facture_print.html}}

{{FICHIER apps/billing/templates/billing/depense_list.html}}

{{FICHIER apps/billing/templates/billing/depense_form.html}}

{{FICHIER apps/finance/templates/finance/tresorerie.html}}

## Étape 4 — Tests et compilation des styles

{{RESTANTS}}

```bash
cd frontend
npm run build:css
cd ..
```

## Vérifier le chapitre

```bash
python manage.py check
```

{{PYTEST}}

**Le circuit d'une facture, dans le navigateur :**

1. **`demo_finances`** : **Facturation → Nouvelle facture**, choisissez la mission **livrée** du chapitre 21.
   Un **brouillon** est créé (prix, TVA 18 %, délai du client). Ajoutez une ligne « Péages refacturés » 18 500.
   Cliquez **Soumettre à la Direction**.
2. **`demo_direction`** : ouvrez la facture (statut **À valider**) : **Valider et émettre**. Le **numéro
   `FACT-<année>-0001`** est attribué **à cet instant**, l'échéance est fixée (émission + 30 jours). Essayez
   avec `demo_admin` : le bouton n'existe pas, et un appel direct est refusé par le service.
3. **`demo_finances`** : **Enregistrer un règlement** (acompte, Wave), puis le solde (virement). Un montant
   **supérieur au reste à recouvrer** est refusé. La facture passe **Partiellement payée** puis **Payée**.
4. **Trésorerie** : les règlements apparaissent en entrées, sur les comptes Mobile Money et Banque.
   Saisissez un **mouvement manuel** (solde d'ouverture) et une **dépense** (péage) : les soldes se mettent à jour.
5. Cliquez **Version imprimable** puis « Imprimer ou enregistrer en PDF ».

## Ce qu'il faut retenir

- Ce que la personne peut faire dépend du **statut de l'objet** *et* de son **rôle** ; les deux sont calculés côté
  serveur.
- Une **page imprimable** est une page autonome, sans menu, avec ses propres règles d'impression.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 25 : écrans de la facturation, des dépenses et de la trésorerie"
```
