"""Comptabilisation automatique des dépenses du parc auto.

Un plein de carburant, un achat de pièces (entrée de stock) et la main-d'œuvre d'un OR clôturé sont des
sorties d'argent : chacun crée sa dépense (``billing.comptabiliser_depense_automatique``), donc une ligne de
la page Dépenses et une sortie de trésorerie, sans double saisie. Les apps d'origine ne connaissent pas
``finance`` : elles émettent un signal, souscrit ici. Récepteurs appelés par ``send`` (pas ``send_robust``) :
une erreur annule l'opération d'origine au lieu de laisser une dépense non comptée.

Les pièces sont comptées à l'**achat**, pas à leur sortie de stock vers un OR : le coût d'un OR clôturé n'entre
donc dans les charges que par sa main-d'œuvre (sinon la pièce serait comptée deux fois).
"""

from django.dispatch import receiver
from django.utils import timezone

from apps.billing import services as billing_services
from apps.billing.models import CategorieDepense, OrigineDepense
from apps.billing.signals import reglement_enregistre
from apps.fuel.signals import plein_enregistre
from apps.garage.signals import or_cloture
from apps.inventory.signals import entree_stock_enregistree
from apps.missions import terrain as missions_terrain
from apps.missions.models import TypeFraisMission
from apps.missions.signals import frais_mission_confirme


@receiver(plein_enregistre)
def comptabiliser_un_plein(sender, plein, **kwargs):
    billing_services.comptabiliser_depense_automatique(
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
    )


@receiver(entree_stock_enregistree)
def comptabiliser_un_achat_de_pieces(sender, mouvement, **kwargs):
    article = mouvement.article
    billing_services.comptabiliser_depense_automatique(
        origine=OrigineDepense.ACHAT_STOCK,
        origine_id=mouvement.pk,
        categorie=CategorieDepense.PIECES,
        date_depense=timezone.localdate(mouvement.date_mouvement),
        libelle=f"Achat de pièces · {article.designation} ({article.reference}) × {mouvement.variation}",
        montant=mouvement.variation * mouvement.prix_unitaire,
    )


@receiver(or_cloture)
def comptabiliser_la_main_d_oeuvre(sender, ordre, **kwargs):
    billing_services.comptabiliser_depense_automatique(
        origine=OrigineDepense.MAIN_OEUVRE_OR,
        origine_id=ordre.pk,
        categorie=CategorieDepense.MAINTENANCE,
        date_depense=timezone.localdate(ordre.date_cloture),
        libelle=f"Main-d'œuvre · {ordre.numero} · {ordre.vehicule.immatriculation}",
        montant=ordre.cout_main_oeuvre,
        reference=ordre.numero,
    )


@receiver(frais_mission_confirme)
def comptabiliser_un_frais_de_mission(sender, frais, **kwargs):
    """Avance de route, dépense prévue ou imprévu confirmé (R4) : une sortie d'argent comme une
    autre. Un encaissement (reflet d'un règlement) ne déclenche jamais ce signal."""
    if frais.type_frais == TypeFraisMission.ENCAISSEMENT:
        return
    billing_services.comptabiliser_depense_automatique(
        origine=OrigineDepense.FRAIS_MISSION,
        origine_id=frais.pk,
        categorie=CategorieDepense.FRAIS_MISSION,
        date_depense=timezone.localdate(),
        libelle=(
            f"{frais.get_type_frais_display()} · {frais.mission.numero}"
            + (f" · {frais.description}" if frais.description else "")
        ),
        montant=frais.montant,
        mission=frais.mission,
    )


@receiver(reglement_enregistre)
def refleter_l_encaissement_sur_la_mission(sender, reglement, **kwargs):
    """Un règlement reçu se reflète dans la prévision de trésorerie de la mission facturée (R4),
    sans double saisie : aucune dépense ni règlement supplémentaire n'est créé ici."""
    missions_terrain.creer_encaissement(
        reglement.facture.mission,
        montant=reglement.montant,
        libelle=f"Règlement {reglement.facture.numero} ({reglement.get_mode_display()})",
        saisi_par=reglement.saisi_par,
    )
