# Avenant — Export PDF généré par le serveur

Précise le cahier des charges : §3 Module 1, ligne 82 (« Export CSV/PDF » du journal d'audit) et §4, ligne 305
(« Export PDF et Excel »). Jusqu'ici, un PDF s'obtenait par l'impression du navigateur (« Enregistrer au format
PDF ») ; seuls les codes de mission et les autorisations de congé étaient de vrais PDF (audit M1-77, TECH-82).

## Décision de l'entreprise (12/10/2026)

**Un vrai PDF, généré par le serveur, partout** : toutes les listes et tous les rapports.

## Ce qui se télécharge en PDF

Bouton « Télécharger en PDF » sur chaque page d'impression ; mêmes filtres que la page (`?format=pdf`) :

| Famille | Rapports |
|---|---|
| Listes (16) | Personnel, congés, chauffeurs, flotte, missions, carburant, garage, stock, clients, factures, dépenses, devis, journal d'audit… (toute liste imprimable) |
| Comptabilité | Grand livre, balance, bilan, compte de résultat, déclaration TVA |
| Trésorerie | Journal de trésorerie |
| Documents | Facture, devis, rapport de frais d'une mission, tableau de bord (selon le rôle) |

## Règles de mise en page

- En-tête de l'entreprise (logo, raison sociale, adresse, NCC) et pied « Généré le … par … — Page N » sur chaque
  page ; tableau découpé sur plusieurs pages avec sa ligne de titres répétée ; paysage au-delà de 6 colonnes.
- Rapports comptables et trésorerie : le PDF est construit sur **les mêmes données que l'export Excel** (mêmes
  chiffres dans les deux formats).
- Listes : 500 lignes au plus par rapport, comme la page imprimable (le PDF le signale) ; l'export Excel va plus
  loin.
- Le bouton « Imprimer » reste disponible.

## Implémentation

`apps/core/pdf.py` (générateur ReportLab), `ImpressionListeMixin` et `TelechargementPdfMixin`
(`apps/core/views.py`), `reponse_rapport` (`apps/core/xlsx.py`). Tests : `apps/core/tests/test_pdf.py`.
