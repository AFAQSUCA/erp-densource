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

from apps.accounts import services as accounts_services
from apps.accounts.models import Role
from apps.billing import services as billing_services
from apps.core import documents_pdf
from apps.core.formats import nombre
from apps.core.services import etat_echeance
from apps.drivers import services as drivers_services
from apps.drivers.models import StatutChauffeur
from apps.fleet import services as fleet_services
from apps.hr import services as hr_services
from apps.hr import sorties as hr_sorties
from apps.hr.models import Conge, StatutConge
from apps.parametres import services as parametres_services

from .models import CategorieNotification, NiveauNotification
from .services import notifier, utilisateurs_du_role


def _phrase_echeance(etat: str, restants: int | None, expiration: date) -> tuple[str, str]:
    """(titre court, niveau) selon l'état de l'échéance."""
    if etat == "EXPIRE":
        return f"expiré depuis le {expiration.strftime('%d/%m/%Y')}", NiveauNotification.URGENT
    jours = "aujourd'hui" if restants == 0 else f"dans {restants} jour{'s' if restants > 1 else ''}"
    return f"expire {jours} ({expiration.strftime('%d/%m/%Y')})", NiveauNotification.ATTENTION


def alerter_documents_vehicules(*, aujourd_hui: date | None = None) -> int:
    """Documents réglementaires des camions à renouveler (délai d'alerte des paramètres) ou expirés."""
    aujourd_hui = aujourd_hui or timezone.localdate()
    jours = parametres_services.delai_alerte()
    destinataires = list(utilisateurs_du_role(Role.PARCAUTO))
    crees = 0
    for document in fleet_services.documents_a_renouveler(aujourd_hui=aujourd_hui, jours=jours):
        etat, restants = etat_echeance(document.date_expiration, aujourd_hui=aujourd_hui, jours=jours)
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
    jours = parametres_services.delai_alerte()
    destinataires = list(utilisateurs_du_role(Role.RH, Role.DIRECTION))
    crees = 0
    chauffeurs = drivers_services.chauffeurs_a_renouveler(aujourd_hui=aujourd_hui, jours=jours).exclude(
        statut=StatutChauffeur.INACTIF
    )
    for chauffeur in chauffeurs:
        for code, echeance in (
            ("permis", chauffeur.date_expiration_permis),
            ("visite", chauffeur.date_expiration_visite_medicale),
        ):
            if echeance is None:
                continue
            etat, restants = etat_echeance(echeance, aujourd_hui=aujourd_hui, jours=jours)
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


def _prevenir_la_direction(conge, niveau: str, delai: str) -> int:
    """La Direction peut décider à la place d'un validateur en retard (``hr.services._direction_remplace``) : elle
    est prévenue une fois, sauf pour sa propre demande (audit AUD-16)."""
    direction = utilisateurs_du_role(Role.DIRECTION)
    if conge.employe.utilisateur_id:
        direction = direction.exclude(pk=conge.employe.utilisateur_id)
    return len(
        notifier(
            direction,
            categorie=CategorieNotification.CONGE,
            niveau=NiveauNotification.ATTENTION,
            titre=f"Congé en retard de validation {niveau} : {conge.employe.prenom} {conge.employe.nom}",
            message=f"Le délai de {delai} est dépassé : la Direction peut valider ou refuser à la place du validateur.",
            url=reverse("hr:conges_detail", args=[conge.pk]),
            cle=f"conge-retard:{conge.pk}:{niveau}:direction",
        )
    )


def relancer_validations_en_retard(*, maintenant: datetime | None = None) -> int:
    """Rappel au validateur dont le délai (48 h en N1, 24 h en N2) est dépassé ; la Direction, qui peut alors
    décider à sa place, est prévenue aussi (audit AUD-16). Renvoie le nombre de rappels aux validateurs."""
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
        _prevenir_la_direction(conge, "N1", "48 h")
    for conge in en_retard.filter(
        statut=StatutConge.VALIDATION_N1, date_limite_n2__lt=maintenant
    ):
        crees += len(
            notifier(
                hr_services.validateurs_n2(conge),  # jamais le compte du N1 (audit M11-11)
                categorie=CategorieNotification.CONGE,
                niveau=NiveauNotification.URGENT,
                titre=f"Validation N2 en retard : {conge.employe.prenom} {conge.employe.nom}",
                message="Le délai de 24 h est dépassé.",
                url=reverse("hr:conges_detail", args=[conge.pk]),
                cle=f"conge-retard:{conge.pk}:N2",
            )
        )
        _prevenir_la_direction(conge, "N2", "24 h")
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


def appliquer_sorties_du_jour(*, aujourd_hui: date | None = None) -> int:
    """Sorties du personnel arrivées à leur date (hr.sorties). Une sortie retenue par une mission en cours est
    réessayée chaque jour ; la RH en est prévenue une fois."""
    resultat = hr_sorties.appliquer_sorties_echues(aujourd_hui=aujourd_hui)
    if resultat["reportees"]:
        destinataires = list(utilisateurs_du_role(Role.RH))
        for sortie, raison in resultat["reportees"]:
            employe = sortie.employe
            notifier(
                destinataires,
                categorie=CategorieNotification.PERSONNEL,
                niveau=NiveauNotification.ATTENTION,
                titre=f"Sortie de {employe.prenom} {employe.nom} en attente",
                message=raison,
                url=reverse("hr:personnel_detail", args=[employe.pk]),
                cle=f"sortie-en-attente:{sortie.pk}",
            )
    return resultat["appliquees"]


def executer_taches_quotidiennes(*, aujourd_hui: date | None = None) -> dict[str, int]:
    """Lance toutes les tâches du jour et retourne leurs compteurs."""
    aujourd_hui = aujourd_hui or timezone.localdate()
    resultat = {
        "documents_vehicules": alerter_documents_vehicules(aujourd_hui=aujourd_hui),
        "echeances_chauffeurs": alerter_echeances_chauffeurs(aujourd_hui=aujourd_hui),
        "validations_en_retard": relancer_validations_en_retard(),
        "factures_echues": alerter_factures_echues(aujourd_hui=aujourd_hui),
        "proformas_expirees": billing_services.expirer_proformas(aujourd_hui=aujourd_hui),
        # Avant la synchronisation des congés : les congés à venir d'un partant sont annulés, pas démarrés.
        "sorties_appliquees": appliquer_sorties_du_jour(aujourd_hui=aujourd_hui),
    }
    # Jours fériés fixes et chrétiens de l'année et de la suivante (un congé de janvier se demande en décembre) :
    # idempotent, les fêtes musulmanes restent saisies par la RH (audit M11-26).
    resultat["jours_feries_crees"] = sum(
        hr_services.initialiser_jours_feries(annee) for annee in (aujourd_hui.year, aujourd_hui.year + 1)
    )
    conges = hr_services.synchroniser_statuts_conges(aujourd_hui=aujourd_hui)
    resultat["conges_demarres"] = conges["demarres"]
    resultat["conges_termines"] = conges["termines"]
    purge = accounts_services.purger_sessions_et_jetons_expires()  # audit AUD-19
    resultat["sessions_purgees"], resultat["jetons_purges"] = purge["sessions"], purge["jetons"]
    resultat["pdf_purges"] = documents_pdf.purger()  # PDF préparés en tâche de fond (audit TECH-70)
    return resultat
