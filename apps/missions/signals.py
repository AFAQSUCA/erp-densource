"""Événements des missions (souscrits par ``notifications``)."""

from django.dispatch import Signal

# La mission vient de démarrer : « en cours de route (départ) » (cahier-des-charges.md:136-137).
# Argument : ``mission`` (instance à jour).
mission_demarree = Signal()
