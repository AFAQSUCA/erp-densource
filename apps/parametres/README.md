# parametres

Rôle : réglages de l'application modifiables sans mise à jour du code — cahier-des-charges.md:48 (« ADMIN : config,
seuils d'alerte ») ; périmètre et droits décidés le 12/10/2026 (`avenant-parametres.md`). Écran `/parametres/`, menu
« Paramètres ». Dépend de `core`, `accounts`, `audit` ; lu par `fleet`, `drivers`, `fuel`, `missions`, `customers`,
`hr`, `dashboard`, `notifications` (architecture.md).

- **Une seule ligne** (`Parametres`, `pk = 1`, contrainte en base) : 12 valeurs — délai d'alerte avant expiration
  (30 j) ; seuils carburant (écart jaune 20 %, rouge 40 %, saisie suspecte ± 60 %, plage plausible 20-45 L/100 km) ;
  distance maximale entre deux relevés du compteur (5 000 km) ; TVA (18 %) et délai de paiement (30 j) proposés aux
  nouveaux clients ; délais de validation d'un congé (N1 48 h, N2 24 h) ; droit annuel de congé (26 jours ouvrés).
- **Valeurs par défaut = cahier des charges et avenants** : tant que l'écran n'a jamais été enregistré, la table est
  vide et `services.parametres()` renvoie ces valeurs **sans rien écrire**.
- **Lecture** : toujours `services.parametres()` (ou `services.delai_alerte(jours)`), jamais une constante. Pas de
  cache partagé : une requête sur une table d'une ligne, et pas de valeur fantôme après l'annulation d'une transaction.
- **Pas de rétroactivité** : un niveau d'alerte de plein, une date limite de validation déjà calculés restent tels
  quels. Exception : le droit annuel, recalculé à chaque lecture d'un solde (année en cours comprise).
- **Modification** (`services.modifier_parametres`) : ADMIN et DIRECTION (`permissions.MODIFICATION`, superutilisateur
  = ADMIN). Bornes de chaque champ (validateurs du modèle) puis cohérence : jaune < rouge < saisie suspecte,
  consommation minimale < maximale, TVA par défaut > 0. Tout est vérifié avant d'écrire.
- **Audit** : `audit_model(Parametres, module="PARAMETRES")` — ancienne et nouvelle valeur de chaque changement.
