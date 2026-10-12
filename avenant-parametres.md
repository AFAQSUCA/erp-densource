# Avenant — Paramètres de l'application modifiables à l'écran

Complète le cahier des charges, §3 Module 1, ligne 48 : « **ADMIN** : accès total, config, seuils d'alerte… ». Ces
réglages étaient écrits dans le code ; les changer demandait un développeur et une mise à jour (audit M1-09, M1-10).

## Décision de l'entreprise (12/10/2026)

| Question | Décision |
|---|---|
| Quels réglages deviennent modifiables ? | Les seuils d'alerte, **plus** la TVA et le délai de paiement proposés aux nouveaux clients, **plus** les règles RH (délais de validation des congés, droit annuel) |
| Qui les modifie ? | L'**ADMIN** et la **DIRECTION** (lecture large de l'avenant R8 : même largeur que l'ADMIN pour la saisie) |

Les valeurs du cahier des charges et des avenants restent les **valeurs par défaut** : tant que personne n'a
enregistré l'écran, l'application se comporte exactement comme avant.

## Les 12 paramètres

| Paramètre | Défaut | Source du défaut | Bornes | Effet |
|---|---|---|---|---|
| Délai d'alerte avant expiration | 30 jours | CDC §3 M2 l.95 | 1-365 | Documents des camions, permis et visite médicale : listes, fiches, centre d'alertes, notifications quotidiennes |
| Alerte jaune : écart de consommation | 20 % | CDC §3 M6 l.153 | 1-500 | Plein enregistré après le changement |
| Alerte rouge : écart de consommation | 40 % | CDC §3 M6 l.154 | 1-500, > jaune | Idem |
| Saisie suspecte : écart de consommation | ± 60 % | CDC §3 M6 l.155 | 1-500, > rouge | Idem (la saisie doit être confirmée) |
| Consommation minimale plausible | 20 L/100 km | CDC §3 M6 l.157 | 1-200 | Anomalie d'un plein ; moyennes par camion et par chauffeur |
| Consommation maximale plausible | 45 L/100 km | CDC §3 M6 l.157 | 1-200, > minimale | Idem |
| Distance maximale entre deux relevés | 5 000 km | Audit M5-10 / M6-09 | 100-50 000 | Plein et arrivée d'une mission refusés au-delà |
| TVA proposée aux nouveaux clients | 18 % | CDC §3 M4 l.120, M9 l.185 | 0,01-100 | Client créé à l'écran ou par l'import Excel sans taux fourni |
| Délai de paiement proposé | 30 jours | Code (aucune valeur dans le CDC) | 1-365 | Idem |
| Délai de validation N1 d'un congé | 48 h | CDC §3 M11 l.213 | 1-720 | Demande faite après le changement |
| Délai de validation N2 d'un congé | 24 h | CDC §3 M11 l.214 | 1-720 | Validation N1 faite après le changement |
| Droit annuel de congé | 26 jours ouvrés | Avenant R7 | 1-60 | **Tous les soldes**, année en cours comprise, dès l'enregistrement |

## Règles

- **Pas de rétroactivité**, sauf le droit annuel : un plein déjà enregistré garde son niveau d'alerte, une demande
  de congé garde sa date limite, un client existant garde son taux. Le droit annuel, lui, est recalculé à chaque
  lecture d'un solde. **Point à surveiller** : baisser le droit en cours d'année peut rendre un solde négatif pour un
  employé qui a déjà pris ses jours ; le minimum légal ivoirien (2,2 jours ouvrables par mois) n'est pas contrôlé par
  l'application, il reste de la responsabilité de la RH et de la direction.
- **Cohérence** : jaune < rouge < saisie suspecte ; consommation minimale < maximale ; TVA par défaut > 0 (un client
  exonéré se règle sur sa fiche, à 0 % avec motif). Tout est vérifié avant d'écrire ; rien n'est enregistré en cas
  d'erreur.
- **Traçabilité** : chaque modification est au journal d'audit (module `PARAMETRES`), avec l'ancienne et la nouvelle
  valeur et son auteur ; l'écran affiche la date et l'auteur de la dernière modification.
- **Hors périmètre** (restent dans le code) : seuil de validation d'un devis par la DIRECTION (500 000 FCFA),
  tolérance de dépassement d'un ordre de décaissement (10 %), validité d'un devis (30 jours).

## Implémentation

App `apps/parametres` (`Parametres`, une seule ligne `pk = 1` garantie par une contrainte en base), écran
`/parametres/` (menu « Paramètres »). Lecture par `parametres.services.parametres()` ; dans un gabarit,
`{{ reglages.<champ> }}` (processeur de contexte paresseux). Détails : `apps/parametres/README.md`.
