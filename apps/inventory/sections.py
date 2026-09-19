"""Bloc « Pièces utilisées » ajouté à la fiche d'un OR (garage) — voir core/sections.py.

Le coût automatique des pièces et le total de l'OR (main-d'œuvre + pièces) sont
affichés ici : ``garage`` n'a pas à connaître le stock (architecture.md:161-163).
"""

from apps.garage.models import StatutOr

from . import permissions, services
from .forms import SortieForm


def section_pieces(ordre, utilisateur):
    role = utilisateur.role_effectif
    if role not in permissions.CONSULTATION:
        return None
    peut_sortir = role in permissions.MODIFICATION and ordre.statut == StatutOr.OUVERT
    return {
        "template": "inventory/_pieces_or.html",
        "contexte": {
            "lignes": [
                {
                    "article": m.article,
                    "quantite": -m.variation,
                    "prix_unitaire": m.prix_unitaire,
                    "montant": -m.variation * m.prix_unitaire,
                }
                for m in services.sorties_de_l_or(ordre)
            ],
            "cout_pieces": services.cout_pieces(ordre),
            "cout_total": services.cout_total(ordre),
            "form_sortie": SortieForm() if peut_sortir else None,
        },
    }
