# finance

Rôle : trésorerie et indicateurs financiers — cahier-des-charges.md:195-199. Interface sous
`/finances/`. Couche au-dessus de `billing`.

**Trésorerie** = ce qui a réellement bougé : règlements reçus (entrées), dépenses payées (sorties) et
`MouvementManuel` (solde d'ouverture, apport, frais bancaires, retrait...). Le compte (Banque, Caisse,
Mobile Money) se déduit du mode de paiement : Virement et Chèque → Banque, Espèces → Caisse, Wave,
Orange et MTN → Mobile Money. Solde en temps réel par compte et total ; journal filtrable.

**Indicateurs du mois** (`services.indicateurs`, affichés au tableau de bord) :
- CA facturé = total **HT** des factures émises ; encaissé = règlements du mois ;
- charges = dépenses saisies + carburant (litres x prix des pleins) + coût des OR clôturés
  (main-d'œuvre et pièces au PUMP). Les trois composantes restent visibles ; ne pas saisir en
  dépense ce qui vient déjà des pleins et des OR ;
- marge nette = CA HT - charges ; créances = reste à recouvrer (dont échu) ; trésorerie = solde.
  Les charges (économiques) et la trésorerie (réelle) ne sont volontairement pas les mêmes chiffres.

Pas encore fait : **rapprochement bancaire** (écarté sur décision de l'utilisateur : trésorerie
seulement), import de relevés, écritures comptables, grand livre.
