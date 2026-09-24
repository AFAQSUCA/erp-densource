# dashboard

Rôle : tableau de bord d'accueil, adapté au rôle — cahier-des-charges.md:225-239. Couche
haute : `services.py` assemble les lectures des apps métier (`fleet.repartition_statuts`,
`fuel.consommation_moyenne`, `hr.absents_du_jour`, `missions.meilleurs_clients`...) et décide
qui voit quoi ; il ne calcule rien lui-même.

Blocs (selon les droits déjà définis dans chaque app) :
- **Centre d'alertes** : documents des camions à 30 jours ou expirés, permis et visites des
  chauffeurs, pièces sous le seuil, surconsommation des 30 derniers jours, validations de
  congés en retard. Seuls les groupes non vides apparaissent, avec les 5 premières lignes.
- **Exploitation** (ADMIN, DIRECTION, PARCAUTO) : camions disponibles / en mission / au garage,
  consommation moyenne globale, missions en cours, à affecter, à clôturer.
- **Ressources humaines** (ADMIN, DIRECTION, RH) : effectif par département, absents du jour,
  prochains départs en congé, demandes à valider.
- **Finances du mois** (ADMIN, DIRECTION, FINANCES) : CA HT facturé, encaissé, charges (dépenses,
  carburant, maintenance), marge nette, créances dont échues, trésorerie ; groupe d'alertes
  « factures impayées échues ».
- **Clientèle** (ADMIN, DIRECTION, CHARGE_CLIENTELE) : clients actifs (mission sur 90 jours),
  réclamations (30 jours), top 3 des clients (missions livrées ou clôturées sur 12 mois).

Graphiques (`apps/core/graphiques.py`, balises `graphique_barres` / `graphique_colonnes`, styles `viz-*` de
`frontend/input.css`) : camions et missions par statut, effectif par département, top des clients, charges du
mois, et facturé / encaissé / charges sur 6 mois. HTML et CSS seulement (aucun script, donc compatible avec la
CSP stricte). Règles suivies : palette bleu, orange, aqua validée avec `validate_palette.js` ; barres
horizontales pour comparer des catégories, colonnes groupées pour suivre 3 séries dans le temps ; valeur
écrite au bout de chaque barre ; infobulle au survol et au focus clavier ; tableau équivalent sous le
graphique des mois ; un seul axe ; pas de camembert. L'interface n'a pas de thème sombre, donc un seul jeu de
couleurs. Ajouter un graphique : préparer les données avec `graphiques.barres_horizontales` ou
`colonnes_groupees` dans le service, puis `{% graphique_barres ... %}` dans le gabarit.

Performance : 80 requêtes SQL au plus pour l'ADMIN (dont ~30 pour l'historique de 6 mois, mis en cache),
quel que soit le volume de données (testé). Les blocs
exploitation, clientèle et finances sont mis en cache `DASHBOARD_CACHE_SECONDS` (60 s par défaut, 0 en
test) via le cache Django, donc partagé entre processus dès que Redis est configuré ; le
centre d'alertes est toujours recalculé.

Reste à faire :
- Dashboard **chauffeur** (course du jour, km, conso, prochaine mission) : espace mobile, étape 6.
- Clientèle : **satisfaction** et **contrats à renouveler** (aucune donnée ne les porte encore).
