"""Reprise, à la demande, des dépenses automatiques déjà enregistrées avant la mise en service de
la comptabilisation automatique (``accounting.receivers``) — même principe que
``comptabiliser_historique_factures``/``comptabiliser_historique_reglements``. Ne reprend que les
dépenses créées automatiquement (``Depense.est_automatique``, catégories CARBURANT, PIECES,
MAINTENANCE, FRAIS_MISSION) : la saisie manuelle (péages, entretien, frais administratifs, autre)
arrive avec la Phase 4.

- pas de solde d'ouverture (ou aucune dépense antérieure à sa date) → lancer sans ``--depuis`` ;
- un solde d'ouverture à une date donnée → lancer avec ``--depuis`` fixé au lendemain de cette date.

Rejouable sans double compte (une écriture par dépense, comme le mécanisme normal).
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounting import services
from apps.accounting.models import EcritureComptable
from apps.billing.models import Depense


class Command(BaseCommand):
    help = (
        "Comptabilise les dépenses automatiques déjà enregistrées avant ce lot (voir --dry-run "
        "pour prévisualiser, --depuis pour ignorer ce qui précède un solde d'ouverture)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--depuis", metavar="AAAA-MM-JJ",
            help="Ne reprend que les dépenses enregistrées à partir de cette date (bornes incluses).",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Affiche ce qui serait comptabilisé sans rien écrire.",
        )

    def handle(self, *args, depuis=None, dry_run=False, **options):
        date_depuis = None
        if depuis:
            try:
                date_depuis = date.fromisoformat(depuis)
            except ValueError:
                raise CommandError(f"Date invalide pour --depuis : {depuis!r} (attendu AAAA-MM-JJ).")

        depenses = Depense.objects.exclude(origine="")
        if date_depuis is not None:
            depenses = depenses.filter(date_depense__gte=date_depuis)

        deja = set(
            EcritureComptable.objects.filter(
                origine="DEPENSE", origine_id__in=depenses.values_list("pk", flat=True)
            ).values_list("origine_id", flat=True)
        )
        comptabilisees = 0
        deja_presentes = 0
        with transaction.atomic():
            for depense in depenses:
                services.comptabiliser_une_depense_automatique(depense)
                if depense.pk in deja:
                    deja_presentes += 1
                else:
                    comptabilisees += 1
            if dry_run:
                transaction.set_rollback(True)

        prefixe = "[Simulation, rien n'a été écrit] " if dry_run else ""
        self.stdout.write(
            f"{prefixe}{comptabilisees} dépense(s) comptabilisée(s) "
            f"({deja_presentes} déjà présentes, inchangées)."
        )
