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

Interface (`views.py`, `templates/hr/`, montée sous `/rh/`) :
- **Congés** (`/rh/conges/`) : ouverts à tout compte de bureau rattaché à une fiche
  (`Personnel.utilisateur`) ; le chauffeur passera par l'espace mobile (étape 6). Trois
  vues : « Mes demandes », « À valider » (N1 pour le supérieur hiérarchique, N2 pour la
  RH) et « Tous les congés » (ADMIN, DIRECTION, RH). Le droit de décider vient de la
  hiérarchie, pas du rôle : `services.actions_disponibles` le tranche et l'écran n'affiche
  que ces boutons. Un refus ou une annulation exige un motif.
- **Personnel** (`/rh/personnel/`) : ADMIN, DIRECTION (lecture) et RH ; recrutement et
  modification par ADMIN et RH. Le matricule (`PERS-AAAA-XXXX`, `services.recruter`) est
  attribué automatiquement au recrutement, jamais saisi ; comme la date d'embauche, il ne se
  modifie plus ensuite. Le compte utilisateur et le supérieur se règlent ici (sans compte
  rattaché, l'employé ne peut ni demander ni valider de congé). Jours exceptionnels : RH seulement.
- Alerte N1 « chauffeur avec mission sur la période » : fournie par `missions`
  (`hr.sections.DETAIL_CONGE`), sur les missions planifiées, affectées ou en cours qui ont
  une date de départ prévue.

Pas encore d'écran : licenciement (sortie du personnel), jours fériés (à saisir dans
l'admin, notamment les fêtes musulmanes), notifications (étape 5).

Événements (`signals.py`) : `conge_soumis`, `conge_valide_n1`, `conge_decide` (approuvé, refusé
ou annulé) sont émis par les services ; `notifications` s'y abonne. Lectures du tableau de bord :
`effectif_par_departement`, `absents_du_jour`, `prochains_conges`, `conges_en_attente`,
`conges_en_retard`. `synchroniser_statuts_conges` est lancée chaque jour par
`manage.py taches_quotidiennes`.
