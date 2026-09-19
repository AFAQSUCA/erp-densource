class CongeError(Exception):
    """Erreur métier du workflow de congés (traduite en 400/403/409 par l'API)."""


class SoldeInsuffisant(CongeError):
    """Blocage si solde insuffisant — cahier-des-charges.md:219."""


class TransitionInterdite(CongeError):
    """Le congé n'est pas dans un statut permettant cette action."""


class ActionNonAutorisee(CongeError):
    """L'acteur n'a pas le droit d'effectuer cette action sur ce congé."""


class PersonnelError(Exception):
    """Erreur métier sur la fiche du personnel (matricule, hiérarchie, compte)."""
