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


class ImportPersonnelError(Exception):
    """Fichier Excel de recrutement en masse invalide : tout ou rien, aucune fiche créée.

    ``erreurs`` : un message par ligne fautive (``"Ligne 4 : …"``), pour un rapport complet en
    un seul passage plutôt qu'un aller-retour par erreur.
    """

    def __init__(self, erreurs: list[str]):
        self.erreurs = erreurs
        super().__init__(f"{len(erreurs)} ligne(s) invalide(s)")
