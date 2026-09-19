class GarageError(Exception):
    """Erreur métier sur un ordre de réparation."""


class TransitionOrInterdite(GarageError):
    """L'OR n'est pas dans le statut requis (ex. déjà clôturé)."""


class CoutInvalide(GarageError):
    """Coût de main-d'œuvre négatif."""
