class FlotteError(Exception):
    """Erreur métier sur la flotte (traduite en message par les écrans / l'API)."""


class DoublonVehicule(FlotteError):
    """Immatriculation ou n° de châssis (VIN) déjà utilisé."""


class VehiculeInvalide(FlotteError):
    """Donnée de fiche véhicule invalide (capacité, réservoir, année...)."""


class KilometrageInvalide(FlotteError):
    """Le compteur d'un camion ne peut pas reculer."""


class DocumentInvalide(FlotteError):
    """Dates d'un document réglementaire incohérentes."""
