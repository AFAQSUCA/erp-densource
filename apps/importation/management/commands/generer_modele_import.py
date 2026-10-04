"""Écrit le classeur modèle sur disque (copie versionnée à la racine du projet : modele-donnees-entreprise-DEN-Source.xlsx)."""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.importation import modele


class Command(BaseCommand):
    help = "Génère le classeur Excel modèle de collecte des données (défaut : racine du projet)."

    def add_arguments(self, parser):
        parser.add_argument("--sortie", default=str(Path(settings.BASE_DIR) / "modele-donnees-entreprise-DEN-Source.xlsx"))

    def handle(self, *args, sortie, **options):
        Path(sortie).write_bytes(modele.construire_modele())
        self.stdout.write(f"Modèle écrit : {sortie}")
