"""Formatage des nombres pour l'affichage, selon la langue active (français : « 1 500,5 »).

À utiliser pour tout nombre écrit dans un message : ``f"{valeur}"`` afficherait un
point décimal (« 1500.50 ») alors que les templates affichent une virgule.

Le formatage de Django (``number_format``) **tronque** les décimales au lieu de les
arrondir (66,67 devient « 66,6 ») : on arrondit donc d'abord, demi supérieur, comme
le filtre de template ``floatformat``.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.utils.formats import number_format


def _arrondi(valeur, decimales: int) -> Decimal:
    return Decimal(str(valeur)).quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)


def nombre(valeur, decimales: int = 0) -> str:
    """Nombre arrondi, avec séparateur de milliers et décimale de la langue active."""
    return number_format(
        _arrondi(valeur, decimales), decimal_pos=decimales, use_l10n=True, force_grouping=True
    )


def pourcentage_signe(valeur, decimales: int = 1) -> str:
    """Pourcentage signé et arrondi : ``+23,3`` / ``-10,0`` / ``0,0`` (sans le symbole %)."""
    arrondi = _arrondi(valeur, decimales)
    signe = "+" if arrondi > 0 else "-" if arrondi < 0 else ""
    return signe + number_format(abs(arrondi), decimal_pos=decimales, use_l10n=True)
