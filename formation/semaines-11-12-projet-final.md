# Semaines 11 et 12 — Le projet final : suivre les pneus des camions

But : livrer **seul** une fonctionnalité complète, du besoin à la mise en ligne. Il n'y a pas de correction :
c'est le test de votre autonomie. Vous pouvez demander de l'aide sur un point précis, pas sur l'ensemble.

## Le besoin

« Les pneus sont notre deuxième dépense après le carburant. Pour chaque camion, on veut savoir **quels pneus sont
montés, depuis quand, à quel kilométrage**, et être prévenus quand un pneu a trop roulé. »

## Ce qu'il faut livrer

1. **Le besoin en une page** (`avenant-pneus.md`), validé par l'entreprise avant de coder : règles, rôles, cas
   limites. Exemples de questions à trancher : un pneu change-t-il de camion ? qui saisit un montage ? quelle
   distance déclenche l'alerte, et est-elle un paramètre ?
2. **Le modèle** : un pneu (référence, marque, position sur le camion, date et kilométrage de montage, statut).
3. **Les règles** dans `services.py` : monter, démonter, kilométrage parcouru (compteur actuel − compteur au montage),
   alerte au-delà de la distance choisie.
4. **Les droits** dans `permissions.py` : qui consulte, qui saisit.
5. **Les écrans** : la liste des pneus d'un camion sur sa fiche, le montage et le démontage.
6. **L'alerte** au centre d'alertes du Parc Auto (tableau de bord).
7. **Les tests** : chaque règle a le sien, écrit **avant** le code.
8. **La documentation** : le README de l'app, et une ligne dans la section 7 du cahier des charges.
9. **La PR**, revue, puis la mise en ligne (`GUIDE-DEPLOIEMENT.md` § 11).

## Grille d'auto-évaluation

| Critère | Oui / non |
|---|---|
| Aucune règle dans une vue ou un gabarit | |
| Chaque droit passe par `permissions.py`, et un test le prouve pour un rôle autorisé et un rôle refusé | |
| Les migrations sont générées, `makemigrations --check` ne signale rien | |
| `python -m pytest -q --no-cov` : tout passe, y compris le test d'architecture | |
| Les montants et kilométrages ne sont jamais des `float` | |
| Une action importante (montage, démontage) va au journal d'audit | |
| Le tutoriel se régénère encore (`python outils/generer_tutoriel.py`) | |
| La PR explique **pourquoi**, pas seulement quoi | |

Si toutes les cases sont « oui » sans aide, l'objectif « pouvoir modifier le projet seul » est atteint.
