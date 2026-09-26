# Chapitre 15 — Les notifications : l'app notifications

> 17 fichier(s) dans ce chapitre, 1371 lignes de code.

## Ce que vous allez construire

**`notifications`** : prévenir **les bonnes personnes au bon moment**. C'est la dernière app « métier » ; elle
est tout en haut du graphe de dépendances : **elle connaît toutes les autres, aucune ne la connaît**. Comment
est-ce possible ? Les autres apps **émettent des signaux** (chapitres 5 à 13) et `notifications` **s'y abonne**.

| Événement | Qui est prévenu |
|---|---|
| congé déposé | le supérieur hiérarchique (N1), avec une alerte urgente s'il y a une mission prévue sur la période |
| congé validé N1 | la RH (N2) ; congé approuvé, refusé ou annulé → l'employé |
| stock au seuil | le Parc Auto |
| surconsommation, anomalie, saisie suspecte | le Parc Auto et la Direction |
| mission partie | le chargé de clientèle du client (à défaut, tous les chargés) |
| incident signalé | le Parc Auto et la Direction ; check-list avec point KO → le Parc Auto |
| facture soumise | la Direction ; validée → Finances et son auteur ; renvoyée → son auteur |
| facture échue (tâche du jour) | Finances et Direction, **une fois par facture** |

À cela s'ajoutent les **tâches du jour** (documents et permis à 30 jours puis expirés, rappels de validation de
congés en retard, passage des congés à « En cours » / « Terminé »), lancées par une commande.

## Prérequis

- Chapitres 1 à 14 terminés.

## Notions Django de ce chapitre

- **Abonnements par `@receiver`** dans un fichier `receivers.py`, branchés par `ready()` : c'est l'inverse
  des chapitres précédents où l'on *émettait*.
- **Clé d'unicité** (`cle_unicite`) : pour qu'un rappel quotidien ne soit **envoyé qu'une fois** à la même
  personne, on lui associe une clé (par exemple `facture-echue-12`) : si elle existe déjà, on ne recrée rien.
- **`Notification.all_objects`** (le manager qui voit aussi les lignes supprimées) : une notification
  supprimée ne doit pas être renvoyée.
- **Envoi d'e-mails optionnel** (`NOTIFICATIONS_EMAIL`) : un e-mail en échec est **journalisé** et ne bloque
  jamais l'opération métier.
- **Commande de gestion planifiable** : `taches_quotidiennes` sera lancée chaque jour (planificateur,
  cron…) ; elle est **rejouable** sans doublon.
- **Lien profond** : chaque notification porte l'adresse de l'écran concerné, résolue avec `reverse()`
  (la table d'adresses s'écrira aux chapitres 16 et suivants).

## Étape 1 — Créer l'application

```bash
mkdir -p apps/notifications/management/commands
```

#### Fichiers vides à créer

Ces fichiers n'ont aucun contenu ; ils servent à faire de leur dossier un *paquet Python* (sans eux, `import apps.xxx` échouerait). Créez d'abord les dossiers, puis les fichiers :

```bash
mkdir -p apps\notifications apps\notifications\management apps\notifications\management\commands apps\notifications\tests
touch apps/notifications/__init__.py
touch apps/notifications/management/__init__.py
touch apps/notifications/management/commands/__init__.py
touch apps/notifications/tests/__init__.py
```

> Sous PowerShell, `mkdir -p` s'écrit `New-Item -ItemType Directory -Force <dossier>` et `touch fichier` s'écrit `New-Item -ItemType File -Force fichier`. Vous pouvez aussi créer ces fichiers avec votre éditeur.

## Étape 2 — Modèle et service de base

#### `apps/notifications/models.py`

*79 lignes*

```python
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class CategorieNotification(models.TextChoices):
    CONGE = "CONGE", _("Congé")
    STOCK = "STOCK", _("Stock")
    CARBURANT = "CARBURANT", _("Carburant")
    DOCUMENT = "DOCUMENT", _("Échéance")
    MISSION = "MISSION", _("Mission")
    FACTURE = "FACTURE", _("Facturation")
    PROFORMA = "PROFORMA", _("Devis")
    FRAIS_MISSION = "FRAIS_MISSION", _("Frais de mission")
    DEMANDE_DEPENSE = "DEMANDE_DEPENSE", _("Demande de dépense")
    INCIDENT = "INCIDENT", _("Incident")


class NiveauNotification(models.TextChoices):
    INFO = "INFO", _("Information")
    ATTENTION = "ATTENTION", _("Attention")
    URGENT = "URGENT", _("Urgent")


class Notification(BaseModel):
    """Message adressé à un utilisateur (cloche de l'en-tête, page « Notifications »).

    Créée par ``services.notifier`` ; ``cle_unicite`` évite d'envoyer deux fois la même
    alerte au même destinataire (rappels quotidiens).
    """

    destinataire = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("destinataire"),
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    categorie = models.CharField(_("catégorie"), max_length=15, choices=CategorieNotification.choices)
    niveau = models.CharField(
        _("niveau"),
        max_length=10,
        choices=NiveauNotification.choices,
        default=NiveauNotification.INFO,
    )
    titre = models.CharField(_("titre"), max_length=200)
    message = models.TextField(_("message"), blank=True)
    url = models.CharField(_("lien"), max_length=300, blank=True)
    action = models.CharField(
        _("bouton d'action"),
        max_length=60,
        blank=True,
        help_text=_("Intitulé du bouton qui mène au lien (ex. « Confirmer le versement ») ; « Ouvrir » si vide."),
    )
    lue_le = models.DateTimeField(_("lue le"), null=True, blank=True)
    cle_unicite = models.CharField(_("clé d'unicité"), max_length=150, blank=True)
    email_envoye = models.BooleanField(_("e-mail envoyé"), default=False)

    class Meta:
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["destinataire", "lue_le"])]
        constraints = [
            models.UniqueConstraint(
                fields=["destinataire", "cle_unicite"],
                condition=~Q(cle_unicite=""),
                name="notification_cle_unique_par_destinataire",
            ),
        ]

    def __str__(self):
        return f"{self.destinataire} : {self.titre}"

    @property
    def est_lue(self) -> bool:
        return self.lue_le is not None
```

Une `Notification` : destinataire, catégorie, niveau (Information, Attention, Urgent), titre, message, lien,
date de lecture, clé d'unicité.

#### `apps/notifications/services.py`

*128 lignes* — Envoi et lecture des notifications.

```python
"""Envoi et lecture des notifications.

Une notification est toujours enregistrée dans l'application ; elle est aussi envoyée par
e-mail si ``NOTIFICATIONS_EMAIL`` est actif et que le destinataire a une adresse. Un e-mail
qui échoue est journalisé mais ne fait jamais échouer l'opération métier qui l'a déclenchée.
"""

from __future__ import annotations

import logging
from typing import Iterable

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from apps.accounts.models import User

from .models import CategorieNotification, NiveauNotification, Notification

logger = logging.getLogger(__name__)


def utilisateurs_du_role(*roles: str) -> QuerySet[User]:
    """Comptes actifs ayant l'un de ces rôles."""
    return User.objects.filter(role__in=roles, is_active=True)


def envoyer_email(notification_id: int) -> None:
    notification = Notification.objects.select_related("destinataire").get(pk=notification_id)
    adresse = notification.destinataire.email
    if not adresse:
        return
    corps = notification.message
    if notification.url:
        corps += f"\n\nOuvrir : {settings.NOTIFICATIONS_URL_BASE.rstrip('/')}{notification.url}"
    try:
        send_mail(notification.titre, corps, settings.DEFAULT_FROM_EMAIL, [adresse])
    except Exception:  # noqa: BLE001 - un e-mail perdu ne doit pas bloquer le métier
        logger.exception("Envoi de la notification %s par e-mail impossible", notification_id)
        return
    Notification.objects.filter(pk=notification_id).update(email_envoye=True)


def notifier(
    destinataires: Iterable[User | None],
    *,
    categorie: str,
    titre: str,
    message: str = "",
    url: str = "",
    niveau: str = NiveauNotification.INFO,
    cle: str = "",
    action: str = "",
) -> list[Notification]:
    """Crée une notification par destinataire actif et retourne celles qui ont été créées.

    ``cle`` : si ce destinataire a déjà reçu une notification avec cette clé, rien n'est
    créé (le rappel n'est envoyé qu'une fois). Les doublons dans ``destinataires`` et les
    valeurs vides sont ignorés. ``action`` : intitulé du bouton qui mène à ``url`` (« Ouvrir » sinon).
    """
    creees: list[Notification] = []
    vus: set[int] = set()
    for utilisateur in destinataires:
        if utilisateur is None or not utilisateur.is_active or utilisateur.pk in vus:
            continue
        vus.add(utilisateur.pk)
        if cle and Notification.all_objects.filter(
            destinataire=utilisateur, cle_unicite=cle
        ).exists():
            continue
        notification = Notification.objects.create(
            destinataire=utilisateur,
            categorie=categorie,
            niveau=niveau,
            titre=titre[:200],
            message=message,
            url=url,
            action=action[:60],
            cle_unicite=cle,
        )
        creees.append(notification)
        if settings.NOTIFICATIONS_EMAIL and utilisateur.email:
            # Import différé : évite un cycle avec tasks.py, qui appelle `envoyer_email` ci-dessus.
            from .tasks import envoyer_email_notification

            transaction.on_commit(lambda pk=notification.pk: envoyer_email_notification.delay(pk))
    return creees


# --- lecture ---


def notifications_de(utilisateur: User, *, non_lues: bool = False) -> QuerySet[Notification]:
    resultat = Notification.objects.filter(destinataire=utilisateur)
    return resultat.filter(lue_le__isnull=True) if non_lues else resultat


def nombre_non_lues(utilisateur: User) -> int:
    return notifications_de(utilisateur, non_lues=True).count()


def marquer_lue(notification: Notification) -> Notification:
    if notification.lue_le is None:
        notification.lue_le = timezone.now()
        notification.save(update_fields=["lue_le", "updated_at"])
    return notification


def marquer_toutes_lues(utilisateur: User) -> int:
    """Marque lues toutes les notifications de l'utilisateur ; retourne leur nombre."""
    return notifications_de(utilisateur, non_lues=True).update(
        lue_le=timezone.now(), updated_at=timezone.now()
    )


__all__ = [
    "CategorieNotification",
    "NiveauNotification",
    "marquer_lue",
    "marquer_toutes_lues",
    "nombre_non_lues",
    "notifications_de",
    "notifier",
    "utilisateurs_du_role",
]
```

- **`notifier(destinataires, ...)`** : crée **une notification par compte actif**, ignore les doublons, les
  valeurs vides et, si une `cle` est fournie, ce que la personne a déjà reçu.
- **`utilisateurs_du_role(*roles)`** : pratique pour cibler « tous les Parc Auto ».
- **`nombre_non_lues`**, **`marquer_lue`**, **`marquer_toutes_lues`** : pour la cloche de l'interface.

## Étape 3 — Les abonnements

#### `apps/notifications/receivers.py`

*582 lignes* — Abonnements de ``notifications`` aux événements métier.

```python
"""Abonnements de ``notifications`` aux événements métier.

Qui est prévenu de quoi (les destinataires suivent les rôles du cahier-des-charges.md:44-55) :

- congé déposé → supérieur hiérarchique (N1), avec une alerte s'il y a une mission prévue ;
- congé validé N1 → RH (N2) ; décision finale, refus ou annulation → l'employé ;
- stock au seuil → PARCAUTO ; surconsommation ou anomalie → PARCAUTO et DIRECTION ;
- mission partie → chargé clientèle attitré du client (à défaut, tous les chargés clientèle) ;
- incident signalé → PARCAUTO et DIRECTION ; check-list avec point KO → PARCAUTO ;
- facture soumise → DIRECTION ; validée → FINANCES et son auteur ; renvoyée → son auteur ;
- devis soumis → FINANCES ; en attente de la direction (montant > seuil) → DIRECTION ;
  validé ou contre-proposé → son auteur ; expiré → son auteur.

Les domaines métier ne connaissent pas ce module : ils émettent des signaux.
"""

from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.billing import signals as billing_signals
from apps.billing.models import SEUIL_VALIDATION_DIRECTION
from apps.core.formats import nombre, pourcentage_signe
from apps.finance import signals as finance_signals
from apps.finance.models import OrigineDemande, StatutDemandeDepense
from apps.fuel.models import NiveauAlerte
from apps.fuel.signals import alerte_consommation
from apps.garage import signals as garage_signals
from apps.garage.models import GraviteIncident
from apps.hr import services as hr_services
from apps.hr import signals as hr_signals
from apps.inventory.signals import seuil_bas_atteint
from apps.missions import services as missions_services
from apps.missions.models import TypeFraisMission
from apps.missions.signals import (
    frais_mission_declare,
    frais_mission_rejete,
    frais_mission_valide_parcauto,
    mission_affectee,
    mission_demarree,
)

from .models import CategorieNotification, NiveauNotification
from .services import notifier, utilisateurs_du_role


def _jour(valeur) -> str:
    return valeur.strftime("%d/%m/%Y")


def _heure(valeur) -> str:
    return timezone.localtime(valeur).strftime("%d/%m/%Y à %H:%M")


def _periode(conge) -> str:
    return f"du {_jour(conge.date_debut)} au {_jour(conge.date_fin)}"


def _jours(n: int) -> str:
    return f"{n} jour{'s' if n > 1 else ''} ouvré{'s' if n > 1 else ''}"


# --- congés ---


@receiver(hr_signals.conge_soumis)
def prevenir_le_validateur_n1(sender, conge, **kwargs):
    employe = conge.employe
    lien = reverse("hr:conges_detail", args=[conge.pk])
    validateur = hr_services.validateur_n1(employe)
    notifier(
        [validateur],
        categorie=CategorieNotification.CONGE,
        niveau=NiveauNotification.ATTENTION,
        titre=f"Demande de congé à valider : {employe.prenom} {employe.nom}",
        message=(
            f"{employe.prenom} {employe.nom} demande {_jours(conge.jours)} {_periode(conge)}. "
            f"Décision attendue avant le {_heure(conge.date_limite_n1)}."
        ),
        url=lien,
    )
    missions = list(
        missions_services.missions_du_personnel_sur_periode(
            employe.pk, conge.date_debut, conge.date_fin
        )
    )
    if missions:
        numeros = ", ".join(m.numero for m in missions)
        notifier(
            [validateur],
            categorie=CategorieNotification.CONGE,
            niveau=NiveauNotification.URGENT,
            titre=f"Mission prévue pendant le congé de {employe.prenom} {employe.nom}",
            message=(
                f"{len(missions)} mission{'s' if len(missions) > 1 else ''} prévue"
                f"{'s' if len(missions) > 1 else ''} {_periode(conge)} : {numeros}. "
                "Vérifiez avec l'exploitation avant de valider."
            ),
            url=lien,
        )


@receiver(hr_signals.conge_valide_n1)
def prevenir_la_rh(sender, conge, **kwargs):
    employe = conge.employe
    notifier(
        hr_services.comptes_rh(sauf=employe),
        categorie=CategorieNotification.CONGE,
        niveau=NiveauNotification.ATTENTION,
        titre=f"Congé à valider en N2 : {employe.prenom} {employe.nom}",
        message=(
            f"Validé par le supérieur hiérarchique : {_jours(conge.jours)} {_periode(conge)}. "
            f"Décision attendue avant le {_heure(conge.date_limite_n2)}."
        ),
        url=reverse("hr:conges_detail", args=[conge.pk]),
    )


@receiver(hr_signals.conge_decide)
def prevenir_l_employe(sender, conge, decision, **kwargs):
    if decision == hr_signals.DECISION_APPROUVE:
        titre = "Votre congé est approuvé"
        message = f"{_jours(conge.jours).capitalize()} {_periode(conge)}."
        niveau = NiveauNotification.INFO
    elif decision == hr_signals.DECISION_REFUSE:
        titre = "Votre demande de congé est refusée"
        message = f"Demande {_periode(conge)}. Motif : {conge.motif_decision or 'non précisé'}."
        niveau = NiveauNotification.ATTENTION
    else:
        titre = "Votre congé approuvé a été annulé"
        message = (
            f"Congé {_periode(conge)} annulé par la RH, les jours vous sont restitués. "
            f"Motif : {conge.motif_decision or 'non précisé'}."
        )
        niveau = NiveauNotification.URGENT
    notifier(
        [conge.employe.utilisateur],
        categorie=CategorieNotification.CONGE,
        niveau=niveau,
        titre=titre,
        message=message,
        url=reverse("hr:conges_detail", args=[conge.pk]),
    )


@receiver(hr_signals.report_demande)
def prevenir_la_rh_du_report(sender, report, **kwargs):
    """Sans cette validation, la demande de report n'est pas recevable (avenant § R7)."""
    employe = report.conge.employe
    notifier(
        hr_services.comptes_rh(sauf=employe),
        categorie=CategorieNotification.CONGE,
        niveau=NiveauNotification.ATTENTION,
        titre=f"Report de congé à valider : {employe.prenom} {employe.nom}",
        message=(
            f"Reprise le {_jour(report.nouvelle_date_fin)} : {_jours(report.jours_restants)} à reverser "
            f"au solde. Motif : {report.motif}"
        ),
        url=reverse("hr:conges_detail", args=[report.conge_id]),
        action="Confirmer le report",
    )


@receiver(hr_signals.report_decide)
def prevenir_l_employe_du_report(sender, report, decision, **kwargs):
    if decision == hr_signals.DECISION_APPROUVE:
        titre = "Votre report de congé est validé"
        message = f"{_jours(report.jours_restants).capitalize()} reversé(s) à votre solde. Vous reprenez le {_jour(report.nouvelle_date_fin)}."
        niveau = NiveauNotification.INFO
    else:
        titre = "Votre demande de report est refusée"
        message = f"Votre congé continue normalement jusqu'au {_jour(report.conge.date_fin)}. Motif : {report.motif_decision or 'non précisé'}."
        niveau = NiveauNotification.ATTENTION
    notifier(
        [report.conge.employe.utilisateur],
        categorie=CategorieNotification.CONGE,
        niveau=niveau,
        titre=titre,
        message=message,
        url=reverse("hr:conges_detail", args=[report.conge_id]),
    )


# --- stock ---


@receiver(seuil_bas_atteint)
def prevenir_du_stock_bas(sender, article, **kwargs):
    notifier(
        utilisateurs_du_role(Role.PARCAUTO),
        categorie=CategorieNotification.STOCK,
        niveau=NiveauNotification.ATTENTION,
        titre=f"Stock bas : {article.designation}",
        message=(
            f"{article.reference} : {article.quantite} en stock pour un seuil minimal "
            f"de {article.seuil_minimal}."
        ),
        url=reverse("inventory:article_detail", args=[article.pk]),
    )


# --- carburant ---


@receiver(alerte_consommation)
def prevenir_de_la_surconsommation(sender, plein, **kwargs):
    grave = plein.niveau_alerte == NiveauAlerte.ROUGE or plein.anomalie
    if plein.niveau_alerte == NiveauAlerte.ROUGE:
        nature = "alerte rouge"
    elif plein.niveau_alerte == NiveauAlerte.JAUNE:
        nature = "alerte jaune"
    elif plein.anomalie:
        nature = "anomalie"
    else:
        nature = "saisie suspecte confirmée"
    camion, chauffeur = plein.vehicule, plein.chauffeur.personnel
    details = [f"{camion.immatriculation}, chauffeur {chauffeur.prenom} {chauffeur.nom}"]
    if plein.consommation is not None:
        details.append(f"{nombre(plein.consommation, 1)} L/100 km")
    if plein.ecart_pct is not None:
        details.append(f"{pourcentage_signe(plein.ecart_pct)} % par rapport à la moyenne")
    notifier(
        utilisateurs_du_role(Role.PARCAUTO, Role.DIRECTION),
        categorie=CategorieNotification.CARBURANT,
        niveau=NiveauNotification.URGENT if grave else NiveauNotification.ATTENTION,
        titre=f"Consommation : {nature} sur {camion.immatriculation}",
        message=" · ".join(details) + ".",
        url=f"{reverse('fuel:liste')}?vehicule={camion.pk}",
    )


# --- missions ---


@receiver(mission_demarree)
def prevenir_du_depart(sender, mission, **kwargs):
    client = mission.client
    destinataires = (
        [client.charge_clientele]
        if client.charge_clientele_id
        else list(utilisateurs_du_role(Role.CHARGE_CLIENTELE))
    )
    chauffeur = mission.chauffeur.personnel
    notifier(
        destinataires,
        categorie=CategorieNotification.MISSION,
        niveau=NiveauNotification.INFO,
        titre=f"En cours de route : {mission.numero}",
        message=(
            f"{client.raison_sociale} : {mission.vehicule.immatriculation} "
            f"({chauffeur.prenom} {chauffeur.nom}) est parti de {mission.lieu_chargement} "
            f"vers {mission.lieu_livraison}."
        ),
        url=reverse("missions:detail", args=[mission.pk]),
    )


@receiver(mission_affectee)
def prevenir_la_finance_d_une_affectation(sender, mission, **kwargs):
    notifier(
        utilisateurs_du_role(Role.FINANCES, Role.RH),
        categorie=CategorieNotification.FRAIS_MISSION,
        niveau=NiveauNotification.INFO,
        titre=f"Mission affectée : {mission.numero}",
        message=(
            f"{mission.client.raison_sociale} : {mission.lieu_chargement} → {mission.lieu_livraison}. "
            "Mouvement de caisse probable (avance de route, dépense prévue)."
        ),
        url=reverse("missions:frais", args=[mission.pk]),
    )


@receiver(frais_mission_declare)
def prevenir_le_parc_auto_d_un_imprevu(sender, frais, **kwargs):
    chauffeur = frais.chauffeur.personnel
    notifier(
        utilisateurs_du_role(Role.PARCAUTO),
        categorie=CategorieNotification.FRAIS_MISSION,
        niveau=NiveauNotification.ATTENTION,
        titre=f"Imprévu signalé : {frais.mission.numero}",
        message=f"{chauffeur.prenom} {chauffeur.nom} : {nombre(frais.montant)} FCFA. À valider.",
        url=reverse("missions:frais", args=[frais.mission_id]),
        action="Examiner",
    )


@receiver(frais_mission_valide_parcauto)
def prevenir_la_finance_d_un_imprevu_valide(sender, frais, **kwargs):
    notifier(
        utilisateurs_du_role(Role.FINANCES, Role.RH),
        categorie=CategorieNotification.FRAIS_MISSION,
        niveau=NiveauNotification.ATTENTION,
        titre=f"Imprévu à confirmer : {frais.mission.numero}",
        message=f"Validé par le Parc Auto : {nombre(frais.montant)} FCFA. Confirmation attendue.",
        url=reverse("missions:frais", args=[frais.mission_id]),
        action="Confirmer",
    )


@receiver(frais_mission_rejete)
def prevenir_de_l_auteur_du_rejet(sender, frais, **kwargs):
    if frais.type_frais == TypeFraisMission.IMPREVU:
        destinataire = frais.chauffeur.personnel.utilisateur if frais.chauffeur_id else None
    else:
        destinataire = frais.saisi_par
    if destinataire is None:
        return
    notifier(
        [destinataire],
        categorie=CategorieNotification.FRAIS_MISSION,
        niveau=NiveauNotification.ATTENTION,
        titre=f"Frais rejeté : {frais.mission.numero}",
        message=f"Motif : {frais.motif_rejet}",
        url=reverse("missions:frais", args=[frais.mission_id]),
    )


# --- facturation ---


ACTION_CONFIRMER_VERSEMENT = "Confirmer le versement"
ACTION_VALIDER_FACTURE = "Examiner et valider"


def _lien_facture(facture) -> str:
    return reverse("billing:facture", args=[facture.pk])


@receiver(billing_signals.facture_a_valider)
def prevenir_la_direction_d_une_facture(sender, facture, **kwargs):
    notifier(
        utilisateurs_du_role(Role.DIRECTION),
        categorie=CategorieNotification.FACTURE,
        niveau=NiveauNotification.ATTENTION,
        titre=f"Facture à valider : {facture.client.raison_sociale}",
        message=(
            f"{nombre(facture.montant_ttc)} FCFA TTC pour la mission {facture.mission.numero}, "
            f"préparée par {facture.cree_par or 'un compte supprimé'}."
        ),
        url=_lien_facture(facture),
        action=ACTION_VALIDER_FACTURE,
    )


@receiver(billing_signals.facture_validee)
def prevenir_de_la_validation_d_une_facture(sender, facture, **kwargs):
    """Facture émise : la FINANCES reçoit un bouton pour **confirmer le versement** quand il arrive (il
    devient alors une entrée de trésorerie) ; son auteur, s'il n'est pas de la FINANCES, est simplement
    prévenu."""
    finances = list(utilisateurs_du_role(Role.FINANCES, Role.RH))
    resume = (
        f"{facture.client.raison_sociale} : {nombre(facture.montant_ttc)} FCFA TTC, "
        f"échéance le {_jour(facture.date_echeance)}."
    )
    notifier(
        finances,
        categorie=CategorieNotification.FACTURE,
        niveau=NiveauNotification.INFO,
        titre=f"Facture {facture.numero} validée : versement à confirmer",
        message=(
            f"{resume} Dès que le versement est reçu, confirmez-le : il sera ajouté en entrée "
            "de trésorerie."
        ),
        url=reverse("finance:versement_confirmer", args=[facture.pk]),
        action=ACTION_CONFIRMER_VERSEMENT,
    )
    if facture.cree_par is not None and facture.cree_par.pk not in {u.pk for u in finances}:
        notifier(
            [facture.cree_par],
            categorie=CategorieNotification.FACTURE,
            niveau=NiveauNotification.INFO,
            titre=f"Facture {facture.numero} validée",
            message=resume,
            url=_lien_facture(facture),
        )


@receiver(billing_signals.facture_refusee)
def prevenir_du_refus_d_une_facture(sender, facture, motif, **kwargs):
    destinataires = (
        [facture.cree_par] if facture.cree_par else utilisateurs_du_role(Role.FINANCES, Role.RH)
    )
    notifier(
        destinataires,
        categorie=CategorieNotification.FACTURE,
        niveau=NiveauNotification.ATTENTION,
        titre=f"Facture renvoyée par la direction : {facture.client.raison_sociale}",
        message=f"Motif : {motif}",
        url=_lien_facture(facture),
    )


# --- devis ---


def _lien_proforma(proforma) -> str:
    return reverse("billing:proforma", args=[proforma.pk])


@receiver(billing_signals.proforma_a_valider)
def prevenir_la_finance_d_un_devis(sender, proforma, **kwargs):
    notifier(
        utilisateurs_du_role(Role.FINANCES, Role.RH),
        categorie=CategorieNotification.PROFORMA,
        niveau=NiveauNotification.ATTENTION,
        titre=f"Devis à valider : {proforma.client.raison_sociale}",
        message=(
            f"{nombre(proforma.montant_ttc)} FCFA TTC pour {proforma.lieu_chargement} → "
            f"{proforma.lieu_livraison}, préparé par {proforma.cree_par or 'un compte supprimé'}."
        ),
        url=_lien_proforma(proforma),
        action="Examiner et valider",
    )


@receiver(billing_signals.proforma_en_attente_direction)
def prevenir_la_direction_d_un_devis(sender, proforma, **kwargs):
    notifier(
        utilisateurs_du_role(Role.DIRECTION),
        categorie=CategorieNotification.PROFORMA,
        niveau=NiveauNotification.ATTENTION,
        titre=f"Devis à valider (montant élevé) : {proforma.client.raison_sociale}",
        message=(
            f"{nombre(proforma.montant_ttc)} FCFA TTC, déjà validé par la finance : "
            f"votre validation est requise au-delà de {nombre(SEUIL_VALIDATION_DIRECTION)} FCFA."
        ),
        url=_lien_proforma(proforma),
        action="Examiner et valider",
    )


@receiver(billing_signals.proforma_validee)
def prevenir_de_la_validation_d_un_devis(sender, proforma, **kwargs):
    if proforma.cree_par is None:
        return
    notifier(
        [proforma.cree_par],
        categorie=CategorieNotification.PROFORMA,
        niveau=NiveauNotification.INFO,
        titre=f"Devis {proforma.numero} validé",
        message=f"{proforma.client.raison_sociale} : {nombre(proforma.montant_ttc)} FCFA TTC. Vous pouvez l'envoyer au client.",
        url=_lien_proforma(proforma),
        action="Envoyer au client",
    )


@receiver(billing_signals.proforma_contre_proposee)
def prevenir_de_la_contre_proposition_d_un_devis(sender, proforma, motif, **kwargs):
    if proforma.cree_par is None:
        return
    notifier(
        [proforma.cree_par],
        categorie=CategorieNotification.PROFORMA,
        niveau=NiveauNotification.ATTENTION,
        titre=f"Devis contesté : {proforma.client.raison_sociale}",
        message=f"Motif : {motif}",
        url=_lien_proforma(proforma),
    )


@receiver(billing_signals.proforma_expiree)
def prevenir_de_l_expiration_d_un_devis(sender, proforma, **kwargs):
    if proforma.cree_par is None:
        return
    notifier(
        [proforma.cree_par],
        categorie=CategorieNotification.PROFORMA,
        niveau=NiveauNotification.ATTENTION,
        titre=f"Devis expiré : {proforma.client.raison_sociale}",
        message=f"Le devis {proforma.numero} n'a pas eu de réponse dans les 30 jours.",
        url=_lien_proforma(proforma),
    )


# --- signalements du chauffeur ---


@receiver(garage_signals.incident_signale)
def prevenir_d_un_incident(sender, incident, **kwargs):
    chauffeur = incident.chauffeur.personnel if incident.chauffeur else None
    auteur = f"{chauffeur.prenom} {chauffeur.nom}" if chauffeur else "un chauffeur"
    detail = f" ({incident.lieu})" if incident.lieu else ""
    notifier(
        utilisateurs_du_role(Role.PARCAUTO, Role.DIRECTION),
        categorie=CategorieNotification.INCIDENT,
        niveau=(
            NiveauNotification.URGENT
            if incident.gravite == GraviteIncident.GRAVE
            else NiveauNotification.ATTENTION
        ),
        titre=f"{incident.get_type_incident_display()} signalé : {incident.vehicule.immatriculation}",
        message=f"{auteur}{detail} : {incident.description}",
        url=reverse("garage:incident", args=[incident.pk]),
    )


@receiver(garage_signals.checklist_anomalie)
def prevenir_d_une_anomalie_de_checklist(sender, checklist, **kwargs):
    ko = [p["libelle"] for p in checklist.points if not p["ok"]]
    notifier(
        utilisateurs_du_role(Role.PARCAUTO),
        categorie=CategorieNotification.INCIDENT,
        niveau=NiveauNotification.ATTENTION,
        titre=f"Check-list : {len(ko)} point{'s' if len(ko) > 1 else ''} KO sur {checklist.vehicule.immatriculation}",
        message=f"Mission {checklist.mission.numero} : " + ", ".join(ko) + ".",
        url=reverse("garage:checklists"),
    )


# --- dépenses du parc auto pré-approuvées (R2) ---


def _lien_demande(demande) -> str:
    return reverse("finance:demande", args=[demande.pk])


@receiver(finance_signals.demande_soumise)
def prevenir_la_direction_d_une_demande(sender, demande, **kwargs):
    if demande.origine == OrigineDemande.DEPASSEMENT_ENVELOPPE:
        titre = f"Enveloppe dépassée : {demande.get_categorie_display()}"
        message = f"{nombre(demande.montant_estime)} FCFA au-delà du plafond. Aucune autre dépense de ce type tant que ce n'est pas décidé."
    else:
        titre = f"Demande de dépense : {demande.get_categorie_display()}"
        message = f"{demande.demandeur or 'Le Parc Auto'} demande {nombre(demande.montant_estime)} FCFA. {demande.motif}"
    notifier(
        utilisateurs_du_role(Role.DIRECTION),
        categorie=CategorieNotification.DEMANDE_DEPENSE,
        niveau=NiveauNotification.ATTENTION,
        titre=titre,
        message=message,
        url=_lien_demande(demande),
        action="Examiner",
    )


@receiver(finance_signals.demande_decidee)
def prevenir_de_la_decision_d_une_demande(sender, demande, **kwargs):
    if demande.origine == OrigineDemande.DEPASSEMENT_ENVELOPPE:
        destinataires = utilisateurs_du_role(Role.PARCAUTO)
    elif demande.demandeur:
        destinataires = [demande.demandeur]
    else:
        destinataires = utilisateurs_du_role(Role.PARCAUTO)
    valide = demande.statut == StatutDemandeDepense.VALIDEE
    notifier(
        destinataires,
        categorie=CategorieNotification.DEMANDE_DEPENSE,
        niveau=NiveauNotification.INFO if valide else NiveauNotification.ATTENTION,
        titre=f"Demande {demande.numero} {'validée' if valide else 'refusée'}",
        message=demande.motif_refus if not valide else "Le mécanisme automatique reprend pour cette catégorie.",
        url=_lien_demande(demande),
    )


@receiver(finance_signals.ordre_a_executer)
def prevenir_la_finance_d_un_ordre(sender, ordre, **kwargs):
    notifier(
        utilisateurs_du_role(Role.FINANCES, Role.RH),
        categorie=CategorieNotification.DEMANDE_DEPENSE,
        niveau=NiveauNotification.ATTENTION,
        titre=f"Ordre à exécuter : {ordre.numero}",
        message=f"{nombre(ordre.montant_valide)} FCFA validés par la direction.",
        url=_lien_demande(ordre.demande),
        action="Exécuter",
    )


@receiver(finance_signals.ordre_depassement)
def prevenir_la_direction_d_un_depassement(sender, ordre, **kwargs):
    notifier(
        utilisateurs_du_role(Role.DIRECTION),
        categorie=CategorieNotification.DEMANDE_DEPENSE,
        niveau=NiveauNotification.URGENT,
        titre=f"Dépassement de plus de 10 % : {ordre.numero}",
        message=(
            f"Montant réel {nombre(ordre.montant_reel)} FCFA contre {nombre(ordre.montant_valide)} FCFA validés. "
            "Revalidation attendue avant exécution."
        ),
        url=_lien_demande(ordre.demande),
        action="Revalider",
    )
```

C'est ici que se lit *qui est prévenu de quoi*. Repérez le motif : chaque fonction reçoit un événement
(`conge_soumis`, `alerte_consommation`, `mission_demarree`…), calcule les destinataires **avec les services
des autres apps** puis appelle `notifier`. Notez `send_robust` côté émetteur : si un récepteur plante, l'action
métier (un plein, un départ de mission) **n'échoue pas**.

## Étape 4 — Les tâches du jour

#### `apps/notifications/taches.py`

*177 lignes* — Tâches quotidiennes : alertes préventives, rappels de validation, statuts des congés.

```python
"""Tâches quotidiennes : alertes préventives, rappels de validation, statuts des congés.

À exécuter une fois par jour (``python manage.py taches_quotidiennes``). Chaque alerte
n'est envoyée qu'une fois par destinataire (``cle_unicite``) : relancer la commande le même
jour, ou tous les jours, ne renvoie pas les mêmes messages. Ces fonctions sont prévues pour
être appelées telles quelles par Celery Beat au déploiement (architecture.md:67).
"""

from __future__ import annotations

from datetime import date, datetime

from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.billing import services as billing_services
from apps.core.formats import nombre
from apps.core.services import etat_echeance
from apps.drivers import services as drivers_services
from apps.drivers.models import StatutChauffeur
from apps.fleet import services as fleet_services
from apps.hr import services as hr_services
from apps.hr.models import Conge, StatutConge

from .models import CategorieNotification, NiveauNotification
from .services import notifier, utilisateurs_du_role


def _phrase_echeance(etat: str, restants: int | None, expiration: date) -> tuple[str, str]:
    """(titre court, niveau) selon l'état de l'échéance."""
    if etat == "EXPIRE":
        return f"expiré depuis le {expiration.strftime('%d/%m/%Y')}", NiveauNotification.URGENT
    jours = "aujourd'hui" if restants == 0 else f"dans {restants} jour{'s' if restants > 1 else ''}"
    return f"expire {jours} ({expiration.strftime('%d/%m/%Y')})", NiveauNotification.ATTENTION


def alerter_documents_vehicules(*, aujourd_hui: date | None = None) -> int:
    """Documents réglementaires des camions à renouveler (30 jours) ou expirés."""
    aujourd_hui = aujourd_hui or timezone.localdate()
    destinataires = list(utilisateurs_du_role(Role.PARCAUTO))
    crees = 0
    for document in fleet_services.documents_a_renouveler(aujourd_hui=aujourd_hui):
        etat, restants = etat_echeance(document.date_expiration, aujourd_hui=aujourd_hui)
        phrase, niveau = _phrase_echeance(etat, restants, document.date_expiration)
        vehicule = document.vehicule
        crees += len(
            notifier(
                destinataires,
                categorie=CategorieNotification.DOCUMENT,
                niveau=niveau,
                titre=f"{document.get_type_document_display()} de {vehicule.immatriculation} : {phrase}",
                message="À renouveler pour garder ce camion en règle.",
                url=reverse("fleet:detail", args=[vehicule.pk]),
                cle=f"doc:{document.pk}:{document.date_expiration.isoformat()}:{etat}",
            )
        )
    return crees


def alerter_echeances_chauffeurs(*, aujourd_hui: date | None = None) -> int:
    """Permis et visites médicales des chauffeurs à renouveler ou expirés."""
    aujourd_hui = aujourd_hui or timezone.localdate()
    destinataires = list(utilisateurs_du_role(Role.RH, Role.DIRECTION))
    crees = 0
    chauffeurs = drivers_services.chauffeurs_a_renouveler(aujourd_hui=aujourd_hui).exclude(
        statut=StatutChauffeur.INACTIF
    )
    for chauffeur in chauffeurs:
        for code, echeance in (
            ("permis", chauffeur.date_expiration_permis),
            ("visite", chauffeur.date_expiration_visite_medicale),
        ):
            if echeance is None:
                continue
            etat, restants = etat_echeance(echeance, aujourd_hui=aujourd_hui)
            if etat not in ("A_RENOUVELER", "EXPIRE"):
                continue
            phrase, niveau = _phrase_echeance(etat, restants, echeance)
            nom = f"{chauffeur.personnel.prenom} {chauffeur.personnel.nom}"
            libelle = "Permis" if code == "permis" else "Visite médicale"
            crees += len(
                notifier(
                    destinataires,
                    categorie=CategorieNotification.DOCUMENT,
                    niveau=niveau,
                    titre=f"{libelle} de {nom} : {phrase}",
                    message="Un chauffeur sans permis ou visite valide ne peut pas être affecté.",
                    url=reverse("drivers:detail", args=[chauffeur.pk]),
                    cle=f"chauffeur:{chauffeur.pk}:{code}:{echeance.isoformat()}:{etat}",
                )
            )
    return crees


def relancer_validations_en_retard(*, maintenant: datetime | None = None) -> int:
    """Rappel au validateur dont le délai (48 h en N1, 24 h en N2) est dépassé."""
    maintenant = maintenant or timezone.now()
    crees = 0
    en_retard = Conge.objects.select_related("employe__superieur", "employe__utilisateur")
    for conge in en_retard.filter(statut=StatutConge.DEMANDE, date_limite_n1__lt=maintenant):
        crees += len(
            notifier(
                [hr_services.validateur_n1(conge.employe)],
                categorie=CategorieNotification.CONGE,
                niveau=NiveauNotification.URGENT,
                titre=f"Validation N1 en retard : {conge.employe.prenom} {conge.employe.nom}",
                message="Le délai de 48 h est dépassé.",
                url=reverse("hr:conges_detail", args=[conge.pk]),
                cle=f"conge-retard:{conge.pk}:N1",
            )
        )
    for conge in en_retard.filter(
        statut=StatutConge.VALIDATION_N1, date_limite_n2__lt=maintenant
    ):
        crees += len(
            notifier(
                hr_services.comptes_rh(sauf=conge.employe),
                categorie=CategorieNotification.CONGE,
                niveau=NiveauNotification.URGENT,
                titre=f"Validation N2 en retard : {conge.employe.prenom} {conge.employe.nom}",
                message="Le délai de 24 h est dépassé.",
                url=reverse("hr:conges_detail", args=[conge.pk]),
                cle=f"conge-retard:{conge.pk}:N2",
            )
        )
    return crees


def alerter_factures_echues(*, aujourd_hui: date | None = None) -> int:
    """Factures émises non soldées dont l'échéance est dépassée : FINANCES et DIRECTION.

    Une seule alerte par facture et par date d'échéance (le montant restant peut évoluer).
    """
    aujourd_hui = aujourd_hui or timezone.localdate()
    finances = list(utilisateurs_du_role(Role.FINANCES, Role.RH))
    direction = list(utilisateurs_du_role(Role.DIRECTION))
    crees = 0
    for facture in billing_services.factures_echues(aujourd_hui):
        retard = (aujourd_hui - facture.date_echeance).days
        commun = dict(
            categorie=CategorieNotification.FACTURE,
            niveau=NiveauNotification.URGENT,
            titre=f"Facture {facture.numero} échue : {facture.client.raison_sociale}",
            message=(
                f"Reste à recouvrer : {nombre(facture.reste)} FCFA, "
                f"échue depuis {retard} jour{'s' if retard > 1 else ''}."
            ),
            cle=f"facture-echue:{facture.pk}:{facture.date_echeance.isoformat()}",
        )
        # La FINANCES peut confirmer le versement d'un clic ; la DIRECTION consulte la facture.
        crees += len(
            notifier(
                finances,
                url=reverse("finance:versement_confirmer", args=[facture.pk]),
                action="Confirmer le versement",
                **commun,
            )
        )
        crees += len(notifier(direction, url=reverse("billing:facture", args=[facture.pk]), **commun))
    return crees


def executer_taches_quotidiennes(*, aujourd_hui: date | None = None) -> dict[str, int]:
    """Lance toutes les tâches du jour et retourne leurs compteurs."""
    aujourd_hui = aujourd_hui or timezone.localdate()
    resultat = {
        "documents_vehicules": alerter_documents_vehicules(aujourd_hui=aujourd_hui),
        "echeances_chauffeurs": alerter_echeances_chauffeurs(aujourd_hui=aujourd_hui),
        "validations_en_retard": relancer_validations_en_retard(),
        "factures_echues": alerter_factures_echues(aujourd_hui=aujourd_hui),
        "proformas_expirees": billing_services.expirer_proformas(aujourd_hui=aujourd_hui),
    }
    conges = hr_services.synchroniser_statuts_conges(aujourd_hui=aujourd_hui)
    resultat["conges_demarres"] = conges["demarres"]
    resultat["conges_termines"] = conges["termines"]
    return resultat
```

Cinq tâches indépendantes, regroupées par `executer_taches_quotidiennes` :

1. **`alerter_documents_vehicules`** : documents à renouveler à 30 jours, puis expirés (une alerte à chaque
   changement d'état).
2. **`alerter_echeances_chauffeurs`** : permis et visite médicale.
3. **`relancer_validations_en_retard`** : rappel au validateur quand le délai (48 h pour le N1, 24 h pour le N2)
   est dépassé.
4. **`alerter_factures_echues`**.
5. Le passage des congés à « En cours » / « Terminé » (`hr.synchroniser_statuts_conges`).

#### `apps/notifications/management/commands/taches_quotidiennes.py`

*17 lignes*

```python
from django.core.management.base import BaseCommand

from apps.notifications import taches


class Command(BaseCommand):
    help = (
        "Tâches du jour : alertes de documents et d'échéances, rappels de validation de "
        "congés, statuts des congés. Sans danger si relancée : aucune alerte en double. "
        "En production, celery beat lance la même fonction chaque jour (voir CELERY_BEAT_SCHEDULE) ; "
        "cette commande reste utilisable manuellement ou par un cron de secours sans Celery."
    )

    def handle(self, *args, **options):
        resultat = taches.executer_taches_quotidiennes()
        for nom, valeur in resultat.items():
            self.stdout.write(f"{nom.replace('_', ' '):<24} {valeur}")
```

## Étape 5 — Administration, démarrage et README

#### `apps/notifications/admin.py`

*13 lignes*

```python
from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("titre", "destinataire", "categorie", "niveau", "lue_le", "created_at")
    list_filter = ("categorie", "niveau")
    search_fields = ("titre", "destinataire__username")

    def get_queryset(self, request):
        return Notification.all_objects.all()
```

#### `apps/notifications/apps.py`

*10 lignes*

```python
from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.notifications'
    label = 'notifications'

    def ready(self):
        from . import receivers  # noqa: F401 - branche les abonnements aux événements métier
```

#### `apps/notifications/README.md`

*42 lignes* — notifications

```markdown
# notifications

Rôle : prévenir les bons utilisateurs au bon moment — cahier-des-charges.md:137, 215, 221,
231-232, 253 ; architecture.md:269-338. Couche haute : elle s'abonne aux événements des apps
métier, qui ne la connaissent pas.

Entité : `Notification` (destinataire, catégorie, niveau, titre, message, lien, `action`, lue le,
`cle_unicite`). `action` est le libellé d'un bouton facultatif (« Confirmer le versement ») : la liste
affiche un bouton vert qui marque la notification lue puis mène au lien. `services.notifier(destinataires, ...)` crée une notification par compte actif ;
avec `cle`, un destinataire ne reçoit qu'une fois le même message (rappels quotidiens).

Qui est prévenu de quoi (`receivers.py`) :
- congé déposé → supérieur hiérarchique (N1), plus une alerte urgente s'il y a une mission
  prévue sur la période ; validé en N1 → RH ; approuvé, refusé ou annulé → l'employé ;
- stock au seuil → PARCAUTO ; surconsommation, anomalie ou saisie suspecte → PARCAUTO et DIRECTION ;
- mission partie → chargé clientèle attitré du client (à défaut, tous les chargés clientèle) ;
- facture soumise → DIRECTION ; validée → FINANCES (avec le bouton « Confirmer le versement », voir
  `finance`) et son auteur (simple information) ; renvoyée → son auteur ;
  facture échue (tâche du jour) → FINANCES et DIRECTION, une fois par facture.

Tâches du jour (`taches.py`, commande `taches_quotidiennes`) : documents des camions et
permis / visites des chauffeurs à 30 jours puis expirés (une alerte à chaque changement d'état),
rappel au validateur quand le délai de 48 h (N1) ou 24 h (N2) est dépassé, et passage des
congés à « En cours » / « Terminé ».

Canaux : toujours dans l'application (cloche + page `/notifications/`) ; en plus par e-mail si
`NOTIFICATIONS_EMAIL` est actif. Un e-mail en échec est journalisé sans jamais bloquer
l'opération métier, et un récepteur en erreur n'empêche pas non plus une validation de congé,
un plein ou un départ de mission (`send_robust`).

Tâches asynchrones (`tasks.py`, étape 7 lot 2, ADR-004) : `envoyer_email_notification` (l'envoi
d'un e-mail, déclenché après le commit par `notifier`) et `executer_taches_quotidiennes` (relais
Celery de `taches.py`, planifiée chaque jour par `CELERY_BEAT_SCHEDULE`). En développement et en
test, `CELERY_TASK_ALWAYS_EAGER` les exécute immédiatement, dans le même processus, sans courtier :
rien à installer pour développer ou tester. En production, un `celery worker` (et `celery beat`
pour la planification) doivent tourner à côté de l'application, contre le Redis de `REDIS_URL`.

Reste à faire :
- **SMS (Twilio) et notifications push (Firebase)** : demandent des comptes externes.
- Notification du client à l'expédition (« en cours de route ») : le CDC ne dit pas à qui ;
  seul le chargé clientèle est prévenu pour l'instant.
- Préférences de notification par utilisateur.
```

#### `apps/notifications/tasks.py`

*25 lignes* — Tâches Celery de l'application (étape 7 lot 2, ADR-004 architecture.md:493-497).

```python
"""Tâches Celery de l'application (étape 7 lot 2, ADR-004 architecture.md:493-497).

En développement et en test, ``CELERY_TASK_ALWAYS_EAGER`` fait exécuter ces tâches immédiatement,
dans le même processus : `.delay()` se comporte comme un appel de fonction normal. Rien ne change
donc pour les tests existants du module.
"""

from __future__ import annotations

from celery import shared_task

from . import services, taches


@shared_task
def envoyer_email_notification(notification_id: int) -> None:
    """Envoie par e-mail la notification déjà créée — hors du chemin critique de la requête."""
    services.envoyer_email(notification_id)


@shared_task
def executer_taches_quotidiennes() -> dict[str, int]:
    """Planifiée chaque jour par celery beat (voir CELERY_BEAT_SCHEDULE) ; idempotente, comme la
    commande `taches_quotidiennes` qui appelle la même fonction (cron de secours sans Celery)."""
    return taches.executer_taches_quotidiennes()
```

#### `apps/notifications/tests/test_receivers_demandes.py`

*69 lignes* — Qui est prévenu de quoi pour les dépenses du parc auto pré-approuvées (R2).

```python
"""Qui est prévenu de quoi pour les dépenses du parc auto pré-approuvées (R2)."""

from decimal import Decimal

import pytest

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing.models import CategorieDepense, ModePaiement
from apps.finance import demandes as services
from apps.notifications.models import CategorieNotification, Notification

pytestmark = pytest.mark.django_db


def _de(utilisateur):
    return list(Notification.objects.filter(destinataire=utilisateur).order_by("pk"))


def test_la_direction_est_prevenue_d_une_demande_manuelle():
    direction = UserFactory(role=Role.DIRECTION)

    services.soumettre_demande(
        UserFactory(role=Role.PARCAUTO), categorie=CategorieDepense.PIECES,
        montant_estime=Decimal("150000"), motif="Pièce rare",
    )

    (notification,) = _de(direction)
    assert notification.categorie == CategorieNotification.DEMANDE_DEPENSE


def test_le_demandeur_est_prevenu_de_la_validation():
    parcauto = UserFactory(role=Role.PARCAUTO)
    demande = services.soumettre_demande(
        parcauto, categorie=CategorieDepense.PIECES, montant_estime=Decimal("150000"), motif="x"
    )

    services.valider_demande(demande, UserFactory(role=Role.DIRECTION))

    notifications = [n for n in _de(parcauto) if n.categorie == CategorieNotification.DEMANDE_DEPENSE]
    assert any("validée" in n.titre for n in notifications)


def test_la_finance_est_prevenue_de_l_ordre_a_executer():
    finance = UserFactory(role=Role.FINANCES)
    demande = services.soumettre_demande(
        UserFactory(role=Role.PARCAUTO), categorie=CategorieDepense.PIECES, montant_estime=Decimal("150000"), motif="x"
    )

    services.valider_demande(demande, UserFactory(role=Role.DIRECTION))

    (notification,) = _de(finance)
    assert notification.categorie == CategorieNotification.DEMANDE_DEPENSE
    assert "à exécuter" in notification.titre.lower()


def test_la_direction_est_prevenue_d_un_depassement_a_l_execution():
    direction = UserFactory(role=Role.DIRECTION)
    demande = services.soumettre_demande(
        UserFactory(role=Role.PARCAUTO), categorie=CategorieDepense.PIECES, montant_estime=Decimal("100000"), motif="x"
    )
    services.valider_demande(demande, direction)
    ordre = demande.ordre_decaissement

    with pytest.raises(Exception):
        services.executer_ordre(ordre, UserFactory(role=Role.FINANCES), mode_paiement=ModePaiement.ESPECES, montant_reel=Decimal("150000"))

    notifications = [n for n in _de(direction) if n.categorie == CategorieNotification.DEMANDE_DEPENSE]
    assert any("dépassement" in n.titre.lower() for n in notifications)
```

#### `apps/notifications/tests/test_receivers_frais_mission.py`

*90 lignes* — Qui est prévenu de quoi pour la prévision de trésorerie des missions (R4).

```python
"""Qui est prévenu de quoi pour la prévision de trésorerie des missions (R4)."""

from decimal import Decimal
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.missions import services as missions_services
from apps.missions import terrain as missions_terrain
from apps.missions.models import TypeFraisMission
from apps.missions.tests.test_frais_mission import _chauffeur, _finances, _mission_affectee, _parcauto
from apps.notifications.models import CategorieNotification, Notification

pytestmark = pytest.mark.django_db


def _de(utilisateur):
    return list(Notification.objects.filter(destinataire=utilisateur).order_by("pk"))


def _preuve():
    return SimpleUploadedFile("p.jpg", BytesIO(b"x").read(), content_type="image/jpeg")


def test_la_finance_est_prevenue_d_une_affectation():
    finance = UserFactory(role=Role.FINANCES)
    from apps.drivers.tests.factories import ChauffeurFactory
    from apps.fleet.tests.factories import VehiculeFactory
    from apps.missions.models import StatutMission
    from apps.missions.tests.factories import MissionFactory

    mission = MissionFactory(statut=StatutMission.PLANIFIEE)

    missions_services.affecter_mission(mission, vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory())

    (notification,) = _de(finance)
    assert notification.categorie == CategorieNotification.FRAIS_MISSION


def test_le_parc_auto_est_prevenu_d_un_imprevu_declare():
    parcauto = UserFactory(role=Role.PARCAUTO)
    chauffeur = _chauffeur()
    mission = _mission_affectee(chauffeur)

    missions_terrain.declarer_imprevu(mission, chauffeur, montant=Decimal("9000"), justificatif=_preuve())

    (notification,) = _de(parcauto)
    assert notification.categorie == CategorieNotification.FRAIS_MISSION
    assert mission.numero in notification.titre


def test_la_finance_est_prevenue_apres_la_validation_du_parc_auto():
    finance = UserFactory(role=Role.FINANCES)
    chauffeur = _chauffeur()
    mission = _mission_affectee(chauffeur)
    frais = missions_terrain.declarer_imprevu(mission, chauffeur, montant=Decimal("9000"), justificatif=_preuve())

    missions_terrain.valider_parcauto(frais, _parcauto())

    (notification,) = _de(finance)
    assert notification.categorie == CategorieNotification.FRAIS_MISSION
    assert "Parc Auto" in notification.message


def test_l_auteur_est_prevenu_du_rejet_d_une_avance():
    mission = _mission_affectee()
    parcauto = _parcauto()
    frais = missions_terrain.planifier_frais(
        mission, parcauto, type_frais=TypeFraisMission.AVANCE_ROUTE, montant=Decimal("50000")
    )

    missions_terrain.rejeter(frais, _finances(), motif="Montant excessif")

    (notification,) = _de(parcauto)
    assert "Montant excessif" in notification.message


def test_le_chauffeur_est_prevenu_du_rejet_de_son_imprevu():
    chauffeur = _chauffeur()
    mission = _mission_affectee(chauffeur)
    frais = missions_terrain.declarer_imprevu(mission, chauffeur, montant=Decimal("9000"), justificatif=_preuve())

    missions_terrain.rejeter(frais, _parcauto(), motif="Aucune preuve valable")

    utilisateur_chauffeur = chauffeur.personnel.utilisateur
    (notification,) = _de(utilisateur_chauffeur)
    assert "Aucune preuve valable" in notification.message
```

#### `apps/notifications/tests/test_receivers_proforma.py`

*72 lignes* — Qui est prévenu de quoi pour un devis (R5) : finance, direction, chargé clientèle.

```python
"""Qui est prévenu de quoi pour un devis (R5) : finance, direction, chargé clientèle."""

from decimal import Decimal

import pytest

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services
from apps.billing.models import SEUIL_VALIDATION_DIRECTION
from apps.billing.tests.helpers import JOUR, charge_clientele, direction, finances, proforma_soumise
from apps.notifications.models import CategorieNotification, Notification

pytestmark = pytest.mark.django_db


def _de(utilisateur):
    return list(Notification.objects.filter(destinataire=utilisateur).order_by("pk"))


def test_la_finance_est_prevenue_d_un_devis_soumis():
    finance = UserFactory(role=Role.FINANCES)
    proforma = proforma_soumise()

    (notification,) = _de(finance)
    assert notification.categorie == CategorieNotification.PROFORMA
    assert proforma.client.raison_sociale in notification.titre


def test_la_direction_est_prevenue_au_dela_du_seuil():
    responsable = UserFactory(role=Role.DIRECTION)
    proforma = proforma_soumise(prix=str(SEUIL_VALIDATION_DIRECTION))

    services.valider_proforma(proforma, finances(), aujourd_hui=JOUR)

    (notification,) = _de(responsable)
    assert notification.categorie == CategorieNotification.PROFORMA
    assert "direction" in notification.titre.lower() or "élevé" in notification.titre.lower()


def test_l_auteur_est_prevenu_de_la_validation():
    auteur = charge_clientele()
    proforma = proforma_soumise(acteur=auteur)

    services.valider_proforma(proforma, finances(), aujourd_hui=JOUR)

    notifications = _de(auteur)
    assert any(n.categorie == CategorieNotification.PROFORMA and proforma.numero in n.titre for n in notifications)


def test_l_auteur_est_prevenu_d_une_contre_proposition():
    auteur = charge_clientele()
    proforma = proforma_soumise(acteur=auteur)

    services.contre_proposer_proforma(proforma, finances(), motif="Prix trop bas")

    notifications = [n for n in _de(auteur) if n.categorie == CategorieNotification.PROFORMA]
    assert notifications and "Prix trop bas" in notifications[-1].message


def test_l_auteur_est_prevenu_de_l_expiration():
    auteur = charge_clientele()
    proforma = proforma_soumise(acteur=auteur)
    services.valider_proforma(proforma, finances(), aujourd_hui=JOUR)
    services.envoyer_proforma_au_client(proforma, auteur, aujourd_hui=JOUR)

    from datetime import timedelta

    services.expirer_proformas(aujourd_hui=JOUR + timedelta(days=31))

    notifications = [n for n in _de(auteur) if n.categorie == CategorieNotification.PROFORMA]
    assert any("expiré" in n.titre.lower() for n in notifications)
```

#### `apps/notifications/tests/test_tasks.py`

*50 lignes* — Les tâches Celery ne sont que de minces relais : elles délèguent à `services` et `taches`.

```python
"""Les tâches Celery ne sont que de minces relais : elles délèguent à `services` et `taches`.

En test, `CELERY_TASK_ALWAYS_EAGER` fait exécuter `.delay()` immédiatement (config/settings/base.py) :
pas besoin d'un vrai courtier Redis pour ces tests.
"""

import pytest

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.notifications import tasks
from apps.notifications.models import Notification
from apps.notifications.services import notifier

pytestmark = pytest.mark.django_db


def test_executer_taches_quotidiennes_delegue_a_la_fonction_idempotente(monkeypatch):
    appels = []
    monkeypatch.setattr(tasks.taches, "executer_taches_quotidiennes", lambda: appels.append(1) or {"documents vehicules": 0})

    resultat = tasks.executer_taches_quotidiennes()

    assert resultat == {"documents vehicules": 0}
    assert appels == [1]


def test_envoyer_email_notification_delegue_au_service(monkeypatch):
    appels = []
    monkeypatch.setattr(tasks.services, "envoyer_email", lambda pk: appels.append(pk))

    tasks.envoyer_email_notification(42)

    assert appels == [42]


def test_notifier_declenche_la_tache_par_e_mail_apres_commit(
    settings, django_capture_on_commit_callbacks, monkeypatch
):
    """Intégration : notifier() -> on_commit -> tâche Celery (eager) -> envoi réel."""
    settings.NOTIFICATIONS_EMAIL = True
    destinataire = UserFactory(role=Role.RH, email="rh@example.com")
    appels = []
    monkeypatch.setattr(tasks.services, "envoyer_email", lambda pk: appels.append(pk))

    with django_capture_on_commit_callbacks(execute=True):
        creees = notifier([destinataire], categorie="CONGE", titre="Essai tâche")

    notification = Notification.objects.get(pk=creees[0].pk)
    assert appels == [notification.pk]
```

Les **tests** de `notifications` sont nombreux (récepteurs, tâches, écrans) : ils sont présentés dans les
chapitres où leurs dépendances existent (20, 23, 24, 25 et 26).

## Étape 6 — Déclarer l'application et migrer

#### `config/settings/base.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/settings/base.py (avant)
+++ config/settings/base.py (après)
@@ -65,4 +65,5 @@
     "apps.billing",
     "apps.finance",
+    "apps.notifications",
 ]
 
```

```bash
python manage.py makemigrations notifications
python manage.py migrate
```

**Résultat attendu :** `Create model Notification`, puis `Applying notifications.0001_initial... OK`.

## Vérifier le chapitre

```bash
python manage.py check
```

**Essai 1 : une notification, et un rappel qui n'est envoyé qu'une fois** (avec le compte `demo_rh` du chapitre 6) :

```bash
python manage.py shell -c "from apps.accounts.models import User; from apps.notifications import services as s; u = User.objects.get(username='demo_rh'); s.notifier([u], categorie='CONGE', titre='Essai', cle='essai-1'); s.notifier([u], categorie='CONGE', titre='Essai', cle='essai-1'); print(s.nombre_non_lues(u))"
```

**Résultat attendu :** `1` (le second appel est ignoré grâce à la clé).

**Essai 2 : les tâches du jour.**

```bash
python manage.py taches_quotidiennes
```

**Résultat attendu :** six lignes de compteurs (`documents vehicules`, `echeances chauffeurs`,
`validations en retard`, `factures echues`, `conges demarres`, `conges termines`), toutes à `0` sur une base
qui ne contient encore rien d'échu.

## Ce qu'il faut retenir

- Le module qui **prévient** ne doit pas être connu de ceux qui **agissent** : les **signaux** inversent la
  dépendance.
- Une tâche répétée chaque jour doit être **idempotente** (rejouable sans effet en double) : d'où la clé
  d'unicité.
- Une erreur dans un **effet secondaire** (e-mail, notification) ne doit **jamais** annuler l'action principale.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 15 : app notifications (abonnements aux événements, tâches quotidiennes)"
```

> **Fin de la première phase.** Vous avez terminé le « cerveau » : toutes les règles métier existent et sont
> testées. Le chapitre suivant commence le « visage » : les écrans.

---

[← Chapitre 14](14-finance.md) · [Sommaire](README.md) · [Chapitre 16 →](16-interface.md)
