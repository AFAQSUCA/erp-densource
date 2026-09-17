# core

Rôle : socle transverse (`BaseModel` avec timestamps + soft delete, mixins,
permissions communes). Aucune dépendance vers les autres apps métier —
c'est la racine du graphe de dépendances (architecture.md:99-163).

Entités principales : `BaseModel` (abstrait) — à créer à l'étape 1.
