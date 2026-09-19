"""Événements du carburant (souscrits par ``notifications``)."""

from django.dispatch import Signal

# Un plein vient d'être enregistré avec une alerte de surconsommation (jaune ou rouge), une
# anomalie ou une saisie suspecte confirmée. Argument : ``plein`` (instance enregistrée).
alerte_consommation = Signal()
