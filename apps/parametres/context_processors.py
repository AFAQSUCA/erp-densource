from django.utils.functional import SimpleLazyObject

from . import services


def parametres(request) -> dict:
    """``{{ reglages.delai_validation_n1_heures }}`` dans tout gabarit : lu en base seulement si la page s'en sert."""
    return {"reglages": SimpleLazyObject(services.parametres)}
