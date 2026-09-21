from . import mfa
from .navigation import entrees_pour


def menu(request):
    """Ajoute ``menu`` (entrées visibles pour le rôle) au contexte des templates."""
    utilisateur = request.user
    if not utilisateur.is_authenticated:
        return {}
    return {
        "menu": entrees_pour(utilisateur.role_effectif, request.path),
        "mfa_requise": mfa.mfa_requise(utilisateur),
    }
