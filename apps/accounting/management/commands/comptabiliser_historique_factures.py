"""Reprise, à la demande, des factures déjà validées avant la mise en service de la
comptabilisation automatique (``accounting.receivers``) : sans cette commande, ces factures
n'auraient jamais leur écriture, alors qu'elles ont bien généré une créance client réelle.

Volontairement **pas une migration automatique**, sur le même principe que
``finance.comptabiliser_historique_parc_auto`` : sur une base qui a déjà un solde d'ouverture
saisi en comptabilité, reprendre l'historique complet compterait deux fois les créances
antérieures à ce solde. À exécuter une fois, après avoir vérifié la date du solde d'ouverture
(s'il y en a un) :
- pas de solde d'ouverture (ou aucune facture antérieure à sa date) → lancer sans ``--depuis`` ;
- un solde d'ouverture à une date donnée → lancer avec ``--depuis`` fixé au lendemain de cette date.

Rejouable sans double compte (une écriture par facture, comme le mécanisme normal) : relancer la
commande après un ``--depuis`` mal choisi, corrigé, ne recrée pas ce qui a déjà été comptabilisé.
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounting import services
from apps.accounting.models import EcritureComptable
from apps.billing.models import STATUTS_EMIS, Facture


class Command(BaseCommand):
    help = (
        "Comptabilise les factures déjà validées avant ce lot (voir --dry-run pour prévisualiser, "
        "--depuis pour ignorer ce qui précède un solde d'ouverture)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--depuis", metavar="AAAA-MM-JJ",
            help="Ne reprend que les factures émises à partir de cette date (bornes incluses).",
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

        factures = Facture.objects.filter(statut__in=STATUTS_EMIS)
        if date_depuis is not None:
            factures = factures.filter(date_emission__gte=date_depuis)

        deja = set(
            EcritureComptable.objects.filter(
                origine="FACTURE", origine_id__in=factures.values_list("pk", flat=True)
            ).values_list("origine_id", flat=True)
        )
        comptabilisees = 0
        deja_presentes = 0
        with transaction.atomic():
            for facture in factures:
                services.comptabiliser_facture_validee(facture)
                if facture.pk in deja:
                    deja_presentes += 1
                else:
                    comptabilisees += 1
            if dry_run:
                transaction.set_rollback(True)

        prefixe = "[Simulation, rien n'a été écrit] " if dry_run else ""
        self.stdout.write(
            f"{prefixe}{comptabilisees} facture(s) comptabilisée(s) "
            f"({deja_presentes} déjà présentes, inchangées)."
        )
