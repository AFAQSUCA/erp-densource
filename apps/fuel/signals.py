"""Événements du carburant (souscrits par ``notifications``)."""

from django.dispatch import Signal

# Un plein vient d'être enregistré avec une alerte de surconsommation (jaune ou rouge), une
# anomalie ou une saisie suspecte confirmée. Argument : ``plein`` (instance enregistrée).
alerte_consommation = Signal()

# Un plein vient d'être enregistré (dans la transaction de la saisie). Argument : ``plein``. Souscrit par
# ``finance``, qui en fait une dépense : émis avec ``send`` (pas ``send_robust``) pour qu'une erreur annule
# la saisie plutôt que de laisser une dépense non comptée.
plein_enregistre = Signal()
