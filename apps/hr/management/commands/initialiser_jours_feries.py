from django.core.management.base import BaseCommand

from apps.hr import services


class Command(BaseCommand):
    help = "Crée les jours fériés fixes et chrétiens d'une année (fêtes musulmanes : à saisir à la main)."

    def add_arguments(self, parser):
        parser.add_argument("annee", type=int)

    def handle(self, *args, annee, **options):
        crees = services.initialiser_jours_feries(annee)
        self.stdout.write(f"{crees} jour(s) férié(s) créé(s) pour {annee}.")
