"""Reprise, à la demande, des règlements déjà enregistrés avant la mise en service de la
comptabilisation automatique des encaissements (``accounting.receivers``) — même principe que
``comptabiliser_historique_factures`` et ``finance.comptabiliser_historique_parc_auto`` : sur une
base qui a déjà un solde d'ouverture saisi en comptabilité, reprendre l'historique complet
compterait deux fois les encaissements antérieurs à ce solde.

- pas de solde d'ouverture (ou aucun règlement antérieur à sa date) → lancer sans ``--depuis`` ;
- un solde d'ouverture à une date donnée → lancer avec ``--depuis`` fixé au lendemain de cette date.

Rejouable sans double compte (une écriture par règlement, comme le mécanisme normal).
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounting import services
from apps.accounting.models import EcritureComptable
from apps.billing.models import Reglement


class Command(BaseCommand):
    help = (
        "Comptabilise les règlements déjà enregistrés avant ce lot (voir --dry-run pour "
        "prévisualiser, --depuis pour ignorer ce qui précède un solde d'ouverture)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--depuis", metavar="AAAA-MM-JJ",
            help="Ne reprend que les règlements enregistrés à partir de cette date (bornes incluses).",
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

        reglements = Reglement.objects.select_related("facture", "facture__client")
        if date_depuis is not None:
            reglements = reglements.filter(date_reglement__gte=date_depuis)

        deja = set(
            EcritureComptable.objects.filter(
                origine="REGLEMENT", origine_id__in=reglements.values_list("pk", flat=True)
            ).values_list("origine_id", flat=True)
        )
        comptabilises = 0
        deja_presents = 0
        with transaction.atomic():
            for reglement in reglements:
                services.comptabiliser_un_reglement(reglement)
                if reglement.pk in deja:
                    deja_presents += 1
                else:
                    comptabilises += 1
            if dry_run:
                transaction.set_rollback(True)

        prefixe = "[Simulation, rien n'a été écrit] " if dry_run else ""
        self.stdout.write(
            f"{prefixe}{comptabilises} règlement(s) comptabilisé(s) "
            f"({deja_presents} déjà présents, inchangés)."
        )
