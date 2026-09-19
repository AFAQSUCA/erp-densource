"""Aides d'affichage : pastilles de statut colorées.

Le texte de la pastille porte toujours le sens ; la couleur est un renfort, pas
la seule information (accessibilité WCAG 2.1 AA, cahier-des-charges.md:304).
"""

from django import template
from django.utils.html import format_html

from apps.core.formats import pourcentage_signe as _pourcentage_signe

register = template.Library()

STYLES = {
    "gris": "bg-slate-100 text-slate-700 ring-slate-300",
    "bleu": "bg-blue-50 text-blue-800 ring-blue-300",
    "indigo": "bg-indigo-50 text-indigo-800 ring-indigo-300",
    "ambre": "bg-amber-50 text-amber-900 ring-amber-400",
    "vert": "bg-emerald-50 text-emerald-900 ring-emerald-400",
    "rouge": "bg-red-50 text-red-800 ring-red-300",
}

# Couleur par code de statut. Les codes identiques d'apps différentes
# (« DISPONIBLE », « EN_MISSION »...) partagent volontairement la même couleur.
COULEURS_STATUT = {
    "BROUILLON": "gris",
    "PLANIFIEE": "bleu",
    "AFFECTEE": "indigo",
    "EN_COURS_DEPART": "ambre",
    "EN_COURS_COLIS_RECUPERE": "ambre",
    "LIVREE": "vert",
    "CLOTUREE": "gris",
    # camions
    "DISPONIBLE": "vert",
    "EN_MISSION": "bleu",
    "EN_MAINTENANCE": "ambre",
    "IMMOBILISE": "rouge",
    "HORS_SERVICE": "gris",
    # chauffeurs
    "EN_CONGE": "indigo",
    "SUSPENDU": "rouge",
    "INACTIF": "gris",
    # documents réglementaires
    "VALIDE": "vert",
    "A_RENOUVELER": "ambre",
    "EXPIRE": "rouge",
    "MANQUANT": "gris",
    # ordres de réparation
    "OUVERT": "ambre",
    "CLOTURE": "gris",
    # stock
    "STOCK_BAS": "ambre",
    "RUPTURE": "rouge",
    "ENTREE": "vert",
    "SORTIE": "bleu",
    "AJUSTEMENT": "ambre",
    # facturation
    "A_VALIDER": "ambre",
    "EMISE": "bleu",
    "PARTIELLEMENT_PAYEE": "indigo",
    "PAYEE": "vert",
    "ECHUE": "rouge",
    # notifications
    "INFO": "bleu",
    "ATTENTION": "ambre",
    "URGENT": "rouge",
    # congés
    "DEMANDE": "ambre",
    "VALIDATION_N1": "bleu",
    "APPROUVE": "vert",
    "EN_COURS": "indigo",
    "TERMINE": "gris",
    "REFUSE": "rouge",
    # clients
    "RECLAMATION": "rouge",
    # carburant
    "JAUNE": "ambre",
    "ROUGE": "rouge",
    "ANOMALIE": "rouge",
    "SAISIE_SUSPECTE": "ambre",
}


@register.simple_tag
def badge(code: str, libelle: str):
    """Pastille de statut : ``{% badge mission.statut mission.get_statut_display %}``."""
    couleur = STYLES[COULEURS_STATUT.get(code, "gris")]
    return format_html(
        '<span class="inline-flex items-center rounded-full px-2.5 py-0.5 '
        'text-xs font-semibold ring-1 ring-inset {}">{}</span>',
        couleur,
        libelle,
    )


@register.filter
def pourcentage_signe(valeur, decimales=1):
    """``{{ ecart|pourcentage_signe }} %`` → « +23,3 % » (virgule française, signe explicite)."""
    if valeur is None:
        return ""
    return _pourcentage_signe(valeur, int(decimales))
