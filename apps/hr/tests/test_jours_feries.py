from datetime import date
from io import StringIO

import pytest
from django.core.management import call_command

from apps.hr import services
from apps.hr.models import JourFerie

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("annee", "attendu"),
    [
        (2024, date(2024, 3, 31)),
        (2025, date(2025, 4, 20)),
        (2026, date(2026, 4, 5)),
        (2027, date(2027, 3, 28)),
    ],
)
def test_date_paques(annee, attendu):
    assert services.date_paques(annee) == attendu


def test_jours_feries_legaux_2026():
    feries = services.jours_feries_legaux(2026)

    assert len(feries) == 10
    assert feries[date(2026, 1, 1)] == "Jour de l'An"
    assert feries[date(2026, 4, 6)] == "Lundi de Pâques"
    assert feries[date(2026, 5, 1)] == "Fête du Travail"
    assert feries[date(2026, 5, 14)] == "Ascension"
    assert feries[date(2026, 5, 25)] == "Lundi de Pentecôte"
    assert feries[date(2026, 8, 7)] == "Fête de l'Indépendance"
    assert feries[date(2026, 8, 15)] == "Assomption"
    assert feries[date(2026, 11, 1)] == "Toussaint"
    assert feries[date(2026, 11, 15)] == "Journée nationale de la Paix"
    assert feries[date(2026, 12, 25)] == "Noël"


def test_initialiser_jours_feries_cree_les_10_jours_puis_est_idempotent():
    assert services.initialiser_jours_feries(2026) == 10
    assert services.initialiser_jours_feries(2026) == 0
    assert JourFerie.objects.count() == 10


def test_initialiser_ne_duplique_pas_un_jour_deja_saisi_a_la_main():
    JourFerie.objects.create(date=date(2026, 1, 1), libelle="Saisi par la RH")

    assert services.initialiser_jours_feries(2026) == 9
    assert JourFerie.objects.get(date=date(2026, 1, 1)).libelle == "Saisi par la RH"


def test_initialiser_conserve_les_fetes_musulmanes_saisies_a_la_main():
    JourFerie.objects.create(date=date(2026, 5, 27), libelle="Tabaski")

    services.initialiser_jours_feries(2026)

    assert JourFerie.objects.filter(libelle="Tabaski").exists()


def test_commande_initialiser_jours_feries():
    sortie = StringIO()

    call_command("initialiser_jours_feries", 2026, stdout=sortie)

    assert "10 jour(s) férié(s) créé(s) pour 2026" in sortie.getvalue()
    assert JourFerie.objects.count() == 10
