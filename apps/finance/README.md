# finance

Rôle : trésorerie et indicateurs financiers — cahier-des-charges.md:195-199. Interface sous
`/finances/`. Couche au-dessus de `billing`.

**Trésorerie** = ce qui a réellement bougé : règlements reçus (entrées), dépenses payées (sorties) et
`MouvementManuel` (solde d'ouverture, apport, frais bancaires, retrait...). Le compte (Banque, Caisse,
Mobile Money) se déduit du mode de paiement : Virement et Chèque → Banque, Espèces → Caisse, Wave,
Orange et MTN → Mobile Money. Solde en temps réel par compte et total ; journal filtrable.

**Dépenses du parc auto** (`receivers.py`) : chaque plein (`fuel.enregistrer_plein`), chaque achat de pièces
(`inventory.enregistrer_entree`) et la main-d'œuvre de chaque OR clôturé (`garage.cloturer_or`) crée une
`billing.Depense` automatique (catégorie Carburant / Pièces détachées / Main-d'œuvre des réparations, une seule par
source, contrainte `depense_une_par_origine`), donc une ligne de la page Dépenses **et** une sortie de trésorerie. Mode
de paiement par défaut : espèces (Caisse) ; la Finance le corrige sur la ligne (`billing.changer_mode_depense`), ce qui
change le compte débité. Les pièces sont comptées **à l'achat** : leur sortie vers un OR ne l'est pas (pas de double
compte), si bien qu'un OR n'ajoute que sa main-d'œuvre. Les apps d'origine émettent un signal (`plein_enregistre`,
`entree_stock_enregistree`, `or_cloture`) émis avec `send` : si la dépense ne peut pas être écrite, l'opération est
annulée. La saisie manuelle de ces trois catégories est refusée (double compte).

Reprise de l'historique (pleins, achats et OR déjà enregistrés avant la mise en service de ce mécanisme) :
`services.reprendre_depenses_parc_auto()` / commande `comptabiliser_historique_parc_auto` — **volontairement pas
une migration automatique**, pour ne jamais rétro-débiter la trésorerie sans décision explicite. Elle rejoue
`billing.comptabiliser_depense_automatique` pour chaque source manquante (idempotent, rejouable sans double
compte) et rapporte le nombre créé par catégorie. À exécuter une fois, après vérification :
```
python manage.py comptabiliser_historique_parc_auto --dry-run   # prévisualiser, rien n'est écrit
python manage.py comptabiliser_historique_parc_auto              # tout l'historique
python manage.py comptabiliser_historique_parc_auto --depuis 2026-09-01   # si un solde d'ouverture au
    # 31/08/2026 comprend déjà les mouvements antérieurs (sinon ils seraient comptés deux fois)
```

## Dépenses pré-approuvées du parc auto (`demandes.py`, R2 — avenant-separation-des-taches.md)

Séparation des tâches : le **Parc Auto** demande, la **DIRECTION** valide (jamais l'ADMIN à sa place,
contrôle strict comme pour une facture), la **FINANCES** exécute. Deux circuits sur le même modèle
`DemandeDepense` (numéro `DEM-AAAA-XXXX`) :

- **Manuelle** : le Parc Auto soumet une demande (catégorie, montant estimé, motif, fournisseur,
  pièce jointe) *avant* un achat ou une réparation non routinière. Validée, elle génère un
  `OrdreDecaissement` (`ODC-AAAA-XXXX`) que la Finance exécute (mode, montant réel, justificatif) :
  cela crée la `billing.Depense` (origine `ORDRE_DECAISSEMENT`). Refusée, elle s'arrête là (motif
  obligatoire).
- **Dépassement d'enveloppe** : la DIRECTION peut fixer une `EnveloppeDepense` — un plafond mensuel
  pour une catégorie automatique (carburant, pièces, main-d'œuvre), globalement ou pour un camion
  précis (prioritaire sur la globale). Tant que les dépenses du mois restent dans ce plafond, le
  mécanisme ci-dessus continue de fonctionner **sans rien changer** : c'est le comportement par
  défaut, sans enveloppe définie, illimité comme avant R2. Une dépense qui fait franchir le plafond
  reste comptabilisée (l'argent est déjà sorti) mais ouvre une `DemandeDepense` a posteriori ; toute
  dépense automatique *suivante* de cette catégorie est bloquée (l'opération d'origine — plein,
  achat, clôture d'OR — est annulée) tant que la DIRECTION n'a pas décidé (validée ou refusée,
  peu importe : les deux débloquent, seul le refus n'est qu'un constat de désaccord).

**Dépassement de plus de 10 %** à l'exécution d'un ordre (manuelle) : bloqué, l'ordre passe en
`EN_ATTENTE_REVALIDATION` (état qui **doit** survivre à l'erreur renvoyée à l'écran — `executer_ordre`
n'a donc pas de `@transaction.atomic` sur toute sa longueur, seulement sur le bloc qui écrit l'état,
sans quoi l'erreur annulerait la mise en attente elle-même). La DIRECTION revalide
(`revalider_ordre`, nouveau montant validé) avant que la Finance ne puisse retenter l'exécution.

Écrans : `/finances/demandes/` (liste + « Nouvelle demande » pour le Parc Auto), fiche par demande
(décision, exécution, revalidation selon le rôle et l'état), `/finances/enveloppes/` (DIRECTION).
Notifications (catégorie `DEMANDE_DEPENSE`) : soumission → DIRECTION ; décision → le demandeur (ou
le Parc Auto pour un dépassement) ; ordre à exécuter → FINANCES ; dépassement de 10 % → DIRECTION.

**Versements à confirmer** : une facture émise mais pas soldée est un versement attendu
(`services.versements_attendus`). Quand la Direction valide une facture, la FINANCES reçoit une
notification avec le bouton « Confirmer le versement » ; il mène à `/finances/versements/<id>/confirmer/`
(`services.confirmer_versement`), où la Finance saisit le montant réellement reçu, la date et le mode. Cela
enregistre un règlement (`billing.enregistrer_reglement`, mêmes contrôles) et donc une **entrée** de
trésorerie sur le compte du mode. Tant que ce n'est pas confirmé, le solde réel ne bouge pas : la
page Trésorerie affiche les versements attendus à part, avec un solde prévisionnel. Un versement
partiel laisse le reste dans la liste. Seule la FINANCES (et l'ADMIN) confirme ; la DIRECTION voit la liste.

**Historique mensuel** (`services.historique_mensuel`) : CA HT, encaissé et charges des 6 derniers mois,
pour le graphique du tableau de bord ; le mois en cours reprend les indicateurs déjà calculés.

**Indicateurs du mois** (`services.indicateurs`, affichés au tableau de bord) :
- CA facturé = total **HT** des factures émises ; encaissé = règlements du mois ;
- charges = **toutes les dépenses** (`services.charges`), y compris celles du parc auto qui se créent toutes
  seules (voir ci-dessous) ; ventilées en carburant, pièces, main-d'œuvre et autres ;
- marge nette = CA HT - charges ; créances = reste à recouvrer (dont échu) ; trésorerie = solde.
  Les charges (économiques) et la trésorerie (réelle) ne sont volontairement pas les mêmes chiffres.

Pas encore fait : **rapprochement bancaire** (écarté sur décision de l'utilisateur : trésorerie
seulement), import de relevés, écritures comptables, grand livre.

Rapport imprimable de la trésorerie (`/finances/imprimer/`, bouton « Imprimer ») : soldes par compte, synthèse et journal de la période filtrée, mêmes filtres que l'écran, plafonné à 500 lignes (voir `apps/core/README.md`).
