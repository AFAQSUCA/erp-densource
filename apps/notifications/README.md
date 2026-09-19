# notifications

Rôle : prévenir les bons utilisateurs au bon moment — cahier-des-charges.md:137, 215, 221,
231-232, 253 ; architecture.md:269-338. Couche haute : elle s'abonne aux événements des apps
métier, qui ne la connaissent pas.

Entité : `Notification` (destinataire, catégorie, niveau, titre, message, lien, lue le,
`cle_unicite`). `services.notifier(destinataires, ...)` crée une notification par compte actif ;
avec `cle`, un destinataire ne reçoit qu'une fois le même message (rappels quotidiens).

Qui est prévenu de quoi (`receivers.py`) :
- congé déposé → supérieur hiérarchique (N1), plus une alerte urgente s'il y a une mission
  prévue sur la période ; validé en N1 → RH ; approuvé, refusé ou annulé → l'employé ;
- stock au seuil → PARCAUTO ; surconsommation, anomalie ou saisie suspecte → PARCAUTO et DIRECTION ;
- mission partie → chargé clientèle attitré du client (à défaut, tous les chargés clientèle).

Tâches du jour (`taches.py`, commande `taches_quotidiennes`) : documents des camions et
permis / visites des chauffeurs à 30 jours puis expirés (une alerte à chaque changement d'état),
rappel au validateur quand le délai de 48 h (N1) ou 24 h (N2) est dépassé, et passage des
congés à « En cours » / « Terminé ».

Canaux : toujours dans l'application (cloche + page `/notifications/`) ; en plus par e-mail si
`NOTIFICATIONS_EMAIL` est actif. Un e-mail en échec est journalisé sans jamais bloquer
l'opération métier, et un récepteur en erreur n'empêche pas non plus une validation de congé,
un plein ou un départ de mission (`send_robust`).

Reste à faire :
- **Celery + Redis** (architecture.md, ADR-004) : non installé (pas de Redis ici, rien à
  vérifier). `taches.executer_taches_quotidiennes` est prévue pour être appelée telle quelle
  par Celery Beat au déploiement (étape 7) ; les e-mails partiront alors en tâche asynchrone.
- **SMS (Twilio) et notifications push (Firebase)** : demandent des comptes externes.
- Notification du client à l'expédition (« en cours de route ») : le CDC ne dit pas à qui ;
  seul le chargé clientèle est prévenu pour l'instant.
- Préférences de notification par utilisateur.
