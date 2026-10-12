"""Vrais PDF des rapports (audit M1-77, TECH-82 ; avenant-export-pdf.md)."""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import URLPattern, URLResolver, get_resolver, reverse

from apps.accounts.tests.factories import UserFactory
from apps.billing.tests.helpers import emise
from apps.core import pdf
from apps.core.formats import nombre
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


# --- rapports comptables et trésorerie : PDF construit sur les feuilles de l'export Excel ---

RAPPORTS = [
    ("accounting:balance_xlsx", "accounting:balance_imprimer", {}),
    ("accounting:bilan_xlsx", "accounting:bilan_imprimer", {}),
    ("accounting:compte_resultat_xlsx", "accounting:compte_resultat_imprimer", {}),
    ("accounting:declaration_tva_xlsx", "accounting:declaration_tva_imprimer", {}),
    ("accounting:grand_livre_xlsx", "accounting:grand_livre_imprimer", {"compte": "411000"}),
    ("finance:xlsx", "finance:imprimer", {}),
]


@pytest.mark.parametrize(("export", "impression", "parametres"), RAPPORTS)
def test_chaque_rapport_se_telecharge_en_pdf_et_reste_disponible_en_excel(client, export, impression, parametres):
    emise(prix="1000000")  # une facture émise : écritures, exercice, trésorerie
    client.force_login(UserFactory(is_superuser=True))

    en_pdf = client.get(reverse(export), {**parametres, "format": "pdf"})
    en_excel = client.get(reverse(export), parametres)
    page = client.get(reverse(impression), parametres).content.decode()

    assert en_pdf.status_code == 200 and en_pdf["Content-Type"] == "application/pdf"
    assert en_pdf.content.startswith(b"%PDF")
    assert en_excel["Content-Type"].startswith("application/vnd.openxmlformats")
    assert "Télécharger en PDF" in page and reverse(export) in page


def test_le_grand_livre_sans_compte_ne_propose_pas_de_pdf(client):
    client.force_login(UserFactory(is_superuser=True))

    page = client.get(reverse("accounting:grand_livre_imprimer")).content.decode()

    assert "Télécharger en PDF" not in page


def test_les_feuilles_sont_converties_avec_des_montants_lisibles():
    feuille = {
        "titre": "Balance", "entetes": ["Compte", "Date", "Montant"],
        "lignes": [["411000", date(2026, 10, 12), Decimal("1500000")], ["571000", None, Decimal("12.50")]],
        "pied": ["", "Total", Decimal("1500012.50")],
    }

    (tableau,) = pdf.blocs_depuis_feuilles([feuille])

    assert tableau.lignes[0] == ["411000", "12/10/2026", nombre(1500000)]
    assert tableau.lignes[1][1] == "" and tableau.lignes[1][2] == nombre(Decimal("12.50"), 2)
    assert tableau.alignes_a_droite == {2} and tableau.total[2] == nombre(Decimal("1500012.50"), 2)


def test_plusieurs_feuilles_deviennent_des_sections():
    feuilles = [
        {"titre": "Actif", "entetes": ["Compte"], "lignes": []},
        {"titre": "Passif", "entetes": ["Compte"], "lignes": [["101000"]]},
    ]

    blocs = pdf.blocs_depuis_feuilles(feuilles)

    assert [b.titre for b in blocs if isinstance(b, pdf.Section)] == ["Actif", "Passif"]
    assert any(isinstance(b, pdf.Texte) and b.texte == "Aucune ligne." for b in blocs)
