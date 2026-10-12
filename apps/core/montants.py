"""Montants en FCFA saisis : toujours des nombres entiers, le franc CFA ne se divisant pas en centimes dans la
pratique (décision du 12/10/2026, avenant-montants-fcfa.md, audit AUD-05).

Un montant saisi avec des décimales est **refusé**, jamais arrondi en silence. Les montants calculés (TVA, TTC,
coût d'un plein = litres × prix) gardent leurs règles d'arrondi propres.
"""

from __future__ import annotations

from decimal import Decimal

from .exceptions import ErreurMetier
from .formats import nombre


def exiger_montant_entier(montant, *, libelle: str = "Le montant", erreur: type[Exception] = ErreurMetier) -> Decimal:
    """Le montant en ``Decimal`` s'il est entier ; sinon ``erreur`` (l'exception métier de l'app appelante, pour
    que son écran affiche le message)."""
    valeur = Decimal(montant)
    if valeur != valeur.to_integral_value():
        raise erreur(f"{libelle} doit être un nombre entier de FCFA, sans centimes ({nombre(valeur, 2)} saisi).")
    return valeur
