class GarageError(Exception):
    """Erreur métier sur un ordre de réparation."""


class TransitionOrInterdite(GarageError):
    """L'OR n'est pas dans le statut requis (ex. déjà clôturé)."""


class CoutInvalide(GarageError):
    """Coût de main-d'œuvre négatif."""


class StatutVehiculeInvalide(GarageError):
    """Immobilisation, mise hors service ou remise en service impossible."""


class ChauffeurNonAutorise(GarageError):
    """Le chauffeur ne peut pas agir sur cette mission, ou l'utilisateur n'a pas le droit."""


class ChecklistInvalide(GarageError):
    """Check-list incomplète, point inconnu, KO sans remarque, ou mission hors avant-départ."""


class ChecklistDejaRemplie(GarageError):
    """Une seule check-list par mission."""


class IncidentInvalide(GarageError):
    """Signalement ou clôture d'incident incomplet."""


class TransitionIncidentInterdite(GarageError):
    """L'incident n'est pas dans le statut requis."""
