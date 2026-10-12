# importation

Rôle : charger les données de l'entreprise (personnel, chauffeurs, copilotes, clients, camions) depuis un classeur Excel, pour
l'administrateur (`/import/`, menu « Import de données »). Dépend de `hr`, `drivers`, `customers`, `fleet` (architecture.md).

- **Modèle** (`modele.py`) : source unique des colonnes. Le modèle téléchargeable (`/import/modele.xlsx`, généré à la volée) et ce que
  l'import lit ne peuvent pas diverger ; les listes déroulantes viennent des énumérations de l'application. Une copie versionnée est à
  la racine : `modele-donnees-entreprise-DEN-Source.xlsx` (`manage.py generer_modele_import` la régénère ; un test vérifie qu'elle a les
  mêmes feuilles et en-têtes que le code).
- **Import** (`services.importer_classeur`) : chaque ligne passe par le service de son application (`hr.recruter`,
  `customers.creer_client`, `fleet.creer_vehicule`/`enregistrer_document`, `drivers.modifier_chauffeur`...) : mêmes contrôles qu'à la
  saisie, même journal d'audit. Ordre : personnel, chauffeurs, copilotes, clients, camions (un camion peut avoir pour chauffeur habituel un
  chauffeur créé par le même fichier).
- **Tout ou rien** : à la moindre ligne en erreur rien n'est enregistré ; chaque erreur est listée avec sa feuille et son numéro de ligne.
  **Simulation** : vérifie le fichier de bout en bout puis annule tout.
- **Rien n'est écrasé** : une personne (même nom et prénom, sans tenir compte de la casse ni des accents), un client (même NCC/NIF) ou un
  camion (même immatriculation) déjà présent est laissé tel quel et compté « déjà présent » : réimporter le même fichier ne crée aucun
  doublon. Seules les fiches chauffeur et copilote existantes sont complétées. Une ligne d'exemple restée telle quelle est ignorée.
- **Fiche supprimée** (décision du 12/10/2026, audit AV-15) : une ligne qui correspond à un employé, un client ou un camion
  supprimé de l'ERP est une erreur de ligne (« restaurez la fiche ou retirez la ligne ») : ni recréée, ni comptée « déjà
  présente ». Même règle pour l'import RH.
- **Fichiers piégés** (audits AV-13, AV-14, AV-16) : « NaN », « Infinity » ou nombre trop grand pour la base = erreur de
  ligne ; la dimension annoncée par le fichier est ignorée (aucune ligne perdue) ; une archive de plus de 50 Mo
  décompressés ou 500 éléments est refusée avant ouverture.
- **Statuts** : seuls ceux qui se posent à la main sont acceptés (chauffeurs et copilotes : Disponible, Suspendu, Inactif ; camions :
  Disponible, Immobilisé, Hors service). « En mission », « En congé » et « En maintenance » sont posés par les missions, les congés et le
  garage. La date de délivrance d'un document de camion est facultative : à défaut, un an avant l'expiration.
- Droits : ADMIN seulement (`permissions.IMPORT_DONNEES`). Fichier .xlsx de 5 Mo au plus, 2 000 lignes par feuille.

L'import du personnel seul de l'écran RH (`/rh/personnel/importer/`) reste disponible.
