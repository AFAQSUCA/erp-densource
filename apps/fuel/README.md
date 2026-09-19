# fuel

Rôle : pleins de carburant et consommation — cahier-des-charges.md:147-157.

Entité : `Plein` (date, camion, chauffeur, station, litres, prix unitaire, km compteur,
n° de ticket unique). Les champs calculés (distance, consommation, moyenne de
référence, écart %, alertes) sont figés à la saisie par `services.enregistrer_plein`.

Règles (seuils stricts) :
- Conso (L/100 km) = litres ÷ (km actuel − km du plein précédent) × 100.
- Référence = moyenne arithmétique des consommations des 3 derniers pleins du camion
  (moins de 3 : ceux qui existent ; aucun : pas de comparaison).
- Jaune si écart > +20 %, rouge si > +40 %, alerte de saisie si |écart| > 60 %
  (indépendante : +65 % est rouge ET saisie suspecte).
- Anomalie si conso > 45 ou < 20 L/100 km.
- Saisie suspecte : `SaisieSuspecte` levée, rien enregistré, jusqu'à renvoi avec
  `confirmer_alerte_saisie=True`.
- Pleins dans l'ordre (date >= dernier, km strictement supérieur) ; le compteur du
  camion est relevé si le km est supérieur.

Analyse : `consommation_moyenne(vehicule=, chauffeur=)` (pondérée par la distance ;
sans filtre = moyenne globale de la flotte), `pleins_a_surveiller()`.

Reste à faire :
- Correction d'un plein saisi par erreur (aucun service de modification pour l'instant).
- Saisies hors ordre venant de la synchronisation hors-ligne du mobile (étape 6).
- Notification des alertes : `notifications` (étape 5).
