"""Recherche texte insensible aux accents et à la casse, et pagination tolérante."""

import pytest
from django.db import connection
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.core.search import Normalise, filtrer_par_texte, normaliser
from apps.hr.models import Personnel
from apps.hr.tests.factories import PersonnelFactory

pytestmark = pytest.mark.django_db


def _noms(queryset):
    return sorted(p.nom for p in queryset)


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [
        ("Traoré", "traore"),
        ("TRAORÉ", "traore"),
        ("Côte d'Ivoire", "cote d'ivoire"),
        ("Ñandú Çà", "nandu ca"),
        ("", ""),
        (None, ""),
    ],
)
def test_normaliser(texte, attendu):
    assert normaliser(texte) == attendu


# --- filtrer_par_texte ---


@pytest.fixture
def equipe():
    PersonnelFactory(nom="Traoré", prenom="Moussa", matricule="M-001", poste="Chauffeur")
    PersonnelFactory(nom="Traore", prenom="Ali", matricule="M-002", poste="Comptable")
    PersonnelFactory(nom="Koné", prenom="Awa", matricule="M-003", poste="Directrice")
    PersonnelFactory(nom="Diallo", prenom="Émile", matricule="M-004", poste="100% fiable_")


@pytest.mark.parametrize("recherche", ["traoré", "TRAORÉ", "traore", "TRAORE", "Traoré", "  traore  "])
def test_les_accents_et_la_casse_ne_changent_pas_le_resultat(equipe, recherche):
    resultat = filtrer_par_texte(Personnel.objects.all(), recherche, "nom")

    assert _noms(resultat) == ["Traore", "Traoré"]


@pytest.mark.parametrize("recherche", ["kone", "KONÉ", "koné"])
def test_un_nom_accentue_se_trouve_sans_ses_accents(equipe, recherche):
    assert _noms(filtrer_par_texte(Personnel.objects.all(), recherche, "nom")) == ["Koné"]


def test_un_prenom_en_majuscule_accentuee_se_trouve(equipe):
    assert _noms(filtrer_par_texte(Personnel.objects.all(), "emile", "prenom")) == ["Diallo"]
    assert _noms(filtrer_par_texte(Personnel.objects.all(), "ÉMILE", "prenom")) == ["Diallo"]


def test_chaque_mot_doit_se_trouver_dans_un_des_champs(equipe):
    personnel = Personnel.objects.all()

    assert _noms(filtrer_par_texte(personnel, "moussa traore", "nom", "prenom")) == ["Traoré"]
    assert _noms(filtrer_par_texte(personnel, "traore moussa", "nom", "prenom")) == ["Traoré"]
    assert _noms(filtrer_par_texte(personnel, "moussa kone", "nom", "prenom")) == []
    assert _noms(filtrer_par_texte(personnel, "m-003 awa", "matricule", "prenom")) == ["Koné"]


def test_les_pourcentages_et_soulignes_saisis_sont_du_texte(equipe):
    personnel = Personnel.objects.all()

    assert _noms(filtrer_par_texte(personnel, "100%", "poste")) == ["Diallo"]
    assert _noms(filtrer_par_texte(personnel, "%", "nom")) == []
    assert _noms(filtrer_par_texte(personnel, "_", "nom")) == []
    assert _noms(filtrer_par_texte(personnel, "fiable_", "poste")) == ["Diallo"]


def test_une_recherche_vide_ou_d_espaces_ne_filtre_rien(equipe):
    assert filtrer_par_texte(Personnel.objects.all(), "", "nom").count() == 4
    assert filtrer_par_texte(Personnel.objects.all(), "   ", "nom").count() == 4


def test_la_recherche_traverse_les_relations(equipe):
    chef = Personnel.objects.get(nom="Koné")
    employe = Personnel.objects.get(nom="Diallo")
    employe.superieur = chef
    employe.save()

    resultat = filtrer_par_texte(Personnel.objects.all(), "KONE", "superieur__nom")

    assert _noms(resultat) == ["Diallo"]


def test_une_recherche_sans_resultat(equipe):
    assert _noms(filtrer_par_texte(Personnel.objects.all(), "zzz", "nom", "prenom")) == []


def test_la_requete_hors_sqlite_utilise_lower_et_translate():
    """Branche PostgreSQL (non exécutée ici faute de serveur) : SQL sans extension."""
    requete = Personnel.objects.annotate(n=Normalise("nom")).query
    compilateur = requete.get_compiler(using="default")

    sql, parametres = Normalise.as_sql(requete.annotations["n"], compilateur, connection)

    assert "LOWER(" in sql and "TRANSLATE(" in sql
    assert parametres[0].startswith("àâä") and len(parametres[0]) == len(parametres[1])


# --- pagination tolérante ---

LISTES = [
    "missions:liste",
    "fleet:liste",
    "drivers:liste",
    "garage:liste",
    "fuel:liste",
    "inventory:articles",
    "inventory:mouvements",
    "customers:liste",
    "hr:personnel_liste",
    "hr:conges_liste",
]


@pytest.mark.parametrize("nom_url", LISTES)
@pytest.mark.parametrize("page", ["abc", "0", "-3", "999", "last", "", "1.5"])
def test_un_numero_de_page_inutilisable_ne_donne_jamais_404(client, nom_url, page):
    client.force_login(UserFactory(role=Role.ADMIN))

    reponse = client.get(reverse(nom_url), {"page": page})

    assert reponse.status_code == 200


@pytest.fixture
def trois_pages():
    for i in range(45):
        PersonnelFactory(nom=f"Nom{i:02d}", matricule=f"P-{i:03d}")


def _matricules(reponse):
    return [p.matricule for p in reponse.context["personnel"]]


def test_une_page_trop_grande_affiche_la_derniere(client, trois_pages):
    client.force_login(UserFactory(role=Role.ADMIN))

    reponse = client.get(reverse("hr:personnel_liste"), {"page": 999})

    assert reponse.context["page_obj"].number == 3
    assert len(_matricules(reponse)) == 5


def test_une_page_invalide_ou_negative_affiche_la_premiere(client, trois_pages):
    client.force_login(UserFactory(role=Role.ADMIN))

    for page in ("abc", "0", "-2"):
        reponse = client.get(reverse("hr:personnel_liste"), {"page": page})
        assert reponse.context["page_obj"].number == 1, page


def test_last_affiche_la_derniere_page_et_les_pages_normales_restent_correctes(client, trois_pages):
    client.force_login(UserFactory(role=Role.ADMIN))

    derniere = client.get(reverse("hr:personnel_liste"), {"page": "last"})
    deuxieme = client.get(reverse("hr:personnel_liste"), {"page": 2})

    assert derniere.context["page_obj"].number == 3
    assert deuxieme.context["page_obj"].number == 2
    assert len(_matricules(deuxieme)) == 20


def test_les_liens_de_pagination_conservent_les_filtres(client, trois_pages):
    client.force_login(UserFactory(role=Role.ADMIN))

    texte = client.get(reverse("hr:personnel_liste"), {"q": "nom", "page": 2}).content.decode()

    assert "q=nom" in texte and "page=3" in texte


def test_la_recherche_du_personnel_ignore_accents_et_casse_dans_l_ecran(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    PersonnelFactory(nom="Traoré", prenom="Moussa")
    PersonnelFactory(nom="Bamba", prenom="Issa")

    for recherche in ("traore", "TRAORÉ", "moussa traore"):
        reponse = client.get(reverse("hr:personnel_liste"), {"q": recherche})
        assert [p.nom for p in reponse.context["personnel"]] == ["Traoré"], recherche
