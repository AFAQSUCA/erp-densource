# Avenant au cahier des charges — Séparation des tâches

> Complète `cahier-des-charges.md` (source de vérité du projet). Sept règles demandées par
> l'entreprise, fondées sur un principe unique : **celui qui demande une dépense ou fixe un prix
> n'est jamais celui qui la valide**. Chaque section ci-dessous est ajoutée une fois la règle
> livrée (services, permissions, tests, écrans) — pas avant.

## État d'avancement

| Règle | Objet | Statut |
|---|---|---|
| R3 | Modification d'une mission | ✅ Livrée |
| R7 | Congés (26 jours ouvrés, report) | À venir |
| R5/R1 | Facture proforma (fusionnée avec la validation des prix) | À venir |
| R6 | Mission créée depuis une proforma | À venir |
| R4 | Prévision de trésorerie des missions | À venir |
| R2 | Dépenses du parc auto (demande → validation → décaissement) | À venir |

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
