# Exercice 4 — Une catégorie de dépense « Frais bancaires »

**Semaine 6** · environ 2 heures · après le chapitre 16 (comptabilité) et le chapitre 27 (écrans des finances)

## La demande

« Les frais de tenue de compte et de virement finissent aujourd'hui dans « Autre ». On veut une catégorie
**Frais bancaires**, proposée à la saisie, et comptée au compte **631000 — Frais bancaires** du plan comptable. »

## Ce qui doit marcher

- `CategorieDepense.FRAIS_BANCAIRES`, libellé « Frais bancaires », proposée dans le formulaire de saisie d'une
  dépense.
- Une dépense de cette catégorie passe une écriture qui **débite le compte 631000** du montant.

## Où regarder

- `apps/billing/models.py` : `CategorieDepense`, et les champs `categorie` qui l'utilisent.
- `apps/accounting/constants.py` : `CATEGORIE_DEPENSE_VERS_COMPTE`.
- `apps/accounting/services.py` : la fonction qui comptabilise une dépense. Que fait-elle d'une catégorie qu'elle
  ne connaît pas ?

## Étapes conseillées

1. Copiez `test_exercice_04.py` dans `apps/billing/tests/` et lancez-le : 2 tests échouent.
2. Ajoutez la catégorie et lancez `python manage.py makemigrations`. **Lisez le message d'erreur** : il vous dit
   exactement ce qui ne va pas.
3. Reliez la catégorie à son compte, relancez le test, puis toute la suite.

## Indice

Dans `FRAIS_BANCAIRES = "...", _("Frais bancaires")`, le **nom** (à gauche) sert dans le code, la **valeur** (la
chaîne) est stockée en base. Les deux n'ont pas à être identiques.

## Correction

`correction.md`, puis `correction.diff`.
