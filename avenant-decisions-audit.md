# Avenant — Décisions de l'audit de conformité (13/10/2026)

L'audit de conformité au cahier des charges (`audit/MATRICE.md`) a relevé des points que le cahier des charges ne
tranchait pas. L'entreprise a décidé le 13/10/2026 :

## Fonctionnement métier

| Point | Décision |
|---|---|
| **AUD-02** — Mission sans issue (panne définitive, client qui annule) | **Annulation et transfert.** Avant le départ, une mission s'annule avec un motif (camion et chauffeur libérés, devis ou facture non émise annulés). En route, elle se transfère vers un autre camion ou chauffeur et continue avec ses codes. |
| **AV-11** — Corriger une facture émise | **Avoir validé par la Direction.** La Finance saisit un avoir (total ou partiel) avec un motif ; la Direction le valide. Il a son propre numéro, réduit le reste à recouvrer et passe l'écriture comptable inverse. La facture d'origine reste intacte. |
| **AV-12** — Annuler une dépense saisie à la main | **Par ceux qui saisissent** (Finance, RH, Direction, administrateur), avec motif ; écriture contre-passée, pointage bancaire défait, comme pour un règlement. |
| **AUD-13** — N° de ticket de carburant | **Inchangé : unique dans toute l'entreprise**, toutes stations confondues. |
| **AV-01** — Report d'un congé en cours | L'employé saisit **le jour où il reprend le travail** ; le congé s'arrête la veille et ce jour lui est reversé. |
| **AV-03** — Dépassement d'enveloppe validé | **La validation relève le plafond** du mois du montant validé : les dépenses suivantes passent tant qu'elles restent dans ce nouveau plafond. |
| **AV-10** — Opération diverse sur un compte de trésorerie | **Interdite.** Un mouvement d'argent se saisit dans Trésorerie (mouvement manuel), qui passe lui-même l'écriture : comptabilité et trésorerie gardent le même solde. |
| **AUD-09** — Compte Direction créé par l'administrateur | **Permis, mais la Direction est prévenue** : toute création d'un compte Direction ou attribution de ce rôle est notifiée immédiatement aux comptes Direction existants et tracée au journal. |

## Services techniques cités par le cahier des charges (§ 4)

| Point | Décision |
|---|---|
| **TECH-18** — SMS (Twilio) | **Pas pour l'instant.** Les alertes partent dans l'application et par e-mail ; à revoir si des chauffeurs n'ont pas d'e-mail. |
| **TECH-19** — Notifications push (Firebase) | **Pas pour l'instant.** L'espace chauffeur reste une page web ; le push demanderait une application mobile publiée. |
| **TECH-20** — Stockage S3 / MinIO | **Disque du serveur conservé**, chiffré dans la sauvegarde nocturne (`avenant-sauvegardes.md`) ; S3 pourra s'ajouter si le volume grossit. |
| **TECH-24** — Prometheus | **Mis en place** : l'application publie ses mesures au format Prometheus sans dépendance supplémentaire (`apps/core/mesures.py` : requêtes, erreurs et temps de réponse par écran, base, cache, file Celery, PDF, âge de la sauvegarde), lues par le service `prometheus` de `docker-compose.yml` avec un jeton, jamais depuis Internet ; alertes dans `ops/prometheus-alertes.yml` ; mode d'emploi `GUIDE-DEPLOIEMENT.md` § 10 bis. |
| **TECH-70** — PDF en tâche de fond | **Mis en place** : les PDF des rapports, listes, factures, devis et avoirs sont préparés par le worker Celery (`apps/core/documents_pdf.py`) ; page d'attente puis téléchargement réservé au demandeur, fichier effacé après 24 h. Restent rendus dans la requête, sans jamais être stockés : les codes d'une mission (un secret) et l'autorisation de congé (document personnel d'une page). |
| **TECH-71** — CDN Cloudflare | **Mis en place côté application** : vraie adresse du visiteur crue seulement depuis les plages de Cloudflare (`nginx/cloudflare-ips.conf`), fichiers statiques publics et cachables, toute autre réponse `private`, défi Let's Encrypt aussi en HTTPS ; réglages du tableau de bord Cloudflare dans `GUIDE-DEPLOIEMENT.md` § 8 bis. Le compte Cloudflare et le DNS sont fournis par l'entreprise. |

## Suivi

Chaque point mis en place est suivi dans `audit/MATRICE.md` (preuve et tests). Les points écartés y sont marqués
« Décision » avec un renvoi à cet avenant.
