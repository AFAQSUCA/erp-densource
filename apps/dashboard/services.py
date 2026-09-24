"""Indicateurs du tableau de bord, selon le rôle (cahier-des-charges.md:225-239).

Ce module ne calcule rien lui-même : il assemble les lectures fournies par les apps métier
(``fleet.repartition_statuts``, ``fuel.consommation_moyenne``, ``hr.absents_du_jour``...)
et décide qui voit quoi. Les indicateurs financiers (chiffre d'affaires, encaissements,
charges, marge, créances, trésorerie) et les factures impayées viennent de ``finance`` et
``billing`` (étape 4).

Les indicateurs globaux (exploitation, clientèle) peuvent être mis en cache
(``DASHBOARD_CACHE_SECONDS``) ; le centre d'alertes est toujours recalculé.
"""

from __future__ import annotations

from datetime import date, timedelta

from django.conf import settings
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.billing import permissions as billing_permissions
from apps.billing import services as billing_services
from apps.core import graphiques
from apps.core.formats import nombre
from apps.core.services import etat_echeance
from apps.customers import permissions as customers_permissions
from apps.customers import services as customers_services
from apps.drivers import permissions as drivers_permissions
from apps.drivers import services as drivers_services
from apps.finance import services as finance_services
from apps.fleet import permissions as fleet_permissions
from apps.fleet import services as fleet_services
from apps.fleet.models import StatutVehicule
from apps.fuel import permissions as fuel_permissions
from apps.fuel import services as fuel_services
from apps.fuel.models import NiveauAlerte
from apps.garage import permissions as garage_permissions
from apps.garage import terrain as garage_terrain
from apps.garage.models import GraviteIncident
from apps.hr import permissions as hr_permissions
from apps.hr import services as hr_services
from apps.inventory import permissions as inventory_permissions
from apps.inventory import services as inventory_services
from apps.missions import services as missions_services
from apps.missions.models import StatutMission

LIGNES_PAR_ALERTE = 5
JOURS_ALERTES_CARBURANT = 30
MOIS_HISTORIQUE = 6
MOIS_ABREGES = ("janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc.")

ROLES_EXPLOITATION = fleet_permissions.CONSULTATION
ROLES_RH = hr_permissions.PERSONNEL_CONSULTATION
ROLES_CLIENTELE = customers_permissions.CONSULTATION
ROLES_FINANCES = billing_permissions.CONSULTATION


def _en_cache(cle: str, calcul):
    secondes = settings.DASHBOARD_CACHE_SECONDS
    if not secondes:
        return calcul()
    return cache.get_or_set(f"dashboard:{cle}", calcul, secondes)


# --- exploitation ---


def exploitation() -> dict:
    """Camions par statut, consommation moyenne globale et missions à suivre."""

    def calculer():
        camions = fleet_services.repartition_statuts()
        missions = missions_services.repartition_par_statut()
        return {
            "camions": {
                "total": camions["total"],
                "disponibles": camions[StatutVehicule.DISPONIBLE],
                "en_mission": camions[StatutVehicule.EN_MISSION],
                "au_garage": camions[StatutVehicule.EN_MAINTENANCE],
                "immobilises": camions[StatutVehicule.IMMOBILISE],
                "hors_service": camions[StatutVehicule.HORS_SERVICE],
            },
            "consommation": fuel_services.consommation_moyenne(),
            "missions_en_cours": missions[StatutMission.EN_COURS_DEPART]
            + missions[StatutMission.EN_COURS_COLIS_RECUPERE],
            "missions_a_affecter": missions[StatutMission.PLANIFIEE],
            "missions_a_cloturer": missions[StatutMission.LIVREE],
            "graphique_camions": graphiques.barres_horizontales(
                {"libelle": libelle, "valeur": camions[code]} for code, libelle in StatutVehicule.choices
            ),
            "graphique_missions": graphiques.barres_horizontales(
                {"libelle": libelle, "valeur": missions[code]} for code, libelle in StatutMission.choices
            ),
        }

    return _en_cache("exploitation", calculer)


# --- ressources humaines ---


def ressources_humaines(*, jour: date | None = None) -> dict:
    """Effectif, absents du jour, prochains départs en congé et demandes en attente."""
    jour = jour or timezone.localdate()
    par_departement = hr_services.effectif_par_departement()
    return {
        "effectif": sum(d["nombre"] for d in par_departement),
        "par_departement": par_departement,
        "graphique_departements": graphiques.barres_horizontales(
            {"libelle": d["libelle"], "valeur": d["nombre"]} for d in par_departement
        ),
        "absents": list(hr_services.absents_du_jour(jour)[:LIGNES_PAR_ALERTE * 2]),
        "nombre_absents": hr_services.absents_du_jour(jour).count(),
        "prochains": list(hr_services.prochains_conges(jour)[:LIGNES_PAR_ALERTE]),
        "en_attente": hr_services.conges_en_attente(),
    }


# --- clientèle ---


def clientele() -> dict:
    """Clients actifs, réclamations récentes et meilleurs clients.

    Ne couvre pas la satisfaction ni les contrats à renouveler (cahier-des-charges.md:236-238) :
    aucune donnée ne les porte encore.
    """

    def calculer():
        meilleurs = missions_services.meilleurs_clients()
        return {
            "clients_actifs": missions_services.clients_actifs(),
            "reclamations": customers_services.reclamations_recentes(),
            "meilleurs": meilleurs,
            "graphique_clients": graphiques.barres_horizontales(
                {
                    "libelle": c["client"],
                    "valeur": c["montant"],
                    "url": reverse("customers:detail", args=[c["client_id"]]),
                    "detail": f"{c['missions']} mission{'s' if c['missions'] > 1 else ''}",
                }
                for c in meilleurs
            ),
        }

    return _en_cache("clientele", calculer)


# --- finances ---


def finances(*, jour: date | None = None) -> dict:
    """Indicateurs du mois en cours : CA HT facturé, encaissé, charges, marge, créances, trésorerie.

    Les charges se décomposent en dépenses saisies, carburant et coût des OR clôturés
    (voir ``finance.services``).
    """
    jour = jour or timezone.localdate()
    debut = jour.replace(day=1)

    def calculer():
        resultat = finance_services.indicateurs(debut, jour, aujourd_hui=jour)
        historique = finance_services.historique_mensuel(
            jour,
            mois=MOIS_HISTORIQUE,
            courant={
                "chiffre_affaires": resultat["chiffre_affaires"],
                "encaisse": resultat["encaisse"],
                "charges": resultat["charges"]["total"],
            },
        )
        resultat["graphique_mensuel"] = graphiques.colonnes_groupees(
            [f"{MOIS_ABREGES[ligne['debut'].month - 1]} {ligne['debut'].year % 100:02d}" for ligne in historique],
            [
                {"nom": "CA facturé (HT)", "valeurs": [ligne["chiffre_affaires"] for ligne in historique]},
                {"nom": "Encaissé", "valeurs": [ligne["encaisse"] for ligne in historique]},
                {"nom": "Charges", "valeurs": [ligne["charges"] for ligne in historique]},
            ],
            unite="FCFA",
        )
        resultat["graphique_charges"] = graphiques.barres_horizontales(
            [
                {"libelle": "Dépenses saisies", "valeur": resultat["charges"]["depenses"]},
                {"libelle": "Carburant", "valeur": resultat["charges"]["carburant"]},
                {"libelle": "Maintenance", "valeur": resultat["charges"]["maintenance"]},
            ],
            unite="FCFA",
        )
        return resultat

    return _en_cache(f"finances:{jour.isoformat()}", calculer)


# --- centre d'alertes ---


def _phrase_jours(etat: str, restants: int | None) -> str:
    if etat == "EXPIRE":
        return f"expiré depuis {-restants} j" if restants else "expiré"
    if restants == 0:
        return "expire aujourd'hui"
    return f"expire dans {restants} j"


def _alerte(code, titre, icone, lignes, *, niveau, voir_tout):
    """Groupe d'alertes : ``nombre`` = total réel, ``lignes`` = les premières seulement."""
    return {
        "code": code,
        "titre": titre,
        "icone": icone,
        "niveau": niveau,
        "nombre": len(lignes),
        "autres": max(len(lignes) - LIGNES_PAR_ALERTE, 0),
        "lignes": lignes[:LIGNES_PAR_ALERTE],
        "voir_tout": voir_tout,
    }


def _alertes_documents(aujourd_hui):
    lignes = []
    for document in fleet_services.documents_a_renouveler(aujourd_hui=aujourd_hui).order_by(
        "date_expiration"
    ):
        etat, restants = etat_echeance(document.date_expiration, aujourd_hui=aujourd_hui)
        lignes.append(
            {
                "libelle": f"{document.get_type_document_display()} · {document.vehicule.immatriculation}",
                "detail": _phrase_jours(etat, restants),
                "etat": etat,
                "url": reverse("fleet:detail", args=[document.vehicule_id]),
            }
        )
    niveau = "URGENT" if any(ligne["etat"] == "EXPIRE" for ligne in lignes) else "ATTENTION"
    return _alerte(
        "documents", "Documents des camions à renouveler", "fa-file-shield", lignes,
        niveau=niveau, voir_tout=f"{reverse('fleet:liste')}?alerte=1",
    )


def _alertes_chauffeurs(aujourd_hui):
    lignes = []
    for chauffeur in drivers_services.chauffeurs_a_renouveler(aujourd_hui=aujourd_hui).exclude(
        statut="INACTIF"
    ):
        nom = f"{chauffeur.personnel.prenom} {chauffeur.personnel.nom}"
        for libelle, echeance in (
            ("Permis", chauffeur.date_expiration_permis),
            ("Visite médicale", chauffeur.date_expiration_visite_medicale),
        ):
            if echeance is None:
                continue
            etat, restants = etat_echeance(echeance, aujourd_hui=aujourd_hui)
            if etat in ("EXPIRE", "A_RENOUVELER"):
                lignes.append(
                    {
                        "libelle": f"{libelle} · {nom}",
                        "detail": _phrase_jours(etat, restants),
                        "etat": etat,
                        "echeance": echeance,
                        "url": reverse("drivers:detail", args=[chauffeur.pk]),
                    }
                )
    lignes.sort(key=lambda ligne: ligne["echeance"])
    niveau = "URGENT" if any(ligne["etat"] == "EXPIRE" for ligne in lignes) else "ATTENTION"
    return _alerte(
        "chauffeurs", "Permis et visites médicales à renouveler", "fa-id-card", lignes,
        niveau=niveau, voir_tout=f"{reverse('drivers:liste')}?alerte=1",
    )


def _alertes_stock():
    articles = list(inventory_services.articles_sous_seuil().order_by("quantite", "reference"))
    lignes = [
        {
            "libelle": f"{a.designation} ({a.reference})",
            "detail": "rupture" if a.quantite == 0 else f"{a.quantite} en stock, seuil {a.seuil_minimal}",
            "etat": "RUPTURE" if a.quantite == 0 else "STOCK_BAS",
            "url": reverse("inventory:article_detail", args=[a.pk]),
        }
        for a in articles
    ]
    niveau = "URGENT" if any(a.quantite == 0 for a in articles) else "ATTENTION"
    return _alerte(
        "stock", "Pièces sous le seuil minimal", "fa-boxes-stacked", lignes,
        niveau=niveau, voir_tout=f"{reverse('inventory:articles')}?alerte=1",
    )


def _alertes_carburant(aujourd_hui):
    pleins = list(
        fuel_services.pleins_a_surveiller(
            depuis=aujourd_hui - timedelta(days=JOURS_ALERTES_CARBURANT)
        ).order_by("-date_plein", "-pk")
    )
    lignes = []
    for plein in pleins:
        if plein.niveau_alerte == NiveauAlerte.ROUGE:
            etat = "ROUGE"
        elif plein.niveau_alerte == NiveauAlerte.JAUNE:
            etat = "JAUNE"
        else:
            etat = "ANOMALIE" if plein.anomalie else "SAISIE_SUSPECTE"
        detail = plein.date_plein.strftime("%d/%m/%Y")
        if plein.consommation is not None:
            detail += f" · {nombre(plein.consommation, 1)} L/100 km"
        lignes.append(
            {
                "libelle": f"{plein.vehicule.immatriculation} · {plein.chauffeur.personnel.nom}",
                "detail": detail,
                "etat": etat,
                "url": f"{reverse('fuel:liste')}?vehicule={plein.vehicule_id}",
            }
        )
    niveau = "URGENT" if any(l["etat"] in ("ROUGE", "ANOMALIE") for l in lignes) else "ATTENTION"
    return _alerte(
        "carburant", f"Surconsommation ({JOURS_ALERTES_CARBURANT} derniers jours)",
        "fa-gas-pump", lignes, niveau=niveau,
        voir_tout=f"{reverse('fuel:liste')}?alerte=A_SURVEILLER",
    )


def _alertes_factures(aujourd_hui):
    lignes = []
    for facture in billing_services.factures_echues(aujourd_hui).order_by("date_echeance"):
        retard = (aujourd_hui - facture.date_echeance).days
        lignes.append(
            {
                "libelle": f"{facture.numero} · {facture.client.raison_sociale}",
                "detail": f"reste {nombre(facture.reste)} FCFA, échue depuis {retard} j",
                "etat": "URGENT",
                "url": reverse("billing:facture", args=[facture.pk]),
            }
        )
    return _alerte(
        "factures", "Factures impayées échues", "fa-file-invoice-dollar", lignes,
        niveau="URGENT", voir_tout=f"{reverse('billing:factures')}?echues=on",
    )


def _alertes_incidents():
    lignes = []
    incidents = list(garage_terrain.incidents_a_traiter().order_by("-created_at"))
    for incident in incidents:
        lignes.append(
            {
                "libelle": f"{incident.get_type_incident_display()} · {incident.vehicule.immatriculation}",
                "detail": incident.get_gravite_display().split(" :")[0],
                "etat": "URGENT" if incident.gravite == GraviteIncident.GRAVE else "ATTENTION",
                "url": reverse("garage:incident", args=[incident.pk]),
            }
        )
    niveau = "URGENT" if any(i.gravite == GraviteIncident.GRAVE for i in incidents) else "ATTENTION"
    return _alerte(
        "incidents", "Incidents signalés à traiter", "fa-triangle-exclamation", lignes,
        niveau=niveau, voir_tout=f"{reverse('garage:incidents')}?statut=SIGNALE",
    )


def _alertes_conges():
    lignes = []
    for conge in hr_services.conges_en_retard():
        niveau_validation = "N1" if conge.statut == "DEMANDE" else "N2"
        lignes.append(
            {
                "libelle": f"{conge.employe.prenom} {conge.employe.nom}",
                "detail": f"validation {niveau_validation} en retard",
                "etat": "URGENT",
                "url": reverse("hr:conges_detail", args=[conge.pk]),
            }
        )
    return _alerte(
        "conges", "Validations de congés en retard", "fa-umbrella-beach", lignes,
        niveau="URGENT", voir_tout=f"{reverse('hr:conges_liste')}?vue=tous",
    )


def centre_alertes(role: str, *, aujourd_hui: date | None = None) -> list[dict] | None:
    """Groupes d'alertes non vides visibles pour ce rôle ; ``None`` si le rôle n'en a aucun.

    Le centre d'alertes du CDC couvre les documents expirants, les pièces sous seuil et les
    factures impayées échues (cahier-des-charges.md:231-232). S'y ajoutent les alertes de
    carburant, de permis et de validations de congés déjà émises par les notifications.
    """
    aujourd_hui = aujourd_hui or timezone.localdate()
    constructeurs = []
    if role in fleet_permissions.CONSULTATION:
        constructeurs.append(lambda: _alertes_documents(aujourd_hui))
    if role in drivers_permissions.CONSULTATION:
        constructeurs.append(lambda: _alertes_chauffeurs(aujourd_hui))
    if role in inventory_permissions.CONSULTATION:
        constructeurs.append(_alertes_stock)
    if role in fuel_permissions.CONSULTATION:
        constructeurs.append(lambda: _alertes_carburant(aujourd_hui))
    if role in garage_permissions.CONSULTATION:
        constructeurs.append(_alertes_incidents)
    if role in hr_permissions.CONGES_TOUS:
        constructeurs.append(_alertes_conges)
    if role in billing_permissions.CONSULTATION:
        constructeurs.append(lambda: _alertes_factures(aujourd_hui))
    if not constructeurs:
        return None
    groupes = [construire() for construire in constructeurs]
    return [groupe for groupe in groupes if groupe["nombre"]]


# --- assemblage ---


def tableau_de_bord(utilisateur, *, aujourd_hui: date | None = None) -> dict:
    """Blocs à afficher pour cet utilisateur (``None`` = bloc non accessible à son rôle)."""
    role = utilisateur.role_effectif
    aujourd_hui = aujourd_hui or timezone.localdate()
    alertes = centre_alertes(role, aujourd_hui=aujourd_hui)
    return {
        "role": role,
        "exploitation": exploitation() if role in ROLES_EXPLOITATION else None,
        "alertes": alertes,
        "nombre_alertes": sum(g["nombre"] for g in alertes) if alertes else 0,
        "ressources_humaines": (
            ressources_humaines(jour=aujourd_hui) if role in ROLES_RH else None
        ),
        "clientele": clientele() if role in ROLES_CLIENTELE else None,
        "finances": finances(jour=aujourd_hui) if role in ROLES_FINANCES else None,
        "espace_mobile": role == Role.CHAUFFEUR,
    }
