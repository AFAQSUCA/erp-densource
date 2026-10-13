"""PDF préparés en tâche de fond par Celery (cahier-des-charges.md:294 ; décision du 13/10/2026, audit TECH-70)."""

import json
import os
from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.core import documents_pdf, pdf
from apps.core.models import DocumentPdf, StatutDocumentPdf
from apps.hr.tests.factories import PersonnelFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def en_tache_de_fond(settings, tmp_path):
    settings.PDF_EN_TACHE_DE_FOND = True
    settings.MEDIA_ROOT = tmp_path
    return settings


@pytest.fixture
def admin(client):
    utilisateur = UserFactory(is_superuser=True)
    client.force_login(utilisateur)
    return utilisateur


def _demander(client, capture, **parametres):
    """Clic sur « Télécharger en PDF » ; ``capture`` exécute la tâche confiée à Celery après la transaction."""
    with capture(execute=True):
        return client.get(reverse("hr:personnel_imprimer"), {"format": "pdf", **parametres})


def test_les_blocs_passent_par_json_sans_rien_perdre():
    blocs = [
        pdf.Section("Actif"),
        pdf.Texte("3 lignes", discret=True),
        pdf.Tableau(entetes=["Compte", "Solde"], lignes=[["411000", Decimal("1250.50")], ["521000", None]],
                    alignes_a_droite={1}, total=["Total", 1250], largeurs=[2, 1]),
        pdf.Rubriques([("Encaissé", "1 000 FCFA")]),
    ]

    relus = pdf.blocs_depuis_donnees(json.loads(json.dumps(pdf.blocs_vers_donnees(blocs))))

    assert relus[:2] == blocs[:2] and relus[3] == blocs[3]
    assert relus[2] == pdf.Tableau(entetes=["Compte", "Solde"], lignes=[["411000", "1250.50"], ["521000", None]],
                                   alignes_a_droite={1}, total=["Total", "1250"], largeurs=[2, 1])


def test_un_type_de_bloc_inconnu_est_refuse():
    with pytest.raises(KeyError):
        pdf.blocs_depuis_donnees([{"type": "Script", "texte": "x"}])


def test_sans_worker_le_pdf_est_rendu_dans_la_requete(client, admin, settings):
    settings.PDF_EN_TACHE_DE_FOND = False

    reponse = client.get(reverse("hr:personnel_imprimer"), {"format": "pdf"})

    assert reponse["Content-Type"] == "application/pdf" and not DocumentPdf.objects.exists()


def test_le_pdf_est_prepare_par_le_worker_puis_telecharge(client, admin, en_tache_de_fond, django_capture_on_commit_callbacks):
    PersonnelFactory(nom="Kone")

    reponse = _demander(client, django_capture_on_commit_callbacks, q="Kone")

    document = DocumentPdf.objects.get()
    assert reponse.status_code == 302 and reponse.url == reverse("document_pdf", args=[document.cle])
    assert document.statut == StatutDocumentPdf.PRET and document.parametres == {}  # données effacées
    assert document.url_retour == reverse("hr:personnel_imprimer") + "?q=Kone"  # sans format=pdf
    page = client.get(reponse.url).content.decode()
    assert "Votre PDF est prêt" in page and reverse("document_pdf_telecharger", args=[document.cle]) in page
    fichier = client.get(reverse("document_pdf_telecharger", args=[document.cle]))
    assert fichier["Content-Type"] == "application/pdf"
    assert fichier["Content-Disposition"].startswith('attachment; filename="personnel-20')
    assert b"".join(fichier.streaming_content).startswith(b"%PDF")


def test_la_page_se_recharge_tant_que_le_pdf_se_prepare(client, admin, en_tache_de_fond):
    with mock.patch("apps.core.tasks.generer_document_pdf.delay"):
        reponse = client.get(reverse("hr:personnel_imprimer"), {"format": "pdf"}, follow=True)

    page = reponse.content.decode()
    assert "Préparation de votre PDF" in page and 'http-equiv="refresh" content="2"' in page
    document = DocumentPdf.objects.get()
    assert client.get(reverse("document_pdf_telecharger", args=[document.cle])).status_code == 404


def test_un_worker_arrete_est_signale_au_lieu_d_attendre_sans_fin(client, admin):
    document = DocumentPdf.objects.create(demande_par=admin, titre="Personnel", nom_fichier="personnel.pdf")
    DocumentPdf.objects.filter(pk=document.pk).update(created_at=timezone.now() - timedelta(minutes=6))

    page = client.get(reverse("document_pdf", args=[document.cle])).content.decode()

    assert "semble arrêté" in page and "http-equiv" not in page


def test_un_echec_de_mise_en_page_est_annonce(client, admin, en_tache_de_fond, django_capture_on_commit_callbacks):
    with mock.patch.object(pdf, "generer_pdf", side_effect=ValueError("police absente")):
        reponse = _demander(client, django_capture_on_commit_callbacks)

    document = DocumentPdf.objects.get()
    assert document.statut == StatutDocumentPdf.ECHEC and "police absente" in document.erreur
    assert "n'a pas pu être fabriqué" in client.get(reponse.url).content.decode()


def test_seul_le_demandeur_voit_et_telecharge_son_pdf(client, admin, en_tache_de_fond, django_capture_on_commit_callbacks):
    _demander(client, django_capture_on_commit_callbacks)
    document = DocumentPdf.objects.get()

    client.force_login(UserFactory(is_superuser=True))  # même un autre administrateur

    assert client.get(reverse("document_pdf", args=[document.cle])).status_code == 404
    assert client.get(reverse("document_pdf_telecharger", args=[document.cle])).status_code == 404
    client.logout()
    assert client.get(reverse("document_pdf", args=[document.cle])).status_code == 302  # vers la connexion


def test_le_fichier_n_est_pas_servi_par_les_medias_proteges(client, admin, en_tache_de_fond, django_capture_on_commit_callbacks):
    _demander(client, django_capture_on_commit_callbacks)
    document = DocumentPdf.objects.get()

    assert client.get(reverse("media", args=[document.fichier.name])).status_code == 404


def test_derriere_nginx_le_fichier_part_par_x_accel_redirect(client, admin, en_tache_de_fond, django_capture_on_commit_callbacks):
    _demander(client, django_capture_on_commit_callbacks)
    document = DocumentPdf.objects.get()
    en_tache_de_fond.MEDIA_ACCEL_REDIRECT = True

    reponse = client.get(reverse("document_pdf_telecharger", args=[document.cle]))

    assert reponse["X-Accel-Redirect"] == f"/medias-internes/pdf-generes/{document.cle}.pdf"
    assert reponse["Cache-Control"] == "private, no-store"


def test_rejouer_la_tache_ne_refait_rien(admin, en_tache_de_fond):
    document = DocumentPdf.objects.create(
        demande_par=admin, titre="Vide", nom_fichier="vide.pdf", statut=StatutDocumentPdf.PRET,
    )

    with mock.patch.object(pdf, "generer_pdf") as generer:
        documents_pdf.preparer(document.pk)

    generer.assert_not_called()


def test_les_pdf_de_plus_d_un_jour_sont_effaces_avec_leur_fichier(client, admin, en_tache_de_fond, django_capture_on_commit_callbacks):
    _demander(client, django_capture_on_commit_callbacks)
    _demander(client, django_capture_on_commit_callbacks)
    ancien, recent = DocumentPdf.objects.order_by("pk")
    DocumentPdf.objects.filter(pk=ancien.pk).update(created_at=timezone.now() - timedelta(hours=25))
    chemin = ancien.fichier.path

    assert documents_pdf.purger() == 1

    assert list(DocumentPdf.objects.all()) == [recent]
    assert not os.path.exists(chemin)


def test_les_taches_quotidiennes_purgent_les_pdf():
    from apps.notifications.taches import executer_taches_quotidiennes

    assert executer_taches_quotidiennes()["pdf_purges"] == 0


def test_la_production_confie_les_pdf_au_worker():
    from pathlib import Path

    from django.conf import settings

    prod = (Path(settings.BASE_DIR) / "config/settings/prod.py").read_text(encoding="utf-8")
    compose = (Path(settings.BASE_DIR) / "docker-compose.yml").read_text(encoding="utf-8")
    assert 'PDF_EN_TACHE_DE_FOND = env.bool("PDF_EN_TACHE_DE_FOND", default=True)' in prod
    worker = compose.split("celery_worker:")[1].split("celery_beat:")[0]
    assert "media_data:/app/media" in worker  # sinon le worker écrirait dans un dossier que `web` ne voit pas
