from django.core.management.base import BaseCommand

from apps.notifications import taches


class Command(BaseCommand):
    help = (
        "Tâches du jour : alertes de documents et d'échéances, rappels de validation de "
        "congés, statuts des congés. Sans danger si relancée : aucune alerte en double."
    )

    def handle(self, *args, **options):
        resultat = taches.executer_taches_quotidiennes()
        for nom, valeur in resultat.items():
            self.stdout.write(f"{nom.replace('_', ' '):<24} {valeur}")
