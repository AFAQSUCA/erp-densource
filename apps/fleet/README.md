# fleet

Rôle : camions et documents réglementaires — cahier-des-charges.md:88-100.

Entités : `Vehicule`, `DocumentReglementaire`. Services : `calculer_statut`
(algorithme du CDC en 4 règles, fonction pure appelée par `garage`/`missions`),
`recalculer_statut`, `definir_statut`, `documents_a_renouveler` (alerte 30 jours).
