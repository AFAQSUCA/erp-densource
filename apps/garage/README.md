# garage

Rôle : ordres de réparation (OR) — cahier-des-charges.md:161-168. Audité (module `PARC_AUTO`).

Entité : `OrdreReparation` (numéro `OR-AAAA-XXXX` via `core.services.prochain_numero`),
4 types (Curatif, Préventif, Diagnostic, Pneumatiques), 2 lieux (garage interne,
prestataire externe), statuts Ouvert / Clôturé.

Services :
- `ouvrir_or` : crée l'OR et passe le camion « En maintenance » (même en mission :
  panne en route).
- `cloturer_or` : enregistre la main-d'œuvre puis recalcule le statut du camion
  avec `fleet.services.recalculer_statut`, en fournissant `or_ouverts` (garage) et
  `mission_active` (`missions.services.vehicule_a_mission_active`).

Dépend de `fleet` et `missions` (jamais l'inverse).

Reste à faire (app `inventory`, étape 3c) : coût automatique des pièces utilisées
et total de l'OR (cahier-des-charges.md:167-168).
