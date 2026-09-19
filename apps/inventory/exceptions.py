class StockError(Exception):
    """Erreur métier sur le stock."""


class QuantiteInvalide(StockError):
    """Quantité nulle ou négative, ou ajustement à zéro."""


class PrixInvalide(StockError):
    """Prix d'achat nul ou négatif."""


class StockInsuffisant(StockError):
    """La sortie demandée dépasse la quantité en stock."""


class OrCloture(StockError):
    """Sortie de pièces impossible sur un OR déjà clôturé (coût figé)."""


class MotifRequis(StockError):
    """Un ajustement d'inventaire doit être justifié."""
