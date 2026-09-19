import pytest

from apps.core.models import CompteurNumero
from apps.core.services import prochain_numero

pytestmark = pytest.mark.django_db


def test_premier_numero_de_l_annee_commence_a_0001():
    assert prochain_numero("MIS", 2026) == "MIS-2026-0001"


def test_les_numeros_sont_consecutifs():
    numeros = [prochain_numero("MIS", 2026) for _ in range(3)]

    assert numeros == ["MIS-2026-0001", "MIS-2026-0002", "MIS-2026-0003"]


def test_chaque_prefixe_a_son_propre_compteur():
    prochain_numero("MIS", 2026)

    assert prochain_numero("OR", 2026) == "OR-2026-0001"
    assert prochain_numero("MIS", 2026) == "MIS-2026-0002"


def test_le_compteur_repart_de_1_chaque_annee():
    prochain_numero("FACT", 2026)
    prochain_numero("FACT", 2026)

    assert prochain_numero("FACT", 2027) == "FACT-2027-0001"


def test_annee_par_defaut_est_l_annee_courante():
    from django.utils import timezone

    numero = prochain_numero("MIS")

    assert numero == f"MIS-{timezone.localdate().year}-0001"


def test_au_dela_de_9999_le_numero_s_allonge_sans_collision():
    CompteurNumero.objects.create(prefixe="MIS", annee=2026, dernier=9999)

    assert prochain_numero("MIS", 2026) == "MIS-2026-10000"
