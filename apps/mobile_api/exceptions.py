class MobileError(Exception):
    """Erreur propre à l'espace chauffeur (camion introuvable, saisie hors périmètre...)."""


class MissionIntrouvable(MobileError):
    """La mission n'existe pas ou n'est pas affectée à ce chauffeur (jamais de fuite : 404)."""


class AucunCamion(MobileError):
    """Le chauffeur n'a aucun camion : pas de mission active, pas de camion habituel."""
