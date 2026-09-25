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

Interface (`views.py`, `templates/inventory/`) :
- liste des articles (recherche, catégorie, « sous le seuil »), valeur totale du stock au
  PUMP et nombre d'articles à réapprovisionner ; fiche d'un article avec ses derniers
  mouvements ; création et modification de la fiche (la référence ne change plus) ;
  entrée d'achat (recalcule le PUMP) ; ajustement d'inventaire (toujours motivé) ;
  journal global des mouvements, filtrable.
- bloc « Pièces utilisées » de la fiche d'un OR (sorties valorisées au PUMP, coût des pièces,
  coût total) et formulaire de sortie de pièces.
- un message d'alerte s'affiche quand un ajustement ou une sortie fait atteindre le seuil
  minimal (le signal `seuil_bas_atteint` reste disponible pour les notifications).

Accès : ADMIN, DIRECTION (lecture seule) et PARCAUTO (`permissions.py`) ; seuls ADMIN et
PARCAUTO créent, modifient, enregistrent des mouvements et font sortir des pièces.
Services ajoutés : `rechercher_articles`, `categories_articles`, `valeur_totale_stock`,
`modifier_article`, `rechercher_mouvements`, `mouvements_de_l_article`.

Rapport imprimable du stock (bouton « Imprimer » sur la liste, mêmes filtres) : voir `apps/core/README.md` (`ImpressionListeMixin`).
