# finance

Rôle : trésorerie et indicateurs financiers — cahier-des-charges.md:195-199. Interface sous
`/finances/`. Couche au-dessus de `billing`.

**Trésorerie** = ce qui a réellement bougé : règlements reçus (entrées), dépenses payées (sorties) et
`MouvementManuel` (solde d'ouverture, apport, frais bancaires, retrait...). Le compte (Banque, Caisse,
Mobile Money) se déduit du mode de paiement : Virement et Chèque → Banque, Espèces → Caisse, Wave,
Orange et MTN → Mobile Money. Solde en temps réel par compte et total ; journal filtrable.

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
- charges = dépenses saisies + carburant (litres x prix des pleins) + coût des OR clôturés
  (main-d'œuvre et pièces au PUMP). Les trois composantes restent visibles ; ne pas saisir en
  dépense ce qui vient déjà des pleins et des OR ;
- marge nette = CA HT - charges ; créances = reste à recouvrer (dont échu) ; trésorerie = solde.
  Les charges (économiques) et la trésorerie (réelle) ne sont volontairement pas les mêmes chiffres.

Pas encore fait : **rapprochement bancaire** (écarté sur décision de l'utilisateur : trésorerie
seulement), import de relevés, écritures comptables, grand livre.
