"""Blocs ajoutés à la fiche d'un congé par des apps situées « en dessous ».

``DETAIL_CONGE`` : fournisseurs appelés avec ``(conge, utilisateur)``. ``missions`` y
ajoute l'alerte « chauffeur avec une mission sur la période » destinée au validateur
(cahier-des-charges.md:219-221).
"""

from apps.core.sections import RegistreSections

DETAIL_CONGE = RegistreSections()
