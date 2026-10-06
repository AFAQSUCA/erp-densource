## Ce que vous allez construire

**`accounting`** : la **comptabilité en partie double**, au référentiel **SYSCOHADA révisé**
(cahier-des-charges.md:340). Comme `finance`, c'est une **couche au-dessus** des autres apps : elle ne
saisit rien elle-même, elle **écoute** ce que `billing` et `finance` ont déjà validé et en tire des
**écritures toujours équilibrées**.

| Événement | Écriture générée |
|---|---|
| Facture **validée** (`billing`) | débit Client (TTC), crédit Ventes (HT) et TVA collectée |
| Règlement **encaissé** (`billing`) | débit Trésorerie (banque/caisse/mobile money selon le mode), crédit Client |
| Dépense **automatique** (plein, pièces, main-d'œuvre d'OR, frais de mission…) | débit Charge (+ TVA déductible), crédit Trésorerie |
| Mode de paiement d'une dépense **corrigé après coup** | contre-passe l'ancien compte de trésorerie, impute le nouveau |
| Mouvement manuel de trésorerie (`finance`) | débit ou crédit Trésorerie, contrepartie selon sa nature |
| Saisie manuelle (« opérations diverses ») | brouillon → lignes → **validation par la DIRECTION** |

**Le principe central : personne n'écrit d'écriture à la main dans le code.** Une seule fonction,
`services.passer_ecriture`, crée une `EcritureComptable` — elle garantit elle-même l'**équilibre**
(débit == crédit), l'**idempotence** (rejouer le même événement ne recrée rien) et que l'**exercice**
concerné n'est pas clôturé. Chaque événement a sa fonction dédiée qui prépare les lignes puis appelle
`passer_ecriture` ; si l'écriture ne peut pas s'équilibrer, **l'opération d'origine est annulée** plutôt
que de laisser un grand livre incomplet.

Une fois validée, une écriture ne se modifie ni ne se supprime : seule une **contre-passation**
(non livrée dans ce lot) la corrige. Un **exercice comptable** (année civile) s'ouvre tout seul à la
première écriture qui le concerne ; la DIRECTION peut le **clôturer**, ce qui verrouille définitivement
toute nouvelle écriture datée dans sa période.

Ce chapitre présente aussi les **rapports en lecture seule** (grand livre, balance, bilan, compte de
résultat, déclaration TVA) : uniquement des agrégations sur les écritures déjà posées, aucun nouveau
modèle. Leurs **écrans** viennent au chapitre 27, une fois le tableau de bord et les autres écrans en
place.

> Le **plan comptable de départ** est une liste de travail, à valider par un expert-comptable avant mise
> en production (aucun cabinet externe consulté à ce stade). Il est chargé par une **migration de
> données** que vous écrivez à la main dans ce chapitre (Étape 7) — la seule migration de tout ce
> tutoriel à ne pas être générée par `makemigrations` : les autres, purement schéma, sont reproductibles
> depuis les modèles et ne sont donc jamais recopiées (voir la couverture en fin de tutoriel).

**Clôture d'un exercice et bilan.** `cloturer_exercice` pose une **écriture de clôture** (`ecriture_de_cloture`, journal OD, datée du
31/12) : chaque compte de charge ou de produit est soldé et le résultat est **viré au compte 120000** (crédit si bénéfice, débit si
perte). Sans elle, le résultat de l'année N disparaissait du bilan de l'année N+1 (cumulé depuis l'origine), qui ne s'équilibrait
plus. Le compte de résultat et la balance **ignorent** cette écriture (un exercice clôturé garde son activité visible) ; le bilan
l'inclut. La commande `ecrire_clotures_historiques` reprend les exercices clôturés avant ce lot.

**Corriger sans effacer.** Une écriture validée ne se modifie jamais : `contre_passer` pose l'écriture inverse (même journal, même
pièce, datée du jour). Annuler un règlement ou un mouvement manuel contre-passe automatiquement son écriture ; la commande
`contre_passer_historique_annulations` reprend l'existant. Le grand livre est en **lecture seule** dans l'administration Django, et
un sens autre que débit/crédit est refusé par `passer_ecriture`.

## Prérequis

- Chapitres 1 à 14 terminés.

## Notions Django de ce chapitre

- **Un seul point d'entrée pour écrire** : `passer_ecriture` est la **seule** fonction qui crée une
  `EcritureComptable` ; elle vérifie l'équilibre elle-même, **jamais l'appelant** — à l'image de
  `_exiger_role`/`_exiger_statut` dans `apps.billing.services`.
- **Idempotence par `(origine, origine_id)`** : une contrainte d'unicité **et** une vérification en
  amont dans `passer_ecriture` garantissent que rejouer le même événement (ou relancer une commande de
  reprise d'historique) ne double jamais une écriture.
- **Verrouillage en Python, pas seulement par une règle métier** : `EcritureComptable.save()` et
  `.delete()`, `LigneEcriture.save()` et `.delete()` lèvent une exception dès qu'on touche à une écriture
  déjà `VALIDEE` — impossible à contourner en passant par un autre chemin que les services.
- **Rattachement générique optionnel** (`tiers_type`/`tiers_id`) : `LigneEcriture` peut pointer vers un
  client sans **aucune** dépendance au niveau du modèle envers `customers` — le découplage entre apps se
  paie ici en indirection, pas en `ForeignKey`.
- **`send()` brut, pas `send_robust`** : contrairement aux signaux que `notifications` consomme
  (chapitre 16), ceux que `accounting` consomme sont envoyés **bruts** — une écriture qui échoue à
  s'équilibrer doit annuler l'opération d'origine, jamais être silencieusement absente du grand livre.
- **`Sum` avec `filter=Q(...)`, `Coalesce`** : `_agreger_par_compte` calcule en une seule requête le
  total débit **et** crédit de chaque compte mouvementé — la base fait le travail, pas une boucle Python.
- **Commandes de reprise d'historique, volontairement pas une migration** : `comptabiliser_historique_*`
  rejoue les événements déjà enregistrés **avant** la mise en service de la comptabilisation automatique
  — à lancer une fois, à la main, jamais dans une migration (le choix d'inclure ou non l'historique avant
  un solde d'ouverture appartient à qui déploie, pas au code).
- **Migration de données (`RunPython`)** : contrairement à une migration de schéma (déduite de
  `models.py` par `makemigrations`), une migration de données est écrite à la main — ici pour peupler le
  plan comptable de départ. `apps.get_model("accounting", "Compte")` (et non un `import` direct du
  modèle) fige la version du modèle **au moment de cette migration** : le code continue de fonctionner
  même si `Compte` change de forme plus tard. `update_or_create` la rend **idempotente** (rejouable sans
  doublon), et son second argument (`retirer`) permet de la défaire avec `migrate accounting 0001`.

## Étape 1 — Créer l'application

```bash
mkdir -p apps/accounting/tests apps/accounting/management/commands
```

{{VIDES}}

## Étape 2 — Le plan comptable et le moteur d'écritures

{{FICHIER apps/accounting/models.py}}

Quatre modèles : `Compte` (plan comptable, table de référence — jamais supprimée, seulement désactivée),
`EcritureComptable` (en-tête, `BROUILLON` ou `VALIDEE`), `LigneEcriture` (ligne débit/crédit,
append-only une fois l'écriture validée) et `ExerciceComptable` (année, statut `OUVERT`/`CLOTURE`).
Repérez les `save()`/`delete()` redéfinis : c'est là que vit le verrouillage.

{{FICHIER apps/accounting/exceptions.py}}

{{FICHIER apps/accounting/constants.py}}

Numéros de comptes **mobilisés par le code** (pas de saisie utilisateur) : `COMPTE_CLIENTS`,
`COMPTE_VENTES_TRANSPORT`, la TVA collectée/déductible, et trois tables de correspondance —
catégorie de dépense, nature de mouvement manuel, mode de paiement — vers un numéro de compte. Ce
mapping est le même genre de choix qu'un `COMPTE_DU_MODE` dans `billing` : un dictionnaire, pas une
suite de `if`.

{{FICHIER apps/accounting/permissions.py}}

Cinq ensembles : `CONSULTATION` (ADMIN, DIRECTION, FINANCES, RH), `SAISIE_OD` et
`GESTION_PLAN_COMPTABLE` (même largeur), puis deux contrôles **stricts**, réservés à la seule
DIRECTION : `VALIDATION_OD` (valider une écriture manuelle) et `CLOTURE_EXERCICE` — les deux seuls
contrôles comptables *a posteriori* sur une saisie humaine, sur le même principe que `Facture.valider`
dans `billing`.

## Étape 3 — Le service central : passer une écriture équilibrée

{{FICHIER apps/accounting/services.py}}

À lire dans cet ordre :

1. **`passer_ecriture`** : le cœur. Rejoue l'idempotence (`origine`/`origine_id`), vérifie l'exercice
   ouvert, qu'il y a au moins 2 lignes, que chaque montant est strictement positif, que les comptes
   existent et sont actifs, puis que le total débit égale le total crédit — **avant** la moindre écriture
   en base.
2. **`comptabiliser_facture_validee`**, **`comptabiliser_un_reglement`**,
   **`comptabiliser_une_depense_automatique`**, **`reclasser_mode_depense`**,
   **`comptabiliser_un_mouvement_manuel`** : une fonction par événement automatique, qui construit les
   `LigneSaisie` puis appelle `passer_ecriture`. Chacune est idempotente, sauf `reclasser_mode_depense`
   (pas d'`origine`/`origine_id`, limite connue et assumée pour ce lot).
3. **Cycle de la saisie manuelle** : `creer_ecriture_manuelle` (brouillon, pas encore de numéro) →
   `ajouter_ligne_manuelle`/`supprimer_ligne_manuelle` (librement, tant que `BROUILLON`) →
   `valider_ecriture_manuelle` (rôle **strict**, vérifie l'équilibre, attribue le numéro) ou
   `abandonner_ecriture_manuelle` (soft delete du brouillon).
4. **`exercice_pour`** / **`cloturer_exercice`** : un exercice s'ouvre tout seul à la première écriture
   qui le concerne (même principe que `core.services.prochain_numero`) ; la clôture est refusée s'il
   reste des brouillons non résolus dans la période.
5. **Rapports en lecture seule** : `grand_livre_avec_solde` (lignes d'un compte + solde cumulé),
   `balance` (tous les comptes mouvementés), `declaration_tva` (TVA collectée − déductible sur une
   période), `compte_de_resultat` (produits − charges, borné à l'exercice) et `bilan` (actif/passif
   cumulés depuis l'origine). Toujours filtrés sur `statut=VALIDEE` : un brouillon d'opération diverse ne
   doit jamais fausser un rapport officiel avant l'approbation de la DIRECTION.

## Étape 4 — Les abonnements automatiques

{{FICHIER apps/accounting/receivers.py}}

`accounting` ne connaît de `billing` et `finance` que leurs **signaux** — jamais l'inverse. Comparez
avec `notifications` (chapitre 16) : même mécanisme d'abonnement par `@receiver`, mais ici les signaux
sont envoyés en `send()` **brut** (voir plus haut) : un récepteur qui échoue doit remonter l'erreur et
annuler l'opération d'origine, pas seulement la journaliser.

## Étape 5 — Reprise de l'historique

Trois commandes indépendantes, une par type d'événement, pour comptabiliser ce qui a été enregistré
**avant** la mise en service de ce lot :

{{FICHIER apps/accounting/management/commands/comptabiliser_historique_factures.py}}

{{FICHIER apps/accounting/management/commands/comptabiliser_historique_reglements.py}}

{{FICHIER apps/accounting/management/commands/comptabiliser_historique_depenses.py}}

Chacune accepte `--depuis AAAA-MM-JJ` (ignorer ce qui précède un solde d'ouverture déjà saisi, pour ne
pas compter deux fois les créances antérieures) et `--dry-run` (prévisualiser sans rien écrire). Toutes
trois sont **rejouables sans double compte** : relancer après un `--depuis` mal choisi ne recrée pas ce
qui a déjà été comptabilisé.

## Étape 6 — Administration, démarrage et tests

{{FICHIER apps/accounting/admin.py}}

{{FICHIER apps/accounting/apps.py}}

Dans `ready()`, on branche l'audit (module `COMPTABILITE`) sur les quatre modèles, et on déclare quatre
entrées de menu : « Plan comptable », « Opérations diverses », « Exercices comptables » et « Rapports
comptables » — ces écrans n'existent pas encore, l'entrée reste simplement inactive jusqu'au chapitre 27.

La migration de données du plan comptable de départ — la seule migration de tout ce tutoriel à être
montrée : les autres, purement schéma, sont reproduites par `makemigrations` (voir l'Étape 7) :

{{FICHIER apps/accounting/migrations/0002_plan_comptable_seed.py}}

Seuls `411000`, `706100`, `443300` et les 3 comptes de trésorerie sont mobilisés par ce chapitre ; le
reste est seedé maintenant pour ne pas fragmenter cette migration quand les dépenses automatiques et la
saisie manuelle (déjà couvertes par `services.py`) s'en serviront.

{{RESTANTS}}

## Étape 7 — Déclarer l'application et migrer

{{CONFIG}}

```bash
python manage.py makemigrations accounting
python manage.py migrate
```

**Résultat attendu :** `Create model Compte`, `Create model EcritureComptable`,
`Create model LigneEcriture`, `Create model ExerciceComptable`, les contraintes, puis
`Applying accounting.0001_initial... OK`.

Puis la migration de données ci-dessus — vous ne pouvez pas la générer avec `makemigrations` (elle ne se
devine pas depuis `models.py`) : créez une migration **vide**, puis complétez-la avec le contenu montré
plus haut :

```bash
python manage.py makemigrations accounting --empty --name plan_comptable_seed
python manage.py migrate
```

**Résultat attendu :** `Applying accounting.0002_plan_comptable_seed... OK`.

## Vérifier le chapitre

```bash
python manage.py check
```

{{PYTEST}}

(Les tests d'écrans de `accounting` sont présentés au chapitre 27.)

Essai dans le shell : une écriture équilibrée sur deux comptes du plan comptable déjà seedé.

```bash
python manage.py shell -c "from datetime import date; from decimal import Decimal; from apps.accounting import services as s; lignes = [s.LigneSaisie(compte='411000', sens='DEBIT', montant=Decimal('118000')), s.LigneSaisie(compte='706100', sens='CREDIT', montant=Decimal('118000'))]; e = s.passer_ecriture(journal='VTE', date_ecriture=date.today(), libelle='Essai', lignes=lignes); print(e.numero, e.lignes.count())"
```

**Résultat attendu :** `VTE-<année>-0001 2` (le numéro commence par le journal Ventes, suivi de
l'année en cours ; l'écriture a bien 2 lignes équilibrées).

## Ce qu'il faut retenir

- Un **seul point d'entrée qui écrit** (`passer_ecriture`) garantit une invariant global (l'équilibre)
  mieux qu'une règle répétée dans chaque appelant.
- **Idempotence par clé d'origine** : indispensable dès qu'un événement peut être rejoué (signal relancé,
  commande de reprise d'historique).
- Une app « qui comptabilise » **s'abonne** aux signaux des autres, elle ne les importe jamais pour agir
  à leur place : `accounting` ne modifie ni `billing` ni `finance`.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 15 : app accounting (plan comptable, écritures équilibrées, comptabilisation automatique)"
```
