from decimal import Decimal

import pytest

from apps.core.formats import nombre, pourcentage_signe


@pytest.mark.parametrize(
    ("valeur", "decimales", "attendu"),
    [
        (Decimal("1500"), 0, "1 500"),
        (Decimal("1500.5"), 1, "1 500,5"),
        (Decimal("38500.00"), 0, "38 500"),
        (Decimal("30"), 1, "30,0"),
        (0, 0, "0"),
        (Decimal("100.33"), 2, "100,33"),
        (Decimal("1500.5"), 0, "1 501"),  # arrondi au demi supérieur, pas tronqué
        (Decimal("66.666"), 1, "66,7"),
        (Decimal("0.005"), 2, "0,01"),
    ],
)
def test_nombre_utilise_la_virgule_et_le_separateur_de_milliers_francais(valeur, decimales, attendu):
    assert nombre(valeur, decimales).replace("\xa0", " ").replace(" ", " ") == attendu


@pytest.mark.parametrize(
    ("valeur", "attendu"),
    [
        (Decimal("23.33"), "+23,3"),
        (Decimal("-9.99"), "-10,0"),
        (Decimal("0"), "0,0"),
        (Decimal("60.00"), "+60,0"),
        (-5, "-5,0"),
        (Decimal("66.67"), "+66,7"),  # arrondi, pas tronqué
        (Decimal("-0.04"), "0,0"),  # arrondi à zéro : pas de signe
    ],
)
def test_pourcentage_signe(valeur, attendu):
    assert pourcentage_signe(valeur) == attendu


def test_pourcentage_signe_accepte_le_nombre_de_decimales():
    assert pourcentage_signe(Decimal("66.666"), decimales=2) == "+66,67"
