class MissionError(Exception):
    """Erreur métier sur une mission (traduite en 400/409 par l'API)."""


class TransitionMissionInterdite(MissionError):
    """La mission n'est pas dans le statut requis pour cette action."""


class AffectationImpossible(MissionError):
    """Camion ou chauffeur indisponible, déjà réservé, ou capacité dépassée."""


class DemarrageImpossible(MissionError):
    """Camion ou chauffeur n'est plus disponible au moment du départ."""


class CodeInvalide(MissionError):
    """Le code saisi (expéditeur ou destinataire) ne correspond pas."""


class KilometrageInvalide(MissionError):
    """Kilométrage d'arrivée incohérent avec le départ ou le compteur."""
