class ChauffeurError(Exception):
    """Erreur métier sur un chauffeur (traduite en message par les écrans / l'API)."""


class CategorieInvalide(ChauffeurError):
    """Catégorie de permis hors C et E."""


class StatutNonModifiable(ChauffeurError):
    """Statut interdit à la main, ou chauffeur en mission ou en congé."""
