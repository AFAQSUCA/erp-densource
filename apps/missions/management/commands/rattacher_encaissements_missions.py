"""Reprise, à la demande, des lignes « Encaissement » créées **avant** que la ligne garde le lien avec son
règlement (``FraisMission.reglement``) : sans lui, annuler un règlement laissait son encaissement dans la
prévision de trésorerie de la mission.

Chaque ligne d'encaissement sans lien est rapprochée du règlement de même montant de la facture de sa mission
(le libellé de la ligne reprend le numéro de facture) quand ce rapprochement est sans ambiguïté ; une ligne
dont le règlement a été annulé est alors retirée. Les cas ambigus sont signalés, jamais devinés.

Rejouable sans effet de bord : une ligne déjà rattachée n'est plus traitée.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.billing.models import Reglement
from apps.missions.models import FraisMission, TypeFraisMission


class Command(BaseCommand):
    help = "Rattache les encaissements de mission à leur règlement et retire ceux d'un règlement annulé."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Affiche ce qui serait fait sans rien écrire.")

    def handle(self, *args, dry_run=False, **options):
        rattaches = retires = ambigus = 0
        with transaction.atomic():
            orphelins = FraisMission.objects.filter(
                type_frais=TypeFraisMission.ENCAISSEMENT, reglement__isnull=True
            ).select_related("mission")
            for ligne in orphelins:
                candidats = [
                    r
                    for r in Reglement.all_objects.filter(
                        facture__mission=ligne.mission, montant=ligne.montant
                    ).select_related("facture")
                    if r.facture.numero and r.facture.numero in ligne.description
                ]
                dejà_lies = set(
                    FraisMission.all_objects.filter(reglement__in=candidats).values_list("reglement_id", flat=True)
                )
                libres = [r for r in candidats if r.pk not in dejà_lies]
                if len(libres) != 1:
                    ambigus += 1
                    self.stderr.write(f"Encaissement #{ligne.pk} (mission {ligne.mission.numero}) : rapprochement ambigu.")
                    continue
                reglement = libres[0]
                if reglement.is_deleted:
                    ligne.delete()
                    retires += 1
                else:
                    ligne.reglement = reglement
                    ligne.save(update_fields=["reglement", "updated_at"])
                    rattaches += 1
            if dry_run:
                transaction.set_rollback(True)

        prefixe = "[Simulation, rien n'a été écrit] " if dry_run else ""
        self.stdout.write(
            f"{prefixe}{rattaches} encaissement(s) rattaché(s), {retires} retiré(s) (règlement annulé), "
            f"{ambigus} ambigu(s)."
        )
