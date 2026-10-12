# Avenant — Validation des factures par la DIRECTION

Modifie le cahier des charges, §3 Module 1, ligne 53 : le périmètre de la **FINANCES** y cite « Validation
factures ». Le code, `architecture.md` (tableau « Facturation » : « Rôle FINANCES + validation DIRECTION ») et
l'avenant de séparation des tâches (R2 : « contrôle strict, comme pour la validation d'une facture ») appliquaient
une autre règle. L'audit (M1-37, contradiction C1) a soumis l'écart à l'entreprise.

## Décision de l'entreprise (12/10/2026)

**La règle du code est maintenue** : séparation des tâches, celui qui prépare la facture ne la valide pas.

| Étape | Qui |
|---|---|
| Préparer la facture (brouillon, lignes, soumission « À valider »), enregistrer les règlements et les dépenses | FINANCES, RH (avenant R8 § 2), DIRECTION, ADMIN |
| **Valider** la facture : numéro `FACT-AAAA-XXXX`, date d'émission, échéance, créance, écriture comptable | **DIRECTION seule** (contrôle strict : ni l'ADMIN ni un superutilisateur à sa place) |

La ligne 53 du CDC se lit donc : FINANCES — « préparation des factures » (et non « validation »).

## Implémentation

Inchangée : `apps/billing/permissions.py` (`VALIDATION = {DIRECTION}`), `billing.services.valider`
(`strict=True`). Test : `apps/billing/tests/test_services.py::test_seule_la_direction_valide_et_attribue_le_numero_et_l_echeance`.
