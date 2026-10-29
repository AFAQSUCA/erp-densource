"""Exercice 6 — Le n° de châssis dans le rapport et l'export de la flotte (formation/exercices/06-colonne-vin-flotte).

À copier dans apps/fleet/tests/ puis : python -m pytest apps/fleet/tests/test_exercice_06.py -q --no-cov
"""

import base64
import re
import zlib
from io import BytesIO

import pytest
from django.urls import reverse
from openpyxl import load_workbook

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.fleet.tests.factories import VehiculeFactory

pytestmark = pytest.mark.django_db

VIN = "WDB9634031L123456"
FLUX_PDF = re.compile(rb"stream\r?\n(.*?)\s*endstream", re.S)


@pytest.fixture
def connecte(client):
    client.force_login(UserFactory(role=Role.PARCAUTO))
    VehiculeFactory(vin=VIN)
    return client


def test_le_rapport_imprimable_montre_le_vin_apres_le_modele(connecte):
    page = connecte.get(reverse("fleet:imprimer"))

    entetes = page.context["entetes"]
    assert entetes.index("N° de châssis (VIN)") == entetes.index("Modèle") + 1
    assert VIN in page.content.decode()


def _texte_du_pdf(contenu: bytes) -> bytes:
    """Le texte d'un PDF de ReportLab est encodé deux fois (ASCII85 puis zlib) : on défait les deux pour y chercher
    une valeur."""
    texte = b""
    for flux in FLUX_PDF.findall(contenu):
        donnees = flux.strip()
        try:
            if donnees.endswith(b"~>"):
                donnees = base64.a85decode(donnees[:-2])
            texte += zlib.decompress(donnees)
        except (ValueError, zlib.error):
            texte += flux
    return texte


def test_le_pdf_du_rapport_contient_le_vin(connecte):
    reponse = connecte.get(reverse("fleet:imprimer"), {"format": "pdf"})

    assert reponse["Content-Type"] == "application/pdf"
    assert VIN.encode() in _texte_du_pdf(reponse.content)


def test_l_export_excel_a_une_colonne_vin_avec_la_valeur_brute(connecte):
    reponse = connecte.get(reverse("fleet:xlsx"))
    feuille = load_workbook(BytesIO(reponse.content)).active

    # Le classeur commence par un titre : la ligne des en-têtes est celle qui commence par « Immatriculation ».
    rang = next(ligne[0].row for ligne in feuille.iter_rows() if ligne[0].value == "Immatriculation")
    entetes = [c.value for c in feuille[rang]]
    colonne = entetes.index("N° de châssis (VIN)")
    assert entetes[colonne - 1] == "Modèle"
    assert feuille.cell(row=rang + 1, column=colonne + 1).value == VIN
