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
