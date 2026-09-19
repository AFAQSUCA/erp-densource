# hr

Rôle : fiche personnel, recrutement et workflow de congés en 3 niveaux —
cahier-des-charges.md:204-221. Audité (module `RH`).

Entités : `Personnel` (avec `superieur` hiérarchique), `Conge`, `ValidationConge`,
`AttributionConge` (jours exceptionnels), `JourFerie`.

Règles de congés :
- N1 = supérieur hiérarchique direct (`Personnel.superieur`) ; le directeur (sans
  supérieur, compte de rôle DIRECTION) valide lui-même. N2 = RH.
- Droit annuel 2 semaines = 12 jours ouvrables (`DROIT_ANNUEL_JOURS`), calculé
  par `droits_conges` (jamais stocké) : droit + exceptions RH - congés approuvés,
  en cours ou terminés de l'année de début.
- Décompte en jours ouvrables : tous les jours sauf dimanches et `JourFerie`.

Services (`services.py`) : `recruter`, `demander_conge`, `valider_n1`,
`valider_n2`, `refuser`, `annuler_conge_approuve`, `accorder_jours_exceptionnels`,
`droits_conges`, `calculer_jours`, `synchroniser_statuts_conges` (à planifier
chaque jour par Celery Beat, étape 5), `initialiser_jours_feries`.

Jours fériés : `python manage.py initialiser_jours_feries 2026` crée les fêtes
fixes et chrétiennes ; les fêtes musulmanes (fixées par décret) se saisissent
dans l'admin.

Points en attente d'autres apps :
- Alerte N1 « chauffeur avec mission sur la période » : à câbler avec `missions` (étape 3).
- Notifications et rappels d'échéance (`date_limite_n1/n2`) : `notifications` (étape 5).
