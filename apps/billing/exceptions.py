class BillingError(Exception):
    """Erreur métier de la facturation."""


class FactureNonFacturable(BillingError):
    """La mission ne peut pas (ou plus) être facturée."""


class TransitionFactureInterdite(BillingError):
    """La facture n'est pas dans un état permettant cette action."""


class ActionFactureNonAutorisee(BillingError):
    """L'utilisateur n'a pas le droit d'effectuer cette action."""


class MontantInvalide(BillingError):
    """Montant, quantité ou taux hors des valeurs permises."""


class ReglementInvalide(BillingError):
    """Règlement refusé (facture non émise, surpaiement, date incohérente)."""
