"""Blocs affichés dans la fiche d'un camion par des apps situées en dessous.

Fournisseurs appelés avec ``(vehicule, utilisateur)`` — voir ``core/sections.py``.
``garage`` y ajoute l'historique de maintenance et les actions d'immobilisation.
"""

from apps.core.sections import RegistreSections

DETAIL_VEHICULE = RegistreSections()
