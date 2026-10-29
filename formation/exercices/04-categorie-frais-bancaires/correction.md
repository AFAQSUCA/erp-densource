# Correction — Exercice 4

## Le piège de l'étape 2

Avec `FRAIS_BANCAIRES = "FRAIS_BANCAIRES", ...`, `makemigrations` refuse :
`'max_length' is too small to fit the longest value in 'choices' (15 characters)`. Les trois champs `categorie`
(dépense, demande de dépense, enveloppe) ont `max_length=14`.

Deux solutions : agrandir les trois champs (trois migrations, sur des tables pleines de données), ou **choisir une
valeur plus courte**. La correction garde le nom lisible dans le code et raccourcit la valeur stockée :

```python
FRAIS_BANCAIRES = "FRAIS_BANQUE", _("Frais bancaires")
```

## Les changements

| Fichier | Changement | Pourquoi |
|---|---|---|
| `apps/billing/models.py` | la catégorie, valeur `FRAIS_BANQUE` | elle apparaît seule dans le formulaire : il propose toutes les catégories sauf les automatiques |
| `apps/accounting/constants.py` | `CategorieDepense.FRAIS_BANCAIRES: "631000"` | sans cette ligne, la comptabilisation lève une erreur et **toute la saisie est annulée** : une dépense n'est jamais enregistrée sans son écriture |
| migrations `billing` et `finance` | générées : elles mettent à jour la liste des choix des trois champs | |

Le compte 631000 existe déjà dans le plan comptable (il sert aux frais bancaires des mouvements de trésorerie) :
rien à créer.

## L'effet en cascade : 1 test

`test_enregistrer_une_depense_et_totaux_par_categorie` listait le total de **chaque** catégorie : il attend
maintenant aussi `"FRAIS_BANQUE": 0`.

**Vérification** : les 2 tests de l'exercice passent, et la suite complète aussi (3 419 tests).
