"""Paramètres de l'application : une seule ligne (``pk = 1``), modifiable par l'ADMIN et la DIRECTION.

Les valeurs par défaut sont celles du cahier des charges et de ses avenants : tant que personne n'a enregistré
l'écran « Paramètres », la table est vide et l'application lit ces valeurs (``services.parametres``).
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.constants import DELAI_ALERTE_JOURS

PK_UNIQUE = 1

# Valeurs du cahier des charges (et des avenants), reprises tant qu'aucun paramètre n'est enregistré.
SEUIL_CONSO_JAUNE_PCT = Decimal("20")  # cahier-des-charges.md:153
SEUIL_CONSO_ROUGE_PCT = Decimal("40")  # cahier-des-charges.md:154
SEUIL_CONSO_SAISIE_PCT = Decimal("60")  # cahier-des-charges.md:155
CONSO_MIN_L100 = Decimal("20")  # cahier-des-charges.md:157
CONSO_MAX_L100 = Decimal("45")  # cahier-des-charges.md:157
# Distance maximale crédible entre deux relevés du compteur d'un même camion (deux pleins, ou le départ et
# l'arrivée d'une mission) : au-delà, c'est une faute de frappe plutôt qu'un trajet (audit M5-10 / M6-09).
ECART_KM_MAX = 5000
TVA_DEFAUT = Decimal("18.00")  # cahier-des-charges.md:120,185
DELAI_PAIEMENT_DEFAUT = 30  # jours ; échéance d'une facture = émission + délai du client
DELAI_VALIDATION_N1_HEURES = 48  # cahier-des-charges.md:213
DELAI_VALIDATION_N2_HEURES = 24  # cahier-des-charges.md:214
# 26 jours ouvrés (lundi-vendredi), au-delà du minimum légal ivoirien de 2,2 jours ouvrables par mois : avantage
# social décidé par l'entreprise (avenant-separation-des-taches.md § R7, remplace les 12 jours du CDC d'origine).
DROIT_ANNUEL_JOURS = 26


def _bornes(minimum, maximum):
    return [MinValueValidator(minimum), MaxValueValidator(maximum)]


class Parametres(models.Model):
    """Réglages modifiables sans mise à jour de l'application (avenant-parametres.md)."""

    # --- alertes ---
    delai_alerte_jours = models.PositiveSmallIntegerField(
        _("délai d'alerte avant expiration (jours)"), default=DELAI_ALERTE_JOURS, validators=_bornes(1, 365),
        help_text=_("Documents des camions, permis et visite médicale des chauffeurs."),
    )
    seuil_conso_jaune_pct = models.DecimalField(
        _("alerte jaune : écart de consommation (%)"), max_digits=5, decimal_places=2,
        default=SEUIL_CONSO_JAUNE_PCT, validators=_bornes(Decimal("1"), Decimal("500")),
        help_text=_("Au-delà de la moyenne des 3 derniers pleins du camion."),
    )
    seuil_conso_rouge_pct = models.DecimalField(
        _("alerte rouge : écart de consommation (%)"), max_digits=5, decimal_places=2,
        default=SEUIL_CONSO_ROUGE_PCT, validators=_bornes(Decimal("1"), Decimal("500")),
    )
    seuil_conso_saisie_pct = models.DecimalField(
        _("saisie suspecte : écart de consommation (± %)"), max_digits=5, decimal_places=2,
        default=SEUIL_CONSO_SAISIE_PCT, validators=_bornes(Decimal("1"), Decimal("500")),
    )
    conso_min_l100 = models.DecimalField(
        _("consommation minimale plausible (L/100 km)"), max_digits=5, decimal_places=2,
        default=CONSO_MIN_L100, validators=_bornes(Decimal("1"), Decimal("200")),
    )
    conso_max_l100 = models.DecimalField(
        _("consommation maximale plausible (L/100 km)"), max_digits=5, decimal_places=2,
        default=CONSO_MAX_L100, validators=_bornes(Decimal("1"), Decimal("200")),
    )
    ecart_km_max = models.PositiveIntegerField(
        _("distance maximale entre deux relevés (km)"), default=ECART_KM_MAX, validators=_bornes(100, 50000),
        help_text=_("Au-delà, la saisie du compteur est refusée (faute de frappe probable)."),
    )
    # --- clients et facturation ---
    tva_defaut = models.DecimalField(
        _("taux de TVA proposé aux nouveaux clients (%)"), max_digits=5, decimal_places=2, default=TVA_DEFAUT,
        validators=_bornes(Decimal("0.01"), Decimal("100")),
        help_text=_("Un client exonéré se règle sur sa fiche (0 % avec motif)."),
    )
    delai_paiement_defaut_jours = models.PositiveSmallIntegerField(
        _("délai de paiement proposé aux nouveaux clients (jours)"), default=DELAI_PAIEMENT_DEFAUT,
        validators=_bornes(1, 365),
    )
    # --- ressources humaines ---
    delai_validation_n1_heures = models.PositiveSmallIntegerField(
        _("délai de validation N1 d'un congé (heures)"), default=DELAI_VALIDATION_N1_HEURES,
        validators=_bornes(1, 720),
    )
    delai_validation_n2_heures = models.PositiveSmallIntegerField(
        _("délai de validation N2 d'un congé (heures)"), default=DELAI_VALIDATION_N2_HEURES,
        validators=_bornes(1, 720),
    )
    droit_annuel_jours = models.PositiveSmallIntegerField(
        _("droit annuel de congé (jours ouvrés)"), default=DROIT_ANNUEL_JOURS, validators=_bornes(1, 60),
        help_text=_("S'applique au calcul de tous les soldes, année en cours comprise."),
    )

    modifie_le = models.DateTimeField(_("modifié le"), auto_now=True)
    modifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("modifié par"), null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )

    class Meta:
        verbose_name = _("paramètres")
        verbose_name_plural = _("paramètres")
        constraints = [models.CheckConstraint(condition=models.Q(pk=PK_UNIQUE), name="parametres_ligne_unique")]

    def __str__(self) -> str:
        return "Paramètres de l'application"
