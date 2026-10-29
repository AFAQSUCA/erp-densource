# Exercice 1 — La couleur d'un camion

**Semaine 3** · environ 2 heures · après le chapitre 22 du tutoriel (écrans de la flotte)

## La demande

« Pour reconnaître nos camions sur la route, on veut noter leur **couleur** sur la fiche. Ce n'est pas obligatoire. »

## Ce qui doit marcher

- Un camion a une couleur facultative, 30 caractères au plus.
- Le formulaire de création et celui de modification la proposent ; la modification reprend la couleur déjà saisie.
- Les espaces autour de la saisie sont retirés (« ␣Blanc␣ » devient « Blanc »).
- La fiche du camion affiche « Couleur » (un tiret si elle n'est pas renseignée).

## Où regarder

| Fichier | Pourquoi |
|---|---|
| `apps/fleet/models.py` | le modèle `Vehicule` : la colonne de la base |
| `apps/fleet/services.py` | `creer_vehicule`, `modifier_vehicule` : ils reçoivent **chaque champ par son nom** |
| `apps/fleet/forms.py` | `VehiculeForm` : ce que l'écran propose |
| `apps/fleet/views.py` | `VehiculeUpdateView.get_initial` : ce qui pré-remplit la modification |
| `apps/fleet/templates/fleet/` | `vehicule_form.html`, `vehicule_detail.html` |

## Étapes conseillées

1. Copiez le test et lancez-le : il **échoue** (5 tests).
   ```bash
   cp formation/exercices/01-couleur-camion/test_exercice_01.py apps/fleet/tests/
   python -m pytest apps/fleet/tests/test_exercice_01.py -q --no-cov
   ```
2. Ajoutez le champ au modèle, puis générez la migration (ne l'écrivez jamais à la main) :
   ```bash
   python manage.py makemigrations fleet
   ```
3. Faites passer les tests un par un, dans l'ordre du fichier.
4. Lancez **toute** la suite : `python -m pytest -q --no-cov`.

## Indice

Le service n'accepte que les arguments qu'il déclare : un champ ajouté au formulaire arrive dans
`form.cleaned_data`, puis dans `creer_vehicule(**form.cleaned_data)`. Que se passe-t-il si le service ne connaît pas
`couleur` ?

## Correction

À ouvrir **après** avoir essayé : `correction.md` (explications) et `correction.diff` (le code exact).
