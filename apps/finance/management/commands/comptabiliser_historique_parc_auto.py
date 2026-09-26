"""Reprise, à la demande, des dépenses du parc auto déjà enregistrées avant la mise en service de leur
comptabilisation automatique (``finance.receivers``) : pleins, achats de pièces, main-d'œuvre d'OR clôturés.

Volontairement **pas une migration automatique** : sur une base qui a déjà un solde d'ouverture saisi en
trésorerie, reprendre l'historique complet compterait deux fois les mouvements antérieurs à ce solde (il
les comprend déjà). À exécuter une fois, après avoir vérifié la date du solde d'ouverture (s'il y en a un) :
- pas de solde d'ouverture (ou aucun mouvement antérieur à sa date) → lancer sans ``--depuis`` ;
- un solde d'ouverture à une date donnée → lancer avec ``--depuis`` fixé au lendemain de cette date.

Rejouable sans double compte (une dépense par source, comme le mécanisme normal) : relancer la commande
après un ``--depuis`` mal choisi, corrigé, ne recrée pas ce qui a déjà été comptabilisé.
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.finance import services


class Command(BaseCommand):
    help = (
        "Comptabilise en dépenses les pleins, achats de pièces et main-d'œuvre d'OR déjà enregistrés "
        "(voir --dry-run pour prévisualiser, --depuis pour ignorer ce qui précède un solde d'ouverture)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--depuis", metavar="AAAA-MM-JJ",
            help="Ne reprend que les sources à partir de cette date (bornes incluses).",
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

        if dry_run:
            from django.db import transaction

            with transaction.atomic():
                compteurs = services.reprendre_depenses_parc_auto(depuis=date_depuis)
                transaction.set_rollback(True)
        else:
            compteurs = services.reprendre_depenses_parc_auto(depuis=date_depuis)

        prefixe = "[Simulation, rien n'a été écrit] " if dry_run else ""
        self.stdout.write(
            prefixe
            + f"Carburant : {compteurs['carburant']} · Pièces : {compteurs['pieces']} · "
            f"Main-d'œuvre : {compteurs['main_oeuvre']} comptabilisées "
            f"({compteurs['deja_comptabilisees']} déjà présentes, inchangées)."
        )
