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

Interface (`views.py`, `templates/missions/`) : liste filtrée et paginée, fiche avec
frise du cycle de vie, création, et une action POST par transition. Droits par rôle
dans `permissions.py` (direction : affectation, suivi, clôture ; chargé clientèle :
création et planification). Les codes ne s'affichent que tant qu'ils servent.

### Retour d'une réunion entreprise : Parc Auto affecte, copilote facultatif

C'est le **Parc Auto** qui affecte les missions (camion, chauffeur, et éventuellement copilote) une
fois que le chargé clientèle les a créées et planifiées (`permissions.AFFECTATION` et
`permissions.CONSULTATION` incluent désormais `Role.PARCAUTO`, en plus d'ADMIN et DIRECTION). Le Parc
Auto ne voit pas pour autant les codes secrets : `permissions.VOIR_CODES` reste un ensemble
indépendant de `CONSULTATION`, réservé à ceux qui gèrent la relation client (ADMIN, DIRECTION, chargé
clientèle).

Certains voyages exigent un **copilote** (assistant du chauffeur pendant le trajet, `drivers.Copilote`
— une fiche distincte du chauffeur, jamais un chauffeur principal). Aucune règle automatique : c'est
une **décision humaine du Parc Auto au moment de l'affectation**, sur le même écran que le camion et
le chauffeur (`AffectationForm.copilote`, facultatif). `affecter_mission` vérifie sa disponibilité
comme pour le chauffeur (non déjà réservé par une autre mission active) ; `demarrer_mission` et
`livrer_mission` le mettent « En mission » / le libèrent en parallèle du chauffeur s'il est affecté.

### Saisie des codes : le chauffeur affecté (ou l'ADMIN / la DIRECTION)

Les codes de récupération et de livraison ne se confirment que par le **chauffeur affecté** (saisie ou
scan du QR depuis l'espace mobile, où une mission d'un autre chauffeur est introuvable) — ou par
l'**ADMIN** ou la **DIRECTION** (même largeur que l'ADMIN, retour réunion), en correction depuis le
back-office (`permissions.CODES_TERRAIN`). Le chargé clientèle et le Parc Auto voient (pour le
premier) ou n'ont pas accès (pour le second) aux codes, mais ne peuvent pas les saisir ; le
« départ », lui, reste ouvert à l'ADMIN et à la DIRECTION (aucun code n'est en jeu).

### Modification (`modifier_mission`, séparation des tâches — avenant-separation-des-taches.md § R3)

Tant que la mission n'a pas dépassé « Colis récupéré » (`STATUTS_MODIFIABLES`), **DIRECTION et ADMIN
seulement** (`permissions.MODIFICATION` — plus restreint que `CREATION`, qui inclut aussi le chargé
clientèle) peuvent modifier lieux, marchandise, poids, prix, date de départ prévue, et — une fois la
mission déjà **Affectée** seulement — réaffecter camion/chauffeur (revérifie leur disponibilité comme à
l'affectation, `_verifier_disponibilite` partagée avec `affecter_mission`). Changer un lieu régénère les
deux codes secrets (donc leurs QR, rendus à la volée). Le client n'est pas modifiable : c'est l'identité
de la mission. Réaffecter camion/chauffeur une fois le départ effectué (`EN_COURS_DEPART`) n'est pas pris
en charge : le camion est physiquement engagé, ça relève d'un signalement d'incident plutôt que d'une
simple modification. Tracé gratuitement par l'audit déjà branché sur `Mission`.

### PDF des codes (`documents.py`, ReportLab)

`/missions/<id>/codes.pdf` (bouton « Télécharger le PDF des codes » de la fiche, proposé dès la création) :
une page par partie, avec l'en-tête de l'entreprise et son logo (`ENTREPRISE_NOM`, `ENTREPRISE_ADRESSE`,
`ENTREPRISE_NCC`) — l'**expéditeur** (code de récupération + QR, à remettre au chauffeur au chargement) et le
**destinataire** (code de réception + QR, à transmettre à la personne qui réceptionnera la marchandise, qui
le remettra au chauffeur). Chaque page ne contient que le code de sa partie ; à envoyer à chacun
séparément. Mêmes règles que l'affichage des codes (rôles qui les voient, et seulement tant qu'ils sont
utiles) ; produit à la demande, jamais stocké ni mis en cache. L'envoi reste manuel : la mission ne
mémorise pas les coordonnées de l'expéditeur ni du destinataire.

### Suivi en direct (WebSocket : `temps_reel.py`, `consumers.py`, `routing.py`, `static/js/suivi-missions.js`)

Toute mission enregistrée (création, planification, affectation, départ, récupération, livraison, clôture —
y compris la saisie du code par le chauffeur depuis son téléphone) est diffusée, une fois la transaction
validée, aux fiches et à la liste des missions ouvertes : elles se mettent à jour seules, sans recharger la
page, avec un voyant « En direct » (et une annonce pour les lecteurs d'écran). Le message ne contient que
« quelle mission, quel statut » — jamais un code ; les données sont relues par une requête ordinaire, avec
les droits de la personne. La WebSocket exige les mêmes garanties que les pages : session, rôle qui consulte
les missions, et double authentification vérifiée (l'ADMIN et la DIRECTION), l'origine étant contrôlée
(`AllowedHostsOriginValidator`). Si Redis est indisponible, la diffusion échoue en silence (journalisée) : le
métier n'est jamais bloqué. Une saisie en cours n'est jamais écrasée : un bandeau propose d'actualiser.

Architecture : Gunicorn sert les pages ; le conteneur `realtime` (Daphne, `config/asgi.py`) tient les
WebSocket ; Redis (`channels-redis`) relie les deux. En développement, `runserver` (Daphne) fait tout, avec une
couche de messages en mémoire — un changement fait depuis un autre processus (`manage.py shell`) n'y est donc
pas diffusé, contrairement à un changement fait par le serveur lui-même.

### Suggestions de lieux

Le formulaire de création propose (liste `datalist`) les lieux de chargement et de livraison déjà saisis,
les plus fréquents d'abord, dès les premières lettres (`services.lieux_deja_utilises`) ; un lieu écrit avec
une autre casse ou sans accent ne compte qu'une fois. La saisie libre reste possible.

### Mission créée depuis un devis accepté (R6)

`Mission.proforma` (`OneToOneField` vers `billing.Proforma`, PROTECT) garantit **1 devis = 1
mission** au niveau base. `billing.services.convertir_en_mission(proforma)` (pas `missions` :
le graphe de dépendance des apps, architecture.md:95-163, interdit à `missions` de dépendre de
`billing` — l'inverse est permis, `billing` appelle donc `missions.services.creer_mission`)
recopie tel quel le trajet, la marchandise, le poids et le **prix HT** du devis (la facture
recalculera la TVA plus tard, avec le taux du client en vigueur ce jour-là) ; le devis passe à
`CONVERTIE`. Déclenché sur `POST /facturation/devis/<id>/creer-mission/`, réservé au rôle
`missions.permissions.CREATION`. Refusé si le devis n'est pas `ACCEPTEE` (y compris s'il l'a
déjà été converti).

### Prévision de trésorerie des missions (`terrain.py`, R4 — avenant-separation-des-taches.md)

Séparation des tâches : celui qui déclare ou planifie un frais n'est jamais celui qui le valide. Modèle
`FraisMission` (`mission`, `type_frais`, `montant`, `justificatif`, `statut`) :

- **Avance de route** / **dépense prévue** : planifiée par le **Parc Auto** (`planifier_frais`,
  écran `/missions/<id>/frais/`), confirmée par la seule **Finance** (`valider_finances`).
- **Imprévu** (panne, incident) : déclaré par le **chauffeur** depuis l'espace mobile (photo ou facture
  obligatoire) puis validé deux fois — le **Parc Auto** d'abord (`valider_parcauto`), la **Finance**
  ensuite (`valider_finances`) — jamais par celui qui l'a déclaré ni en une seule fois.
- **Encaissement** : reflet automatique d'un règlement déjà enregistré pour la facture de la mission
  (`billing.signals.reglement_enregistre`, souscrit par `finance`), créé directement confirmé : aucune
  double saisie.

Seule une ligne **confirmée** représente un mouvement de trésorerie réel : `finance.receivers` la
transforme alors en `billing.Depense` (catégorie « Frais de mission »), sauf l'encaissement qui n'en
crée pas (déjà compté via son règlement). `missions` ignore `billing` et `finance` — c'est `finance` qui
relie les trois signaux (`frais_mission_confirme`, `reglement_enregistre`), pour respecter le graphe de
dépendance des apps (architecture.md:95-163).

Signal `mission_affectee` (Affectée = mouvement de caisse probable) prévient la Finance. Écran séparé de
la fiche mission (`permissions.FRAIS_CONSULTATION` : ADMIN, DIRECTION, PARCAUTO, FINANCES — pas le chargé
clientèle, qui ne voit déjà pas le prix convenu côté chauffeur). Rapport de mission imprimable
(`/missions/<id>/frais/imprimer/`) : lignes et totaux (sorties confirmées, encaissé, solde).

**Limite connue** : la modification d'une mission (R3) ne verrouille pas encore son prix une fois des
frais confirmés dessus, ni une fois créée depuis un devis accepté (R6).

Reste à faire :
- Notification « en cours de route (départ) » : signal `mission_demarree`, abonné par `notifications` (fait, étape 5).
- Alerte N1 des congés « chauffeur avec mission sur la période » (via `date_depart_prevue`).

Rapport imprimable des missions (bouton « Imprimer » sur la liste, mêmes filtres) : voir `apps/core/README.md` (`ImpressionListeMixin`).
