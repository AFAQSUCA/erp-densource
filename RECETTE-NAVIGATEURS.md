# Recette navigateurs — Chrome, Edge, Safari, Firefox

Le cahier des charges demande que l'ERP fonctionne sur **Chrome, Edge, Safari et Firefox, dans leurs deux dernières
versions** (`cahier-des-charges.md:300`, audit TECH-74 à TECH-77). Les tests automatiques vérifient le code, mais
pas le rendu dans chaque navigateur : cette recette se fait **à la main**, une fois avant la mise en service, puis
après chaque changement important de l'interface.

Comptez environ **45 minutes par navigateur**. Une seule personne peut tout faire, avec un ordinateur (Chrome, Edge,
Firefox ; Safari sur un Mac) et un téléphone (Chrome sur Android, Safari sur iPhone) pour l'espace chauffeur.

## Avant de commencer

- Faire la recette sur le **serveur de recette ou de production**, en HTTPS (`GUIDE-DEPLOIEMENT.md`), pas sur
  `localhost` : la caméra et l'installation de l'espace chauffeur exigent HTTPS.
- Utiliser les comptes de démonstration (`COMPTES-ESSAI.md`), jamais de vraies données.
- Noter la **version exacte** de chaque navigateur : menu « Aide » ou « À propos ». Les deux dernières versions
  au moment de la recette doivent être couvertes ; une version plus ancienne n'est pas exigée.
- Pour chaque ligne : **OK**, ou **KO** avec une capture d'écran et une phrase (« le menu ne s'ouvre pas »).

## Fiche de résultats

Recopiez ce tableau (un exemplaire par passage) et remplissez une colonne par navigateur.

| Navigateur | Version | Système | Date | Testeur |
|---|---|---|---|---|
| Chrome | | | | |
| Edge | | | | |
| Safari | | | | |
| Firefox | | | | |

## A. Connexion et sécurité

| # | Vérification | Chrome | Edge | Safari | Firefox |
|---|---|---|---|---|---|
| A1 | Se connecter avec `demo_rh` ; la page d'accueil s'affiche, sans message d'erreur | | | | |
| A2 | Se connecter avec un compte DIRECTION : le QR code de double authentification s'affiche et se scanne ; le code à 6 chiffres est accepté | | | | |
| A3 | « Mot de passe oublié » : le formulaire s'envoie et affiche sa confirmation | | | | |
| A4 | Rester inactif 30 minutes : la session expire et ramène à la connexion | | | | |
| A5 | Se déconnecter : retour à la page de connexion ; le bouton « Précédent » ne réaffiche pas de page protégée | | | | |

## B. Mise en page et navigation

| # | Vérification | Chrome | Edge | Safari | Firefox |
|---|---|---|---|---|---|
| B1 | Menu latéral : chaque rubrique s'ouvre ; icônes et logo visibles (aucun carré vide) | | | | |
| B2 | Fenêtre réduite à la largeur d'un téléphone : le menu devient un bouton « ☰ », s'ouvre et se ferme (touche Échap comprise) | | | | |
| B3 | Une liste longue (missions, personnel) : la pagination fonctionne ; la recherche sans accents trouve « Kone » pour « Koné » | | | | |
| B4 | Cloche des notifications : le compteur s'affiche, la liste s'ouvre, « tout marquer comme lu » fonctionne | | | | |
| B5 | Tableau de bord : les indicateurs et les graphiques s'affichent, sans zone vide ni texte qui déborde | | | | |

## C. Formulaires

| # | Vérification | Chrome | Edge | Safari | Firefox |
|---|---|---|---|---|---|
| C1 | Créer une mission : les champs de date affichent un calendrier ; la date choisie s'enregistre au bon jour | | | | |
| C2 | Saisir un montant entier (1250000) : il est accepté et réaffiché « 1 250 000 FCFA » ; un montant à décimales est refusé avec un message | | | | |
| C3 | Envoyer un formulaire incomplet : les erreurs s'affichent à côté des champs, les valeurs saisies restent | | | | |
| C4 | Téléverser un justificatif PDF ou une photo (plein de carburant) : le fichier s'enregistre et se rouvre | | | | |
| C5 | Une action à confirmer (annuler une mission) : la boîte de confirmation apparaît ; « Annuler » n'enregistre rien | | | | |

## D. Documents et exports

| # | Vérification | Chrome | Edge | Safari | Firefox |
|---|---|---|---|---|---|
| D1 | Fiche facture → « Imprimer » : l'aperçu d'impression montre la facture seule, sans menu | | | | |
| D2 | « Télécharger en PDF » d'une liste : la page « Préparation de votre PDF » apparaît puis le téléchargement démarre seul ; le PDF s'ouvre | | | | |
| D3 | Export Excel d'un rapport comptable : le fichier `.xlsx` se télécharge et s'ouvre dans Excel ou LibreOffice | | | | |
| D4 | PDF des codes d'une mission : il se télécharge et les QR codes y sont lisibles | | | | |

## E. Suivi en direct

| # | Vérification | Chrome | Edge | Safari | Firefox |
|---|---|---|---|---|---|
| E1 | Ouvrir le suivi des missions dans un onglet ; démarrer une mission depuis un autre onglet : le suivi se met à jour **sans recharger la page** | | | | |

## F. Espace chauffeur (téléphone)

À faire sur **Chrome Android** et **Safari iPhone** (colonnes Chrome et Safari), avec le compte d'un chauffeur.

| # | Vérification | Chrome (Android) | Safari (iPhone) |
|---|---|---|---|
| F1 | L'espace chauffeur s'affiche à la taille de l'écran, sans défilement horizontal ; la barre du bas reste sur une ligne | | |
| F2 | « Ajouter à l'écran d'accueil » : l'icône apparaît et l'application s'ouvre en plein écran | | |
| F3 | Scanner le QR code d'une mission : le navigateur demande l'accès à la caméra ; le code est lu et la récupération validée | | |
| F4 | Sans scanner : le code de la mission se saisit aussi à la main et est accepté | | |
| F5 | Déclarer un plein avec une photo prise par le téléphone | | |

## G. Les 7 critères de recette du cahier des charges (§ 6)

À rejouer **une fois**, dans le navigateur principal de l'entreprise, de bout en bout.

| # | Critère | Résultat |
|---|---|---|
| G1 | 20 camions et 20 chauffeurs configurés (import Excel ou saisie) | |
| G2 | Une mission créée, affectée, suivie sur téléphone et clôturée sans erreur | |
| G3 | Un plein calcule la consommation exacte et signale une surconsommation | |
| G4 | Un ordre de réparation bloque puis libère le camion | |
| G5 | Une sortie de pièce met le stock à jour et alerte au seuil bas | |
| G6 | Une facture émise crée la créance client et une écriture comptable équilibrée | |
| G7 | Les documents qui expirent bientôt s'affichent sur le tableau de bord | |

## Après la recette

- **Tout est OK** : envoyer la fiche remplie ; les lignes TECH-74 à TECH-77 de `audit/MATRICE.md` passent à ✅ avec
  la date, les versions et le nom du testeur.
- **Un KO** : transmettre la capture et la phrase ; la correction est faite, puis seule la ligne concernée est
  rejouée dans le navigateur concerné.
