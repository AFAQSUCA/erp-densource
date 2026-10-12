# Avenant — Montants en FCFA sans centimes

Précise le cahier des charges, qui exprime tous les montants en FCFA sans dire s'ils peuvent porter des décimales.
Jusqu'ici, un prix, un règlement ou une dépense pouvait être saisi avec des centimes (« 1 179 999,50 ») : une facture
restait alors avec un reste à recouvrer de 0,50 FCFA, impossible à solder (audit AUD-05, M9-16, M9-24).

## Décision de l'entreprise (12/10/2026)

| Question | Décision |
|---|---|
| Un montant saisi avec des centimes est-il accepté ? | **Non : refusé**, avec un message clair (jamais arrondi en silence) |

Le franc CFA ne se divise pas en centimes dans la pratique.

## Règles

- Tout montant **saisi** doit être un nombre entier de FCFA : prix unitaire d'une ligne de facture, prix convenu d'un
  devis ou d'une mission, règlement, dépense et sa TVA, mouvement de trésorerie, ligne de relevé bancaire, demande de
  dépense (montants estimé, validé et réel), frais et imprévus de mission, main-d'œuvre d'un ordre de réparation, prix
  d'achat d'une pièce, prix au litre du carburant, ligne d'écriture comptable manuelle.
- Le message nomme le montant fautif et la valeur saisie, par exemple « Le prix convenu doit être un nombre entier de
  FCFA, sans centimes (850 000,75 saisi). »
- Les montants **calculés** gardent leurs règles d'arrondi propres : TVA, TTC, coût d'un plein (litres × prix),
  valeur d'un stock.
- Une quantité (litres, tonnes, nombre de pièces) peut rester décimale : seul le prix est entier.

## Double saisie (audit AUD-06)

Dans le même esprit de fiabilité des montants, un double clic ne crée plus deux règlements, deux dépenses, deux
mouvements ou deux frais :

- le navigateur n'envoie un formulaire qu'une fois (`static/js/app.js`) ;
- le serveur refuse un enregistrement **identique** créé il y a moins d'une minute. Une seconde opération réelle du
  même montant, le même jour, reste possible une minute plus tard.

## Implémentation

`apps/core/montants.py` (`exiger_montant_entier`), appelé par les services de chaque app ; `apps/core/doublons.py`
(`exiger_pas_de_doublon_recent`). Tests : `apps/core/tests/test_montants.py`, `apps/core/tests/test_doublons.py`.
