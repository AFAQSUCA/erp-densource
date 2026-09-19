# inventory

Rôle : magasin de pièces détachées — cahier-des-charges.md:177-183.

Entités :
- `Article` : référence, désignation, catégorie, emplacement, quantité, seuil
  minimal (0 = non surveillé), PUMP. `quantite` et `pump` ne bougent que par les
  mouvements.
- `MouvementStock` : journal immuable (append-only) des entrées (achat), sorties
  (liées à un OR ouvert) et ajustements (motif obligatoire). Une erreur se corrige
  par un ajustement.

Services (`services.py`) : `creer_article`, `enregistrer_entree` (recalcule le
PUMP pondéré), `sortir_pour_or` (valorisée au PUMP du moment), `ajuster_stock`,
`articles_sous_seuil`, `cout_pieces`, `cout_total` (main-d'œuvre + pièces d'un OR).

Signal `signals.seuil_bas_atteint` : émis quand un mouvement fait passer un article
au seuil minimal ou en dessous ; `notifications` (étape 5) s'y abonnera.

Dépend de `garage` (la sortie est liée à un OR), jamais l'inverse.

Interface : pour l'instant, le bloc « Pièces utilisées » de la fiche d'un OR (sorties
valorisées au PUMP, coût des pièces, coût total avec la main-d'œuvre) et le formulaire de
sortie de pièces (`SortieOrView`). Accès : ADMIN, DIRECTION (lecture) et PARCAUTO ; seuls
ADMIN et PARCAUTO font sortir des pièces. Les écrans de gestion du stock (articles,
entrées, ajustements, alertes de seuil) restent à faire.
