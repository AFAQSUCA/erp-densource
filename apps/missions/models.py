from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class StatutMission(models.TextChoices):
    """Cycle de vie — cahier-des-charges.md:132-134, architecture.md:239-256.

    « En cours » se décompose en deux étapes : départ, puis colis récupéré.
    """

    BROUILLON = "BROUILLON", _("Brouillon")
    PLANIFIEE = "PLANIFIEE", _("Planifiée")
    AFFECTEE = "AFFECTEE", _("Affectée")
    EN_COURS_DEPART = "EN_COURS_DEPART", _("En cours : départ")
    EN_COURS_COLIS_RECUPERE = "EN_COURS_COLIS_RECUPERE", _("En cours : colis récupéré")
    LIVREE = "LIVREE", _("Livrée")
    CLOTUREE = "CLOTUREE", _("Clôturée et validée")


# Camion et chauffeur réservés : la mission a été affectée mais n'est pas terminée.
STATUTS_ACTIFS = (
    StatutMission.AFFECTEE,
    StatutMission.EN_COURS_DEPART,
    StatutMission.EN_COURS_COLIS_RECUPERE,
)

# Modification autorisée tant que le colis n'est pas encore récupéré : au-delà, le client a déjà le
# camion à quai / la marchandise est en route sur la base de ces informations (règle de séparation des
# tâches, avenant-separation-des-taches.md § R3).
STATUTS_MODIFIABLES = (
    StatutMission.BROUILLON,
    StatutMission.PLANIFIEE,
    StatutMission.AFFECTEE,
    StatutMission.EN_COURS_DEPART,
)


class Mission(BaseModel):
    """Mission de transport — cahier-des-charges.md:127-143."""

    numero = models.CharField(_("numéro"), max_length=20, unique=True)
    client = models.ForeignKey(
        "customers.Client",
        verbose_name=_("client"),
        on_delete=models.PROTECT,
        related_name="missions",
    )
    vehicule = models.ForeignKey(
        "fleet.Vehicule",
        verbose_name=_("camion"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="missions",
    )
    chauffeur = models.ForeignKey(
        "drivers.Chauffeur",
        verbose_name=_("chauffeur"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="missions",
    )
    lieu_chargement = models.CharField(_("lieu de chargement"), max_length=200)
    lieu_livraison = models.CharField(_("lieu de livraison"), max_length=200)
    nature_marchandise = models.CharField(_("nature de la marchandise"), max_length=200)
    poids_t = models.DecimalField(_("poids (t)"), max_digits=8, decimal_places=2)
    prix_convenu = models.DecimalField(
        _("prix convenu (FCFA)"), max_digits=12, decimal_places=2
    )
    date_depart_prevue = models.DateField(
        _("départ prévu"),
        null=True,
        blank=True,
        help_text=_(
            "Nécessaire à l'alerte N1 « chauffeur avec mission sur la période » "
            "des congés (cahier-des-charges.md:219-221)."
        ),
    )
    statut = models.CharField(
        _("statut"),
        max_length=25,
        choices=StatutMission.choices,
        default=StatutMission.BROUILLON,
    )

    # Codes remis à l'expéditeur (récupération du colis) et au destinataire
    # (confirmation de livraison) — cahier-des-charges.md:135-137. Exclus de
    # l'audit (voir apps.py). Le QR ne fait qu'encoder ces codes.
    code_expediteur = models.CharField(_("code expéditeur"), max_length=12)
    code_destinataire = models.CharField(_("code destinataire"), max_length=12)

    km_depart = models.PositiveIntegerField(_("km au départ"), null=True, blank=True)
    km_arrivee = models.PositiveIntegerField(_("km à l'arrivée"), null=True, blank=True)
    date_depart = models.DateTimeField(_("départ effectif"), null=True, blank=True)
    date_recuperation = models.DateTimeField(_("colis récupéré le"), null=True, blank=True)
    date_livraison = models.DateTimeField(_("livrée le"), null=True, blank=True)
    date_cloture = models.DateTimeField(_("clôturée le"), null=True, blank=True)

    class Meta:
        verbose_name = _("mission")
        verbose_name_plural = _("missions")
        ordering = ["-numero"]
        indexes = [
            models.Index(fields=["statut"]),
            models.Index(fields=["vehicule", "statut"]),
            models.Index(fields=["chauffeur", "statut"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    statut__in=[StatutMission.BROUILLON, StatutMission.PLANIFIEE]
                )
                | (Q(vehicule__isnull=False) & Q(chauffeur__isnull=False)),
                name="mission_affectee_requiert_camion_et_chauffeur",
            ),
            models.CheckConstraint(
                condition=Q(poids_t__gt=0), name="mission_poids_positif"
            ),
            models.CheckConstraint(
                condition=Q(prix_convenu__gte=0), name="mission_prix_positif_ou_nul"
            ),
            models.CheckConstraint(
                condition=Q(km_arrivee__isnull=True)
                | Q(km_depart__isnull=True)
                | Q(km_arrivee__gte=F("km_depart")),
                name="mission_km_arrivee_apres_depart",
            ),
        ]

    def __str__(self):
        return f"{self.numero} ({self.client})"

    @property
    def est_en_cours(self) -> bool:
        return self.statut in (
            StatutMission.EN_COURS_DEPART,
            StatutMission.EN_COURS_COLIS_RECUPERE,
        )


class TypeFraisMission(models.TextChoices):
    """Nature d'une ligne de prévision de trésorerie — avenant-separation-des-taches.md (R4)."""

    AVANCE_ROUTE = "AVANCE_ROUTE", _("Avance de route")
    DEPENSE_PREVUE = "DEPENSE_PREVUE", _("Dépense prévue")
    IMPREVU = "IMPREVU", _("Imprévu (panne, incident)")
    ENCAISSEMENT = "ENCAISSEMENT", _("Encaissement")


# Sorties d'argent (financent la mission) : à distinguer de l'encaissement, qui n'en est
# qu'un reflet (relié à un Règlement existant, jamais une source de mouvement à part).
TYPES_SORTIE_FRAIS = (
    TypeFraisMission.AVANCE_ROUTE,
    TypeFraisMission.DEPENSE_PREVUE,
    TypeFraisMission.IMPREVU,
)


class StatutFraisMission(models.TextChoices):
    PREVU = "PREVU", _("Prévu")
    CONFIRME = "CONFIRME", _("Confirmé")
    REJETE = "REJETE", _("Rejeté")


class FraisMission(BaseModel):
    """Ligne de prévision de trésorerie d'une mission — avenant-separation-des-taches.md (R4).

    Une avance de route ou une dépense prévue est planifiée par le Parc Auto puis validée par
    la Finance ; un imprévu est déclaré par le chauffeur (mobile, avec preuve) puis validé
    deux fois (Parc Auto, puis Finance) — jamais par celui qui l'a saisi. Un encaissement est le
    simple reflet d'un règlement déjà enregistré (``billing.Reglement``), créé automatiquement,
    directement confirmé : aucune double saisie. Seule une ligne ``CONFIRME`` représente un
    mouvement de trésorerie réel (``finance.receivers`` la transforme alors en dépense pour les
    3 premiers types, cahier-des-charges des dépenses du parc auto compris).
    """

    mission = models.ForeignKey(
        Mission, verbose_name=_("mission"), on_delete=models.PROTECT, related_name="frais"
    )
    type_frais = models.CharField(_("type"), max_length=15, choices=TypeFraisMission.choices)
    montant = models.DecimalField(_("montant (FCFA)"), max_digits=12, decimal_places=2)
    description = models.CharField(_("libellé"), max_length=255, blank=True)
    justificatif = models.FileField(
        _("justificatif"), upload_to="frais_mission/justificatifs/%Y/%m/", blank=True
    )
    statut = models.CharField(
        _("statut"), max_length=10, choices=StatutFraisMission.choices, default=StatutFraisMission.PREVU
    )
    motif_rejet = models.TextField(_("motif du rejet"), blank=True)
    chauffeur = models.ForeignKey(
        "drivers.Chauffeur",
        verbose_name=_("chauffeur"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="frais_mission_declares",
        help_text=_("Renseigné pour un imprévu déclaré depuis l'espace mobile."),
    )
    saisi_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("saisi par"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    valide_parcauto_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("validé par le parc auto"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    date_validation_parcauto = models.DateTimeField(_("validé par le parc auto le"), null=True, blank=True)
    valide_finances_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("validé par la finance"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    date_validation_finances = models.DateTimeField(_("validé par la finance le"), null=True, blank=True)

    class Meta:
        verbose_name = _("frais de mission")
        verbose_name_plural = _("frais de mission")
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["mission", "statut"])]
        constraints = [
            models.CheckConstraint(condition=Q(montant__gt=0), name="frais_mission_montant_positif"),
        ]

    def __str__(self):
        return f"{self.get_type_frais_display()} · {self.mission.numero} ({self.montant})"

    @property
    def est_sortie(self) -> bool:
        return self.type_frais in TYPES_SORTIE_FRAIS

    @property
    def attend_le_parc_auto(self) -> bool:
        """Imprévu encore prévu, pas encore validé par le Parc Auto (première validation)."""
        return (
            self.statut == StatutFraisMission.PREVU
            and self.type_frais == TypeFraisMission.IMPREVU
            and self.valide_parcauto_par_id is None
        )

    @property
    def attend_la_finance(self) -> bool:
        """Prévu, et déjà passé (ou pas concerné) par la première validation du Parc Auto."""
        return self.statut == StatutFraisMission.PREVU and not self.attend_le_parc_auto
