# billing

Rôle : factures, TVA, règlements et dépenses — cahier-des-charges.md:181-193 ;
architecture.md:213, 224-229, 432. Interface sous `/facturation/`.

Entités : `Facture` (+ `LigneFacture`), `Reglement`, `Depense`. Audités (module `FINANCES`).

Cycle d'une facture (décision : FINANCES prépare, DIRECTION valide) :
`BROUILLON` → `A_VALIDER` → `EMISE` → `PARTIELLEMENT_PAYEE` → `PAYEE`.
- Le brouillon se crée depuis une **mission livrée ou clôturée** (une facture par mission, garantie
  en base) et reprend le prix convenu, la TVA et le délai de paiement du client. FINANCES peut
  ajouter des lignes (péages refacturés...) et ajuster la TVA et le délai tant que c'est un brouillon.
- **TVA à 3 niveaux** : système 18 %, client, facture. À 0 %, le motif d'exonération est obligatoire
  (contrainte en base). La TVA est arrondie au franc (le FCFA n'a pas de centimes).
- **Numéro `FACT-AAAA-XXXX` attribué à la validation** : un brouillon abandonné ne laisse aucun
  trou. La validation fixe aussi la date d'émission et l'échéance (émission + délai de paiement du
  client, 30 jours par défaut) et gèle les montants. Seul le rôle DIRECTION valide (un ADMIN ou un
  superutilisateur non). La DIRECTION peut renvoyer en brouillon avec un motif.
- **Règlements** (acomptes et solde) : Virement, Chèque, Espèces, Wave, Orange Money, MTN. Refusés si
  la facture n'est pas émise, si le montant dépasse le reste à recouvrer, ou si la date est future ou
  antérieure à l'émission. Un règlement erroné s'annule avec un motif (annulation logique) ; le
  reste à recouvrer et le statut se recalculent.
- **Échue** = émise, non soldée, échéance dépassée : alerte au tableau de bord et notification.
- **Dépenses** : Péages, Entretien, Frais administratifs (+ « Autre », ajout à notre initiative), plus Carburant, Pièces
  détachées et Main-d'œuvre des réparations **créées automatiquement** par `finance` (voir `apps/finance/README.md`) :
  `Depense.origine` / `origine_id` identifient la source (une dépense par plein, achat ou OR), `changer_mode_depense`
  corrige le mode de paiement.

Droits (`permissions.py`) : consultation ADMIN, DIRECTION, FINANCES ; préparation, règlements et
dépenses ADMIN et FINANCES ; validation DIRECTION seulement.

Version imprimable : `/facturation/<id>/imprimer/` (Ctrl+P puis « Enregistrer au format PDF »). Les
mentions de l'émetteur viennent des variables `ENTREPRISE_NOM`, `ENTREPRISE_ADRESSE`,
`ENTREPRISE_NCC`.

Pas encore fait :
- **Écritures comptables** (critère de recette n°6 du CDC : « écriture comptable équilibrée ») :
  écarté sur décision de l'utilisateur pour cette étape.
- **Avoir / annulation d'une facture émise** : le CDC n'en parle pas ; une facture émise ne se
  modifie ni ne se supprime.
- Génération de PDF côté serveur (Celery, étape 7) ; paiement initié par Mobile Money.
- Accès du chargé clientèle aux factures de ses clients.

Rapports imprimables des factures et des dépenses (bouton « Imprimer » sur chaque liste, mêmes filtres) : voir `apps/core/README.md` (`ImpressionListeMixin`).
