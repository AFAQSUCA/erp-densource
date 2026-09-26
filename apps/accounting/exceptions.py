class AccountingError(Exception):
    """Erreur métier de la comptabilité."""


class EcritureNonEquilibree(AccountingError):
    """Le total des débits ne correspond pas au total des crédits."""


class CompteInconnu(AccountingError):
    """Le compte demandé n'existe pas dans le plan comptable, ou n'est plus actif."""


class EcritureVerrouillee(AccountingError):
    """Une écriture déjà validée ne se modifie ni ne se supprime."""
