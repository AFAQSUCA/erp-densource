# audit

Rôle : journal d'audit append-only (`audit_log`), 14 champs —
cahier-des-charges.md:56-82. Capture LOGIN/LOGOUT/CREATE/UPDATE/DELETE/
VALIDATE via middleware + signals `post_save` (ADR-003, architecture.md:488-493).
Dépend de `core` (architecture.md:135).

Entités principales : `AuditLog`. `registry.audit_model()` branche l'audit automatique (CREATE/UPDATE/DELETE avant/après) sur un modèle.

Règles :
- Immuabilité stricte : aucun `update()`/`delete()` autorisé sur ce modèle.
- Conservation ≥ 5 ans.
- Consultation : ADMIN (complet), DIRECTION (lecture seule).
