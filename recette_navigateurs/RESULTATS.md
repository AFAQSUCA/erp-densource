# Résultats de la recette navigateurs automatisée

Passage du 13/10/2026 à 19:37, `python -m pytest recette_navigateurs` (fiche `RECETTE-NAVIGATEURS.md`, audit TECH-74 à TECH-77). Fichier régénéré à chaque passage.

| Navigateur | Version |
|---|---|
| Chrome | 155.0.8059.40 |
| Edge | 155.0.4283.45 |
| Firefox | 155.0 |
| WebKit (moteur de Safari) | 26.6 |

| Scénario | Chrome | Edge | Firefox | WebKit (moteur de Safari) |
|---|---|---|---|---|
| A1 — Connexion, puis refus d'un mauvais mot de passe | réussi | réussi | réussi | réussi |
| A2 — Double authentification : QR affiché, code à 6 chiffres accepté | réussi | réussi | réussi | réussi |
| A3 — « Mot de passe oublié » : envoi et confirmation | réussi | réussi | réussi | réussi |
| A4 — La session expire après l'inactivité et ramène à la connexion | réussi | réussi | réussi | réussi |
| A5 — Déconnexion : « Précédent » ne réaffiche pas une page protégée | réussi | réussi | réussi | réussi |
| B1 — Menu latéral, logo et icônes affichés | réussi | réussi | réussi | réussi |
| B2 — Petit écran : le menu s'ouvre par « ☰ » et se ferme par Échap | réussi | réussi | réussi | réussi |
| B3 — Pagination et recherche sans accents (« kone » trouve « Koné ») | réussi | réussi | réussi | réussi |
| B4 — Cloche des notifications et « Tout marquer comme lu » | réussi | réussi | réussi | réussi |
| B5 — Tableau de bord : indicateurs et graphiques sans débordement | réussi | réussi | réussi | réussi |
| C1-C3 — Calendrier de date, montant en FCFA, erreurs affichées sans perdre la saisie | réussi | réussi | réussi | réussi |
| C5 — Confirmation avant une action : « Annuler » n'enregistre rien | réussi | réussi | réussi | réussi |
| D1 — Impression d'une facture : la page imprimée ne montre que la facture | réussi | réussi | réussi | réussi |
| D2 — « Télécharger en PDF » : page d'attente puis téléchargement automatique | réussi | réussi | réussi | réussi |
| D3 — Export Excel : le fichier .xlsx se télécharge | réussi | réussi | réussi | réussi |
| D4 — PDF des codes d'une mission et QR affichés | réussi | réussi | réussi | réussi |
| F1 — Espace chauffeur à la taille de l'écran, barre du bas sur une ligne | réussi | réussi | réussi | réussi |
| F2 — Installable : manifeste valide et service worker enregistré | réussi | réussi | réussi | réussi |
| F4 — Code de récupération saisi à la main (en minuscules) et accepté | réussi | réussi | réussi | réussi |
| F3 — Caméra ouverte depuis l'espace chauffeur ; QR lu (Chrome, Edge : caméra simulée filmant un QR) | réussi | réussi | réussi | ignoré |
| F5 — Imprévu déclaré avec une photo | réussi | réussi | réussi | réussi |
| E1 — Suivi des missions : l'écran se met à jour seul quand une mission change | réussi | réussi | réussi | réussi |
