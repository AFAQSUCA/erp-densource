"""Vrais PDF des rapports (audit M1-77, TECH-82 ; avenant-export-pdf.md)."""

import pytest
from django.urls import URLPattern, URLResolver, get_resolver, reverse

from apps.accounts.tests.factories import UserFactory
from apps.core import pdf
from apps.core.views import ImpressionListeMixin
from apps.hr.tests.factories import PersonnelFactory

pytestmark = pytest.mark.django_db

ENTREPRISE = {"nom": "DEN Source Group", "adresse": "Abidjan, Plateau", "ncc": "CI-123"}


def _vues_d_impression(motifs=None, prefixe=""):
    """Toutes les URL sans paramètre dont la vue est une liste imprimable (``ImpressionListeMixin``)."""
    trouvees = []
    for motif in motifs if motifs is not None else get_resolver().url_patterns:
        if isinstance(motif, URLResolver):
            espace = f"{prefixe}{motif.namespace}:" if motif.namespace else prefixe
            trouvees += _vues_d_impression(motif.url_patterns, espace)
        elif isinstance(motif, URLPattern) and motif.name and not motif.pattern.converters:
            classe = getattr(motif.callback, "view_class", None)
            if classe is not None and issubclass(classe, ImpressionListeMixin):
                trouvees.append(f"{prefixe}{motif.name}")
    return trouvees


VUES = _vues_d_impression()


def test_les_listes_imprimables_sont_trouvees():
    assert len(VUES) >= 10 and "hr:personnel_imprimer" in VUES and "audit:imprimer" in VUES


@pytest.mark.parametrize("nom", VUES)
def test_chaque_liste_imprimable_se_telecharge_en_pdf(client, nom):
    client.force_login(UserFactory(is_superuser=True))  # agit en ADMIN : voit toutes les listes

    reponse = client.get(reverse(nom), {"format": "pdf"})

    assert reponse.status_code == 200, nom
    assert reponse["Content-Type"] == "application/pdf"
    assert reponse["Content-Disposition"].startswith('attachment; filename="')
    assert reponse.content.startswith(b"%PDF")


def test_la_page_d_impression_propose_le_pdf_avec_les_memes_filtres(client):
    client.force_login(UserFactory(is_superuser=True))

    page = client.get(reverse("hr:personnel_imprimer"), {"q": "Kone", "presence": "tous"}).content.decode()

    assert "Télécharger en PDF" in page
    assert "q=Kone" in page and "presence=tous" in page and "format=pdf" in page


def test_le_pdf_reprend_les_filtres_de_la_liste(client):
    client.force_login(UserFactory(is_superuser=True))
    PersonnelFactory(nom="Kone")
    PersonnelFactory(nom="Traore")

    avec_filtre = client.get(reverse("hr:personnel_imprimer"), {"q": "Kone", "format": "pdf"}).content
    sans_filtre = client.get(reverse("hr:personnel_imprimer"), {"format": "pdf"}).content

    assert len(avec_filtre) < len(sans_filtre)


def test_le_nom_du_fichier_reprend_le_titre_et_la_date(client):
    client.force_login(UserFactory(is_superuser=True))

    reponse = client.get(reverse("hr:personnel_imprimer"), {"format": "pdf"})

    assert reponse["Content-Disposition"].startswith('attachment; filename="personnel-20')


def test_un_tableau_long_et_large_passe_en_paysage_sur_plusieurs_pages():
    tableau = pdf.Tableau(entetes=[f"Col {i}" for i in range(8)], lignes=[[f"v{i}"] * 8 for i in range(200)])

    contenu = pdf.generer_pdf(titre="Essai", blocs=[tableau], entreprise=ENTREPRISE, genere_par="Test")

    assert contenu.startswith(b"%PDF") and contenu.count(b"/Type /Page\n") + contenu.count(b"/Type /Page ") >= 1
    assert b"/MediaBox [ 0 0 841.8898 595.2756 ]" in contenu  # A4 paysage


def test_un_tableau_etroit_reste_en_portrait_et_les_blocs_divers_sont_acceptes():
    blocs = [
        pdf.Section("Résumé"),
        pdf.Rubriques([("Chiffre d'affaires", "1 000 000 FCFA"), ("Marge", "200 000 FCFA")]),
        pdf.Texte("Commentaire <avec> des caractères & spéciaux", discret=True),
        pdf.Tableau(entetes=["Compte", "Montant"], lignes=[["411000", "10"]], alignes_a_droite={1}, total=["Total", "10"]),
        pdf.Rubriques([]),
    ]

    contenu = pdf.generer_pdf(titre="Essai", sous_titre="Période", blocs=blocs, entreprise=ENTREPRISE, genere_par="Test")

    assert b"/MediaBox [ 0 0 595.2756 841.8898 ]" in contenu  # A4 portrait
