# audit

Rôle : journal d'audit append-only (`audit_log`), 14 champs —
cahier-des-charges.md:56-82. Capture LOGIN/LOGOUT/CREATE/UPDATE/DELETE/
VALIDATE via middleware + signals `post_save` (ADR-003, architecture.md:488-493).
Dépend de `core` (architecture.md:135).

Entités principales : `AuditLog`. `registry.audit_model()` branche l'audit automatique (CREATE/UPDATE/DELETE avant/après) sur un modèle. Un champ fichier (`FileField`/`ImageField`, ex. `missions.FraisMission.justificatif` (R4), `finance.DemandeDepense.piece_jointe`/`finance.OrdreDecaissement.justificatif` (R2)) est normalisé en son chemin (chaîne vide sans fichier) avant l'écriture JSON : la valeur brute (`FieldFile`) n'est pas sérialisable telle quelle. `audit_model(..., masquer=("champ",))` ne journalise qu'une empreinte du champ (`masqué:ab12cd34`) : le changement reste visible sans écrire la valeur. Les comptes (`accounts.User`, module `UTILISATEURS`) sont audités ainsi : création, rôle, activation, droits d'administration, mot de passe (empreinte seulement) ; `last_login` est exclu (il change à chaque connexion).

Règles :
- Immuabilité stricte, en profondeur : `save()` / `delete()` du modèle refusent, le manager
  (`apps.core.immuable.AppendOnlyQuerySet`) refuse `update()` / `delete()` / `bulk_update()` en masse, et sur
  PostgreSQL un trigger `BEFORE UPDATE OR DELETE` (migration `0002`) refuse aussi le SQL direct — seul le
  détachement de l'utilisateur (`utilisateur_id` → NULL, `on_delete=SET_NULL`) est toléré. Même protection sur
  le journal des mouvements de stock (`inventory.0002`).
- Validations : `audit_model(..., validation=("statut", ("EMISE",)))` fait sortir un changement de statut vers
  l'une de ces valeurs en action `VALIDATE` (factures, devis, demandes de dépense, congés, frais de mission,
  écritures manuelles) ; `auto_validation=("cree_par", ("validee_par",))` ajoute `auto_validation: true` quand
  la même personne a saisi et validé (permis, mais jamais passé sous silence). Les suppressions physiques
  (`post_delete`) sont journalisées.
- Conservation ≥ 5 ans : aucune purge applicative n'existe. La purge éventuelle se fait hors application, par
  l'administrateur de la base, qui doit désactiver explicitement le trigger le temps de l'opération
  (`ALTER TABLE audit_log DISABLE TRIGGER append_only`) puis le réactiver. Les sauvegardes
  (`ops/sauvegarde.sh`, rotation `SAUVEGARDE_CONSERVER_JOURS`, 30 jours par défaut) ne servent pas d'archive :
  pour garder ≥ 5 ans, régler la rotation en conséquence ou archiver les fichiers chiffrés à part.
- Consultation : ADMIN (complet), DIRECTION (lecture seule). En pratique les deux ont le même accès en
  lecture (`permissions.CONSULTATION`) : il n'y a de toute façon aucune écriture possible depuis l'écran.

Écran (`/audit/`, menu « Journal d'audit ») : liste filtrable (texte sur utilisateur/entité/IP, module,
action, statut, période), `services.rechercher()`. Export PDF/CSV pour les audits externes
(cahier-des-charges.md:82) : bouton « Imprimer » (rapport HTML, voir `apps/core/rapports.py`) et bouton
« Exporter en CSV » (`JournalExporterCsvView`, mêmes filtres, `;` en séparateur pour Excel ; en plus des colonnes de
l'écran : anciennes et nouvelles valeurs en JSON et user-agent).
