# customers

Rôle : fiche client et historique commercial — cahier-des-charges.md:119-124.
TVA 18 % par défaut ; 0 % exige un motif d'exonération (contrainte en base).

Entités : `Client`, `Interaction`.

Services (`services.py`) : `creer_client`, `modifier_client` (TVA 0 % = motif obligatoire,
motif effacé si la TVA redevient positive, NCC / NIF unique même parmi les clients
supprimés, chargé clientèle = compte actif de ce rôle), `enregistrer_interaction` (résumé
obligatoire, date non future), `rechercher_clients`.

Interface (`views.py`, `templates/customers/`, montée sous `/clients/`) : portefeuille
filtrable (texte, « Mon portefeuille », exonérés de TVA) avec dernière interaction et
nombre de réclamations ; fiche avec historique commercial ; création et modification ;
ajout d'interactions. Accès : ADMIN et CHARGE_CLIENTELE gèrent, DIRECTION lit seulement.
Les missions du client s'affichent dans sa fiche via `customers.sections.DETAIL_CLIENT`
(fournisseur enregistré par `missions`).

Pas encore de gestion des devis ni des contrats à renouveler (indicateurs du tableau de
bord chargé clientèle, étape 5) ; l'accès des FINANCES aux clients se décidera avec la
facturation (étape 4).
