"""Reprise, à la demande, des règlements et mouvements manuels **annulés avant** la mise en service de la
contre-passation automatique (``accounting.receivers``) : leur écriture est restée au grand livre alors
que la trésorerie ne les compte plus. Chaque annulation reçoit son écriture inverse, datée du jour de
l'annulation (jamais d'un exercice clôturé : ceux-là sont signalés, à traiter à la main).

Rejouable sans double contre-passation (une par écriture d'origine, comme le mécanisme normal).
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounting import services
from apps.accounting.exceptions import AccountingError
from apps.accounting.models import EcritureComptable
from apps.billing.models import Reglement
from apps.finance.models import MouvementManuel


class Command(BaseCommand):
    help = (
        "Contre-passe les règlements et mouvements manuels déjà annulés avant ce lot "
        "(voir --dry-run pour prévisualiser)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Affiche ce qui serait contre-passé sans rien écrire."
        )

    def handle(self, *args, dry_run=False, **options):
        faites = deja = sans_ecriture = impossibles = 0
        sources = (("REGLEMENT", Reglement), ("MOUVEMENT", MouvementManuel))
        with transaction.atomic():
            for origine, modele in sources:
                for annule in modele.all_objects.filter(is_deleted=True):
                    if not EcritureComptable.objects.filter(origine=origine, origine_id=annule.pk).exists():
                        sans_ecriture += 1
                        continue
                    if EcritureComptable.objects.filter(
                        origine=services.ORIGINE_CONTRE_PASSATION,
                        origine_id=EcritureComptable.objects.get(origine=origine, origine_id=annule.pk).pk,
                    ).exists():
                        deja += 1
                        continue
                    jour = timezone.localdate(annule.deleted_at) if annule.deleted_at else None
                    try:
                        with transaction.atomic():
                            services.contre_passer_origine(
                                origine, annule.pk, date_ecriture=jour, motif=annule.motif_annulation
                            )
                    except AccountingError as erreur:
                        impossibles += 1
                        self.stderr.write(f"{origine} #{annule.pk} non contre-passé : {erreur}")
                    else:
                        faites += 1
            if dry_run:
                transaction.set_rollback(True)

        prefixe = "[Simulation, rien n'a été écrit] " if dry_run else ""
        self.stdout.write(
            f"{prefixe}{faites} annulation(s) contre-passée(s) ({deja} déjà faites, {sans_ecriture} jamais "
            f"comptabilisées, {impossibles} impossible(s))."
        )
