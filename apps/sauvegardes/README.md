# sauvegardes

Rôle : suivi des sauvegardes par l'ADMIN — cahier-des-charges.md:48 (« ADMIN : … sauvegardes ») et :282 (« sauvegardes
chiffrées et testées ») ; décision du 12/10/2026 (`avenant-sauvegardes.md`). Écran `/sauvegardes/`, menu « Sauvegardes »,
ADMIN seulement. Dépend de `core`, `accounts`, `audit` ; lu par `dashboard` (architecture.md).

- **Qui sauvegarde** : le service `sauvegarde` de `docker-compose.yml` (`ops/planificateur-sauvegarde.sh`, image
  `ops/Dockerfile.sauvegarde`) appelle `ops/sauvegarde.sh` chaque nuit (`SAUVEGARDE_HEURE`) et à la demande. Base
  (`pg_dump`) et fichiers déposés (`tar` du volume `media_data`), chiffrés GPG, rotation, copie hors serveur facultative.
- **Ce que fait l'application** : elle **lit** le journal (`journal.jsonl`, une ligne JSON par essai) et
  `en_cours.json`, et **dépose une demande** (`demandes/<horodatage>.demande`, écriture atomique) quand l'ADMIN clique
  sur « Sauvegarder maintenant ». Elle n'a aucun accès à Docker ni aux fichiers chiffrés (droits 600, propriétaire root).
  Dossier partagé : `settings.SAUVEGARDES_DIR` (volume `sauvegardes_data`, monté sur `/app/sauvegardes`).
- **Statuts** : `OK` ; `ALERTE` (sauvegarde faite, copie hors serveur échouée) ; `ECHEC` (rien n'est gardé, aucun
  fichier tronqué). Une ligne illisible du journal est ignorée sans masquer les autres.
- **Double clic** : une demande est refusée tant qu'une autre attend ou qu'une sauvegarde est en cours.
- **Alerte** (`services.alerte`, centre d'alertes de l'ADMIN) : aucune sauvegarde réussie, dernière réussie de plus de
  26 h (urgent) ; dernier essai en échec, copie hors serveur échouée (attention). Seulement si
  `SAUVEGARDES_SURVEILLEES` (vrai par défaut en production, faux en développement où le service ne tourne pas).
- **Audit** : chaque demande est journalisée (module `SAUVEGARDES`, entité `DemandeSauvegarde`).
- **Restauration** : `ops/restauration.sh` (base : `.dump.gpg` ; fichiers : `.tar.gz.gpg` avec `RESTAURATION_MEDIAS`),
  essai mensuel décrit dans GUIDE-DEPLOIEMENT.md § 9.
