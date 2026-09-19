# missions

Rôle : missions de transport et leur cycle de vie — cahier-des-charges.md:127-143.
Audité (module `MISSION`) ; les codes secrets sont exclus du journal.

Entité : `Mission` (numéro `MIS-AAAA-XXXX` via `core.services.prochain_numero`).

Cycle : Brouillon → Planifiée → Affectée → En cours (départ → colis récupéré)
→ Livrée → Clôturée. Services : `creer_mission`, `planifier_mission`,
`affecter_mission` (camion et chauffeur disponibles, non réservés, capacité
respectée), `demarrer_mission` (camion + chauffeur « En mission »),
`confirmer_recuperation` (code expéditeur), `livrer_mission` (code destinataire,
km d'arrivée → compteur du camion, camion + chauffeur libérés),
`cloturer_mission`. `vehicule_a_mission_active` fournit `mission_active` à
`fleet.services.calculer_statut`.

Reste à faire :
- Contrôle des rôles (chargé clientèle, direction, chauffeur) : permissions DRF, étape 6.
- Image QR des deux codes (bibliothèque `qrcode` + Pillow) : étape 6 / mobile.
- Notification « en cours de route (départ) » : `notifications`, étape 5.
- Alerte N1 des congés « chauffeur avec mission sur la période » (via `date_depart_prevue`).
