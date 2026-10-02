## Ce que vous allez construire

Les **écrans de la comptabilité** : le plan comptable, la saisie manuelle d'opérations diverses (avec son
cycle brouillon → validation par la DIRECTION), la clôture d'un exercice, et cinq rapports en lecture
seule.

| Écran | Adresse | Qui |
|---|---|---|
| **Plan comptable** (liste, création, modification) | `/comptabilite/plan-comptable/` | consultation : ADMIN, DIRECTION, FINANCES, RH ; gestion : mêmes rôles |
| **Opérations diverses** (liste, **brouillon**, ajout/retrait de ligne, validation, abandon) | `/comptabilite/operations-diverses/` | saisie : mêmes rôles ; validation : **DIRECTION seule** |
| **Exercices comptables** (liste, clôture) | `/comptabilite/exercices/` | consultation : mêmes rôles ; clôture : **DIRECTION seule** |
| **Grand livre** d'un compte | `/comptabilite/grand-livre/` | consultation |
| **Balance** générale | `/comptabilite/balance/` | consultation |
| **Bilan** et **compte de résultat** (par exercice) | `/comptabilite/bilan/`, `/comptabilite/compte-de-resultat/` | consultation |
| **Déclaration TVA** (par période, le mois en cours par défaut) | `/comptabilite/declaration-tva/` | consultation |

Chacun des 5 rapports a sa **version imprimable** (`.../imprimer/`), accessible depuis le menu « Rapports
comptables ».

## Prérequis

- Chapitres 1 à 26 terminés.

## Ce que ce chapitre apporte de nouveau

- **Un formulaire qui gagne son propre queryset dans `__init__`** : `GrandLivreForm.compte` et
  `LigneManuelleForm.compte` fixent `self.fields["compte"].queryset` après coup, pour ne lister que les
  comptes **actifs** — impossible à exprimer comme attribut de classe (le queryset serait figé au
  chargement du module, avant toute migration).
- **Une fiche à deux formulaires imbriqués** : `EcritureManuelleDetailView` affiche l'écriture **et**,
  si l'utilisateur peut encore saisir, un formulaire d'ajout de ligne (`LigneAjouterView`, une vue à part,
  en POST). `peut_saisir`, `peut_valider` et `equilibree` sont calculés **une fois**, dans
  `get_context_data`, jamais recalculés dans le gabarit.
- **Un rapport toujours borné à un exercice existant** : `_RapportExerciceView.get_exercice` choisit
  l'exercice demandé en paramètre `?exercice=`, ou **le plus récent** à défaut — jamais « aucun exercice »
  tant qu'au moins un existe.
- **Cinq rapports, un seul gabarit de navigation** (`_nav_rapports.html`, inclus par chacun) : l'onglet
  actif se déduit de `request.resolver_match.url_name`, sans variable de contexte dédiée.
- **La version imprimable réutilise le même service** que l'écran, avec `core.rapports.contexte_rapport`
  pour l'en-tête (entreprise, titre, généré le/par) — même mécanisme que `billing`/`finance` au
  chapitre 26.

## Étape 1 — Formulaires

{{FICHIER apps/accounting/forms.py}}

`PeriodeForm` (début/fin facultatifs) est la base de `GrandLivreForm` (qui y ajoute le compte) et sert
telle quelle à la balance et à la déclaration TVA. `EcritureManuelleForm` et `LigneManuelleForm`
couvrent la saisie manuelle ; `CompteForm` et `CompteModifierForm`, le plan comptable.

## Étape 2 — Vues et adresses

{{FICHIER apps/accounting/views.py}}

Repérez `EcritureManuelleDetailView.get_context_data` : c'est elle qui décide, pour le gabarit, **ce que
la personne peut faire** (`peut_saisir`, `peut_valider`) à partir du statut de l'écriture et du rôle
effectif — jamais le gabarit. `_RapportExerciceView` factorise le choix de l'exercice pour `BilanView`,
`BilanImprimerView`, `CompteDeResultatView` et `CompteDeResultatImprimerView`.

{{FICHIER apps/accounting/urls.py}}

{{CONFIG}}

## Étape 3 — Gabarits

```bash
mkdir -p apps/accounting/templates/accounting
```

{{FICHIER apps/accounting/templates/accounting/plan_comptable_list.html}}

{{FICHIER apps/accounting/templates/accounting/compte_form.html}}

{{FICHIER apps/accounting/templates/accounting/compte_modifier_form.html}}

{{FICHIER apps/accounting/templates/accounting/ecriture_manuelle_list.html}}

{{FICHIER apps/accounting/templates/accounting/ecriture_manuelle_form.html}}

{{FICHIER apps/accounting/templates/accounting/ecriture_manuelle_detail.html}}

{{FICHIER apps/accounting/templates/accounting/exercice_list.html}}

{{FICHIER apps/accounting/templates/accounting/_nav_rapports.html}}

Incluse par les cinq gabarits de rapport suivants (`{% include %}`), pour l'onglet de navigation commun.

{{FICHIER apps/accounting/templates/accounting/grand_livre.html}}

{{FICHIER apps/accounting/templates/accounting/grand_livre_print.html}}

{{FICHIER apps/accounting/templates/accounting/balance.html}}

{{FICHIER apps/accounting/templates/accounting/balance_print.html}}

{{FICHIER apps/accounting/templates/accounting/bilan.html}}

{{FICHIER apps/accounting/templates/accounting/bilan_print.html}}

{{FICHIER apps/accounting/templates/accounting/compte_resultat.html}}

{{FICHIER apps/accounting/templates/accounting/compte_resultat_print.html}}

{{FICHIER apps/accounting/templates/accounting/declaration_tva.html}}

{{FICHIER apps/accounting/templates/accounting/declaration_tva_print.html}}

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

**Le cycle d'une opération diverse, dans le navigateur** (le plan comptable est déjà seedé depuis le
chapitre 15 : `571000` Caisse, `101000` Capital social… y figurent déjà) :

1. **`demo_finances`** : **Plan comptable** : le plan de départ y est. **Nouveau compte** : ajoutez
   `612000` « Locations » (Charge) pour voir l'écran de création — numéro et nature ne se modifient
   plus ensuite.
2. **`demo_finances`** : **Opérations diverses → Nouvelle opération**, date du jour, libellé « Apport en
   caisse ». Le brouillon se crée **sans numéro**. Ajoutez deux lignes : `571000` au débit, `101000` au
   crédit, même montant. Le bandeau passe à **équilibrée**.
3. Essayez de valider avec `demo_finances` : le bouton n'existe pas (rôle **strict**, DIRECTION seule).
4. **`demo_direction`** : ouvrez l'écriture, **Valider**. Le numéro `OD-<année>-0001` est attribué à cet
   instant ; les lignes ne se modifient plus.
5. **Grand livre** sur le compte `571000` : la ligne apparaît, avec son solde cumulé. **Balance** : le
   compte y figure avec son solde. **Bilan** : l'exercice en cours (auto-créé à la première écriture)
   propose le compte en actif.
6. Cliquez la **version imprimable** d'un rapport, puis « Imprimer ou enregistrer en PDF ».

## Ce qu'il faut retenir

- Un rapport comptable est une **agrégation à la demande**, pas un état stocké : il reste vrai même si de
  nouvelles écritures arrivent entre deux consultations.
- La **saisie** et la **validation** d'une même écriture peuvent être deux personnes différentes — le
  contrôle de rôle vit dans le service, la vue ne fait qu'afficher ce qui est possible.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 27 : écrans de la comptabilité (plan comptable, opérations diverses, rapports)"
```
