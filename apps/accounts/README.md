# accounts

Rôle : authentification, 7 rôles utilisateurs (ADMIN, DIRECTION, RH, CHARGE_CLIENTELE, PARCAUTO,
FINANCES, CHAUFFEUR) — cahier-des-charges.md:44-55 — et sécurité de la connexion (étape 7, lot 1).
Dépend uniquement de `core` (architecture.md:134) ; `audit` s'abonne à ses signaux, pas l'inverse.

Entités : `User` (`AUTH_USER_MODEL`), `Role`, `AppareilMFA` (application TOTP d'un compte),
`CodeSecours` (10 codes à usage unique, empreinte SHA-256 seulement).

## Connexion

- **Mots de passe en Argon2** (cahier-des-charges.md:273). PBKDF2 reste accepté : un ancien hachage est
  converti à la prochaine connexion. Longueur minimale : 10 caractères.
- **Anti force brute** (`throttle.py`, cache Django) : 5 échecs pour un même identifiant depuis une même
  adresse, ou 20 échecs depuis une adresse, bloquent la connexion 15 minutes, **même avec le bon mot de
  passe**. Le blocage compte aussi les échecs de l'API et de l'administration. Il ne dit pas si le
  compte existe. En production, le cache doit être partagé entre processus (Redis, lot 2).
- **Adresse du client** (`core.middleware.get_client_ip`) : `X-Forwarded-For` n'est lu que si
  `TRUSTED_PROXY_COUNT` (proxys de confiance) est renseigné, et seule l'adresse ajoutée par eux compte.
  Sinon un client pourrait forger son adresse et échapper à la limitation. Derrière Nginx : `1`.
- L'administration Django n'a plus son propre formulaire : `/admin/login/` renvoie vers `/connexion/`.
- **Mot de passe oublié** (`/mot-de-passe/`) : les 4 vues standard de Django (demande de l'adresse,
  confirmation d'envoi, lien reçu par e-mail, nouveau mot de passe), gabarits français assortis au
  reste du site. Ne révèle jamais si l'adresse correspond à un compte (même page dans les deux cas).
  Le nouveau mot de passe passe par les mêmes règles qu'à la création (Argon2, longueur 10,
  validateurs). Nécessite un serveur SMTP réel en production (`EMAIL_HOST` et consorts,
  `.env.example`) ; sans lui, sans autre canal, cette fonctionnalité ne peut pas envoyer de lien.
  Tracé au journal d'audit (module AUTH, entité User), sans jamais inscrire le mot de passe.

## Double authentification (MFA)

Obligatoire pour l'ADMIN et la DIRECTION (`settings.MFA_ROLES`, `MFA_ENFORCED`), cahier-des-charges.md:276.

- **Porte** (`middleware.py`) : refus par défaut. Un ADMIN ou une DIRECTION dont la session n'est pas
  « vérifiée » est renvoyé vers `/mfa/verifier/` (ou `/mfa/activer/` s'il n'a pas d'appareil) pour toute page,
  administration et documentation de l'API comprises. Les requêtes d'API reçoivent un 403 JSON.
  Seules `/mfa/`, `/connexion/`, `/deconnexion/` et `/static/` sont libres.
- **Activation** : à la première connexion, QR code à scanner (Google/Microsoft Authenticator…), premier
  code, puis 10 codes de secours affichés **une seule fois**.
- **Vérification** (`mfa.py`) : code à 6 chiffres sur 30 s (±1 intervalle), **un code ne sert qu'une fois**
  (anti-rejeu), 5 codes faux par 10 minutes puis blocage. Une nouvelle ouverture de session redemande la MFA.
- **API** : `POST /api/v1/auth/token/` exige le champ `otp` pour ces rôles (code ou code de secours) ; un
  compte sans MFA activée doit d'abord l'activer sur le site (`401` avec `code` = `mfa_non_activee`,
  `mfa_requise` ou `mfa_invalide`).
- **Téléphone perdu** : codes de secours, sinon un compte de rôle ADMIN réinitialise l'appareil depuis
  l'administration (action « Réinitialiser la double authentification »), ou en ligne de commande :
  `python manage.py reinitialiser_mfa <identifiant>`. Les codes se régénèrent depuis l'en-tête (`/mfa/codes/`).
  Toutes les étapes sont inscrites au journal d'audit (module AUTH, entité MFA), sans aucun secret.
- Tests : `MFA_ENFORCED = False` dans `settings/test.py` ; les tests de la MFA la réactivent.

Limites connues :
- Le secret TOTP est stocké tel quel en base (il doit pouvoir être relu pour recalculer les codes).
- L'activation se fait à la première connexion : un mot de passe volé **avant** l'activation permettrait
  d'enrôler l'appareil d'un tiers. Activer la MFA de chaque ADMIN et DIRECTION dès la création du compte.
- Un compte ADMIN (non superutilisateur) peut lister les utilisateurs et réinitialiser leur MFA dans
  l'administration, mais ne peut pas les modifier : ces droits restent réservés aux superutilisateurs.
