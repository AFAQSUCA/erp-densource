"""PDF « Autorisation de congé », produit à la demande une fois le congé approuvé (N2) — avenant
« séparation des tâches » § R7. Comme les codes de mission (``apps.missions.documents``) : jamais
stocké, toujours regénéré à la demande — donc toujours à jour, y compris après un report du solde
(``ReportConge`` approuvé), sans document à « régénérer » explicitement quelque part.

ReportLab (même choix que ``apps.missions.documents`` : aucune bibliothèque système à ajouter à
l'image Docker, contrairement à WeasyPrint — cahier-des-charges.md:252).
"""

from __future__ import annotations

import io
from xml.sax.saxutils import escape

from django.conf import settings
from django.contrib.staticfiles import finders
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from . import services
from .models import Conge, NiveauValidation

MARQUE = colors.HexColor("#8B0319")
ACCENT = colors.HexColor("#F28A14")
GRIS = colors.HexColor("#475569")
ENCRE = colors.HexColor("#0f172a")
MARGE = 20 * mm
LARGEUR, HAUTEUR = A4

STYLE_ATTESTATION = ParagraphStyle(
    "attestation", fontName="Helvetica", fontSize=11, leading=16, textColor=ENCRE
)


def _entete(c: canvas.Canvas, entreprise: str, titre: str) -> float:
    """En-tête : logo, raison sociale, adresse et NCC, filet aux couleurs de la marque (même gabarit
    que ``apps.missions.documents._entete``). Renvoie l'ordonnée sous l'en-tête."""
    haut = HAUTEUR - MARGE
    logo = finders.find("img/logo-emblem.jpg")
    if logo:
        c.drawImage(logo, MARGE, haut - 22 * mm, width=22 * mm, height=22 * mm, preserveAspectRatio=True, mask="auto")
    x = MARGE + 28 * mm
    c.setFillColor(MARQUE)
    c.setFont("Helvetica-Bold", 18)
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
    y = haut - 34 * mm
    c.setFillColor(ENCRE)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(MARGE, y, titre)
    return y - 12 * mm


def _ligne(c: canvas.Canvas, libelle: str, valeur: str, y: float) -> float:
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 10)
    c.drawString(MARGE, y, libelle)
    c.setFillColor(ENCRE)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(MARGE + 55 * mm, y, valeur)
    return y - 7 * mm


def _paragraphe(c: canvas.Canvas, texte: str, style: ParagraphStyle, y: float) -> float:
    paragraphe = Paragraph(texte, style)
    _, hauteur = paragraphe.wrap(LARGEUR - 2 * MARGE, HAUTEUR)
    paragraphe.drawOn(c, MARGE, y - hauteur)
    return y - hauteur


def _phrase_attestation(conge: Conge, entreprise: str, *, report_approuve: bool) -> str:
    """Formule d'attestation (identité, dates, motif) : le détail administratif (n°, validateurs,
    report, solde) reste en liste ci-dessous, moins naturel à lire en phrase."""
    employe = conge.employe
    jours = f"{conge.jours} jour{'s' if conge.jours > 1 else ''} ouvré{'s' if conge.jours > 1 else ''}"
    phrase = (
        f"Nous soussignés, <b>{escape(entreprise)}</b>, attestons que "
        f"<b>{escape(employe.prenom)} {escape(employe.nom)}</b> (matricule {escape(employe.matricule)}), "
        f"{escape(employe.poste)}, est autorisé(e) à s'absenter du "
        f"<b>{conge.date_debut.strftime('%d/%m/%Y')}</b> au "
        f"<b>{conge.date_fin.strftime('%d/%m/%Y')}</b> inclus, soit {jours}, "
        f"au titre de : « {escape(conge.motif[:200])} »."
    )
    if report_approuve:
        phrase += " Un report du solde restant a été approuvé ; il est détaillé ci-dessous."
    return phrase


def generer_pdf_autorisation(conge: Conge) -> bytes:
    """PDF de l'autorisation de congé : une phrase d'attestation (identité, dates, motif), puis le
    détail administratif (n°, validateurs, report, solde) en liste, plus lisible que la prose.
    ``ValueError`` si le congé n'a jamais été approuvé (N2)."""
    if conge.statut not in services.STATUTS_DECOMPTES:
        raise ValueError("Ce congé n'a pas (encore) été approuvé : pas d'autorisation à délivrer.")

    entreprise = settings.ENTREPRISE_NOM
    employe = conge.employe
    droits = services.droits_conges(employe, conge.date_debut.year)
    validation_n1 = conge.validations.filter(niveau=NiveauValidation.N1).order_by("date_decision").first()
    validation_n2 = conge.validations.filter(niveau=NiveauValidation.N2).order_by("date_decision").first()
    report = conge.reports.filter(statut="APPROUVE").order_by("-date_decision").first()

    tampon = io.BytesIO()
    c = canvas.Canvas(tampon, pagesize=A4, pageCompression=0)
    c.setTitle(f"Autorisation de congé - {employe.prenom} {employe.nom}")
    c.setAuthor(entreprise)

    y = _entete(c, entreprise, "Autorisation de congé")
    y = _paragraphe(c, _phrase_attestation(conge, entreprise, report_approuve=bool(report)), STYLE_ATTESTATION, y)
    y -= 8 * mm

    y = _ligne(c, "N° de congé", f"CONGE-{conge.pk:06d}", y)
    y -= 3 * mm

    if validation_n1:
        y = _ligne(c, "Validé N1 par", f"{validation_n1.validateur} le {validation_n1.date_decision.strftime('%d/%m/%Y')}", y)
    if validation_n2:
        y = _ligne(c, "Validé N2 (RH) par", f"{validation_n2.validateur} le {validation_n2.date_decision.strftime('%d/%m/%Y')}", y)

    if report:
        y -= 5 * mm
        c.setFillColor(MARQUE)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(MARGE, y, "Report de solde")
        y -= 7 * mm
        y = _ligne(c, "Reprise anticipée le", report.nouvelle_date_fin.strftime("%d/%m/%Y"), y)
        y = _ligne(c, "Jours reversés au solde", f"{report.jours_restants} jour{'s' if report.jours_restants > 1 else ''} ouvré{'s' if report.jours_restants > 1 else ''}", y)
        y = _ligne(c, "Motif du report", report.motif[:80], y)
        y = _ligne(c, "Validé par (RH)", f"{report.valide_par} le {report.date_decision.strftime('%d/%m/%Y')}", y)

    y -= 5 * mm
    y = _ligne(c, f"Solde disponible ({conge.date_debut.year})", f"{droits['disponible']} jour(s)", y)

    c.setFillColor(GRIS)
    c.setFont("Helvetica", 8)
    c.drawString(MARGE, MARGE, f"Édité le {timezone.localtime().strftime('%d/%m/%Y à %H:%M')} — document généré à la demande, non stocké.")

    c.showPage()
    c.save()
    return tampon.getvalue()
