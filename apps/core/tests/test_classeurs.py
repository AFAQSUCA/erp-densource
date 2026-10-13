"""Archives piégées (« bombe zip ») refusées avant d'être ouvertes — audit AV-16."""

import zipfile
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.core import classeurs
from apps.core.classeurs import ClasseurSuspect, exiger_classeur_raisonnable
from apps.hr import services as hr_services
from apps.hr.exceptions import ImportPersonnelError
from apps.importation import services as import_services
from apps.importation.tests.helpers import CLIENT, classeur

pytestmark = pytest.mark.django_db


def _piege(fichier: BytesIO, *, taille: int = 2 * 1024 * 1024, elements: int = 1) -> BytesIO:
    """Ajoute au classeur des éléments qui se décompressent en ``taille`` octets de zéros (quelques ko compressés)."""
    sortie = BytesIO()
    with zipfile.ZipFile(fichier) as source, zipfile.ZipFile(sortie, "w", zipfile.ZIP_DEFLATED) as cible:
        for element in source.infolist():
            cible.writestr(element, source.read(element.filename))
        for numero in range(elements):
            cible.writestr(f"xl/media/piege{numero}.bin", b"\0" * taille)
    sortie.seek(0)
    return sortie


@pytest.fixture
def limites_basses(monkeypatch):
    monkeypatch.setattr(classeurs, "TAILLE_DECOMPRESSEE_MAX", 1024 * 1024)
    monkeypatch.setattr(classeurs, "ELEMENTS_MAX", 50)


def test_un_classeur_normal_passe_et_reste_lisible_depuis_le_debut(limites_basses):
    fichier = classeur(clients=[CLIENT])

    exiger_classeur_raisonnable(fichier)

    assert fichier.tell() == 0


def test_une_archive_qui_se_decompresse_trop_ou_compte_trop_d_elements_est_refusee(limites_basses):
    with pytest.raises(ClasseurSuspect, match="trop volumineux une fois décompressé"):
        exiger_classeur_raisonnable(_piege(classeur(clients=[CLIENT])))
    with pytest.raises(ClasseurSuspect, match="trop d'éléments"):
        exiger_classeur_raisonnable(_piege(classeur(clients=[CLIENT]), taille=10, elements=60))


def test_un_fichier_qui_n_est_pas_une_archive_est_laisse_au_lecteur_excel():
    exiger_classeur_raisonnable(BytesIO(b"pas une archive"))  # openpyxl le refusera avec son propre message


def test_les_deux_imports_refusent_l_archive_piegee(limites_basses):
    with pytest.raises(import_services.ImportInvalide, match="trop volumineux"):
        import_services.importer_classeur(_piege(classeur(clients=[CLIENT])), UserFactory(role=Role.ADMIN))
    with pytest.raises(ImportPersonnelError) as exc:
        hr_services.importer_personnel(_piege(classeur(clients=[CLIENT])))
    assert "trop volumineux" in exc.value.erreurs[0]


def test_l_import_rh_refuse_un_fichier_de_plus_de_5_mo(client):
    client.force_login(UserFactory(role=Role.RH))
    lourd = SimpleUploadedFile("personnel.xlsx", b"0" * (5 * 1024 * 1024 + 1))

    reponse = client.post(reverse("hr:personnel_importer"), {"fichier": lourd})

    assert reponse.status_code == 200 and "dépasse 5 Mo" in reponse.content.decode()
