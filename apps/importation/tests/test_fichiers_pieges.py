"""Fichiers mal formés ou valeurs extrêmes : une erreur de ligne, jamais une erreur 500 ni une ligne perdue en
silence — audit AV-13 (NaN, Infinity, nombre énorme) et AV-14 (dimension fausse)."""

import re
import zipfile
from io import BytesIO

import pytest

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.customers.models import Client
from apps.hr import services as hr_services
from apps.hr.exceptions import ImportPersonnelError
from apps.importation import services

from .helpers import CLIENT, PERSONNEL, VEHICULE, classeur

pytestmark = pytest.mark.django_db


def _importer(fichier):
    return services.importer_classeur(fichier, UserFactory(role=Role.ADMIN))


@pytest.mark.parametrize(
    "feuille, ligne, attendu",
    [
        ("personnel", [*PERSONNEL[:6], "NaN"], "Le salaire de base « NaN » invalide"),
        ("personnel", [*PERSONNEL[:6], "Infinity"], "Le salaire de base « Infinity » invalide"),
        ("personnel", [*PERSONNEL[:6], "1e30"], "Le salaire de base « 1e30 » trop grand"),
        ("vehicules", [*VEHICULE[:5], "1e20", *VEHICULE[6:]], "Le kilométrage « 1e20 » trop grand"),
        ("vehicules", [*VEHICULE[:6], "99999", *VEHICULE[7:]], "La capacité de charge « 99999 » trop grand"),
        ("vehicules", [*VEHICULE[:3], "99999", *VEHICULE[4:]], "L'année « 99999 » trop grand"),
        ("vehicules", [*VEHICULE[:7], "-inf", *VEHICULE[8:]], "Le réservoir « -inf » invalide"),
        ("clients", [*CLIENT[:6], "nan", *CLIENT[7:]], "Le taux de TVA « nan » invalide"),
        ("clients", [*CLIENT[:8], 999999], "Le délai de paiement « 999999 » trop grand"),
    ],
)
def test_une_valeur_non_finie_ou_demesuree_est_une_erreur_de_ligne(feuille, ligne, attendu):
    rapport = _importer(classeur(**{feuille: [ligne]}))

    assert not rapport.enregistre
    assert any(attendu in erreur for erreur in rapport.erreurs), rapport.erreurs


@pytest.mark.parametrize("salaire", ["NaN", "Infinity", "1e30"])
def test_l_import_rh_refuse_aussi_un_salaire_non_fini_ou_demesure(salaire):
    from openpyxl import Workbook

    wb = Workbook()
    wb.active.append(hr_services.COLONNES_IMPORT)
    wb.active.append([*PERSONNEL[:6], salaire])
    fichier = BytesIO()
    wb.save(fichier)
    fichier.seek(0)

    with pytest.raises(ImportPersonnelError) as exc:
        hr_services.importer_personnel(fichier)

    assert any("salaire de base" in erreur for erreur in exc.value.erreurs)


def _avec_dimension_fausse(fichier: BytesIO) -> BytesIO:
    """Réécrit la dimension annoncée de chaque feuille à « A1:A1 », comme certains logiciels qui exportent mal."""
    sortie = BytesIO()
    with zipfile.ZipFile(fichier) as source, zipfile.ZipFile(sortie, "w", zipfile.ZIP_DEFLATED) as cible:
        for element in source.infolist():
            contenu = source.read(element.filename)
            if element.filename.startswith("xl/worksheets/sheet"):
                contenu = re.sub(rb'<dimension ref="[^"]*"', b'<dimension ref="A1:A1"', contenu)
            cible.writestr(element, contenu)
    sortie.seek(0)
    return sortie


def test_une_dimension_fausse_ne_fait_perdre_aucune_ligne():
    autre = ["Orange CI", "CI-NCC-1111111A", *CLIENT[2:]]
    fichier = _avec_dimension_fausse(classeur(clients=[CLIENT, autre]))

    rapport = _importer(fichier)

    assert rapport.enregistre and rapport.total_crees == 2
    assert Client.objects.count() == 2


# --- fiche supprimée dans l'ERP (audit AV-15, décision du 12/10/2026) ---


def _supprimes():
    from apps.fleet.models import Vehicule
    from apps.hr.models import Personnel

    assert _importer(classeur(personnel=[PERSONNEL], clients=[CLIENT], vehicules=[VEHICULE])).enregistre
    for modele in (Personnel, Client, Vehicule):
        modele.objects.get().delete()


@pytest.mark.parametrize(
    "feuille, ligne, attendu",
    [
        ("personnel", PERSONNEL, "Diallo Fatou a été supprimé(e) de l'ERP"),
        ("clients", CLIENT, "le client au NCC / NIF « CI-NCC-9876543B » a été supprimé de l'ERP"),
        ("vehicules", VEHICULE, "le camion CI-9999-ZZ a été supprimé de l'ERP"),
    ],
)
def test_une_ligne_qui_correspond_a_une_fiche_supprimee_est_refusee(feuille, ligne, attendu):
    _supprimes()

    rapport = _importer(classeur(**{feuille: [ligne]}))

    assert not rapport.enregistre
    assert any(attendu in e and "restaurez la fiche" in e for e in rapport.erreurs), rapport.erreurs


def test_l_import_rh_refuse_aussi_un_employe_supprime():
    from openpyxl import Workbook

    from apps.hr.models import Personnel

    _supprimes()
    wb = Workbook()
    wb.active.append(hr_services.COLONNES_IMPORT)
    wb.active.append(PERSONNEL)
    fichier = BytesIO()
    wb.save(fichier)
    fichier.seek(0)

    with pytest.raises(ImportPersonnelError) as exc:
        hr_services.importer_personnel(fichier)

    assert any("a été supprimé(e) de l'ERP" in e for e in exc.value.erreurs)
    assert not Personnel.objects.exists()
