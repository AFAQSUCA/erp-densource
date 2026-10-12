"""Reprise des reclassements de mode de paiement passés **à l'envers** avant la correction de l'audit AV-04 (le
nouveau compte de trésorerie était débité et l'ancien crédité : erreur de deux fois le montant). Chacun reçoit une
contre-passation puis le bon reclassement, datés du jour ; rien n'est effacé.

Rejouable sans doublon. À lancer d'abord avec --dry-run pour voir la liste.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounting import services
from apps.accounting.exceptions import AccountingError


class Command(BaseCommand):
    help = "Corrige les reclassements de mode de paiement passés à l'envers (voir --dry-run pour prévisualiser)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Affiche ce qui serait corrigé sans rien écrire."
        )

    def handle(self, *args, dry_run=False, **options):
        corrigees = impossibles = 0
        with transaction.atomic():
            for ecriture in services.reclassements_inverses():
                try:
                    with transaction.atomic():
                        correction = services.corriger_reclassement_inverse(ecriture)
                except AccountingError as erreur:
                    impossibles += 1
                    self.stderr.write(f"{ecriture.numero} non corrigée : {erreur}")
                    continue
                corrigees += 1
                self.stdout.write(f"{ecriture.numero} ({ecriture.libelle}) -> {correction.numero}")
            if dry_run:
                transaction.set_rollback(True)

        prefixe = "[Simulation, rien n'a été écrit] " if dry_run else ""
        self.stdout.write(f"{prefixe}{corrigees} reclassement(s) corrigé(s), {impossibles} impossible(s).")
