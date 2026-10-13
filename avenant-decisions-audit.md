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
| **TECH-24** — Prometheus | **À mettre en place** : mesures techniques du serveur (temps de réponse, erreurs), en plus de Sentry. |
| **TECH-70** — PDF en tâche de fond | **À mettre en place** : les PDF sont générés par Celery plutôt que dans la requête. |
| **TECH-71** — CDN Cloudflare | **À mettre en place** : l'application est servie derrière Cloudflare (réglages côté application et guide de déploiement ; le compte Cloudflare et le DNS sont fournis par l'entreprise). |

## Suivi

Chaque point mis en place est suivi dans `audit/MATRICE.md` (preuve et tests). Les points écartés y sont marqués
« Décision » avec un renvoi à cet avenant.
