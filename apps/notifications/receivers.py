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


@receiver(mission_affectee)
def prevenir_la_finance_d_une_affectation(sender, mission, **kwargs):
    notifier(
        utilisateurs_du_role(Role.FINANCES),
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
        utilisateurs_du_role(Role.FINANCES),
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
    finances = list(utilisateurs_du_role(Role.FINANCES))
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
