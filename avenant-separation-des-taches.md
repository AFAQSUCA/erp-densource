# Avenant au cahier des charges — Séparation des tâches

> Complète `cahier-des-charges.md` (source de vérité du projet). Sept règles demandées par
> l'entreprise, fondées sur un principe unique : **celui qui demande une dépense ou fixe un prix
> n'est jamais celui qui la valide**. Chaque section ci-dessous est ajoutée une fois la règle
> livrée (services, permissions, tests, écrans) — pas avant.

## État d'avancement

| Règle | Objet | Statut |
|---|---|---|
| R3 | Modification d'une mission | ✅ Livrée (PR #12, en attente de fusion) |
| R7 | Congés (26 jours ouvrés, report du solde) | ✅ Livrée |
| R5/R1 | Facture proforma (fusionnée avec la validation des prix) | À venir |
| R6 | Mission créée depuis une proforma | À venir |
| R4 | Prévision de trésorerie des missions | À venir |
| R2 | Dépenses du parc auto (demande → validation → décaissement, enveloppes) | À venir |

---

## R3 — Modification d'une mission

**Ajoute à** cahier-des-charges.md Module 5 (Missions & Trajets), après le cycle de vie
(cahier-des-charges.md:132-134).

- Une mission peut être modifiée (lieux, marchandise, poids, prix convenu, date de départ prévue)
  tant qu'elle n'a pas dépassé le statut **« Colis récupéré »**.
- Modification réservée à **DIRECTION et ADMIN** (plus restreint que la création, ouverte aussi au
  chargé clientèle).
- Changer le camion ou le chauffeur revérifie leur disponibilité (mêmes contrôles qu'à
  l'affectation initiale) — possible uniquement sur une mission déjà **Affectée**, avant le départ.
- Changer un lieu de chargement ou de livraison régénère les deux codes secrets (expéditeur,
  destinataire) : l'ancien code, et son QR, ne servent plus.
- Le client n'est pas modifiable.
- Chaque modification est tracée dans le journal d'audit (ancienne/nouvelle valeur), au même titre
  que le reste du cycle de vie de la mission.

**Implémentation** : `apps.missions.services.modifier_mission`, `permissions.MODIFICATION`,
écran `/missions/<id>/modifier/`. Détails : `apps/missions/README.md` § Modification.

---

## R7 — Congés : 26 jours ouvrés, report du solde d'un congé en cours

**Remplace, dans cahier-des-charges.md Module 11** (cahier-des-charges.md:219-221) :

- **Droit annuel : 26 jours ouvrés** (au lieu de 12 jours ouvrables) — avantage social au-delà du
  minimum légal ivoirien (2,2 jours ouvrables/mois ≈ 26,4 jours ouvrables/an). Décision confirmée
  explicitement par l'entreprise après vérification du calcul (26 jours **ouvrés**, lundi-vendredi,
  donne davantage de repos calendaire que le minimum légal en jours **ouvrables**, samedi compris).
- **Décompte en jours ouvrés** : du lundi au vendredi, hors jours fériés légaux (`JourFerie`). Le
  samedi ne compte plus (avant : « ouvrables », tous les jours sauf dimanche).
- **Annulation par la RH inchangée** : un congé approuvé annulé continue de restituer les jours à
  l'employé (règle non modifiée — l'entreprise n'a pas confirmé ce changement-là lors de la
  clarification).
- **Nouveau : report du solde d'un congé en cours.** Un bouton « Reporter » apparaît sur la ligne
  du tableau des congés de l'employé **actuellement en congé** (statut « En cours »). Il indique le
  jour où il reprend réellement le travail (avant la fin initialement prévue) et un motif. **Sans
  validation de la RH, la demande n'a aucun effet** : le congé continue normalement. La RH est
  notifiée (bouton « Confirmer le report ») ; une fois validée : le congé est raccourci à la
  nouvelle date de reprise, les jours ouvrés non pris sont reversés au solde de l'année, et le
  document d'autorisation (PDF) reflète le report (motif, date, jours reversés) — automatiquement,
  puisqu'il est régénéré à la demande à chaque téléchargement plutôt que stocké une fois pour
  toutes. Une seule demande de report à la fois par congé.
- **Nouveau : PDF « Autorisation de congé ».** Téléchargeable dès qu'un congé est approuvé (N2) :
  numéro, employé, dates, jours décomptés, validateurs N1/N2, solde restant de l'année, et la
  section report si applicable. Même en-tête (logo, couleurs de la marque) que le PDF des codes de
  mission.

**Implémentation** : `apps.hr.models.ReportConge`, `apps.hr.services.demander_report` /
`approuver_report` / `refuser_report`, écran `/rh/conges/<id>/reporter/`, PDF
`/rh/conges/<id>/autorisation.pdf` (`apps.hr.documents`). Détails : `apps/hr/README.md`.
