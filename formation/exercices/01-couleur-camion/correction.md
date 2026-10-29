# Correction — Exercice 1

Six fichiers changent, plus une migration générée. Le code exact est dans `correction.diff`.

| Fichier | Changement | Pourquoi |
|---|---|---|
| `models.py` | `couleur = models.CharField(_("couleur"), max_length=30, blank=True)` | `blank=True` rend le champ facultatif ; pas de `null=True` pour un texte : Django stocke une chaîne vide |
| migration `0004_couleur_vehicule.py` | générée par `makemigrations fleet` | la base doit suivre le modèle |
| `forms.py` | `couleur = forms.CharField(..., required=False)` | l'écran propose le champ, sans l'exiger |
| `services.py` | `couleur: str = ""` dans `creer_vehicule` et `modifier_vehicule`, enregistrée avec `.strip()` | la règle « sans espaces autour » vit dans le service, pas dans la vue : l'import Excel ou l'API en profiteraient aussi |
| `views.py` | `"couleur": v.couleur` dans `get_initial` | sans cela, la modification afficherait un champ vide et effacerait la couleur à l'enregistrement |
| gabarits | le champ dans le formulaire, la ligne « Couleur » sur la fiche avec `|default:"—"` | l'affichage |

**Ce qu'il fallait remarquer** : sans le paramètre `couleur` dans le service, l'écran plante
(`TypeError: unexpected keyword argument 'couleur'`), car la vue passe tout `form.cleaned_data` au service.
C'est voulu : le service décide de ce qu'il accepte.

**Vérification** : les 5 tests de l'exercice passent, et la suite complète aussi (3 422 tests).
