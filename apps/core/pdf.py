"""PDF des rapports, générés par le serveur (cahier-des-charges.md:305 « Export PDF » ; décision du 12/10/2026 :
avenant-export-pdf.md).

Un rapport = des blocs (titres, paragraphes, tableaux, paires libellé/valeur), mis en page par ReportLab
(``platypus``) : texte qui passe à la ligne, tableau découpé sur plusieurs pages avec sa ligne de titres répétée,
paysage automatique pour un tableau large. Chaque page porte l'en-tête de l'entreprise (logo, raison sociale,
adresse, NCC) et un pied « Généré le … par … — Page N », comme les rapports imprimables HTML.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from xml.sax.saxutils import escape

from django.contrib.staticfiles import finders
from django.http import HttpResponse
from django.utils import timezone
from django.utils.text import slugify
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

from .formats import nombre

MARQUE = colors.HexColor("#8B0319")
ACCENT = colors.HexColor("#F28A14")
GRIS = colors.HexColor("#475569")
ENCRE = colors.HexColor("#0f172a")
FOND_TITRES = colors.HexColor("#f1f5f9")
FILET = colors.HexColor("#cbd5e1")
MARGE = 15 * mm
HAUT_ENTETE = 30 * mm
COLONNES_PORTRAIT_MAX = 6  # au-delà, le tableau passe en paysage

STYLE_TEXTE = ParagraphStyle("texte", fontName="Helvetica", fontSize=9, leading=12, textColor=ENCRE)
STYLE_CELLULE = ParagraphStyle("cellule", fontName="Helvetica", fontSize=8, leading=10, textColor=ENCRE)
STYLE_ENTETE = ParagraphStyle("entete", parent=STYLE_CELLULE, fontName="Helvetica-Bold")
STYLE_TITRE = ParagraphStyle("titre", fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=ENCRE)
STYLE_SOUS_TITRE = ParagraphStyle("sous_titre", parent=STYLE_TEXTE, textColor=GRIS)
STYLE_SECTION = ParagraphStyle("section", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=MARQUE,
                               spaceBefore=6, spaceAfter=3)


@dataclass
class Tableau:
    """Tableau d'un rapport. ``alignes_a_droite`` : indices des colonnes de montants. ``total`` : dernière ligne
    mise en gras (totaux)."""

    entetes: list[str]
    lignes: list[list]
    alignes_a_droite: set[int] = field(default_factory=set)
    total: list | None = None
    largeurs: list[float] | None = None  # en proportions (somme libre), sinon parts égales
    sans_entete: bool = False


@dataclass
class Section:
    titre: str


@dataclass
class Texte:
    texte: str
    discret: bool = False


@dataclass
class Rubriques:
    """Paires « libellé : valeur » (résumé, indicateurs)."""

    paires: list[tuple[str, str]]


def _texte(valeur) -> str:
    return escape("" if valeur is None else str(valeur)).replace("\n", "<br/>")


def _tableau(bloc: Tableau, largeur_utile: float) -> LongTable:
    def cellule(valeur, style, colonne):
        style_colonne = ParagraphStyle(f"{style.name}-d", parent=style, alignment=2) if colonne in bloc.alignes_a_droite else style
        return Paragraph(_texte(valeur), style_colonne)

    donnees = [] if bloc.sans_entete else [[cellule(e, STYLE_ENTETE, i) for i, e in enumerate(bloc.entetes)]]
    donnees += [[cellule(v, STYLE_CELLULE, i) for i, v in enumerate(ligne)] for ligne in bloc.lignes]
    if not donnees:
        donnees = [[cellule("", STYLE_CELLULE, i) for i in range(len(bloc.entetes))]]
    if bloc.total is not None:
        donnees.append([cellule(v, STYLE_ENTETE, i) for i, v in enumerate(bloc.total)])
    parts = bloc.largeurs or [1] * len(bloc.entetes)
    largeurs = [largeur_utile * p / sum(parts) for p in parts]
    tableau = LongTable(donnees, colWidths=largeurs, repeatRows=0 if bloc.sans_entete else 1)
    style = [] if bloc.sans_entete else [
        ("BACKGROUND", (0, 0), (-1, 0), FOND_TITRES),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, GRIS),
    ]
    style += [
        ("LINEBELOW", (0, 0 if bloc.sans_entete else 1), (-1, -1), 0.25, FILET),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if bloc.total is not None:
        style += [("LINEABOVE", (0, -1), (-1, -1), 0.8, GRIS), ("BACKGROUND", (0, -1), (-1, -1), FOND_TITRES)]
    tableau.setStyle(TableStyle(style))
    return tableau


def generer_pdf(
    *, titre: str, sous_titre: str = "", blocs: list, entreprise: dict, genere_par: str,
    genere_le: datetime | None = None, paysage: bool | None = None,
) -> bytes:
    """PDF d'un rapport. ``paysage`` : par défaut, si un tableau dépasse ``COLONNES_PORTRAIT_MAX`` colonnes."""
    if paysage is None:
        paysage = any(isinstance(b, Tableau) and len(b.entetes) > COLONNES_PORTRAIT_MAX for b in blocs)
    taille = landscape(A4) if paysage else A4
    largeur, hauteur = taille
    genere_le = timezone.localtime(genere_le or timezone.now())
    tampon = io.BytesIO()
    document = SimpleDocTemplate(
        tampon, pagesize=taille, leftMargin=MARGE, rightMargin=MARGE, topMargin=MARGE + HAUT_ENTETE,
        bottomMargin=MARGE + 8 * mm, title=titre, author=entreprise.get("nom", ""), creator="DEN Source ERP",
    )
    largeur_utile = largeur - 2 * MARGE

    def decor(c, doc):
        c.saveState()
        haut = hauteur - MARGE
        logo = finders.find("img/logo-emblem.jpg")
        if logo:
            c.drawImage(logo, MARGE, haut - 18 * mm, width=18 * mm, height=18 * mm, preserveAspectRatio=True, mask="auto")
        x = MARGE + 22 * mm
        c.setFillColor(MARQUE)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(x, haut - 6 * mm, entreprise.get("nom", ""))
        c.setFillColor(GRIS)
        c.setFont("Helvetica", 8)
        ligne = haut - 11 * mm
        for texte in ((entreprise.get("adresse") or "").replace("\n", " · "), f"NCC {entreprise['ncc']}" if entreprise.get("ncc") else ""):
            if texte:
                c.drawString(x, ligne, texte)
                ligne -= 4 * mm
        c.setStrokeColor(ACCENT)
        c.setLineWidth(1.5)
        c.line(MARGE, haut - 22 * mm, largeur - MARGE, haut - 22 * mm)
        c.setFillColor(GRIS)
        c.setFont("Helvetica", 7.5)
        c.drawString(MARGE, MARGE, f"Généré le {genere_le:%d/%m/%Y à %H:%M} par {genere_par} — DEN Source ERP")
        c.drawRightString(largeur - MARGE, MARGE, f"Page {doc.page}")
        c.restoreState()

    histoire = [Paragraph(_texte(titre), STYLE_TITRE)]
    if sous_titre:
        histoire.append(Paragraph(_texte(sous_titre), STYLE_SOUS_TITRE))
    histoire.append(Spacer(1, 5 * mm))
    for bloc in blocs:
        if isinstance(bloc, Tableau):
            histoire.append(_tableau(bloc, largeur_utile))
            histoire.append(Spacer(1, 4 * mm))
        elif isinstance(bloc, Section):
            histoire.append(Paragraph(_texte(bloc.titre), STYLE_SECTION))
        elif isinstance(bloc, Rubriques):
            if bloc.paires:
                rubriques = Tableau(
                    entetes=["", ""], lignes=[list(p) for p in bloc.paires], alignes_a_droite={1}, largeurs=[2, 1],
                    sans_entete=True,
                )
                histoire.append(_tableau(rubriques, largeur_utile * 0.6))
            histoire.append(Spacer(1, 4 * mm))
        elif isinstance(bloc, Texte):
            histoire.append(Paragraph(_texte(bloc.texte), STYLE_SOUS_TITRE if bloc.discret else STYLE_TEXTE))
            histoire.append(Spacer(1, 2 * mm))
    document.build(histoire, onFirstPage=decor, onLaterPages=decor)
    return tampon.getvalue()


def cellule(valeur) -> str:
    """Valeur brute d'une feuille de rapport (celle de l'export Excel) mise en forme pour le PDF : montants avec
    séparateur de milliers (décimales seulement s'il y en a), dates JJ/MM/AAAA, vide pour ``None``."""
    if valeur is None:
        return ""
    if isinstance(valeur, bool):
        return "Oui" if valeur else "Non"
    if isinstance(valeur, (int, float, Decimal)):
        decimale = Decimal(str(valeur))
        return nombre(decimale, 0 if decimale == decimale.to_integral_value() else 2)
    if isinstance(valeur, datetime):
        return f"{timezone.localtime(valeur):%d/%m/%Y %H:%M}" if timezone.is_aware(valeur) else f"{valeur:%d/%m/%Y %H:%M}"
    if isinstance(valeur, date):
        return f"{valeur:%d/%m/%Y}"
    return str(valeur)


def blocs_depuis_feuilles(feuilles: list[dict]) -> list:
    """Feuilles d'un export Excel (``apps.core.xlsx.classeur``) → blocs PDF : mêmes chiffres dans les deux formats.
    Un titre de section par feuille quand il y en a plusieurs (ex. actif et passif du bilan)."""
    blocs = []
    for feuille in feuilles:
        if len(feuilles) > 1:
            blocs.append(Section(feuille["titre"]))
        lignes = feuille["lignes"]
        chiffres = {
            i for i in range(len(feuille["entetes"]))
            if any(isinstance(l[i], (int, float, Decimal)) and not isinstance(l[i], bool) for l in lignes if len(l) > i)
            or (feuille.get("pied") and isinstance(feuille["pied"][i], (int, float, Decimal)))
        }
        blocs.append(Tableau(
            entetes=feuille["entetes"],
            lignes=[[cellule(v) for v in ligne] for ligne in lignes],
            alignes_a_droite=chiffres,
            total=[cellule(v) for v in feuille["pied"]] if feuille.get("pied") else None,
        ))
        if not lignes:
            blocs.append(Texte("Aucune ligne.", discret=True))
    return blocs


def reponse_pdf(contenu: bytes, titre: str) -> HttpResponse:
    """Réponse de téléchargement : ``<titre>-<date>.pdf``."""
    reponse = HttpResponse(contenu, content_type="application/pdf")
    nom = f"{slugify(titre) or 'rapport'}-{timezone.localdate():%Y-%m-%d}.pdf"
    reponse["Content-Disposition"] = f'attachment; filename="{nom}"'
    return reponse
