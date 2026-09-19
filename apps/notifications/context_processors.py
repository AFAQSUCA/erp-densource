from . import services


def notifications(request):
    """Ajoute ``nombre_non_lues`` (cloche de l'en-tête) au contexte des templates."""
    utilisateur = request.user
    if not utilisateur.is_authenticated:
        return {}
    return {"nombre_non_lues": services.nombre_non_lues(utilisateur)}
