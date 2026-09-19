"""Signaux émis par le stock (souscrits par ``notifications``, étape 5)."""

from django.dispatch import Signal

# Émis quand un mouvement fait passer un article au niveau de son seuil minimal
# (ou en dessous) alors qu'il était au-dessus — cahier-des-charges.md:337-338.
# Arguments : ``article`` (instance à jour). Émis dans la transaction du
# mouvement : un récepteur qui envoie un message doit utiliser
# ``transaction.on_commit``.
seuil_bas_atteint = Signal()
