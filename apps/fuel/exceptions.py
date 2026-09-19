from decimal import Decimal


class CarburantError(Exception):
    """Erreur métier sur la saisie d'un plein."""


class SaisieInvalide(CarburantError):
    """Quantité, prix ou n° de ticket invalide."""


class TicketDejaEnregistre(CarburantError):
    """Ce n° de ticket existe déjà : probable double saisie."""


class HorsChronologie(CarburantError):
    """Plein antérieur au dernier plein enregistré du camion."""


class KilometrageInvalide(CarburantError):
    """Le km compteur doit dépasser celui du plein précédent."""


class SaisieSuspecte(CarburantError):
    """Écart > ±60 % : à vérifier puis à confirmer (cahier-des-charges.md:155).

    Rien n'est enregistré tant que la saisie n'est pas confirmée.
    """

    def __init__(self, ecart_pct: Decimal, consommation: Decimal, moyenne: Decimal):
        self.ecart_pct = ecart_pct
        self.consommation = consommation
        self.moyenne = moyenne
        super().__init__(
            f"Consommation de {consommation} L/100 km, soit {ecart_pct:+} % par rapport "
            f"à la moyenne ({moyenne} L/100 km) : vérifiez litres et kilométrage."
        )
