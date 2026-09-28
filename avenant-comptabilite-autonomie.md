# Avenant — Autonomie complète du comptable dans l'ERP

Complète `avenant-comptabilite-syscohada.md` (qui a livré le moteur de comptabilité en partie
double, 6 phases, toutes fusionnées). Cet avenant est né d'un test en conditions réelles : je me
suis connecté avec le rôle FINANCES et j'ai exécuté les tâches qu'un comptable ferait vraiment
(facturation, encaissement, dépenses, trésorerie, écritures manuelles, rapports). Deux constats :
un bug réel (les brouillons non validés faussaient déjà les rapports officiels), et plusieurs
tâches qu'un comptable ne peut aujourd'hui pas faire seul dans l'ERP.

Décision confirmée par l'entreprise : l'ERP doit devenir complet pour un usage **100% autonome**
de comptable — à l'exception du contrôle Finances/Direction (préparation/validation des écritures
manuelles), qui reste volontairement en place (séparation des tâches, pas un manque).

Chaque lot est livré, testé, documenté et fusionné séparément (même principe que les phases de
`avenant-comptabilite-syscohada.md`).

| Lot | Contenu | Statut |
|---|---|---|
| A | Rapports comptables : exclure les brouillons non validés (bug trouvé en testant) | ✅ Fusionnée (PR #25) |
| B | Export / impression des rapports comptables (grand livre, balance, bilan, compte de résultat) | ✅ Ce lot (PR #26) |
| C | Comptabilisation automatique des dépenses manuelles (péages, entretien, frais admin, autre) | **✅ Ce lot** — voir ci-dessous |
| D | TVA déductible réelle sur les dépenses | À livrer |
| E | Déclaration TVA (synthèse collectée / déductible) | À livrer |
| F | Écran de gestion du plan comptable | À livrer |
| G | Rapprochement bancaire | À livrer |

## Lot A — Rapports comptables : exclure les brouillons non validés

Trouvé en testant : `grand_livre`, `balance`, `compte_de_resultat` et `bilan`
(`apps/accounting/services.py`) ne filtraient jamais sur `statut=VALIDEE`. Un brouillon
d'opération diverse — créé mais pas encore approuvé par la DIRECTION — apparaissait déjà dans les
états financiers officiels. Démontré en direct : créer un brouillon a immédiatement changé le
résultat net affiché.

**Correctif** : les 4 fonctions filtrent désormais sur `ecriture__statut=VALIDEE`. 4 tests ajoutés
(un par rapport), suite complète verte. Détails : PR #25.

## Lot B — Export / impression des rapports comptables

Aucun des 4 rapports (grand livre, balance, bilan, compte de résultat) n'avait de version
imprimable, alors que tout le reste de l'ERP en a une (factures, journal d'audit, tableau de
bord, trésorerie) — un comptable ne pouvait pas sortir un bilan pour une banque ou un commissaire
aux comptes.

**Implémentation** : même mécanisme que partout ailleurs dans l'ERP (`apps/core/rapports.py`,
impression navigateur via CSS, pas de génération PDF côté serveur) — 4 nouvelles vues
(`GrandLivreImprimerView`, `BalanceImprimerView`, `BilanImprimerView`,
`CompteDeResultatImprimerView`, `apps/accounting/views.py`), 4 routes `.../imprimer/`, 4 gabarits
`accounting/*_print.html` réutilisant `rapports/_style_impression.html` +
`_entete_impression.html` + `_pied_impression.html`, bouton « Imprimer » ajouté sur les 4 écrans
existants (même style que `finance.tresorerie`).

**Vérifié manuellement** (navigateur, `demo_finances`) : les 4 versions imprimables affichent
exactement les mêmes chiffres que les écrans en ligne, avec l'en-tête entreprise et le pied
« Généré le / par ».

**Implémentation** : `apps.accounting.views.GrandLivreImprimerView` /
`BalanceImprimerView` / `BilanImprimerView` / `CompteDeResultatImprimerView`,
`apps/accounting/templates/accounting/grand_livre_print.html` /
`balance_print.html` / `bilan_print.html` / `compte_resultat_print.html`.

## Lot C — Comptabilisation automatique des dépenses manuelles

Trouvé en testant : une dépense saisie à la main (péages, entretien, frais administratifs, autre
— `billing.services.enregistrer_depense`) apparaissait bien en trésorerie mais ne générait
**aucune écriture comptable**. Seules les 4 catégories automatiques (carburant, pièces,
main-d'œuvre des OR, frais de mission) étaient comptabilisées depuis la Phase 3
(`avenant-comptabilite-syscohada.md` § P4, « limite de périmètre »). Concrètement : la
comptabilité prenait du retard sur la trésorerie sans que rien ne l'alerte.

**Mapping retenu** (`apps/accounting/constants.py::CATEGORIE_DEPENSE_VERS_COMPTE`), à valider par
un expert-comptable comme le reste du plan comptable de départ :
- Péages → 628100 (Frais de mission et déplacements — même nature que les frais de route)
- Entretien → 624100 (Entretien, réparations — même compte que la main-d'œuvre des OR)
- Frais administratifs et Autre → 658000 (Charges diverses de gestion courante)

**Implémentation** : `apps.billing.services.enregistrer_depense` émet désormais
`billing.signals.depense_a_comptabiliser` après création de la `Depense` (même signal que les
dépenses automatiques, `@transaction.atomic` : une dépense dont l'écriture ne s'équilibre pas est
annulée plutôt que de laisser une sortie d'argent non comptée). Côté `accounting`, aucun nouveau
code : `services.comptabiliser_une_depense_automatique` était déjà générique par catégorie, elle
gère maintenant les 8 catégories au lieu de 4. `comptabiliser_historique_depenses` reprend
désormais toutes les dépenses (plus seulement celles avec une `origine` automatique).

**Vérifié manuellement** (navigateur, `demo_finances`) : rattrapage des dépenses manuelles
existantes dans la base de dev via la commande (`4 dépense(s) comptabilisée(s)`), balance
correctement mouvementée sur 624100/628100/658000 ; une nouvelle dépense « Péages » saisie en
direct génère immédiatement son écriture (journal Caisse, visible dans le grand livre du compte
628100) sans action supplémentaire.

**Implémentation** : `apps.accounting.constants.CATEGORIE_DEPENSE_VERS_COMPTE`,
`apps.billing.services.enregistrer_depense`,
`apps.accounting.management.commands.comptabiliser_historique_depenses`.
