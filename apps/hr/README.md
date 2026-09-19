# hr

Rôle : fiche personnel, recrutement et workflow de congés en 3 niveaux —
cahier-des-charges.md:204-221. Auditée (module `RH`).

Entités : `Personnel`, `Conge`, `ValidationConge`.

Services (`services.py`) : `recruter`, `demander_conge`, `valider_n1`,
`valider_n2`, `refuser`, `annuler_conge_approuve`, `synchroniser_statuts_conges`
(à planifier chaque jour par Celery Beat, étape 5).

Points en attente d'autres apps :
- Alerte N1 « chauffeur avec mission sur la période » : à câbler avec `missions` (étape 3).
- Notifications employé / validateurs et rappels d'échéance (`date_limite_n1/n2`) : `notifications` (étape 5).
