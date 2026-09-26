"""Comptabilisation automatique des dépenses du parc auto.

Un plein de carburant, un achat de pièces (entrée de stock) et la main-d'œuvre d'un OR clôturé sont des
sorties d'argent : chacun crée sa dépense (``demandes.comptabiliser_avec_controle_enveloppe``, qui vérifie
d'abord l'enveloppe mensuelle de la DIRECTION avant de déléguer à ``billing.comptabiliser_depense_automatique``
— R2, avenant-separation-des-taches.md), donc une ligne de la page Dépenses et une sortie de trésorerie, sans
double saisie. Les apps d'origine ne connaissent pas ``finance`` : elles émettent un signal, souscrit ici.
Récepteurs appelés par ``send`` (pas ``send_robust``) : une erreur (dépense refusée, enveloppe dépassée en
attente de décision...) annule l'opération d'origine au lieu de laisser une dépense non comptée.

Les pièces sont comptées à l'**achat**, pas à leur sortie de stock vers un OR : le coût d'un OR clôturé n'entre
donc dans les charges que par sa main-d'œuvre (sinon la pièce serait comptée deux fois).
"""

from django.dispatch import receiver
from django.utils import timezone

from apps.billing.models import CategorieDepense, OrigineDepense
from apps.fuel.signals import plein_enregistre
from apps.garage.signals import or_cloture
from apps.inventory.signals import entree_stock_enregistree

from . import demandes


@receiver(plein_enregistre)
def comptabiliser_un_plein(sender, plein, **kwargs):
    demandes.comptabiliser_avec_controle_enveloppe(
        origine=OrigineDepense.PLEIN,
        origine_id=plein.pk,
        categorie=CategorieDepense.CARBURANT,
        date_depense=plein.date_plein,
        libelle=(
            f"Carburant · {plein.vehicule.immatriculation} · {plein.station} "
            f"({plein.quantite_litres.normalize():f} L)"
        ),
        montant=plein.quantite_litres * plein.prix_unitaire,
        reference=plein.numero_ticket,
        vehicule=plein.vehicule,
    )


@receiver(entree_stock_enregistree)
def comptabiliser_un_achat_de_pieces(sender, mouvement, **kwargs):
    article = mouvement.article
    demandes.comptabiliser_avec_controle_enveloppe(
        origine=OrigineDepense.ACHAT_STOCK,
        origine_id=mouvement.pk,
        categorie=CategorieDepense.PIECES,
        date_depense=timezone.localdate(mouvement.date_mouvement),
        libelle=f"Achat de pièces · {article.designation} ({article.reference}) × {mouvement.variation}",
        montant=mouvement.variation * mouvement.prix_unitaire,
    )


@receiver(or_cloture)
def comptabiliser_la_main_d_oeuvre(sender, ordre, **kwargs):
    demandes.comptabiliser_avec_controle_enveloppe(
        origine=OrigineDepense.MAIN_OEUVRE_OR,
        origine_id=ordre.pk,
        categorie=CategorieDepense.MAINTENANCE,
        date_depense=timezone.localdate(ordre.date_cloture),
        libelle=f"Main-d'œuvre · {ordre.numero} · {ordre.vehicule.immatriculation}",
        montant=ordre.cout_main_oeuvre,
        reference=ordre.numero,
        vehicule=ordre.vehicule,
    )
