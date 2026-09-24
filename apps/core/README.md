# core

Rôle : socle transverse (`BaseModel` avec timestamps + soft delete, mixins,
permissions communes). Aucune dépendance vers les autres apps métier —
c'est la racine du graphe de dépendances (architecture.md:99-163).

Entités principales : `BaseModel` (abstrait) — à créer à l'étape 1.

Recherche texte (`search.py`) : `filtrer_par_texte(queryset, texte, *champs)` compare des valeurs
sans accents ni majuscules (« traore » trouve « Traoré », « moussa traore » trouve Moussa
Traoré) ; à utiliser pour tout champ de recherche des listes plutôt que `icontains`. Sur
PostgreSQL : `LOWER(TRANSLATE(...))` sans extension ; sur SQLite : fonction `NORMALISER`
enregistrée à la connexion. `views.PaginationTolerante` : une page inexistante ou illisible
affiche la première ou la dernière page au lieu d'une erreur 404.

Formulaires (`forms.py`) : `StyleTailwindMixin` applique le style commun **et** écrit les champs `type="date"` au
format `AAAA-MM-JJ` que le navigateur exige (en français, Django écrivait `JJ/MM/AAAA` : la date du jour ou la date
existante n'apparaissait pas dans le champ). À utiliser pour tout formulaire.

Graphiques (`graphiques.py`, balises `graphiques`) et séries mensuelles (`services.py` : `debuts_de_mois`,
`total_par_mois`) : voir `apps/dashboard/README.md`.
