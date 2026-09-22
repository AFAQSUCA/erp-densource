# Chapitre 15 — Les notifications : l'app notifications

> 12 fichier(s) dans ce chapitre, 741 lignes de code.

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

*70 lignes*

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
    categorie = models.CharField(_("catégorie"), max_length=12, choices=CategorieNotification.choices)
    niveau = models.CharField(
        _("niveau"),
        max_length=10,
        choices=NiveauNotification.choices,
        default=NiveauNotification.INFO,
    )
    titre = models.CharField(_("titre"), max_length=200)
    message = models.TextField(_("message"), blank=True)
    url = models.CharField(_("lien"), max_length=300, blank=True)
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

*123 lignes* — Envoi et lecture des notifications.

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


def _envoyer_email(notification_id: int) -> None:
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
) -> list[Notification]:
    """Crée une notification par destinataire actif et retourne celles qui ont été créées.

    ``cle`` : si ce destinataire a déjà reçu une notification avec cette clé, rien n'est
    créé (le rappel n'est envoyé qu'une fois). Les doublons dans ``destinataires`` et les
    valeurs vides sont ignorés.
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
            cle_unicite=cle,
        )
        creees.append(notification)
        if settings.NOTIFICATIONS_EMAIL and utilisateur.email:
            transaction.on_commit(lambda pk=notification.pk: _envoyer_email(pk))
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

*293 lignes* — Abonnements de ``notifications`` aux événements métier.

```python
"""Abonnements de ``notifications`` aux événements métier.

Qui est prévenu de quoi (les destinataires suivent les rôles du cahier-des-charges.md:44-55) :

- congé déposé → supérieur hiérarchique (N1), avec une alerte s'il y a une mission prévue ;
- congé validé N1 → RH (N2) ; décision finale, refus ou annulation → l'employé ;
- stock au seuil → PARCAUTO ; surconsommation ou anomalie → PARCAUTO et DIRECTION ;
- mission partie → chargé clientèle attitré du client (à défaut, tous les chargés clientèle) ;
- incident signalé → PARCAUTO et DIRECTION ; check-list avec point KO → PARCAUTO ;
- facture soumise → DIRECTION ; validée → FINANCES et son auteur ; renvoyée → son auteur.

Les domaines métier ne connaissent pas ce module : ils émettent des signaux.
"""

from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.billing import signals as billing_signals
from apps.core.formats import nombre, pourcentage_signe
from apps.fuel.models import NiveauAlerte
from apps.fuel.signals import alerte_consommation
from apps.garage import signals as garage_signals
from apps.garage.models import GraviteIncident
from apps.hr import services as hr_services
from apps.hr import signals as hr_signals
from apps.inventory.signals import seuil_bas_atteint
from apps.missions import services as missions_services
from apps.missions.signals import mission_demarree

from .models import CategorieNotification, NiveauNotification
from .services import notifier, utilisateurs_du_role


def _jour(valeur) -> str:
    return valeur.strftime("%d/%m/%Y")


def _heure(valeur) -> str:
    return timezone.localtime(valeur).strftime("%d/%m/%Y à %H:%M")


def _periode(conge) -> str:
    return f"du {_jour(conge.date_debut)} au {_jour(conge.date_fin)}"


def _jours(n: int) -> str:
    return f"{n} jour{'s' if n > 1 else ''} ouvrable{'s' if n > 1 else ''}"


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


# --- facturation ---


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
    )


@receiver(billing_signals.facture_validee)
def prevenir_de_la_validation_d_une_facture(sender, facture, **kwargs):
    destinataires = list(utilisateurs_du_role(Role.FINANCES))
    destinataires.append(facture.cree_par)
    notifier(
        destinataires,
        categorie=CategorieNotification.FACTURE,
        niveau=NiveauNotification.INFO,
        titre=f"Facture {facture.numero} validée",
        message=(
            f"{facture.client.raison_sociale} : {nombre(facture.montant_ttc)} FCFA TTC, "
            f"échéance le {_jour(facture.date_echeance)}."
        ),
        url=_lien_facture(facture),
    )


@receiver(billing_signals.facture_refusee)
def prevenir_du_refus_d_une_facture(sender, facture, motif, **kwargs):
    destinataires = [facture.cree_par] if facture.cree_par else utilisateurs_du_role(Role.FINANCES)
    notifier(
        destinataires,
        categorie=CategorieNotification.FACTURE,
        niveau=NiveauNotification.ATTENTION,
        titre=f"Facture renvoyée par la direction : {facture.client.raison_sociale}",
        message=f"Motif : {motif}",
        url=_lien_facture(facture),
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
```

C'est ici que se lit *qui est prévenu de quoi*. Repérez le motif : chaque fonction reçoit un événement
(`conge_soumis`, `alerte_consommation`, `mission_demarree`…), calcule les destinataires **avec les services
des autres apps** puis appelle `notifier`. Notez `send_robust` côté émetteur : si un récepteur plante, l'action
métier (un plein, un départ de mission) **n'échoue pas**.

## Étape 4 — Les tâches du jour

#### `apps/notifications/taches.py`

*169 lignes* — Tâches quotidiennes : alertes préventives, rappels de validation, statuts des congés.

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
    destinataires = list(utilisateurs_du_role(Role.FINANCES, Role.DIRECTION))
    crees = 0
    for facture in billing_services.factures_echues(aujourd_hui):
        retard = (aujourd_hui - facture.date_echeance).days
        crees += len(
            notifier(
                destinataires,
                categorie=CategorieNotification.FACTURE,
                niveau=NiveauNotification.URGENT,
                titre=f"Facture {facture.numero} échue : {facture.client.raison_sociale}",
                message=(
                    f"Reste à recouvrer : {nombre(facture.reste)} FCFA, "
                    f"échue depuis {retard} jour{'s' if retard > 1 else ''}."
                ),
                url=reverse("billing:facture", args=[facture.pk]),
                cle=f"facture-echue:{facture.pk}:{facture.date_echeance.isoformat()}",
            )
        )
    return crees


def executer_taches_quotidiennes(*, aujourd_hui: date | None = None) -> dict[str, int]:
    """Lance toutes les tâches du jour et retourne leurs compteurs."""
    aujourd_hui = aujourd_hui or timezone.localdate()
    resultat = {
        "documents_vehicules": alerter_documents_vehicules(aujourd_hui=aujourd_hui),
        "echeances_chauffeurs": alerter_echeances_chauffeurs(aujourd_hui=aujourd_hui),
        "validations_en_retard": relancer_validations_en_retard(),
        "factures_echues": alerter_factures_echues(aujourd_hui=aujourd_hui),
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

*15 lignes*

```python
from django.core.management.base import BaseCommand

from apps.notifications import taches


class Command(BaseCommand):
    help = (
        "Tâches du jour : alertes de documents et d'échéances, rappels de validation de "
        "congés, statuts des congés. Sans danger si relancée : aucune alerte en double."
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

*36 lignes* — notifications

```markdown
# notifications

Rôle : prévenir les bons utilisateurs au bon moment — cahier-des-charges.md:137, 215, 221,
231-232, 253 ; architecture.md:269-338. Couche haute : elle s'abonne aux événements des apps
métier, qui ne la connaissent pas.

Entité : `Notification` (destinataire, catégorie, niveau, titre, message, lien, lue le,
`cle_unicite`). `services.notifier(destinataires, ...)` crée une notification par compte actif ;
avec `cle`, un destinataire ne reçoit qu'une fois le même message (rappels quotidiens).

Qui est prévenu de quoi (`receivers.py`) :
- congé déposé → supérieur hiérarchique (N1), plus une alerte urgente s'il y a une mission
  prévue sur la période ; validé en N1 → RH ; approuvé, refusé ou annulé → l'employé ;
- stock au seuil → PARCAUTO ; surconsommation, anomalie ou saisie suspecte → PARCAUTO et DIRECTION ;
- mission partie → chargé clientèle attitré du client (à défaut, tous les chargés clientèle) ;
- facture soumise → DIRECTION ; validée → FINANCES et son auteur ; renvoyée → son auteur ;
  facture échue (tâche du jour) → FINANCES et DIRECTION, une fois par facture.

Tâches du jour (`taches.py`, commande `taches_quotidiennes`) : documents des camions et
permis / visites des chauffeurs à 30 jours puis expirés (une alerte à chaque changement d'état),
rappel au validateur quand le délai de 48 h (N1) ou 24 h (N2) est dépassé, et passage des
congés à « En cours » / « Terminé ».

Canaux : toujours dans l'application (cloche + page `/notifications/`) ; en plus par e-mail si
`NOTIFICATIONS_EMAIL` est actif. Un e-mail en échec est journalisé sans jamais bloquer
l'opération métier, et un récepteur en erreur n'empêche pas non plus une validation de congé,
un plein ou un départ de mission (`send_robust`).

Reste à faire :
- **Celery + Redis** (architecture.md, ADR-004) : non installé (pas de Redis ici, rien à
  vérifier). `taches.executer_taches_quotidiennes` est prévue pour être appelée telle quelle
  par Celery Beat au déploiement (étape 7) ; les e-mails partiront alors en tâche asynchrone.
- **SMS (Twilio) et notifications push (Firebase)** : demandent des comptes externes.
- Notification du client à l'expédition (« en cours de route ») : le CDC ne dit pas à qui ;
  seul le chargé clientèle est prévenu pour l'instant.
- Préférences de notification par utilisateur.
```

Les **tests** de `notifications` sont nombreux (récepteurs, tâches, écrans) : ils sont présentés dans les
chapitres où leurs dépendances existent (20, 23, 24, 25 et 26).

## Étape 6 — Déclarer l'application et migrer

#### `config/settings/base.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/settings/base.py (avant)
+++ config/settings/base.py (après)
@@ -62,4 +62,5 @@
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
