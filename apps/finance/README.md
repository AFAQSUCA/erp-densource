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
annulée. La saisie manuelle de ces trois catégories est refusée (double compte). Reprise de l'existant :
migration `billing.0003` (pleins, achats et OR déjà enregistrés, en espèces). **À vérifier avant de la déployer** :
elle rétro-débite la trésorerie ; si un « solde d'ouverture » a été saisi à une date, les dépenses antérieures sont
déjà comprises dedans.

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
