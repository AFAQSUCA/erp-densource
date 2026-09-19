# drivers

Rôle : extension 1-1 de `Personnel` pour les chauffeurs — cahier-des-charges.md:105-113.
La fiche est créée automatiquement (signal) quand le poste est « Chauffeur ».
Dépend de `hr` (jamais l'inverse).

Entités : `Chauffeur`. Services : `assurer_fiche_chauffeur`, `changer_statut`,
`chauffeurs_a_renouveler` (alerte 30 jours permis / visite médicale).
