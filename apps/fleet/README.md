# fleet

Rôle : camions et documents réglementaires — cahier-des-charges.md:88-100.

Entités : `Vehicule`, `DocumentReglementaire`. Services : `calculer_statut`
(algorithme du CDC en 4 règles, fonction pure appelée par `garage`/`missions`),
`recalculer_statut`, `definir_statut`, `documents_a_renouveler` (alerte 30 jours).

Interface (`views.py`, `templates/fleet/`) : liste filtrée (statut, texte, documents à
renouveler), fiche avec l'état des 4 documents, création et modification, enregistrement
et renouvellement d'un document. Accès : ADMIN, DIRECTION, PARCAUTO (`permissions.py`).
Le statut n'est jamais saisi à la main : il se calcule (missions, OR).
Services ajoutés : `creer_vehicule`, `modifier_vehicule` (immatriculation et VIN
normalisés, compteur qui ne recule pas), `rechercher_vehicules`, `enregistrer_document`,
`etat_documents`, `vehicules_avec_documents_a_renouveler`.

Reste à faire : marquer un camion Immobilisé / Hors service et le remettre en service
(demande de croiser garage et missions : à porter par l'écran du garage).
