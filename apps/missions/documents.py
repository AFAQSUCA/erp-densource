"""PDF des codes d'une mission, à transmettre à l'expéditeur et au destinataire.

Une page par partie (chacune ne voit que son code) : en-tête de l'entreprise avec son logo, rappel de
la mission, le code en grand et son code QR, puis la consigne à suivre. Le chauffeur saisit ou scanne
ce code pour confirmer la récupération (expéditeur) ou la livraison (destinataire) : c'est le seul
secret de la mission, le document doit donc partir vers la bonne personne.

ReportLab (cahier-des-charges.md:252 « PDF/QR : WeasyPrint / ReportLab »), choisi pour sa simplicité
de déploiement : aucune bibliothèque système à ajouter à l'image Docker, contrairement à WeasyPrint.
Le document n'est jamais stocké : il est produit à la demande, tant que les codes sont utiles.
"""

from __future__ import annotations

import io

import qrcode
from django.conf import settings
from django.contrib.staticfiles import finders
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

MARQUE = colors.HexColor("#8B0319")
ACCENT = colors.HexColor("#F28A14")
GRIS = colors.HexColor("#475569")
MARGE = 20 * mm
LARGEUR, HAUTEUR = A4

STYLE_TEXTE = ParagraphStyle("texte", fontName="Helvetica", fontSize=11, leading=16, textColor=colors.HexColor("#0f172a"))
STYLE_ALERTE = ParagraphStyle(
    "alerte", parent=STYLE_TEXTE, fontSize=10, leading=14, textColor=colors.HexColor("#78350f")
)


def _pages(mission, codes: dict[str, str | None], entreprise: str) -> list[dict]:
    """Les pages à produire : celles dont le code est encore utile (``codes`` vient de
    ``permissions.codes_visibles``)."""
    pages = []
    if codes.get("expediteur"):
        pages.append({
            "titre": "Code de récupération du colis",
            "destinataire_du_document": "À l'attention de l'expéditeur",
            "code": codes["expediteur"],
            "legende": "Code de l'expéditeur",
            "consignes": (
                f"Un camion {entreprise} viendra charger la marchandise décrite ci-dessus. Au moment "
                "du chargement, remettez le code ci-dessous au chauffeur, ou faites-lui scanner le "
                "code QR : c'est ce qui confirme que le colis a bien été récupéré."
            ),
            "alerte": "Confidentiel : ne communiquez ce code qu'au chauffeur présent au chargement. "
            "Il ne sert qu'une fois.",
        })
    if codes.get("destinataire"):
        pages.append({
            "titre": "Code de réception de la marchandise",
            "destinataire_du_document": "À l'attention du destinataire",
            "code": codes["destinataire"],
            "legende": "Code de réception",
            "consignes": (
                f"Un camion {entreprise} vous livrera la marchandise décrite ci-dessus. Merci de "
                "transmettre le code de réception ci-dessous à la personne qui réceptionnera la "
                "marchandise sur votre site (votre réceptionnaire). À l'arrivée du camion, elle le "
                "remettra au chauffeur, ou lui fera scanner le code QR : c'est ce qui confirme la livraison."
            ),
            "alerte": "Sans ce code, la livraison ne peut pas être confirmée. Ne le communiquez qu'à la "
            "personne chargée de la réception.",
        })
    return pages


def _entete(c: canvas.Canvas, entreprise: str) -> float:
    """En-tête : logo, raison sociale, adresse et NCC, filet aux couleurs de la marque. Renvoie l'ordonnée
    sous l'en-tête."""
    haut = HAUTEUR - MARGE
    logo = finders.find("img/logo-emblem.jpg")
    if logo:
        c.drawImage(logo, MARGE, haut - 22 * mm, width=22 * mm, height=22 * mm, preserveAspectRatio=True, mask="auto")
    x = MARGE + 28 * mm
    c.setFillColor(MARQUE)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(x, haut - 9 * mm, entreprise)
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 9)
    ligne = haut - 15 * mm
    for texte in (settings.ENTREPRISE_ADRESSE, f"N° CC : {settings.ENTREPRISE_NCC}" if settings.ENTREPRISE_NCC else ""):
        if texte:
            c.drawString(x, ligne, texte)
            ligne -= 4.5 * mm
    c.setStrokeColor(ACCENT)
    c.setLineWidth(2)
    c.line(MARGE, haut - 26 * mm, LARGEUR - MARGE, haut - 26 * mm)
    return haut - 34 * mm


def _paragraphe(c: canvas.Canvas, texte: str, style: ParagraphStyle, y: float) -> float:
    paragraphe = Paragraph(texte, style)
    _, hauteur = paragraphe.wrap(LARGEUR - 2 * MARGE, HAUTEUR)
    paragraphe.drawOn(c, MARGE, y - hauteur)
    return y - hauteur


def _rappel_mission(c: canvas.Canvas, mission, y: float) -> float:
    lignes = [
        ("Mission", mission.numero),
        ("Client", str(mission.client)),
        ("Marchandise", f"{mission.nature_marchandise} — {mission.poids_t.normalize():f} t"),
        ("Chargement", mission.lieu_chargement),
        ("Livraison", mission.lieu_livraison),
    ]
    if mission.date_depart_prevue:
        lignes.append(("Départ prévu", mission.date_depart_prevue.strftime("%d/%m/%Y")))
    for libelle, valeur in lignes:
        c.setFillColor(GRIS)
        c.setFont("Helvetica", 10)
        c.drawString(MARGE, y, libelle)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.setFont("Helvetica-Bold", 10)
        c.drawString(MARGE + 32 * mm, y, valeur)
        y -= 6 * mm
    return y


def _code_et_qr(c: canvas.Canvas, code: str, legende: str, y: float) -> float:
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 10)
    c.drawCentredString(LARGEUR / 2, y, legende.upper())
    y -= 4 * mm
    haut_cadre = 24 * mm
    c.setStrokeColor(MARQUE)
    c.setFillColor(colors.HexColor("#fff7ed"))
    c.setLineWidth(1.5)
    c.roundRect(MARGE + 20 * mm, y - haut_cadre, LARGEUR - 2 * MARGE - 40 * mm, haut_cadre, 4 * mm, stroke=1, fill=1)
    c.setFillColor(colors.HexColor("#0f172a"))
    c.setFont("Courier-Bold", 38)
    c.drawCentredString(LARGEUR / 2, y - 16 * mm, " ".join(code))  # espacé : se dicte plus facilement
    y -= haut_cadre + 8 * mm

    image = io.BytesIO()
    qrcode.make(code, box_size=10, border=2).save(image, format="PNG")
    image.seek(0)
    cote = 55 * mm
    c.drawImage(ImageReader(image), (LARGEUR - cote) / 2, y - cote, width=cote, height=cote)
    return y - cote - 8 * mm


def generer_pdf_codes(mission, codes: dict[str, str | None]) -> bytes:
    """PDF des codes encore utiles de ``mission`` (une page par code). Vide (aucun code) : ``ValueError``."""
    entreprise = settings.ENTREPRISE_NOM
    pages = _pages(mission, codes, entreprise)
    if not pages:
        raise ValueError("Aucun code à communiquer pour cette mission.")

    tampon = io.BytesIO()
    c = canvas.Canvas(tampon, pagesize=A4, pageCompression=0)
    c.setTitle(f"Codes de la mission {mission.numero}")
    c.setAuthor(entreprise)
    edite_le = timezone.localtime().strftime("%d/%m/%Y à %H:%M")
    for page in pages:
        y = _entete(c, entreprise)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.setFont("Helvetica-Bold", 17)
        c.drawString(MARGE, y, page["titre"])
        y -= 6 * mm
        c.setFillColor(GRIS)
        c.setFont("Helvetica-Oblique", 11)
        c.drawString(MARGE, y, page["destinataire_du_document"])
        y -= 10 * mm
        y = _rappel_mission(c, mission, y)
        y -= 4 * mm
        y = _paragraphe(c, page["consignes"], STYLE_TEXTE, y) - 8 * mm
        y = _code_et_qr(c, page["code"], page["legende"], y)
        _paragraphe(c, page["alerte"], STYLE_ALERTE, y)
        c.setFillColor(GRIS)
        c.setFont("Helvetica", 8)
        c.drawString(MARGE, 12 * mm, f"Document confidentiel — mission {mission.numero} — édité le {edite_le}")
        c.showPage()
    c.save()
    return tampon.getvalue()
