# Chapitre 31 — L'import Excel des données : l'app importation

> 16 fichier(s) dans ce chapitre, 1222 lignes de code.

## Ce que vous allez construire

**`importation`** : charger les données **réelles** de l'entreprise (personnel, chauffeurs, copilotes, clients,
camions) depuis **un classeur Excel**, au lieu de les saisir fiche par fiche. C'est une app de *reprise de données*,
réservée à l'**administrateur**.

| Écran | Adresse | Qui |
|---|---|---|
| **Import de données** (dépôt du fichier, rapport par feuille et par ligne, case « Simulation ») | `/import/` | **ADMIN seulement** |
| **Télécharger le modèle** (classeur Excel prêt à remplir) | `/import/modele.xlsx` | ADMIN seulement |

Le classeur contient **une feuille d'instructions et cinq feuilles de données** : Personnel, Véhicules, Chauffeurs,
Copilotes, Clients. Une copie du modèle est versionnée à la racine du dépôt
(`modele-donnees-entreprise-DEN-Source.xlsx`).

## Prérequis

- Chapitres 1 à 30 terminés (l'import s'appuie sur `hr`, `drivers`, `customers` et `fleet`, et sur l'écran
  des utilisateurs du chapitre 17).

## Ce que ce chapitre apporte de nouveau

- **Une source unique pour le modèle et pour l'import** : `modele.py` décrit les colonnes **une seule fois** ; le
  modèle téléchargeable et la lecture du fichier l'utilisent tous les deux, ils ne peuvent donc pas diverger. Les
  listes déroulantes viennent des énumérations de l'application (postes, départements, statuts…).
- **« Tout ou rien » avec des points de sauvegarde** : tout l'import s'exécute dans **une transaction** ; chaque
  ligne dans un **point de sauvegarde** (`transaction.atomic()` imbriqué), pour pouvoir noter l'erreur d'une ligne
  sans interrompre la lecture des suivantes. À la fin, s'il y a la moindre erreur — ou si la case
  « Simulation » est cochée — **tout est annulé** (`transaction.set_rollback(True)`).
- **Ne rien écraser** : une personne, un client ou un camion déjà présent est laissé tel quel ; réimporter le même
  fichier ne crée donc **aucun doublon**.
- **Réutiliser les services** plutôt que d'écrire dans les tables : chaque ligne passe par `hr.recruter`,
  `customers.creer_client`, `fleet.creer_vehicule`, `drivers.modifier_chauffeur`… — mêmes contrôles, même journal
  d'audit qu'à la saisie à l'écran.
- **Fabriquer un classeur Excel avec `openpyxl`** : en-têtes, ligne d'exemple, listes déroulantes
  (`DataValidation`).

## Étape 1 — Créer l'application

```bash
mkdir -p apps/importation/management/commands apps/importation/tests templates/importation
```

#### Fichiers vides à créer

Ces fichiers n'ont aucun contenu ; ils servent à faire de leur dossier un *paquet Python* (sans eux, `import apps.xxx` échouerait). Créez d'abord les dossiers, puis les fichiers :

```bash
mkdir -p apps\importation apps\importation\management apps\importation\management\commands apps\importation\tests
touch apps/importation/__init__.py
touch apps/importation/management/__init__.py
touch apps/importation/management/commands/__init__.py
touch apps/importation/tests/__init__.py
```

> Sous PowerShell, `mkdir -p` s'écrit `New-Item -ItemType Directory -Force <dossier>` et `touch fichier` s'écrit `New-Item -ItemType File -Force fichier`. Vous pouvez aussi créer ces fichiers avec votre éditeur.

## Étape 2 — Le modèle Excel

#### `apps/importation/modele.py`

*186 lignes* — Le classeur Excel de collecte des données de l'entreprise : source unique du modèle.

```python
"""Le classeur Excel de collecte des données de l'entreprise : source unique du modèle.

Le même module décrit le modèle téléchargeable (``construire_modele``) et les colonnes que l'import lit
(``services.importer_classeur``) : les deux ne peuvent donc pas diverger. Les listes déroulantes viennent des
énumérations de l'application (postes, départements, statuts...).

Feuilles : Personnel, Véhicules, Chauffeurs, Copilotes, Clients. La feuille « Instructions » n'est pas lue.
"""

from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

from apps.customers.models import MotifExoneration
from apps.fleet.models import StatutVehicule, TypeDocument
from apps.hr.models import POSTES_COURANTS, Departement
from apps.hr.services import COLONNES_IMPORT as COLONNES_PERSONNEL

# Clés des feuilles (ordre de traitement de l'import : un chauffeur doit exister avant de devenir le « chauffeur
# habituel » d'un camion, et une fiche du personnel avant d'être complétée en chauffeur ou copilote).
PERSONNEL, CHAUFFEURS, COPILOTES, CLIENTS, VEHICULES = "personnel", "chauffeurs", "copilotes", "clients", "vehicules"
ORDRE = (PERSONNEL, CHAUFFEURS, COPILOTES, CLIENTS, VEHICULES)

TITRES = {
    PERSONNEL: "Personnel (Employés)",
    VEHICULES: "Véhicules (Camions)",
    CHAUFFEURS: "Chauffeurs",
    COPILOTES: "Copilotes",
    CLIENTS: "Clients",
}
# Mot par lequel commence le nom de l'onglet : « Personnel », « Personnel (Employés) »... sont acceptés.
MOT_CLE = {PERSONNEL: "personnel", VEHICULES: "vehicules", CHAUFFEURS: "chauffeurs", COPILOTES: "copilotes", CLIENTS: "clients"}

# Statuts qui se posent à la main : « En mission » et « En congé » (chauffeurs, copilotes) et « En mission » /
# « En maintenance » (camions) sont posés par les missions, les congés et le garage — jamais depuis un fichier.
STATUTS_PERSONNE = ["Disponible", "Suspendu", "Inactif"]
STATUTS_VEHICULE = [StatutVehicule.DISPONIBLE.label, StatutVehicule.IMMOBILISE.label, StatutVehicule.HORS_SERVICE.label]
CATEGORIES_PERMIS = ["C", "E", "C,E"]
DEPARTEMENTS = [str(libelle) for _, libelle in Departement.choices]
MOTIFS_EXONERATION = [""] + [str(libelle) for _, libelle in MotifExoneration.choices]

DOCUMENTS = [
    (TypeDocument.CARTE_GRISE, "Carte grise"),
    (TypeDocument.ASSURANCE, "Assurance"),
    (TypeDocument.VISITE_TECHNIQUE, "Visite technique"),
    (TypeDocument.PATENTE, "Patente"),
]

COLONNES = {
    PERSONNEL: list(COLONNES_PERSONNEL),
    VEHICULES: [
        "Immatriculation", "Marque", "Modèle", "Année", "N° de châssis (VIN)", "Kilométrage actuel",
        "Capacité de charge (t)", "Réservoir (L)", "Statut", "Chauffeur habituel (Nom Prénom, facultatif)",
    ]
    + [
        libelle
        for _, nom in DOCUMENTS
        for libelle in (f"{nom} — délivrée le (facultatif)", f"{nom} — expire le")
    ],
    CHAUFFEURS: [
        "Nom (comme sur Personnel)", "Prénom (comme sur Personnel)", "Téléphone", "Contact d'urgence", "N° de permis",
        "Catégories de permis", "Expiration du permis", "Expiration visite médicale", "Statut",
    ],
    COPILOTES: ["Nom (comme sur Personnel)", "Prénom (comme sur Personnel)", "Téléphone", "Contact d'urgence", "Statut"],
    CLIENTS: [
        "Raison sociale", "NCC / NIF", "Contact principal", "Téléphone", "Email", "Adresse / siège", "Taux de TVA (%)",
        "Motif d'exonération (si TVA = 0)", "Délai de paiement (jours)",
    ],
}

# Ligne d'exemple (fond jaune) de chaque feuille. L'import l'ignore si elle est restée telle quelle : un exemple
# oublié ne doit jamais devenir une vraie fiche.
EXEMPLES = {
    PERSONNEL: ["Traoré", "Awa", "Comptable", "Ressources Humaines et Finances", "CDI", "01/09/2026", 250000],
    VEHICULES: [
        "CI-1234-AB", "Mercedes-Benz", "Actros", 2019, "WDB9634031L123456", 185000, 25.0, 400, "Disponible",
        "Kouassi Jean", "15/03/2025", "15/03/2027", "01/01/2026", "01/01/2027", "20/06/2026", "20/06/2027",
        "01/01/2026", "31/12/2026",
    ],
    CHAUFFEURS: [
        "Kouassi", "Jean", "+225 07 00 00 00 00", "Kouassi Marie (épouse) +225 05 00 00 00 00", "CI-PL-045678", "C,E",
        "12/11/2028", "03/05/2027", "Disponible",
    ],
    COPILOTES: ["Bamba", "Issouf", "+225 01 00 00 00 00", "Bamba Aïcha (sœur) +225 05 11 11 11 11", "Disponible"],
    CLIENTS: [
        "Cimaf Côte d'Ivoire", "CI-NCC-0123456A", "M. Koné Salif", "+225 27 00 00 00 00", "contact@cimaf.ci",
        "Zone Industrielle, Abidjan", 18.00, "", 30,
    ],
}

INSTRUCTIONS = [
    "DEN Source Group — Classeur de collecte des données de l'entreprise",
    "",
    "Objectif : renseigner vos vraies données (personnel, véhicules, chauffeurs, copilotes, clients) pour les charger "
    "dans l'ERP (menu « Import de données », réservé à l'administrateur). Chaque type de donnée a sa feuille.",
    "",
    "Règles à respecter :",
    "1. Ne modifiez pas la ligne d'en-tête (ligne 1, en gris foncé) de chaque feuille : le libellé et l'ordre des "
    "colonnes doivent rester identiques, sinon l'import refuse la feuille.",
    "2. La ligne d'exemple (fond jaune clair) illustre le format : remplacez-la par vos données ou supprimez-la. Si elle "
    "reste telle quelle, l'import l'ignore.",
    "3. Dates : JJ/MM/AAAA (ex. 05/09/2026), ou une vraie date Excel.",
    "4. Colonnes à liste déroulante : choisissez une valeur dans la liste plutôt que de taper un texte libre.",
    "5. Feuilles « Chauffeurs » et « Copilotes » : indiquez Nom et Prénom EXACTEMENT comme sur la feuille « Personnel » "
    "(ou comme une fiche déjà dans l'ERP), et le poste de la personne doit être « Chauffeur » ou « Copilote ». Le "
    "matricule est généré automatiquement.",
    "6. Statuts : seuls « Disponible », « Suspendu » et « Inactif » (chauffeurs, copilotes) et « Disponible », "
    "« Immobilisé » et « Hors service » (camions) se posent depuis un fichier ; « En mission », « En congé » et « En "
    "maintenance » sont posés par les missions, les congés et le garage.",
    "7. Feuille « Véhicules » : « Chauffeur habituel » est facultatif (Nom Prénom comme sur la fiche du chauffeur). Pour "
    "chaque document, indiquez la date d'expiration ; la date de délivrance est facultative — si elle manque, l'ERP "
    "retient un an avant l'expiration.",
    "8. Laissez une cellule vide quand l'information n'existe pas (n'écrivez pas « N/A »).",
    "9. Rien n'est écrasé : une personne (même Nom et Prénom), un client (même NCC/NIF) ou un camion (même "
    "immatriculation) déjà dans l'ERP est signalé « déjà présent » et laissé tel quel. Les fiches chauffeur et copilote "
    "existantes, elles, sont mises à jour.",
    "10. Tout ou rien : à la moindre ligne en erreur, rien n'est enregistré et chaque erreur est listée avec sa feuille "
    "et son numéro de ligne. La case « Simulation » permet de vérifier le fichier sans rien enregistrer.",
    "11. Le plan comptable (SYSCOHADA) est déjà configuré dans l'ERP : inutile de le renseigner ici.",
]

ENTETE_FILL = PatternFill("solid", fgColor="1F2937")
ENTETE_FONT = Font(color="FFFFFF", bold=True)
EXEMPLE_FILL = PatternFill("solid", fgColor="FEF3C7")
EXEMPLE_FONT = Font(italic=True, color="92400E")
BORDURE = Border(*(Side(style="thin", color="D1D5DB"),) * 4)


def _liste(valeurs: list[str]) -> DataValidation:
    formule = '"' + ",".join(str(v) for v in valeurs) + '"'
    assert len(formule) <= 255, "liste déroulante trop longue pour Excel"
    validation = DataValidation(type="list", formula1=formule, allow_blank=True, showDropDown=False)
    validation.error, validation.errorTitle = "Choisissez une valeur dans la liste.", "Valeur invalide"
    return validation


def _feuille(wb: Workbook, cle: str, largeurs: list[int], listes: dict[str, list[str]]) -> None:
    ws = wb.create_sheet(TITRES[cle])
    for i, texte in enumerate(COLONNES[cle], start=1):
        c = ws.cell(row=1, column=i, value=texte)
        c.fill, c.font, c.border = ENTETE_FILL, ENTETE_FONT, BORDURE
        c.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[c.column_letter].width = largeurs[i - 1]
    ws.row_dimensions[1].height = 32
    ws.freeze_panes = "A2"
    for i, valeur in enumerate(EXEMPLES[cle], start=1):
        c = ws.cell(row=2, column=i, value=valeur)
        c.fill, c.font, c.border = EXEMPLE_FILL, EXEMPLE_FONT, BORDURE
    ws.cell(row=2, column=len(EXEMPLES[cle]) + 2, value="← exemple, à remplacer ou supprimer").font = Font(
        italic=True, color="9CA3AF", size=9
    )
    for lettre, valeurs in listes.items():
        validation = _liste(valeurs)
        ws.add_data_validation(validation)
        validation.add(f"{lettre}2:{lettre}500")


def construire_modele() -> bytes:
    """Le classeur modèle (octets .xlsx) : instructions, puis une feuille par type de donnée."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Instructions"
    ws["A1"] = INSTRUCTIONS[0]
    ws["A1"].font = Font(bold=True, size=14, color="1F2937")
    for i, texte in enumerate(INSTRUCTIONS[1:], start=2):
        c = ws.cell(row=i, column=1, value=texte)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if texte.startswith("Règles"):
            c.font = Font(bold=True, size=11, color="1F2937")
        ws.row_dimensions[i].height = 30
    ws.column_dimensions["A"].width = 110

    _feuille(wb, PERSONNEL, [18, 16, 22, 30, 16, 16, 16], {"C": list(POSTES_COURANTS), "D": DEPARTEMENTS})
    _feuille(
        wb, VEHICULES, [16, 16, 14, 8, 20, 16, 16, 12, 14, 30] + [18] * 8, {"I": STATUTS_VEHICULE}
    )
    _feuille(wb, CHAUFFEURS, [22, 22, 20, 32, 18, 16, 18, 20, 14], {"F": CATEGORIES_PERMIS, "I": STATUTS_PERSONNE})
    _feuille(wb, COPILOTES, [22, 22, 20, 32, 14], {"E": STATUTS_PERSONNE})
    _feuille(wb, CLIENTS, [26, 18, 20, 20, 24, 30, 14, 24, 16], {"H": MOTIFS_EXONERATION})
    tampon = BytesIO()
    wb.save(tampon)
    return tampon.getvalue()
```

Trois idées à retenir : `COLONNES` (l'ordre et les intitulés exacts de chaque feuille), `EXEMPLES` (la ligne jaune de
chaque feuille — l'import l'**ignore** si elle est restée telle quelle : un exemple oublié ne devient jamais une
vraie fiche) et `construire_modele()` (le classeur en mémoire).

#### `apps/importation/management/commands/generer_modele_import.py`

*19 lignes* — Écrit le classeur modèle sur disque (copie versionnée à la racine du projet : modele-donnees-entreprise-DEN-Source.xlsx).

```python
"""Écrit le classeur modèle sur disque (copie versionnée à la racine du projet : modele-donnees-entreprise-DEN-Source.xlsx)."""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.importation import modele


class Command(BaseCommand):
    help = "Génère le classeur Excel modèle de collecte des données (défaut : racine du projet)."

    def add_arguments(self, parser):
        parser.add_argument("--sortie", default=str(Path(settings.BASE_DIR) / "modele-donnees-entreprise-DEN-Source.xlsx"))

    def handle(self, *args, sortie, **options):
        Path(sortie).write_bytes(modele.construire_modele())
        self.stdout.write(f"Modèle écrit : {sortie}")
```

Cette commande écrit le classeur sur disque ; la copie versionnée à la racine du dépôt est produite ainsi.

## Étape 3 — Les droits et l'import

#### `apps/importation/permissions.py`

*5 lignes* — Qui peut importer les données de l'entreprise depuis Excel : l'administrateur (un superutilisateur agit en ADMIN).

```python
"""Qui peut importer les données de l'entreprise depuis Excel : l'administrateur (un superutilisateur agit en ADMIN)."""

from apps.accounts.models import Role

IMPORT_DONNEES = frozenset({Role.ADMIN})
```

#### `apps/importation/services.py`

*414 lignes* — Import des données de l'entreprise depuis le classeur Excel (``modele.py``) — réservé à l'administrateur.

```python
"""Import des données de l'entreprise depuis le classeur Excel (``modele.py``) — réservé à l'administrateur.

Une seule opération pour les cinq feuilles : personnel, chauffeurs, copilotes, clients, puis camions (dans cet ordre
— un camion peut avoir un chauffeur habituel créé par le même fichier). Chaque ligne passe par le service de son
application (``hr.recruter``, ``customers.creer_client``, ``fleet.creer_vehicule``, ``drivers.modifier_chauffeur``...) :
mêmes contrôles qu'à la saisie, même journal d'audit. Principes :

* **tout ou rien** : à la moindre ligne en erreur, rien n'est enregistré, et chaque erreur est listée avec sa feuille
  et son numéro de ligne ;
* **rien n'est écrasé** : une personne (même nom et prénom), un client (même NCC/NIF) ou un camion (même
  immatriculation) déjà présent est signalé et laissé tel quel — réimporter le même fichier ne crée aucun doublon ;
  seules les fiches chauffeur et copilote existantes sont complétées ;
* **simulation** : le fichier est vérifié de bout en bout puis tout est annulé ;
* une ligne d'exemple restée telle quelle est ignorée.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import openpyxl
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.core.exceptions import ErreurMetier
from apps.core.search import normaliser
from apps.customers import services as clients_services
from apps.customers.exceptions import ClientError
from apps.customers.models import Client, MotifExoneration
from apps.drivers import services as drivers_services
from apps.drivers.exceptions import ChauffeurError
from apps.drivers.models import Chauffeur, Copilote, StatutChauffeur
from apps.fleet import services as fleet_services
from apps.fleet.exceptions import FlotteError
from apps.fleet.models import StatutVehicule, Vehicule
from apps.hr import services as hr_services
from apps.hr.exceptions import PersonnelError
from apps.hr.models import POSTES_COURANTS, Departement, Personnel

from . import modele, permissions

LIGNES_MAX = 2000  # par feuille : au-delà, le fichier n'est pas un classeur de collecte


class ImportInvalide(ErreurMetier):
    """Le fichier lui-même est inutilisable (illisible, aucune feuille reconnue) ou l'acteur n'a pas le droit."""


class _Ligne(Exception):
    """Une ligne qui ne peut pas être importée : le message est affiché tel quel avec son numéro."""


@dataclass
class ResultatFeuille:
    cle: str
    titre: str
    crees: int = 0
    mis_a_jour: int = 0
    deja_presents: int = 0
    exemples_ignores: int = 0
    erreurs: list[str] = field(default_factory=list)
    presente: bool = True


@dataclass
class Rapport:
    feuilles: list[ResultatFeuille]
    simulation: bool
    enregistre: bool

    @property
    def erreurs(self) -> list[str]:
        return [e for f in self.feuilles for e in f.erreurs]

    @property
    def total_crees(self) -> int:
        return sum(f.crees for f in self.feuilles)

    @property
    def total_mis_a_jour(self) -> int:
        return sum(f.mis_a_jour for f in self.feuilles)


# --- lecture des cellules ---


def _texte(valeur) -> str:
    if valeur is None:
        return ""
    if isinstance(valeur, datetime):
        return valeur.strftime("%d/%m/%Y")
    if isinstance(valeur, date):
        return valeur.strftime("%d/%m/%Y")
    if isinstance(valeur, float) and valeur.is_integer():
        return str(int(valeur))
    return str(valeur).strip()


def _date(valeur, libelle: str, *, obligatoire: bool = False) -> date | None:
    if valeur in (None, ""):
        if obligatoire:
            raise _Ligne(f"{libelle} est obligatoire.")
        return None
    resultat = hr_services.date_importee(valeur)
    if resultat is None:
        raise _Ligne(f"{libelle} « {valeur} » invalide (attendu JJ/MM/AAAA).")
    return resultat


def _entier(valeur, libelle: str) -> int:
    try:
        nombre = Decimal(_texte(valeur).replace(" ", "").replace(",", "."))
    except InvalidOperation:
        raise _Ligne(f"{libelle} « {valeur} » invalide (nombre entier attendu).") from None
    if nombre != nombre.to_integral_value() or nombre < 0:
        raise _Ligne(f"{libelle} « {valeur} » invalide (nombre entier positif attendu).")
    return int(nombre)


def _decimal(valeur, libelle: str) -> Decimal:
    try:
        return Decimal(_texte(valeur).replace(" ", "").replace(",", "."))
    except InvalidOperation:
        raise _Ligne(f"{libelle} « {valeur} » invalide (nombre attendu).") from None


def _obligatoire(valeur, libelle: str) -> str:
    texte = _texte(valeur)
    if not texte:
        raise _Ligne(f"{libelle} est obligatoire.")
    return texte


def _choix(valeur, correspondances: dict[str, str], libelle: str, *, defaut: str) -> str:
    """Valeur d'une liste fermée (insensible à la casse et aux accents) ; vide = ``defaut``."""
    texte = _texte(valeur)
    if not texte:
        return defaut
    trouve = correspondances.get(normaliser(texte))
    if trouve is None:
        raise _Ligne(f"{libelle} « {texte} » inconnu. Valeurs acceptées : {', '.join(sorted(set(correspondances.values())))}.")
    return trouve


def _cle_nom(nom: str, prenom: str) -> tuple[str, str]:
    return " ".join(normaliser(nom).split()), " ".join(normaliser(prenom).split())


def _index_personnel() -> dict[tuple[str, str], list[Personnel]]:
    index: dict[tuple[str, str], list[Personnel]] = {}
    for personne in Personnel.objects.all():
        index.setdefault(_cle_nom(personne.nom, personne.prenom), []).append(personne)
    return index


def _personne(index, nom: str, prenom: str) -> Personnel:
    trouvees = index.get(_cle_nom(nom, prenom), [])
    if not trouvees:
        raise _Ligne(f"{nom} {prenom} ne figure ni sur la feuille Personnel ni dans l'ERP (même orthographe attendue).")
    if len(trouvees) > 1:
        raise _Ligne(f"{nom} {prenom} : plusieurs fiches du personnel portent ce nom, impossible de choisir.")
    return trouvees[0]


# --- une feuille = une fonction ---


def _personnel(ligne: list, ctx: dict) -> str:
    nom, prenom, poste_brut, dept_brut, contrat, date_brut, salaire_brut = ligne[:7]
    nom, prenom = _obligatoire(nom, "Le nom"), _obligatoire(prenom, "Le prénom")
    if ctx["index"].get(_cle_nom(nom, prenom)):
        return "present"
    poste = hr_services.poste_importe(poste_brut)
    if poste is None:
        raise _Ligne(f"poste « {poste_brut} » inconnu. Postes acceptés : {', '.join(POSTES_COURANTS)}.")
    departement = hr_services.departement_importe(dept_brut)
    if departement is None:
        raise _Ligne(
            f"département « {dept_brut} » inconnu. Acceptés : {', '.join(str(l) for _, l in Departement.choices)}."
        )
    date_embauche = _date(date_brut, "La date d'embauche", obligatoire=True)
    salaire = _decimal(salaire_brut, "Le salaire de base")
    if salaire < 0:
        raise _Ligne(f"le salaire de base « {salaire_brut} » ne peut pas être négatif.")
    personne = hr_services.recruter(
        nom=nom, prenom=prenom, poste=poste, departement=departement, type_contrat=_texte(contrat),
        date_embauche=date_embauche, salaire_base=salaire,
    )
    ctx["index"].setdefault(_cle_nom(nom, prenom), []).append(personne)
    return "cree"


def _categories(valeur) -> list[str]:
    return [c for c in re.split(r"[,\s;/]+", _texte(valeur).upper()) if c]


def _statut_personne(valeur) -> str:
    correspondances = {normaliser(libelle): code for libelle, code in (
        ("Disponible", StatutChauffeur.DISPONIBLE), ("Suspendu", StatutChauffeur.SUSPENDU), ("Inactif", StatutChauffeur.INACTIF),
    )}
    return _choix(valeur, correspondances, "Le statut", defaut=StatutChauffeur.DISPONIBLE)


def _chauffeur(ligne: list, ctx: dict) -> str:
    nom, prenom, telephone, urgence, permis, categories, exp_permis, exp_visite, statut_brut = ligne[:9]
    personne = _personne(ctx["index"], _obligatoire(nom, "Le nom"), _obligatoire(prenom, "Le prénom"))
    fiche = Chauffeur.objects.filter(personnel=personne).first()
    if fiche is None:
        raise _Ligne(f"{personne} n'a pas de fiche chauffeur : son poste doit être « Chauffeur » (feuille Personnel).")
    statut = _statut_personne(statut_brut)
    drivers_services.modifier_chauffeur(
        fiche, telephone=_texte(telephone), contact_urgence=_texte(urgence), numero_permis=_texte(permis),
        categories_permis=_categories(categories),
        date_expiration_permis=_date(exp_permis, "L'expiration du permis"),
        date_expiration_visite_medicale=_date(exp_visite, "L'expiration de la visite médicale"),
    )
    if statut != fiche.statut:
        drivers_services.changer_statut_manuel(fiche, statut)
    return "maj"


def _copilote(ligne: list, ctx: dict) -> str:
    nom, prenom, telephone, urgence, statut_brut = ligne[:5]
    personne = _personne(ctx["index"], _obligatoire(nom, "Le nom"), _obligatoire(prenom, "Le prénom"))
    fiche = Copilote.objects.filter(personnel=personne).first()
    if fiche is None:
        raise _Ligne(f"{personne} n'a pas de fiche copilote : son poste doit être « Copilote » (feuille Personnel).")
    fiche.telephone, fiche.contact_urgence = _texte(telephone), _texte(urgence)
    fiche.save(update_fields=["telephone", "contact_urgence", "updated_at"])
    statut = _statut_personne(statut_brut)
    if statut != fiche.statut:
        drivers_services.changer_statut_copilote(fiche, statut)
    return "maj"


def _client(ligne: list, ctx: dict) -> str:
    raison, ncc, contact, telephone, email, adresse, taux_brut, motif_brut, delai_brut = ligne[:9]
    raison, ncc = _obligatoire(raison, "La raison sociale"), _obligatoire(ncc, "Le NCC / NIF")
    if Client.all_objects.filter(ncc_nif=ncc).exists():
        return "present"
    motifs = {normaliser(str(libelle)): code for code, libelle in MotifExoneration.choices}
    motifs.update({normaliser(code): code for code, _ in MotifExoneration.choices})
    taux = _decimal(taux_brut, "Le taux de TVA") if _texte(taux_brut) else None
    kwargs = dict(
        raison_sociale=raison, ncc_nif=ncc, contact_principal=_obligatoire(contact, "Le contact principal"),
        telephone=_obligatoire(telephone, "Le téléphone"), email=_texte(email), adresse=_obligatoire(adresse, "L'adresse"),
        motif_exoneration=_choix(motif_brut, motifs, "Le motif d'exonération", defaut=""),
    )
    if taux is not None:
        kwargs["taux_tva"] = taux
    if _texte(delai_brut):
        kwargs["delai_paiement_jours"] = _entier(delai_brut, "Le délai de paiement")
    clients_services.creer_client(**kwargs)
    return "cree"


def _vehicule(ligne: list, ctx: dict) -> str:
    immat, marque, mod, annee, vin, km, capacite, reservoir, statut_brut, habituel = ligne[:10]
    immat = _obligatoire(immat, "L'immatriculation")
    immat_normalisee = re.sub(r"\s+", "", immat).upper()
    if Vehicule.all_objects.filter(immatriculation__iexact=immat).exists() or Vehicule.all_objects.filter(
        immatriculation=immat_normalisee
    ).exists():
        return "present"
    statuts = {
        normaliser(str(StatutVehicule(code).label)): code
        for code in (StatutVehicule.DISPONIBLE, StatutVehicule.IMMOBILISE, StatutVehicule.HORS_SERVICE)
    }
    statut = _choix(statut_brut, statuts, "Le statut", defaut=StatutVehicule.DISPONIBLE)
    chauffeur = None
    if _texte(habituel):
        chauffeur = _chauffeur_habituel(_texte(habituel), ctx["index"])
    documents = []
    for rang, (type_document, nom_doc) in enumerate(modele.DOCUMENTS):
        delivree, expire = ligne[10 + 2 * rang], ligne[11 + 2 * rang]
        if expire in (None, "") and delivree in (None, ""):
            continue
        expiration = _date(expire, f"{nom_doc} : la date d'expiration", obligatoire=True)
        delivrance = _date(delivree, f"{nom_doc} : la date de délivrance")
        documents.append((type_document, delivrance or _un_an_avant(expiration), expiration))
    vehicule = fleet_services.creer_vehicule(
        immatriculation=immat, marque=_obligatoire(marque, "La marque"), modele=_obligatoire(mod, "Le modèle"),
        annee=_entier(annee, "L'année"), vin=_obligatoire(vin, "Le n° de châssis (VIN)"),
        kilometrage=_entier(km, "Le kilométrage") if _texte(km) else 0,
        capacite_charge_t=_decimal(capacite, "La capacité de charge"), reservoir_l=_entier(reservoir, "Le réservoir"),
        chauffeur_habituel=chauffeur,
    )
    if statut != vehicule.statut:
        fleet_services.definir_statut(vehicule, statut)
    for type_document, delivrance, expiration in documents:
        fleet_services.enregistrer_document(
            vehicule, type_document=type_document, date_delivrance=delivrance, date_expiration=expiration
        )
    return "cree"


def _un_an_avant(expiration: date) -> date:
    try:
        return expiration.replace(year=expiration.year - 1)
    except ValueError:  # 29 février
        return expiration - timedelta(days=365)


def _chauffeur_habituel(texte: str, index) -> Chauffeur:
    cible = " ".join(normaliser(texte).split())
    trouves = [
        fiche
        for fiche in Chauffeur.objects.select_related("personnel")
        if " ".join(normaliser(f"{fiche.personnel.nom} {fiche.personnel.prenom}").split()) == cible
    ]
    if not trouves:
        raise _Ligne(f"chauffeur habituel « {texte} » introuvable (Nom Prénom comme sur la fiche du chauffeur).")
    if len(trouves) > 1:
        raise _Ligne(f"chauffeur habituel « {texte} » : plusieurs chauffeurs portent ce nom.")
    return trouves[0]


TRAITEMENTS = {
    modele.PERSONNEL: _personnel,
    modele.CHAUFFEURS: _chauffeur,
    modele.COPILOTES: _copilote,
    modele.CLIENTS: _client,
    modele.VEHICULES: _vehicule,
}

ERREURS_METIER = (
    ErreurMetier, PersonnelError, ClientError, ChauffeurError, FlotteError, ValidationError, IntegrityError, ValueError,
)


def _feuilles_du_classeur(classeur) -> dict[str, object]:
    trouvees = {}
    for feuille in classeur.worksheets:
        nom = normaliser(feuille.title)
        for cle, mot in modele.MOT_CLE.items():
            if nom.startswith(mot) and cle not in trouvees:
                trouvees[cle] = feuille
    return trouvees


def _entetes_conformes(feuille, cle: str) -> bool:
    attendues = [normaliser(c) for c in modele.COLONNES[cle]]
    lues = next(feuille.iter_rows(min_row=1, max_row=1, values_only=True), ())
    lues = [normaliser(_texte(c)) for c in lues[: len(attendues)]]
    return lues == attendues


def _est_exemple(ligne: list, cle: str) -> bool:
    exemple = [_texte(v) for v in modele.EXEMPLES[cle]]
    return [_texte(v) for v in ligne[: len(exemple)]] == exemple


def importer_classeur(fichier, acteur, *, simulation: bool = False) -> Rapport:
    """Importe les feuilles reconnues du classeur. Tout ou rien ; ``simulation`` vérifie sans rien enregistrer."""
    if acteur.role_effectif not in permissions.IMPORT_DONNEES:
        raise ImportInvalide("Seul l'administrateur peut importer des données.")
    try:
        classeur = openpyxl.load_workbook(fichier, data_only=True, read_only=True)
    except Exception as erreur:  # fichier corrompu, mauvais format, archive illisible...
        raise ImportInvalide("Ce fichier n'est pas un classeur Excel (.xlsx) lisible.") from erreur
    feuilles = _feuilles_du_classeur(classeur)
    if not feuilles:
        raise ImportInvalide(
            "Aucune feuille reconnue : le classeur doit contenir au moins une feuille « Personnel », « Véhicules », "
            "« Chauffeurs », « Copilotes » ou « Clients » (téléchargez le modèle)."
        )

    resultats = [ResultatFeuille(cle=cle, titre=modele.TITRES[cle], presente=cle in feuilles) for cle in modele.ORDRE]
    with transaction.atomic():
        ctx = {"index": _index_personnel()}
        for resultat in resultats:
            if not resultat.presente:
                continue
            feuille = feuilles[resultat.cle]
            if not _entetes_conformes(feuille, resultat.cle):
                resultat.erreurs.append(
                    f"{resultat.titre} : en-têtes inattendus. Gardez la ligne 1 du modèle telle quelle "
                    f"(colonnes : {', '.join(modele.COLONNES[resultat.cle])})."
                )
                continue
            largeur = len(modele.COLONNES[resultat.cle])
            for numero, brut in enumerate(feuille.iter_rows(min_row=2, values_only=True), start=2):
                if numero - 1 > LIGNES_MAX:
                    resultat.erreurs.append(f"{resultat.titre} : plus de {LIGNES_MAX} lignes, import refusé.")
                    break
                ligne = (list(brut) + [None] * largeur)[:largeur]
                if all(c in (None, "") for c in ligne):
                    continue
                if _est_exemple(ligne, resultat.cle):
                    resultat.exemples_ignores += 1
                    continue
                try:
                    with transaction.atomic():
                        issue = TRAITEMENTS[resultat.cle](ligne, ctx)
                except _Ligne as erreur:
                    resultat.erreurs.append(f"{resultat.titre}, ligne {numero} : {erreur}")
                except ERREURS_METIER as erreur:
                    resultat.erreurs.append(f"{resultat.titre}, ligne {numero} : {erreur}")
                else:
                    if issue == "cree":
                        resultat.crees += 1
                    elif issue == "maj":
                        resultat.mis_a_jour += 1
                    else:
                        resultat.deja_presents += 1
        erreurs = any(r.erreurs for r in resultats)
        enregistre = not erreurs and not simulation
        if not enregistre:
            transaction.set_rollback(True)
    classeur.close()
    return Rapport(feuilles=resultats, simulation=simulation, enregistre=enregistre)
```

Lisez `importer_classeur` de haut en bas :

1. Seul l'**ADMIN** peut importer (un superutilisateur agit en ADMIN).
2. Le fichier est ouvert ; les feuilles sont reconnues par le **début de leur nom** (« Personnel », « Personnel
   (Employés) »… sont acceptés), et leurs **en-têtes** doivent être ceux du modèle.
3. L'ordre de traitement est **personnel → chauffeurs → copilotes → clients → camions** : un chauffeur doit exister
   avant d'être le « chauffeur habituel » d'un camion.
4. Chaque ligne est lue par la fonction de sa feuille (`_personnel`, `_chauffeur`, `_client`, `_vehicule`…) qui
   renvoie `"cree"`, `"maj"` ou `"present"`, ou lève `_Ligne` avec un message **destiné à l'utilisateur** (feuille et
   numéro de ligne ajoutés par l'appelant).
5. Les statuts acceptés sont **ceux qui se posent à la main** : « En mission », « En congé » et « En maintenance »
   sont posés par les missions, les congés et le garage, jamais depuis un fichier.

## Étape 4 — L'écran

#### `apps/importation/forms.py`

*22 lignes*

```python
from django import forms

from apps.core.forms import StyleTailwindMixin

TAILLE_MAX = 5 * 1024 * 1024  # 5 Mo : un classeur de collecte pèse quelques dizaines de ko


class ImportForm(StyleTailwindMixin, forms.Form):
    fichier = forms.FileField(label="Classeur Excel rempli (.xlsx)")
    simulation = forms.BooleanField(
        label="Simulation : vérifier le fichier sans rien enregistrer",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-slate-300"}),
    )

    def clean_fichier(self):
        fichier = self.cleaned_data["fichier"]
        if not fichier.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Le fichier doit être un classeur Excel (.xlsx).")
        if fichier.size > TAILLE_MAX:
            raise forms.ValidationError("Le fichier dépasse 5 Mo : ce n'est pas un classeur de collecte.")
        return fichier
```

#### `apps/importation/views.py`

*40 lignes*

```python
from django.http import HttpResponse
from django.views import View
from django.views.generic import FormView

from apps.accounts.mixins import RoleRequiredMixin

from . import modele, permissions, services
from .forms import ImportForm


class ImportView(RoleRequiredMixin, FormView):
    """Dépose le classeur rempli ; le rapport (créés, déjà présents, erreurs par ligne) s'affiche sur la même page."""

    roles = permissions.IMPORT_DONNEES
    template_name = "importation/importer.html"
    form_class = ImportForm

    def form_valid(self, form):
        try:
            rapport = services.importer_classeur(
                form.cleaned_data["fichier"], self.request.user, simulation=form.cleaned_data["simulation"]
            )
        except services.ImportInvalide as erreur:
            form.add_error("fichier", str(erreur))
            return self.form_invalid(form)
        return self.render_to_response(self.get_context_data(form=ImportForm(), rapport=rapport))


class ModeleView(RoleRequiredMixin, View):
    """Télécharge le classeur modèle (généré à la volée : toujours aligné sur ce que l'import lit)."""

    roles = permissions.IMPORT_DONNEES

    def get(self, request):
        reponse = HttpResponse(
            modele.construire_modele(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        reponse["Content-Disposition"] = 'attachment; filename="modele-donnees-entreprise-DEN-Source.xlsx"'
        return reponse
```

#### `apps/importation/urls.py`

*10 lignes*

```python
from django.urls import path

from . import views

app_name = "importation"

urlpatterns = [
    path("", views.ImportView.as_view(), name="importer"),
    path("modele.xlsx", views.ModeleView.as_view(), name="modele"),
]
```

#### `apps/importation/apps.py`

*16 lignes*

```python
from django.apps import AppConfig


class ImportationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.importation"
    label = "importation"

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer

        from . import permissions

        enregistrer(
            EntreeMenu("Import de données", "importation:importer", "fa-file-import", permissions.IMPORT_DONNEES, ordre=88)
        )
```

`ready()` ajoute l'entrée « Import de données » au menu (ADMIN seulement) : le système de menu du chapitre 3
n'importe aucune app métier, ce sont les apps qui s'y inscrivent.

#### `config/settings/base.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/settings/base.py (avant)
+++ config/settings/base.py (après)
@@ -66,4 +66,5 @@
     "apps.finance",
     "apps.accounting",
+    "apps.importation",
     "apps.notifications",
     "apps.dashboard",
```

#### `config/urls.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/urls.py (avant)
+++ config/urls.py (après)
@@ -32,4 +32,5 @@
     path("comptabilite/", include("apps.accounting.urls")),
     path("audit/", include("apps.audit.urls")),
+    path("import/", include("apps.importation.urls")),
     path("notifications/", include("apps.notifications.urls")),
     path("api/v1/", include("apps.api.urls")),
```

#### `templates/importation/importer.html`

*90 lignes*

```django
{% extends "base.html" %}
{% block titre %}Import de données{% endblock %}
{% block entete %}Administration{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-4xl">
  <h1 class="text-2xl font-bold text-slate-900">Import de données</h1>
  <p class="mt-1 text-sm text-slate-600">
    Charge en une fois le personnel, les chauffeurs, les copilotes, les clients et les camions de l'entreprise depuis un
    classeur Excel. Chaque ligne passe par les mêmes contrôles qu'une saisie à l'écran et reste tracée au journal d'audit.
  </p>

  {% if rapport %}
    <section class="mt-6 rounded-xl border {% if rapport.erreurs %}border-red-300 bg-red-50{% elif rapport.enregistre %}border-emerald-300 bg-emerald-50{% else %}border-amber-300 bg-amber-50{% endif %} p-5" aria-labelledby="titre-rapport">
      <h2 id="titre-rapport" class="text-base font-semibold {% if rapport.erreurs %}text-red-900{% elif rapport.enregistre %}text-emerald-900{% else %}text-amber-900{% endif %}">
        {% if rapport.erreurs %}
          Rien n'a été importé : corrigez les lignes ci-dessous, puis déposez le fichier à nouveau.
        {% elif rapport.enregistre %}
          Import terminé : {{ rapport.total_crees }} fiche{{ rapport.total_crees|pluralize }} créée{{ rapport.total_crees|pluralize }}{% if rapport.total_mis_a_jour %}, {{ rapport.total_mis_a_jour }} mise{{ rapport.total_mis_a_jour|pluralize }} à jour{% endif %}.
        {% else %}
          Simulation réussie : le fichier est correct, rien n'a été enregistré. Décochez « Simulation » pour l'importer.
        {% endif %}
      </h2>

      <div class="mt-4 overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table class="min-w-full divide-y divide-slate-200 text-sm">
          <caption class="sr-only">Résultat de l'import par feuille</caption>
          <thead class="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
            <tr>
              <th scope="col" class="px-4 py-2">Feuille</th>
              <th scope="col" class="px-4 py-2 text-right">{% if rapport.enregistre %}Créés{% else %}À créer{% endif %}</th>
              <th scope="col" class="px-4 py-2 text-right">Mis à jour</th>
              <th scope="col" class="px-4 py-2 text-right">Déjà présents</th>
              <th scope="col" class="px-4 py-2 text-right">Exemples ignorés</th>
              <th scope="col" class="px-4 py-2 text-right">Erreurs</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            {% for f in rapport.feuilles %}
              <tr>
                <th scope="row" class="px-4 py-2 text-left font-medium text-slate-900">{{ f.titre }}{% if not f.presente %} <span class="font-normal text-slate-600">(absente du fichier)</span>{% endif %}</th>
                <td class="px-4 py-2 text-right">{{ f.crees }}</td>
                <td class="px-4 py-2 text-right">{{ f.mis_a_jour }}</td>
                <td class="px-4 py-2 text-right">{{ f.deja_presents }}</td>
                <td class="px-4 py-2 text-right">{{ f.exemples_ignores }}</td>
                <td class="px-4 py-2 text-right {% if f.erreurs %}font-semibold text-red-800{% endif %}">{{ f.erreurs|length }}</td>
              </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>

      {% if rapport.erreurs %}
        <ul class="mt-4 list-disc space-y-1 pl-5 text-sm text-red-900">
          {% for erreur in rapport.erreurs %}<li>{{ erreur }}</li>{% endfor %}
        </ul>
      {% endif %}
    </section>
  {% endif %}

  <div class="mt-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
    <h2 class="text-sm font-semibold text-slate-900">1. Préparer le fichier</h2>
    <p class="mt-2 text-sm text-slate-600">
      Téléchargez le modèle (instructions et une feuille par type de donnée, listes déroulantes, ligne d'exemple), remplissez-le
      sans toucher à la ligne d'en-tête, puis déposez-le ci-dessous. Une personne, un client ou un camion déjà dans l'application
      n'est jamais écrasé ; à la moindre ligne en erreur, rien n'est enregistré.
    </p>
    <a href="{% url 'importation:modele' %}" download
       class="mt-3 inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 shadow-sm hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
      <i class="fa-solid fa-download" aria-hidden="true"></i> Télécharger le modèle Excel
    </a>
  </div>

  <form method="post" enctype="multipart/form-data" novalidate class="mt-6 space-y-5 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
    {% csrf_token %}
    <h2 class="text-sm font-semibold text-slate-900">2. Déposer le fichier rempli</h2>
    {% if form.non_field_errors %}
      <div role="alert" class="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">{% for erreur in form.non_field_errors %}<p>{{ erreur }}</p>{% endfor %}</div>
    {% endif %}
    {% include "components/_champ.html" with champ=form.fichier %}
    <div class="flex items-center gap-2">
      {{ form.simulation }}
      <label for="{{ form.simulation.id_for_label }}" class="text-sm text-slate-700">{{ form.simulation.label }}</label>
    </div>
    <div class="flex items-center justify-end gap-3 border-t border-slate-100 pt-5">
      <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Importer</button>
    </div>
  </form>
</div>
{% endblock %}
```

## Étape 5 — Tests, README et compilation des styles

#### `apps/importation/README.md`

*24 lignes* — importation

```markdown
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
- **Statuts** : seuls ceux qui se posent à la main sont acceptés (chauffeurs et copilotes : Disponible, Suspendu, Inactif ; camions :
  Disponible, Immobilisé, Hors service). « En mission », « En congé » et « En maintenance » sont posés par les missions, les congés et le
  garage. La date de délivrance d'un document de camion est facultative : à défaut, un an avant l'expiration.
- Droits : ADMIN seulement (`permissions.IMPORT_DONNEES`). Fichier .xlsx de 5 Mo au plus, 2 000 lignes par feuille.

L'import du personnel seul de l'écran RH (`/rh/personnel/importer/`) reste disponible.
```

#### `apps/importation/tests/helpers.py`

*43 lignes* — Fabrique de classeurs pour les tests : le modèle réel, vidé de ses exemples puis rempli.

```python
"""Fabrique de classeurs pour les tests : le modèle réel, vidé de ses exemples puis rempli."""

from io import BytesIO

from openpyxl import Workbook, load_workbook

from apps.importation import modele


def classeur(**feuilles) -> BytesIO:
    """``classeur(personnel=[[...], ...], clients=[...])`` : en-têtes du modèle + les lignes données."""
    wb = Workbook()
    wb.remove(wb.active)
    for cle, lignes in feuilles.items():
        ws = wb.create_sheet(modele.TITRES[cle])
        ws.append(modele.COLONNES[cle])
        for ligne in lignes:
            ws.append(ligne)
    tampon = BytesIO()
    wb.save(tampon)
    tampon.seek(0)
    return tampon


PERSONNEL = ["Diallo", "Fatou", "Comptable", "Ressources Humaines et Finances", "CDI", "01/09/2026", 250000]
CHAUFFEUR_PERSONNE = ["Soro", "Ali", "Chauffeur", "Parc Auto", "CDI", "01/03/2025", 180000]
COPILOTE_PERSONNE = ["Diomandé", "Seydou", "Copilote", "Parc Auto", "CDD", "01/03/2025", 120000]
CHAUFFEUR = [
    "Soro", "Ali", "+225 07 00 00 00 00", "Marie +225 05 00 00 00 00", "CI-PL-099999", "C,E", "12/11/2028",
    "03/05/2027", "Disponible",
]
COPILOTE = ["Diomandé", "Seydou", "+225 01 00 00 00 00", "Aïcha", "Suspendu"]
CLIENT = [
    "Sodeci", "CI-NCC-9876543B", "Mme Touré", "+225 27 00 00 00 00", "contact@sodeci.ci", "Abidjan", 18, "", 30,
]
VEHICULE = [
    "CI-9999-ZZ", "Mercedes-Benz", "Actros", 2019, "WDB9634031L999999", 185000, 25, 400, "Disponible", "",
    "", "15/03/2027", "01/01/2026", "01/01/2027", "", "", "", "",
]


def modele_vide_lu():
    return load_workbook(BytesIO(modele.construire_modele()))
```

#### `apps/importation/tests/test_import.py`

*337 lignes* — Import des données de l'entreprise depuis Excel : une feuille par type de donnée, tout ou rien, rien d'écrasé.

```python
"""Import des données de l'entreprise depuis Excel : une feuille par type de donnée, tout ou rien, rien d'écrasé."""

from io import BytesIO
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse
from openpyxl import load_workbook

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.audit.models import ActionChoices, AuditLog
from apps.customers.models import Client
from apps.drivers.models import Chauffeur, Copilote, StatutChauffeur
from apps.fleet.models import DocumentReglementaire, StatutVehicule, TypeDocument, Vehicule
from apps.hr.models import Personnel
from apps.importation import modele, services

from .helpers import (
    CHAUFFEUR, CHAUFFEUR_PERSONNE, CLIENT, COPILOTE, COPILOTE_PERSONNE, PERSONNEL, VEHICULE, classeur, modele_vide_lu,
)

pytestmark = pytest.mark.django_db


def _admin():
    return UserFactory(role=Role.ADMIN)


def _importer(fichier, **kwargs):
    return services.importer_classeur(fichier, _admin(), **kwargs)


def _tout():
    return classeur(
        personnel=[PERSONNEL, CHAUFFEUR_PERSONNE, COPILOTE_PERSONNE], chauffeurs=[CHAUFFEUR], copilotes=[COPILOTE],
        clients=[CLIENT], vehicules=[[*VEHICULE[:9], "Soro Ali", *VEHICULE[10:]]],
    )


# --- le modèle ---


def test_le_modele_a_les_six_feuilles_et_les_en_tetes_que_l_import_lit():
    wb = modele_vide_lu()

    assert wb.sheetnames == ["Instructions"] + [modele.TITRES[c] for c in (
        modele.PERSONNEL, modele.VEHICULES, modele.CHAUFFEURS, modele.COPILOTES, modele.CLIENTS)]
    for cle in modele.ORDRE:
        entetes = [c.value for c in wb[modele.TITRES[cle]][1]][: len(modele.COLONNES[cle])]
        assert entetes == modele.COLONNES[cle]


def test_les_en_tetes_du_personnel_sont_ceux_de_l_import_rh_existant():
    from apps.hr.services import COLONNES_IMPORT

    assert modele.COLONNES[modele.PERSONNEL] == list(COLONNES_IMPORT)


CHEMIN_COPIE = Path(settings.BASE_DIR) / "modele-donnees-entreprise-DEN-Source.xlsx"


@pytest.mark.skipif(not CHEMIN_COPIE.exists(), reason="copie versionnée absente (générée par `manage.py generer_modele_import`)")
def test_la_copie_versionnee_du_modele_a_les_memes_feuilles_et_en_tetes():
    wb = load_workbook(CHEMIN_COPIE)

    assert wb.sheetnames == modele_vide_lu().sheetnames
    for cle in modele.ORDRE:
        assert [c.value for c in wb[modele.TITRES[cle]][1]][: len(modele.COLONNES[cle])] == modele.COLONNES[cle]


def test_un_modele_non_modifie_s_importe_sans_rien_creer():
    """Le modèle brut (avec ses exemples) est valide, et ses exemples ne deviennent jamais de vraies fiches."""
    fichier = BytesIO(modele.construire_modele())

    rapport = _importer(fichier)

    assert rapport.enregistre and rapport.total_crees == 0
    assert sum(f.exemples_ignores for f in rapport.feuilles) == 5
    assert not Personnel.objects.exists() and not Client.objects.exists() and not Vehicule.objects.exists()


# --- import complet ---


def test_un_import_complet_cree_et_relie_tout():
    rapport = _importer(_tout())

    assert rapport.enregistre and not rapport.erreurs
    assert rapport.total_crees == 3 + 1 + 1  # 3 personnes, 1 client, 1 camion
    assert rapport.total_mis_a_jour == 2  # fiches chauffeur et copilote complétées
    chauffeur = Chauffeur.objects.get(personnel__nom="Soro")
    assert chauffeur.numero_permis == "CI-PL-099999" and chauffeur.categories_permis == ["C", "E"]
    assert str(chauffeur.date_expiration_permis) == "2028-11-12"
    copilote = Copilote.objects.get(personnel__nom="Diomandé")
    assert copilote.telephone == "+225 01 00 00 00 00" and copilote.statut == StatutChauffeur.SUSPENDU
    client = Client.objects.get(ncc_nif="CI-NCC-9876543B")
    assert client.taux_tva == 18 and client.delai_paiement_jours == 30
    camion = Vehicule.objects.get(immatriculation="CI-9999-ZZ")
    assert camion.chauffeur_habituel == chauffeur and camion.kilometrage == 185000
    assert Personnel.objects.get(nom="Diallo").matricule.startswith("PERS-")


def test_les_documents_du_camion_sont_enregistres_avec_une_delivrance_par_defaut():
    _importer(_tout())

    assurance = DocumentReglementaire.objects.get(type_document=TypeDocument.ASSURANCE)
    carte = DocumentReglementaire.objects.get(type_document=TypeDocument.CARTE_GRISE)
    assert (str(assurance.date_delivrance), str(assurance.date_expiration)) == ("2026-01-01", "2027-01-01")
    assert (str(carte.date_delivrance), str(carte.date_expiration)) == ("2026-03-15", "2027-03-15")  # un an avant
    assert DocumentReglementaire.objects.count() == 2


def test_chaque_creation_est_tracee_au_journal_d_audit_avec_l_importateur():
    _importer(_tout())

    assert AuditLog.objects.filter(entite="Personnel", action=ActionChoices.CREATE).count() == 3
    assert AuditLog.objects.filter(entite="Client", action=ActionChoices.CREATE).count() == 1
    assert AuditLog.objects.filter(entite="Vehicule", action=ActionChoices.CREATE).count() == 1


def test_reimporter_le_meme_fichier_ne_cree_aucun_doublon():
    _importer(_tout())

    rapport = _importer(_tout())

    assert rapport.enregistre and rapport.total_crees == 0
    assert sum(f.deja_presents for f in rapport.feuilles) == 3 + 1 + 1
    assert Personnel.objects.count() == 3 and Client.objects.count() == 1 and Vehicule.objects.count() == 1


def test_une_fiche_deja_dans_l_erp_n_est_jamais_ecrasee():
    from apps.customers.tests.factories import ClientFactory

    ClientFactory(ncc_nif="CI-NCC-9876543B", raison_sociale="Nom d'origine")

    rapport = _importer(classeur(clients=[CLIENT]))

    assert rapport.feuilles[3].deja_presents == 1
    assert Client.objects.get(ncc_nif="CI-NCC-9876543B").raison_sociale == "Nom d'origine"


def test_une_feuille_peut_etre_importee_seule():
    rapport = _importer(classeur(clients=[CLIENT]))

    assert rapport.enregistre and rapport.total_crees == 1
    assert [f.presente for f in rapport.feuilles] == [False, False, False, True, False]


def test_les_chauffeurs_se_rattachent_a_une_fiche_deja_dans_l_erp():
    from apps.hr.tests.factories import PersonnelFactory

    PersonnelFactory(nom="Soro", prenom="Ali", poste="Chauffeur")

    rapport = _importer(classeur(chauffeurs=[CHAUFFEUR]))

    assert rapport.enregistre and Chauffeur.objects.get(personnel__nom="Soro").numero_permis == "CI-PL-099999"


def test_les_noms_se_rapprochent_sans_tenir_compte_de_la_casse_ni_des_accents():
    ligne = ["SORO", "ali"] + CHAUFFEUR[2:]
    habituel = [*VEHICULE[:9], "soro ALI", *VEHICULE[10:]]

    rapport = _importer(classeur(personnel=[CHAUFFEUR_PERSONNE], chauffeurs=[ligne], vehicules=[habituel]))

    assert rapport.enregistre and Vehicule.objects.get().chauffeur_habituel.personnel.nom == "Soro"


# --- tout ou rien et erreurs ---


def test_une_ligne_en_erreur_annule_tout_et_la_liste_avec_sa_feuille_et_son_numero():
    mauvais_client = [*CLIENT[:6], 18, "", "abc"]
    mauvais_poste = ["Yao", "Marc", "Astronaute", *PERSONNEL[3:]]

    rapport = _importer(classeur(personnel=[PERSONNEL, mauvais_poste], clients=[mauvais_client]))

    assert not rapport.enregistre
    assert any("Personnel (Employés), ligne 3 : poste « Astronaute » inconnu" in e for e in rapport.erreurs)
    assert any("Clients, ligne 2 : Le délai de paiement" in e for e in rapport.erreurs)
    assert not Personnel.objects.exists() and not Client.objects.exists()  # la ligne 2 valide n'a pas été gardée


@pytest.mark.parametrize(
    "feuille, ligne, attendu",
    [
        ("chauffeurs", ["Inconnu", "Nom"] + CHAUFFEUR[2:], "ne figure ni sur la feuille Personnel"),
        ("chauffeurs", [*CHAUFFEUR[:8], "En mission"], "Le statut « En mission » inconnu"),
        ("chauffeurs", [*CHAUFFEUR[:5], "Z", *CHAUFFEUR[6:]], "Catégorie(s) de permis inconnue(s)"),
        ("copilotes", [*COPILOTE[:4], "En congé"], "Le statut « En congé » inconnu"),
        ("clients", [*CLIENT[:6], 0, "", 30], "motif d'exonération"),
        ("clients", [*CLIENT[:7], "Inventé", 30], "Le motif d'exonération « Inventé » inconnu"),
        ("vehicules", [*VEHICULE[:8], "En mission", ""] + VEHICULE[10:], "Le statut « En mission » inconnu"),
        ("vehicules", [*VEHICULE[:9], "Personne Inconnu", *VEHICULE[10:]], "chauffeur habituel « Personne Inconnu » introuvable"),
        ("vehicules", [*VEHICULE[:3], "deux mille", *VEHICULE[4:9], "", *VEHICULE[10:]], "L'année « deux mille » invalide"),
        ("vehicules", [*VEHICULE[:10], "10/10/2026", "", *VEHICULE[12:]], "Carte grise : la date d'expiration"),
        ("vehicules", [*VEHICULE[:11], "pas une date", *VEHICULE[12:]], "invalide (attendu JJ/MM/AAAA)"),
    ],
)
def test_les_erreurs_de_ligne_sont_expliquees(feuille, ligne, attendu):
    if feuille == "chauffeurs":
        fichier = classeur(personnel=[CHAUFFEUR_PERSONNE], chauffeurs=[ligne])
    elif feuille == "copilotes":
        fichier = classeur(personnel=[COPILOTE_PERSONNE], copilotes=[ligne])
    else:
        fichier = classeur(**{feuille: [ligne]})

    rapport = _importer(fichier)

    assert not rapport.enregistre
    assert any(attendu in e for e in rapport.erreurs), rapport.erreurs


def test_un_chauffeur_dont_le_poste_n_est_pas_chauffeur_est_refuse():
    rapport = _importer(classeur(personnel=[PERSONNEL], chauffeurs=[["Diallo", "Fatou"] + CHAUFFEUR[2:]]))

    assert any("n'a pas de fiche chauffeur" in e for e in rapport.erreurs)


def test_deux_fiches_au_meme_nom_sont_ambigues():
    from apps.hr.tests.factories import PersonnelFactory

    PersonnelFactory(nom="Soro", prenom="Ali", poste="Chauffeur")
    PersonnelFactory(nom="Soro", prenom="Ali", poste="Chauffeur")

    rapport = _importer(classeur(chauffeurs=[CHAUFFEUR]))

    assert any("plusieurs fiches du personnel" in e for e in rapport.erreurs)


def test_des_en_tetes_modifies_refusent_la_feuille():
    wb = modele_vide_lu()
    wb["Clients"]["A1"] = "Société"
    tampon = BytesIO()
    wb.save(tampon)
    tampon.seek(0)

    rapport = _importer(tampon)

    assert not rapport.enregistre and any("en-têtes inattendus" in e for e in rapport.erreurs)


def test_la_simulation_verifie_sans_rien_enregistrer():
    rapport = _importer(_tout(), simulation=True)

    assert not rapport.enregistre and not rapport.erreurs and rapport.total_crees == 5
    assert not Personnel.objects.exists() and not Client.objects.exists() and not Vehicule.objects.exists()


def test_un_camion_au_statut_hors_service_garde_ce_statut():
    ligne = [*VEHICULE[:8], "Hors service", ""] + VEHICULE[10:]

    _importer(classeur(vehicules=[ligne]))

    assert Vehicule.objects.get().statut == StatutVehicule.HORS_SERVICE


def test_les_lignes_vides_sont_ignorees_et_les_fichiers_invalides_refuses():
    assert _importer(classeur(clients=[[], [None] * 9, CLIENT])).total_crees == 1
    with pytest.raises(services.ImportInvalide, match="pas un classeur Excel"):
        _importer(BytesIO(b"ceci n'est pas un classeur"))
    from openpyxl import Workbook

    vide = BytesIO()
    Workbook().save(vide)
    vide.seek(0)
    with pytest.raises(services.ImportInvalide, match="Aucune feuille reconnue"):
        _importer(vide)


def test_les_onglets_acceptent_un_nom_court():
    wb = load_workbook(classeur(clients=[CLIENT]))
    wb.active.title = "clients"
    tampon = BytesIO()
    wb.save(tampon)
    tampon.seek(0)

    assert _importer(tampon).total_crees == 1


# --- droits et écran ---


@pytest.mark.parametrize("role", [Role.DIRECTION, Role.RH, Role.FINANCES, Role.PARCAUTO, Role.CHAUFFEUR])
def test_seul_l_admin_importe(client, role):
    client.force_login(UserFactory(role=role))

    assert client.get(reverse("importation:importer")).status_code == 403
    assert client.get(reverse("importation:modele")).status_code == 403
    assert client.post(reverse("importation:importer"), {"fichier": _tout()}).status_code == 403
    with pytest.raises(services.ImportInvalide, match="administrateur"):
        services.importer_classeur(_tout(), UserFactory(role=role))


def test_le_menu_propose_l_import_a_l_admin_seulement(client):
    client.force_login(_admin())
    assert reverse("importation:importer") in client.get(reverse("home")).content.decode()
    client.force_login(UserFactory(role=Role.RH))
    assert reverse("importation:importer") not in client.get(reverse("home")).content.decode()


def test_l_admin_telecharge_le_modele(client):
    client.force_login(_admin())

    reponse = client.get(reverse("importation:modele"))

    assert reponse.status_code == 200 and "spreadsheetml" in reponse["Content-Type"]
    assert "Clients" in load_workbook(BytesIO(reponse.content)).sheetnames


def test_l_admin_depose_un_fichier_et_voit_le_rapport(client):
    client.force_login(_admin())
    fichier = _tout()
    fichier.name = "donnees.xlsx"

    reponse = client.post(reverse("importation:importer"), {"fichier": fichier})

    page = reponse.content.decode()
    assert reponse.status_code == 200 and "Import terminé" in page and "5 fiches créées" in page
    assert Client.objects.count() == 1


def test_l_ecran_affiche_les_erreurs_par_ligne_et_refuse_un_mauvais_fichier(client):
    client.force_login(_admin())
    mauvais = classeur(clients=[[*CLIENT[:6], 18, "", "abc"]])
    mauvais.name = "donnees.xlsx"

    page = client.post(reverse("importation:importer"), {"fichier": mauvais}).content.decode()
    assert "Rien n'a été importé" in page and "Clients, ligne 2" in page

    faux = BytesIO(b"pas un classeur")
    faux.name = "donnees.xlsx"
    assert "pas un classeur Excel" in client.post(reverse("importation:importer"), {"fichier": faux}).content.decode()
    pdf = BytesIO(b"%PDF")
    pdf.name = "donnees.pdf"
    assert ".xlsx" in client.post(reverse("importation:importer"), {"fichier": pdf}).content.decode()
```

```bash
cd frontend
npm run build:css
cd ..
```

## Vérifier le chapitre

```bash
python manage.py check
python manage.py generer_modele_import
```

**Résultat attendu :** `Modèle écrit : …/modele-donnees-entreprise-DEN-Source.xlsx`. Ce fichier binaire n'est pas montré dans
ce tutoriel : on le **génère** (un test compare sa copie versionnée au code ; sans cette copie, il est simplement ignoré).

```bash
python -m pytest apps/importation/tests/test_import.py -q --no-cov
```

**Résultat attendu :** `39 passed` (pour les 1 fichier(s) de tests présentés dans ce chapitre).

**Un import dans le navigateur** (compte `demo_admin`, qui demande sa double authentification à la première
connexion) :

1. Menu **Import de données** → **Télécharger le modèle Excel**. Ouvrez-le : les listes déroulantes proposent les
   postes, départements, statuts.
2. Dans la feuille **Clients**, supprimez la ligne jaune et ajoutez un client (NCC/NIF, contact, téléphone, adresse).
   Déposez le fichier avec **Simulation** cochée : « Simulation réussie… rien n'a été enregistré ».
3. Décochez la case et redéposez : « Import terminé : 1 fiche créée ».
4. Déposez-le **une troisième fois** : « 1 déjà présent », aucun doublon.
5. Cassez volontairement une ligne (un délai de paiement « abc ») : « Rien n'a été importé » et l'erreur est listée
   avec sa feuille et son numéro de ligne.

## Ce qu'il faut retenir

- Une reprise de données doit être **rejouable** (aucun doublon) et **réversible** avant validation (simulation,
  « tout ou rien »).
- On importe **par les services** de chaque app : les règles métier et l'audit restent appliqués, il n'y a pas de
  « chemin parallèle » vers la base.
- Le modèle téléchargeable et le lecteur partagent **la même description des colonnes**.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 31 : app importation (import Excel des données, modèle téléchargeable, simulation)"
```

---

[← Chapitre 30](30-api.md) · [Sommaire](README.md) · [Chapitre 32 →](32-finalisation.md)
