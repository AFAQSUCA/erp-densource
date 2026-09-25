"""Infrastructure commune aux rapports imprimables : en-tête et mixin de liste."""

from datetime import datetime
from datetime import timezone as dt_timezone

import pytest
from django.template import Context, Template

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.core.rapports import contexte_entreprise, contexte_rapport
from apps.core.views import ImpressionListeMixin

pytestmark = pytest.mark.django_db


class _Requete:
    def __init__(self, user):
        self.user = user


def test_contexte_entreprise_reprend_les_reglages(settings):
    settings.ENTREPRISE_NOM = "DEN Source Group"
    settings.ENTREPRISE_ADRESSE = "Abidjan"
    settings.ENTREPRISE_NCC = "CI-123"

    assert contexte_entreprise() == {"nom": "DEN Source Group", "adresse": "Abidjan", "ncc": "CI-123"}


def test_contexte_rapport_identifie_qui_l_a_genere():
    utilisateur = UserFactory(role=Role.ADMIN, first_name="Awa", last_name="Koné")

    contexte = contexte_rapport(_Requete(utilisateur), titre="Missions", sous_titre="6 lignes")

    assert contexte["titre"] == "Missions" and contexte["sous_titre"] == "6 lignes"
    assert contexte["genere_par"] == "Awa Koné"
    assert (datetime.now(dt_timezone.utc) - contexte["genere_le"]).total_seconds() < 5


def test_sans_nom_le_genere_par_retombe_sur_l_identifiant():
    utilisateur = UserFactory(role=Role.ADMIN, first_name="", last_name="", username="demo_admin")

    contexte = contexte_rapport(_Requete(utilisateur), titre="x")

    assert contexte["genere_par"] == "demo_admin"


# --- ImpressionListeMixin._valeur ---


class _Sous:
    def __init__(self, nom):
        self.nom = nom


class _Objet:
    def __init__(self, libelle, sous=None):
        self.libelle = libelle
        self.sous = sous

    def get_libelle_display(self):
        return f"« {self.libelle} »"


def test_valeur_resout_un_attribut_simple():
    assert ImpressionListeMixin._valeur(_Objet("Abidjan"), "libelle") == "Abidjan"


def test_valeur_resout_une_methode_get_display():
    assert ImpressionListeMixin._valeur(_Objet("Abidjan"), "get_libelle_display") == "« Abidjan »"


def test_valeur_resout_un_chemin_en_pointilles():
    assert ImpressionListeMixin._valeur(_Objet("x", sous=_Sous("Bolloré")), "sous.nom") == "Bolloré"


def test_valeur_vide_ou_chemin_casse_donne_un_tiret():
    assert ImpressionListeMixin._valeur(_Objet(""), "libelle") == "—"
    assert ImpressionListeMixin._valeur(_Objet("x", sous=None), "sous.nom") == "—"
    assert ImpressionListeMixin._valeur(_Objet("x"), "inconnu") == "—"


def test_valeur_accepte_un_callable_pour_une_colonne_composee():
    colonne = lambda o: f"{o.libelle}!"  # noqa: E731

    assert ImpressionListeMixin._valeur(_Objet("Abidjan"), colonne) == "Abidjan!"


def test_le_rendu_echappe_les_libelles():
    html = Template(
        '{% include "rapports/liste_impression.html" %}'
    ).render(
        Context(
            {
                "entreprise": {"nom": "DEN"}, "titre": "T", "sous_titre": "",
                "genere_par": "x", "genere_le": datetime.now(dt_timezone.utc),
                "entetes": ["Client"], "lignes": [["<script>alert(1)</script>"]],
                "nombre": 1, "tronque": False,
            }
        )
    )

    assert "<script>" not in html and "&lt;script&gt;" in html
