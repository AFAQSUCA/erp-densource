"""Reprise, à la demande, des exercices **déjà clôturés avant** l'écriture de clôture : leur résultat n'a jamais
été viré au compte 120000, et le bilan de l'exercice suivant ne le retrouve pas. Chaque exercice clôturé sans
écriture de clôture reçoit la sienne, datée de son dernier jour (le seul cas où l'on écrit dans un exercice
clôturé, pour la clôture elle-même).

Rejouable sans doublon (une écriture de clôture par exercice).
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounting import services
from apps.accounting.exceptions import AccountingError
from apps.accounting.models import EcritureComptable, ExerciceComptable, StatutExercice


class Command(BaseCommand):
    help = "Pose l'écriture de clôture des exercices déjà clôturés (voir --dry-run pour prévisualiser)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Affiche ce qui serait écrit sans rien écrire."
        )

    def handle(self, *args, dry_run=False, **options):
        faites = deja = sans_resultat = impossibles = 0
        with transaction.atomic():
            for exercice in ExerciceComptable.objects.filter(statut=StatutExercice.CLOTURE).order_by("annee"):
                if EcritureComptable.objects.filter(
                    origine=services.ORIGINE_CLOTURE, origine_id=exercice.pk
                ).exists():
                    deja += 1
                    continue
                try:
                    with transaction.atomic():
                        ecriture = services.ecriture_de_cloture(exercice)
                except AccountingError as erreur:
                    impossibles += 1
                    self.stderr.write(f"Exercice {exercice.annee} sans écriture de clôture : {erreur}")
                    continue
                if ecriture is None:
                    sans_resultat += 1
                else:
                    faites += 1
            if dry_run:
                transaction.set_rollback(True)

        prefixe = "[Simulation, rien n'a été écrit] " if dry_run else ""
        self.stdout.write(
            f"{prefixe}{faites} écriture(s) de clôture posée(s) ({deja} déjà faites, {sans_resultat} exercice(s) "
            f"sans charge ni produit, {impossibles} impossible(s))."
        )
