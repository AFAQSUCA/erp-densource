# audit

Rôle : journal d'audit append-only (`audit_log`), 14 champs —
cahier-des-charges.md:56-82. Capture LOGIN/LOGOUT/CREATE/UPDATE/DELETE/
VALIDATE via middleware + signals `post_save` (ADR-003, architecture.md:488-493).
Dépend de `core` (architecture.md:135).

Entités principales : `AuditLog`. `registry.audit_model()` branche l'audit automatique (CREATE/UPDATE/DELETE avant/après) sur un modèle. Un champ fichier (`FileField`/`ImageField`, ex. `missions.FraisMission.justificatif` (R4), `finance.DemandeDepense.piece_jointe`/`finance.OrdreDecaissement.justificatif` (R2)) est normalisé en son chemin (chaîne vide sans fichier) avant l'écriture JSON : la valeur brute (`FieldFile`) n'est pas sérialisable telle quelle.

Règles :
- Immuabilité stricte : aucun `update()`/`delete()` autorisé sur ce modèle.
- Conservation ≥ 5 ans.
- Consultation : ADMIN (complet), DIRECTION (lecture seule). En pratique les deux ont le même accès en
  lecture (`permissions.CONSULTATION`) : il n'y a de toute façon aucune écriture possible depuis l'écran.

Écran (`/audit/`, menu « Journal d'audit ») : liste filtrable (texte sur utilisateur/entité/IP, module,
action, statut, période), `services.rechercher()`. Export PDF/CSV pour les audits externes
(cahier-des-charges.md:82) : bouton « Imprimer » (rapport HTML, voir `apps/core/rapports.py`) et bouton
« Exporter en CSV » (`JournalExporterCsvView`, mêmes filtres, `;` en séparateur pour Excel).
