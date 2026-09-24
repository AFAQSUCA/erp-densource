"""Balises des graphiques du tableau de bord (données préparées par ``apps.core.graphiques``)."""

from django import template

register = template.Library()


@register.inclusion_tag("components/_graphique_barres.html")
def graphique_barres(donnees, vide="Aucune donnée pour le moment."):
    """Barres horizontales : ``{% graphique_barres graphique %}``."""
    return {"g": donnees, "vide": vide}


@register.inclusion_tag("components/_graphique_colonnes.html")
def graphique_colonnes(donnees, identifiant, vide="Aucune donnée sur la période."):
    """Colonnes groupées : ``{% graphique_colonnes graphique "id-unique" %}``."""
    return {"g": donnees, "id": identifiant, "vide": vide}
