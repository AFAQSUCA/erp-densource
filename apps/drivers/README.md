# drivers

Rôle : extension 1-1 de `Personnel` pour les chauffeurs — cahier-des-charges.md:105-113.
La fiche est créée automatiquement (signal) quand le poste est « Chauffeur ».
Dépend de `hr` (jamais l'inverse).

Entités : `Chauffeur`. Services : `assurer_fiche_chauffeur`, `changer_statut`,
`chauffeurs_a_renouveler` (alerte 30 jours permis / visite médicale).

Interface (`views.py`, `templates/drivers/`) : liste filtrée (statut, texte, permis ou
visite à renouveler), fiche avec l'état du permis et de la visite médicale (alerte à
30 jours), modification des informations propres au chauffeur, suspension / désactivation
/ réactivation. Accès : ADMIN, DIRECTION, RH (`permissions.py`). Matricule, nom et
prénom viennent de la fiche du personnel et ne se modifient pas ici ; « En mission » et
« En congé » sont posés par les missions et les congés et ne se changent pas à la main.
Services ajoutés : `rechercher_chauffeurs`, `etat_echeances`, `modifier_chauffeur`,
`changer_statut_manuel`, `chauffeurs_avec_echeance_proche`.
