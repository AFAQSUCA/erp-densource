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
| B | Export / impression des rapports comptables (grand livre, balance, bilan, compte de résultat) | ✅ Fusionnée (PR #31) |
| C | Comptabilisation automatique des dépenses manuelles (péages, entretien, frais admin, autre) | ✅ Fusionnée (PR #32) |
| D | TVA déductible réelle sur les dépenses | ✅ Fusionnée (PR #33) |
| E | Déclaration TVA (synthèse collectée / déductible) | ✅ Fusionnée (PR #34) |
| F | Écran de gestion du plan comptable | ✅ Fusionnée (PR #35) |
| G | Rapprochement bancaire | ✅ Fusionnée (PR #36) |
| H | Contre-passation (annulation d'un règlement ou d'un mouvement) | ✅ Fusionnée (PR #41) |
| I | Écriture de clôture : le résultat est viré au 120000, le bilan du 2e exercice s'équilibre | **✅ Ce lot** — voir ci-dessous |

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

## Lot D — TVA déductible réelle sur les dépenses

Jusqu'ici, une dépense n'avait qu'un montant unique traité comme une charge TTC sans TVA
récupérable — même les dépenses automatiques (carburant, pièces…) chargeaient le compte de charge
pour le montant plein. Le compte 445200 « État, TVA déductible » du plan comptable seedé n'était
jamais mouvementé.

**Décisions confirmées avec l'entreprise** :
- Toutes les catégories peuvent porter de la TVA déductible, au cas par cas (pas systématique :
  un fournisseur informel ou non assujetti ne la facture pas).
- Taux par défaut 18 % (aligné sur les ventes), mais l'utilisateur saisit le montant de TVA
  directement depuis sa pièce justificative plutôt qu'un taux — plus fidèle à ce qui est écrit sur
  un vrai reçu (HT / TVA / TTC).

**Modèle** (`billing.models.Depense`) : nouveau champ `montant_tva` (FCFA, défaut 0, facultatif).
`montant` reste le TTC payé ; `montant_ht` est une propriété calculée (`montant - montant_tva`).
Contraintes DB : `montant_tva >= 0` et `montant_tva < montant` (une TVA ne peut jamais égaler ou
dépasser le TTC). Les dépenses existantes gardent `montant_tva = 0` (aucune TVA reconstituée a
posteriori sur l'historique).

**Écriture comptable** (`accounting.services.comptabiliser_une_depense_automatique`) : quand
`montant_tva > 0`, l'écriture passe à 3 lignes — débit du compte de charge au HT, débit du compte
445200 pour la TVA déductible, crédit de la trésorerie au TTC (toujours équilibrée). Quand
`montant_tva = 0` (cas par défaut, y compris toutes les dépenses automatiques pour l'instant —
leurs apps sources ne capturent pas encore la TVA à la source), le comportement est inchangé : une
seule ligne de charge au montant plein.

**Écran** (`/facturation/depenses/nouvelle/`) : nouveau champ « dont TVA déductible (FCFA) »,
facultatif, avec l'aide « ex. 18 % : montant TTC × 18 ÷ 118 » ; affiché aussi dans la liste des
dépenses (« dont X TVA déd. » sous le montant) quand non nul.

**Limite de périmètre (pas un oubli)** : seule la saisie manuelle expose le champ TVA pour
l'instant. Les 4 catégories automatiques (carburant, pièces, main-d'œuvre des OR, frais de
mission) restent à TVA = 0 tant que leurs apps sources (`fuel`, `inventory`, `garage`, `missions`)
ne capturent pas elles-mêmes une ventilation HT/TVA — un chantier séparé, plus large (il toucherait
4 apps et leurs formulaires), pas nécessaire pour que le moteur comptable gère déjà la TVA
déductible correctement partout où elle est saisie.

**Vérifié manuellement** (navigateur, `demo_finances`) : péage à 11 800 FCFA TTC dont 1 800 FCFA de
TVA saisi en direct → écriture à 3 lignes (628100 débit 10 000, 445200 débit 1 800, 571000 crédit
11 800), balance équilibrée, compte de résultat n'inclut pas la TVA déductible dans les charges
(c'est un compte d'actif, pas une charge).

**Suite (audit global, marge nette)** : l'indicateur « Marge nette » du tableau de bord retranchait les
charges **TTC** d'un CA **HT**, donc sous-estimait la marge de la TVA récupérable et divergeait du compte de
résultat comptable. Il se calcule désormais hors taxes des deux côtés : CA HT − (charges − TVA déductible).
`finance.charges()` garde `total` en TTC (même total que la page Dépenses et la trésorerie) et expose
`tva_deductible` et `total_ht` ; la carte des charges affiche « dont X de TVA récupérable » quand il y en a.
Le graphique mensuel « Charges » reste en TTC (flux payé), comme la carte.

**Implémentation** : `billing.models.Depense.montant_tva`/`montant_ht`,
`billing.services.enregistrer_depense`, `billing.forms.DepenseForm`,
`accounting.constants.COMPTE_TVA_DEDUCTIBLE`,
`accounting.services.comptabiliser_une_depense_automatique`.

## Lot E — Déclaration TVA

Dernier maillon manquant côté TVA : une fois la TVA déductible réelle en place (Lot D), rien ne
calculait « TVA collectée − TVA déductible » pour une période — un comptable devait le faire à la
main à partir de la balance, en repérant lui-même les comptes 443300 et 445200.

**Service** (`accounting.services.declaration_tva(*, debut, fin)`) : agrège les mouvements
VALIDEE des deux comptes sur la période, renvoie `tva_collectee`, `tva_deductible` et
`tva_nette` (positive = à reverser au Trésor Public, négative = crédit de TVA reportable sur la
période suivante). Contrairement à la balance ou au grand livre, une déclaration porte toujours
sur une période bornée : le mois en cours par défaut si aucune date n'est choisie (cycle de
déclaration usuel en Côte d'Ivoire), ou le mois complet de la seule date fournie si une seule
borne est donnée.

**Écran** (`/comptabilite/declaration-tva/`, formulaire de période, accessible depuis le menu
« Rapports comptables ») + version imprimable (`.../imprimer/`, même mécanisme que les autres
rapports — Lot B).

**Vérifié manuellement** (navigateur, `demo_finances`) : sur l'année 2026 complète, TVA collectée
216 000 FCFA (identique à la ligne 443300 de la balance), TVA déductible 1 800 FCFA (identique à
la ligne 445200), TVA nette à payer 214 200 FCFA ; sur le mois en cours (aucune vente, une
dépense facturée), correctement affiché comme un crédit de TVA reportable négatif.

**Implémentation** : `accounting.services.declaration_tva`,
`accounting.views.DeclarationTvaView` / `DeclarationTvaImprimerView`,
`accounting/templates/accounting/declaration_tva.html` / `declaration_tva_print.html`.

## Lot F — Écran de gestion du plan comptable

Le plan comptable (`accounting.Compte`) n'était consultable et modifiable que depuis l'admin
Django, réservé à l'ADMIN — alors que le plan de départ est explicitement marqué « à valider par
un expert-comptable » dans le code depuis la Phase 1 : le comptable qui doit le corriger n'y avait
pas accès.

**Décisions de conception** (pas de question business ouverte, choix techniques directs, cohérents
avec le reste de l'app) :
- Même largeur de rôle que la saisie d'écritures manuelles (`GESTION_PLAN_COMPTABLE` = ADMIN,
  DIRECTION, FINANCES, RH) — ce n'est pas une transaction financière nécessitant un contrôle
  Direction a posteriori, seulement le paramétrage du référentiel.
- Le numéro et la nature d'un compte ne se modifient plus une fois créés (`services.creer_compte`
  vs `services.modifier_compte`) : changer la nature d'un compte après coup reclasserait
  silencieusement toutes ses écritures passées dans le bilan/compte de résultat.
- Un compte ne se supprime jamais (comme documenté depuis la Phase 1) : seule la désactivation
  (`actif=False`) est possible, empêchant son usage dans une nouvelle écriture
  (`passer_ecriture` refuse déjà un compte inactif) sans perdre son historique.

**Écran** (`/comptabilite/plan-comptable/`, menu « Plan comptable ») : liste triée par numéro avec
nature et statut, bouton « Nouveau compte » et lien « Modifier » par ligne pour les rôles
autorisés.

**Vérifié manuellement** (navigateur, `demo_finances`) : création d'un compte 626000 « Péages et
parkings » (Charge), immédiatement disponible dans les formulaires d'opération diverse ; puis
modification de son libellé, conservée après rechargement de la liste.

**Implémentation** : `accounting.services.creer_compte` / `modifier_compte`,
`accounting.permissions.GESTION_PLAN_COMPTABLE`, `accounting.exceptions.CompteDejaExistant`,
`accounting.views.PlanComptableListView` / `CompteCreateView` / `CompteModifierView`,
`accounting/templates/accounting/plan_comptable_list.html` / `compte_form.html` /
`compte_modifier_form.html`.

## Lot G — Rapprochement bancaire

Dernier écart trouvé en testant : rien dans l'ERP ne confrontait le relevé réel de la banque aux
mouvements de trésorerie enregistrés. Un comptable ne pouvait pas s'assurer que la banque était
d'accord avec le solde affiché ; en cas d'écart (frais bancaires prélevés directement, virement non
enregistré...), rien ne l'aurait signalé.

**Décisions confirmées avec l'entreprise** :
- Saisie manuelle ligne par ligne du relevé bancaire — pas d'import de fichier (aucun format de
  relevé n'est imposé par la banque actuelle, et l'import serait un chantier séparé si le besoin
  se confirme).
- Suggestion automatique de rapprochement (même sens et même montant que la ligne saisie, mouvement
  le plus proche en date en premier) avec pointage manuel confirmé par l'utilisateur — jamais de
  pointage automatique silencieux.
- Un écart qui persiste après pointage se corrige par l'opération diverse déjà existante
  (`apps/accounting/README.md`), pas par un nouveau mécanisme de correction.

**Modèle** (`finance.models.LigneReleve`) : une ligne du relevé saisie à la main (date, libellé,
montant, sens, référence facultative) ; `pointee`, `mouvement_origine` et `mouvement_id`
restent vides tant qu'elle n'est pas associée à un mouvement de trésorerie précis. Le
rapprochement ne concerne que le compte Banque (Virement, Chèque) — jamais la Caisse ni le Mobile
Money, cohérent avec `apps.billing.models.COMPTE_DU_MODE`.

**Service** (`finance.services`) : `saisir_ligne_releve` (mêmes droits que toute saisie
trésorerie, `billing.permissions.SAISIE`) ; `suggestions_pointage` (mouvements Banque non encore
pointés, même sens et montant, triés par proximité de date) ; `pointer_ligne_releve` /
`depointer_ligne_releve` (un mouvement ne peut être pointé que sur une seule ligne à la fois) ;
`rapprochement_bancaire(*, debut, fin)` calcule le solde du relevé, le solde des mouvements Banque
déjà enregistrés, l'écart entre les deux, et le détail de chaque côté non encore pointé.

**Écran** (`/finances/rapprochement/`, menu « Rapprochement bancaire ») : les trois totaux
(solde relevé, solde comptable, écart — en rouge si non nul), formulaire de saisie d'une ligne,
lignes non pointées avec leurs suggestions et un bouton « Associer » par suggestion, mouvements
Banque non pointés, et la liste complète des lignes de la période avec un bouton « Dépointer » en
cas d'erreur.

**Vérifié manuellement** (navigateur, `demo_finances`) : avec un règlement Cimaf de 916 000 FCFA
et un apport de 1 500 000 FCFA déjà en trésorerie, écart initial de -2 416 000 FCFA (aucune ligne
de relevé saisie) ; saisie d'une ligne « Virement Cimaf » de 916 000 FCFA → suggestion automatique
du règlement correspondant, écart ramené à -1 500 000 FCFA ; « Associer » → ligne pointée, sortie
des listes « non pointées » des deux côtés ; « Dépointer » → pointage annulé, suggestion réapparaît,
écart revient à -1 500 000 FCFA.

**Implémentation** : `finance.models.LigneReleve`, `finance.services.saisir_ligne_releve` /
`suggestions_pointage` / `pointer_ligne_releve` / `depointer_ligne_releve` /
`rapprochement_bancaire`, `finance.forms.LigneReleveForm` / `PeriodeRapprochementForm` /
`PointerLigneReleveForm`, `finance.views.RapprochementBancaireView` / `LigneReleveCreateView` /
`LigneRelevePointerView` / `LigneReleveDepointerView`,
`finance/templates/finance/rapprochement.html`.

## Lot H — Contre-passation

Trouvé par la 2e passe d'audit global (ACC-07) : annuler un règlement ou un mouvement manuel le retirait de
la trésorerie mais laissait son écriture au grand livre (comptes 411, 521, 571). Les deux vues divergeaient
sans trace ni alerte, et une écriture validée, jamais modifiable, n'avait aucun moyen d'être corrigée.

**Décisions de conception** (écriture inverse standard, pas de question business ouverte) :
- `accounting.services.contre_passer` crée une écriture aux sens inversés, dans le même journal, avec la
  même pièce, **datée du jour** : l'écriture d'origine reste intacte (append-only) et, si elle est dans un
  exercice clôturé, la correction tombe dans l'exercice ouvert.
- Idempotente (une seule contre-passation par écriture), refusée pour un brouillon (il s'abandonne) et pour
  une contre-passation (pas de chaîne).
- Câblée par des signaux **bloquants** (`billing.reglement_annule`, `finance.mouvement_annule`) : si la
  contre-passation est impossible (exercice du jour clos, compte désactivé), l'annulation est refusée avec
  son message plutôt que de laisser trésorerie et grand livre diverger.
- L'annulation défait aussi le pointage bancaire d'une ligne de relevé associée (elle redevient à pointer).
- Reprise de l'existant : `contre_passer_historique_annulations [--dry-run]` contre-passe les annulations
  faites avant ce lot (datées du jour de l'annulation) et signale celles qui tombent dans un exercice clos.

**Limites connues** : pas d'écran pour contre-passer à la main une opération diverse validée (la correction
manuelle d'une saisie reste à livrer) ; la ligne « encaissement » du suivi de trésorerie d'une mission
(`missions.FraisMission`, type ENCAISSEMENT) n'est pas retirée quand son règlement est annulé, faute de lien
entre les deux.

**Implémentation** : `accounting.services.contre_passer` / `contre_passer_origine`,
`accounting.exceptions.ContrePassationImpossible`, `accounting.receivers`, `billing.signals.reglement_annule`,
`finance.signals.mouvement_annule`, `finance.services.depointer_mouvement`,
`accounting.management.commands.contre_passer_historique_annulations`.


## Lot I — Écriture de clôture (résultat → compte 120000)

**Problème** (audit global, écart n°8) : `bilan()` cumule l'actif et le passif depuis l'origine, mais le
résultat n'était ajouté au passif qu'à l'affichage, pour l'exercice demandé seulement. Aucune écriture de
clôture ne le virait au compte 120000 : dès le 2e exercice, le bilan perdait le résultat du 1er et le total
du passif ne rejoignait plus le total de l'actif.

**Décisions de conception** (pratique comptable standard, pas de question business ouverte) :
- `cloturer_exercice` pose l'écriture de clôture (`accounting.services.ecriture_de_cloture`), journal OD,
  datée du dernier jour : chaque compte de charge ou de produit est soldé et la différence est portée au
  crédit (bénéfice) ou au débit (perte) du 120000. Aucune écriture si l'exercice n'a ni charge ni produit.
  Atomique avec la clôture : sans 120000 actif, l'exercice reste ouvert.
- Idempotente (`origine` = `CLOTURE`) ; seule écriture autorisée dans un exercice clôturé (paramètre
  `ignorer_cloture` de `passer_ecriture`) ; ne se contre-passe pas (un exercice clôturé ne se rouvre jamais).
- Lisibilité des rapports : `compte_de_resultat` et `balance` ignorent l'écriture de clôture (un exercice
  clôturé garde son activité visible ; `balance(avec_cloture=True)` pour l'inclure) ; `bilan` l'inclut, ce qui
  annule le résultat déjà viré et n'ajoute au passif que le résultat pas encore viré — il s'équilibre à tout
  moment, même si un exercice antérieur n'a pas été clôturé.
- Reprise de l'existant : `ecrire_clotures_historiques [--dry-run]` pose l'écriture des exercices clôturés
  avant ce lot (rejouable).

**Implémentation** : `accounting.services.ecriture_de_cloture`, `ORIGINE_CLOTURE`, `constants.COMPTE_RESULTAT`,
`accounting.management.commands.ecrire_clotures_historiques`, `templates/accounting/bilan*.html`.

---

Les 9 lots sont désormais livrés : l'ERP est complet pour un usage autonome de comptable, à
l'exception volontaire du contrôle Finances/Direction sur les écritures manuelles (séparation des
tâches, confirmée comme devant rester en place dès l'ouverture de cet avenant).
