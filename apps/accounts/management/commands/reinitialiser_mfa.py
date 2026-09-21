from django.core.management.base import BaseCommand, CommandError

from apps.accounts import mfa
from apps.accounts.models import User
from apps.accounts.signals import mfa_evenement


class Command(BaseCommand):
    help = (
        "Réinitialise la double authentification d'un compte (téléphone perdu, plus de codes de "
        "secours). À utiliser quand plus aucun administrateur ne peut le faire depuis l'interface."
    )

    def add_arguments(self, parser):
        parser.add_argument("identifiant", help="Identifiant (username) du compte")

    def handle(self, *args, identifiant, **options):
        try:
            utilisateur = User.objects.get(username=identifiant)
        except User.DoesNotExist as erreur:
            raise CommandError(f"Aucun compte « {identifiant} ».") from erreur
        mfa.reinitialiser(utilisateur)
        mfa_evenement.send(
            sender=type(self), request=None, utilisateur=utilisateur,
            evenement="reinitialisation_en_ligne_de_commande", succes=True,
        )
        self.stdout.write(self.style.SUCCESS(
            f"Double authentification réinitialisée pour {identifiant} : elle sera à réactiver à sa prochaine connexion."
        ))
