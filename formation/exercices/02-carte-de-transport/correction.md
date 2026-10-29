# Correction — Exercice 2

## Le changement principal (3 lignes)

| Fichier | Changement |
|---|---|
| `apps/fleet/models.py` | `CARTE_TRANSPORT = "CARTE_TRANSPORT", _("Carte de transport")` dans `TypeDocument` |
| migration `0004_carte_de_transport.py` | générée : elle ne fait que mettre à jour la liste des choix |
| `apps/importation/modele.py` | `(TypeDocument.CARTE_TRANSPORT, "Carte de transport")` dans `DOCUMENTS` |

Le reste suit **tout seul** parce que le code lit `TypeDocument.choices` au lieu d'une liste écrite en dur :
l'affectation, les alertes, la fiche, et même la fabrique de test `VehiculeEnRegleFactory` (qui crée « tous les
documents »). C'est la récompense d'une bonne conception : une seule source de vérité.

## L'effet en cascade : 9 tests à mettre à jour

Lancée après ce changement, la suite complète signale 9 échecs. Aucun n'est un bug du nouveau code :

| Tests | Pourquoi ils échouent | Ce qu'on fait |
|---|---|---|
| 4 tests de `apps/fleet/tests/` (`…les_4_types…`, `…4_documents…`, `…manquant`, `…types_du_cdc`) | ils listaient exactement 4 documents | on ajoute la carte de transport à la liste attendue et on renomme le test |
| 5 tests de `apps/importation/tests/test_import.py` | le classeur plante (`IndexError`) : la ligne d'exemple et les largeurs de colonnes étaient prévues pour 4 documents | on ajoute deux dates d'exemple, on calcule les largeurs (`[18] * 2 * len(DOCUMENTS)`), et on **régénère** le classeur livré (`python manage.py generer_modele_import`) |

Deux commentaires qui disaient « les 4 documents » sont aussi corrigés : un commentaire faux est un piège pour le
prochain lecteur.

**Vérification** : les 5 tests de l'exercice passent, et la suite complète aussi (3 422 tests).
