# Correction — Exercice 7

| Fichier | Changement | Pourquoi |
|---|---|---|
| `apps/missions/services.py` | `missions_annulees_entre(debut, fin)` : un `count()` sur `statut=ANNULEE` et `date_annulation__date` entre les deux dates | le calcul appartient à l'app qui possède les missions ; `__date` compare la date **locale** (Abidjan), pas l'heure UTC |
| `apps/dashboard/services.py` | `"missions_annulees_du_mois": missions_services.missions_annulees_entre(jour.replace(day=1), jour)` dans `exploitation()` | le tableau de bord assemble ; `jour.replace(day=1)` donne le 1er du mois |
| `apps/dashboard/templates/dashboard/index.html` | une 4e case « Annulées ce mois » ; la grille passe à `sm:grid-cols-2 lg:grid-cols-4` | quatre cases sur une ligne en grand écran, deux sur tablette. Ces classes existent déjà dans la feuille compilée : pas besoin de recompiler Tailwind |
| `apps/dashboard/views.py` | la même ligne dans le PDF du tableau de bord | la page et son PDF montrent les mêmes chiffres |

Le bloc Exploitation est mis en cache (`DASHBOARD_CACHE_SECONDS`) : le nouveau chiffre aussi, sans rien ajouter.

**Le test des 34 requêtes** passe toujours : l'indicateur coûte une requête, et la page d'un ADMIN restait sous la
limite. Si elle l'avait dépassée, il aurait fallu calculer ce nombre dans la même requête que
`repartition_par_statut`, plutôt que d'augmenter la limite du test.

Aucun test existant ne casse.

**Vérification** : les 4 tests de l'exercice passent, et la suite complète aussi (3 421 tests).
