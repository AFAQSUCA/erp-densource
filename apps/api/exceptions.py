"""Traduction des erreurs métier en réponses HTTP claires.

Les services lèvent des exceptions métier (``MissionError``, ``CarburantError``...). L'API les
transforme en JSON ``{"code": ..., "detail": ...}`` :

- 403 : l'utilisateur n'a pas le droit (``ChauffeurNonAutorise``, ``ActionFactureNonAutorisee``...) ;
- 409 : ``SaisieSuspecte`` (plein à confirmer), avec les chiffres à afficher ;
- 404 : mission introuvable ou d'un autre chauffeur (on ne révèle pas son existence) ;
- 400 : toute autre règle métier refusée (statut incompatible, code faux, solde insuffisant...).

Le ``code`` est le nom de la classe en minuscules avec soulignés (``code_invalide``) : un client
mobile peut s'en servir pour réagir sans lire le message.
"""

import re

from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as gestionnaire_drf

from apps.billing.exceptions import ActionFactureNonAutorisee, BillingError
from apps.customers.exceptions import ClientError
from apps.drivers.exceptions import ChauffeurError
from apps.fleet.exceptions import FlotteError
from apps.fuel.exceptions import CarburantError, SaisieSuspecte
from apps.garage.exceptions import ChauffeurNonAutorise, GarageError
from apps.hr.exceptions import ActionNonAutorisee, CongeError, PersonnelError
from apps.inventory.exceptions import StockError
from apps.missions.exceptions import ActionFraisNonAutorisee, MissionError
from apps.mobile_api.exceptions import MissionIntrouvable, MobileError

ERREURS_METIER = (
    BillingError, ClientError, ChauffeurError, FlotteError, CarburantError, GarageError,
    CongeError, PersonnelError, StockError, MissionError, MobileError,
)
ERREURS_DE_DROIT = (
    ChauffeurNonAutorise, ActionFactureNonAutorisee, ActionNonAutorisee, ActionFraisNonAutorisee,
)


CODES_MFA = frozenset({"mfa_requise", "mfa_non_activee", "mfa_invalide"})


def _code(exc: Exception) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", type(exc).__name__).lower()


def gestionnaire_erreurs(exc, context):
    if isinstance(exc, SaisieSuspecte):
        return Response(
            {
                "code": _code(exc),
                "detail": str(exc),
                "consommation": str(exc.consommation),
                "moyenne": str(exc.moyenne),
                "ecart_pct": str(exc.ecart_pct),
                "confirmer": "Renvoyez la même demande avec confirmer=true si les valeurs sont exactes.",
            },
            status=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, MissionIntrouvable):
        return Response({"code": _code(exc), "detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
    if isinstance(exc, ERREURS_DE_DROIT):
        return Response({"code": _code(exc), "detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
    if isinstance(exc, ERREURS_METIER):
        return Response({"code": _code(exc), "detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    reponse = gestionnaire_drf(exc, context)
    # Erreurs de double authentification : le code lisible par une machine accompagne le message.
    if isinstance(exc, exceptions.AuthenticationFailed) and reponse is not None:
        code = getattr(exc.detail, "code", "")
        if code in CODES_MFA:
            reponse.data["code"] = code
    return reponse
