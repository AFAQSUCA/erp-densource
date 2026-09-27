class AccountingError(Exception):
    """Erreur métier de la comptabilité."""


class EcritureNonEquilibree(AccountingError):
    """Le total des débits ne correspond pas au total des crédits."""


class CompteInconnu(AccountingError):
    """Le compte demandé n'existe pas dans le plan comptable, ou n'est plus actif."""


class EcritureVerrouillee(AccountingError):
    """Une écriture déjà validée ne se modifie ni ne se supprime."""


class ActionComptableNonAutorisee(AccountingError):
    """L'utilisateur n'a pas le droit d'effectuer cette action."""


class ExerciceCloture(AccountingError):
    """L'exercice comptable concerné est déjà clôturé : aucune écriture ne peut plus y être
    datée, ni y être clôturé une seconde fois."""


class ClotureImpossible(AccountingError):
    """Des brouillons non résolus (saisie manuelle) empêchent de clôturer l'exercice."""
