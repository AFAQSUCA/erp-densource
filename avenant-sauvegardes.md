# Avenant — Sauvegardes planifiées et suivies par l'ADMIN

Complète le cahier des charges : §3 Module 1, ligne 48 (« **ADMIN** : … sauvegardes ») et §4, ligne 282
(« sauvegardes chiffrées et testées »). L'audit (M1-14, TECH-56, AUD-18) relevait trois manques : les fichiers déposés
n'étaient pas sauvegardés, aucune planification n'était livrée (un exemple de cron dans le guide seulement), et le mot
de passe de la base apparaissait dans la liste des processus du serveur.

## Décision de l'entreprise (12/10/2026)

| Question | Décision |
|---|---|
| Comment la sauvegarde de nuit se déclenche ? | Un **service Docker dédié** (`sauvegarde`), démarré avec le reste : rien à installer sur le serveur |
| Que voit l'ADMIN dans l'ERP ? | Un **écran de suivi** (derniers essais, dernière réussite), une **alerte** au tableau de bord, et un bouton **« Sauvegarder maintenant »** |

## Ce qui est sauvegardé

- La **base** (`pg_dump`) et les **fichiers déposés** (justificatifs, pièces jointes : volume `media_data`), chaque
  nuit à 2 h (réglable) et à la demande ; chiffrés (GPG, AES-256), rotation 30 jours, copie hors serveur facultative.
- Chaque essai est consigné dans un journal : date, réussite ou échec, taille et empreinte SHA-256 de chaque fichier.

## Règles

- **Droits** : écran et bouton réservés à l'**ADMIN** (cahier des charges, M1). La DIRECTION n'y a pas accès.
- **Séparation** : l'application ne lance rien elle-même ; elle dépose une demande que le service exécute dans les 30
  secondes. Elle ne peut ni lire ni télécharger les fichiers chiffrés.
- **Alerte** à l'ADMIN : aucune sauvegarde réussie, ou dernière réussite de plus de 26 h (urgent) ; dernier essai en
  échec, ou copie hors serveur échouée (attention).
- **Secrets** : ni la phrase de passe ni le mot de passe de la base n'apparaissent dans la liste des processus.
- **Test** : une restauration à blanc reste à faire chaque mois (GUIDE-DEPLOIEMENT.md § 9) ; l'ERP le rappelle sur
  l'écran.

## Implémentation

Scripts `ops/sauvegarde.sh`, `ops/restauration.sh`, `ops/fonctions-sauvegarde.sh`, `ops/planificateur-sauvegarde.sh` ;
image `ops/Dockerfile.sauvegarde` ; service `sauvegarde` et volume `sauvegardes_data` (`docker-compose.yml`) ; app
`apps/sauvegardes` (écran, alerte). Détails : `apps/sauvegardes/README.md`.
