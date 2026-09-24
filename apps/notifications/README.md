# notifications

Rôle : prévenir les bons utilisateurs au bon moment — cahier-des-charges.md:137, 215, 221,
231-232, 253 ; architecture.md:269-338. Couche haute : elle s'abonne aux événements des apps
métier, qui ne la connaissent pas.

Entité : `Notification` (destinataire, catégorie, niveau, titre, message, lien, `action`, lue le,
`cle_unicite`). `action` est le libellé d'un bouton facultatif (« Confirmer le versement ») : la liste
affiche un bouton vert qui marque la notification lue puis mène au lien. `services.notifier(destinataires, ...)` crée une notification par compte actif ;
avec `cle`, un destinataire ne reçoit qu'une fois le même message (rappels quotidiens).

Qui est prévenu de quoi (`receivers.py`) :
- congé déposé → supérieur hiérarchique (N1), plus une alerte urgente s'il y a une mission
  prévue sur la période ; validé en N1 → RH ; approuvé, refusé ou annulé → l'employé ;
- stock au seuil → PARCAUTO ; surconsommation, anomalie ou saisie suspecte → PARCAUTO et DIRECTION ;
- mission partie → chargé clientèle attitré du client (à défaut, tous les chargés clientèle) ;
- facture soumise → DIRECTION ; validée → FINANCES (avec le bouton « Confirmer le versement », voir
  `finance`) et son auteur (simple information) ; renvoyée → son auteur ;
  facture échue (tâche du jour) → FINANCES et DIRECTION, une fois par facture.

Tâches du jour (`taches.py`, commande `taches_quotidiennes`) : documents des camions et
permis / visites des chauffeurs à 30 jours puis expirés (une alerte à chaque changement d'état),
rappel au validateur quand le délai de 48 h (N1) ou 24 h (N2) est dépassé, et passage des
congés à « En cours » / « Terminé ».

Canaux : toujours dans l'application (cloche + page `/notifications/`) ; en plus par e-mail si
`NOTIFICATIONS_EMAIL` est actif. Un e-mail en échec est journalisé sans jamais bloquer
l'opération métier, et un récepteur en erreur n'empêche pas non plus une validation de congé,
un plein ou un départ de mission (`send_robust`).

Tâches asynchrones (`tasks.py`, étape 7 lot 2, ADR-004) : `envoyer_email_notification` (l'envoi
d'un e-mail, déclenché après le commit par `notifier`) et `executer_taches_quotidiennes` (relais
Celery de `taches.py`, planifiée chaque jour par `CELERY_BEAT_SCHEDULE`). En développement et en
test, `CELERY_TASK_ALWAYS_EAGER` les exécute immédiatement, dans le même processus, sans courtier :
rien à installer pour développer ou tester. En production, un `celery worker` (et `celery beat`
pour la planification) doivent tourner à côté de l'application, contre le Redis de `REDIS_URL`.

Reste à faire :
- **SMS (Twilio) et notifications push (Firebase)** : demandent des comptes externes.
- Notification du client à l'expédition (« en cours de route ») : le CDC ne dit pas à qui ;
  seul le chargé clientèle est prévenu pour l'instant.
- Préférences de notification par utilisateur.
