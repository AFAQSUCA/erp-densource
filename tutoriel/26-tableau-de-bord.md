# Chapitre 26 — La page d'accueil : le tableau de bord

> 13 fichier(s) dans ce chapitre, 2161 lignes de code.

## Ce que vous allez construire

La **vraie page d'accueil** : le **tableau de bord**, différent pour chaque rôle. Il **remplace** la page provisoire
du chapitre 16.

| Bloc | Qui le voit | Contenu |
|---|---|---|
| **Centre d'alertes** | selon les droits de chacun | documents des camions à 30 jours ou expirés, permis et visites des chauffeurs, pièces sous le seuil, surconsommation des 30 derniers jours, validations de congés en retard, **incidents à traiter**, **factures échues** |
| **Exploitation** | ADMIN, DIRECTION, PARCAUTO | camions disponibles / en mission / au garage, consommation moyenne, missions en cours, à affecter, à clôturer |
| **Ressources humaines** | ADMIN, DIRECTION, RH | effectif par département, absents du jour, prochains départs en congé, demandes à valider |
| **Finances du mois** | ADMIN, DIRECTION, FINANCES | CA HT, encaissé, charges, marge nette, créances (dont échues), trésorerie |
| **Clientèle** | ADMIN, DIRECTION, CHARGE_CLIENTELE | clients actifs, réclamations, top 3 des clients |
| **Accès rapides** | tous | raccourcis vers les écrans du menu |

## Prérequis

- Chapitres 1 à 25 terminés. C'est **pour cela** que le tableau de bord arrive maintenant : il renvoie vers tous les
  écrans (`reverse('inventory:articles')`…), qui doivent tous exister.

## Ce que ce chapitre apporte de nouveau

- **Une app qui n'a presque pas de règles** : `dashboard/services.py` **assemble** des lectures que les autres
  apps fournissent (`fleet.repartition_statuts`, `fuel.consommation_moyenne`, `hr.absents_du_jour`,
  `finance.indicateurs`…). Il **ne calcule rien lui-même** : aucune règle n'est dupliquée.
- **Qui voit quoi, sans le réécrire** : les ensembles de rôles sont **importés** des `permissions` de chaque app
  (`fleet_permissions.CONSULTATION`…). Si un droit change dans une app, le tableau de bord suit.
- **Le cache** : les blocs *exploitation* et *clientèle* sont mis en cache `DASHBOARD_CACHE_SECONDS` (60 s par
  défaut). Le centre d'alertes, lui, est **toujours recalculé**. En production avec Redis, le cache est partagé
  entre les processus.
- **Performance** : le tableau de bord d'un ADMIN fait **au plus 34 requêtes SQL** quel que soit le volume de
  données ; un test le vérifie (`django_assert_max_num_queries`).
- **Remplacer une page provisoire** : on supprime le fichier provisoire et la ligne d'adresse qui l'utilisait.

## Étape 1 — Créer l'application

```bash
mkdir -p apps/dashboard/templates/dashboard apps/dashboard/tests
```

#### Fichiers vides à créer

Ces fichiers n'ont aucun contenu ; ils servent à faire de leur dossier un *paquet Python* (sans eux, `import apps.xxx` échouerait). Créez d'abord les dossiers, puis les fichiers :

```bash
mkdir -p apps\dashboard apps\dashboard\tests
touch apps/dashboard/__init__.py
touch apps/dashboard/tests/__init__.py
```

> Sous PowerShell, `mkdir -p` s'écrit `New-Item -ItemType Directory -Force <dossier>` et `touch fichier` s'écrit `New-Item -ItemType File -Force fichier`. Vous pouvez aussi créer ces fichiers avec votre éditeur.

## Étape 2 — Services, vue, gabarit

#### `apps/dashboard/services.py`

*496 lignes* — Indicateurs du tableau de bord, selon le rôle (cahier-des-charges.md:225-239).

```python
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
from apps.core.services import debuts_de_mois
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
PERIODES = (3, 6, 12)  # mois affichables sur les graphiques dans le temps
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


def _depenses(categorie: str) -> str:
    """Lien vers la page Dépenses filtrée sur une catégorie."""
    return f"{reverse('billing:depenses')}?categorie={categorie}"


def _libelle_mois(debut: date) -> str:
    return f"{MOIS_ABREGES[debut.month - 1]} {debut.year % 100:02d}"


def periode_valide(valeur) -> int:
    """Nombre de mois demandé (``?periode=``) : 3, 6 ou 12 ; 6 par défaut."""
    try:
        mois = int(valeur)
    except (TypeError, ValueError):
        return MOIS_HISTORIQUE
    return mois if mois in PERIODES else MOIS_HISTORIQUE


# --- exploitation ---


def exploitation(*, jour: date | None = None, mois: int = MOIS_HISTORIQUE) -> dict:
    """Camions par statut, consommation moyenne globale, missions à suivre et missions par mois."""
    jour = jour or timezone.localdate()

    def calculer():
        camions = fleet_services.repartition_statuts()
        missions = missions_services.repartition_par_statut()
        debuts = debuts_de_mois(jour, mois)
        par_mois = missions_services.missions_par_mois(debuts[0], jour)
        cles = [(d.year, d.month) for d in debuts]
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
            # Chaque barre mène à la liste filtrée sur ce statut (drill-down).
            "graphique_camions": graphiques.barres_horizontales(
                {
                    "libelle": libelle,
                    "valeur": camions[code],
                    "url": f"{reverse('fleet:liste')}?statut={code}",
                }
                for code, libelle in StatutVehicule.choices
            ),
            "graphique_missions": graphiques.barres_horizontales(
                {
                    "libelle": libelle,
                    "valeur": missions[code],
                    "url": f"{reverse('missions:liste')}?statut={code}",
                }
                for code, libelle in StatutMission.choices
            ),
            "graphique_missions_mois": graphiques.colonnes_groupees(
                [_libelle_mois(d) for d in debuts],
                [
                    {"nom": "Créées", "valeurs": [par_mois["creees"].get(c, 0) for c in cles]},
                    {"nom": "Livrées", "valeurs": [par_mois["livrees"].get(c, 0) for c in cles]},
                ],
                unite="missions",
                entier=True,
            ),
        }

    return _en_cache(f"exploitation:{jour.isoformat()}:{mois}", calculer)


# --- ressources humaines ---


def ressources_humaines(*, jour: date | None = None) -> dict:
    """Effectif, absents du jour, prochains départs en congé et demandes en attente."""
    jour = jour or timezone.localdate()
    par_departement = hr_services.effectif_par_departement()
    return {
        "effectif": sum(d["nombre"] for d in par_departement),
        "par_departement": par_departement,
        "graphique_departements": graphiques.barres_horizontales(
            {
                "libelle": d["libelle"],
                "valeur": d["nombre"],
                "url": f"{reverse('hr:personnel_liste')}?departement={d['code']}",
            }
            for d in par_departement
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


def finances(*, jour: date | None = None, mois: int = MOIS_HISTORIQUE) -> dict:
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
            mois=mois,
            courant={
                "chiffre_affaires": resultat["chiffre_affaires"],
                "encaisse": resultat["encaisse"],
                "charges": resultat["charges"]["total"],
            },
        )
        resultat["graphique_mensuel"] = graphiques.colonnes_groupees(
            [_libelle_mois(ligne["debut"]) for ligne in historique],
            [
                {"nom": "CA facturé (HT)", "valeurs": [ligne["chiffre_affaires"] for ligne in historique]},
                {"nom": "Encaissé", "valeurs": [ligne["encaisse"] for ligne in historique]},
                {"nom": "Charges", "valeurs": [ligne["charges"] for ligne in historique]},
            ],
            unite="FCFA",
        )
        resultat["graphique_charges"] = graphiques.barres_horizontales(
            [
                {"libelle": "Carburant", "valeur": resultat["charges"]["carburant"], "url": _depenses("CARBURANT")},
                {"libelle": "Pièces détachées", "valeur": resultat["charges"]["pieces"], "url": _depenses("PIECES")},
                {"libelle": "Main-d'œuvre des réparations", "valeur": resultat["charges"]["main_oeuvre"], "url": _depenses("MAINTENANCE")},
                {"libelle": "Frais de mission", "valeur": resultat["charges"]["frais_mission"], "url": _depenses("FRAIS_MISSION")},
                {"libelle": "Autres dépenses", "valeur": resultat["charges"]["depenses"], "url": reverse("billing:depenses")},
            ],
            unite="FCFA",
        )
        resultat["graphique_creances"] = graphiques.barres_horizontales(
            [
                {
                    "libelle": tranche["libelle"],
                    "valeur": tranche["montant"],
                    "detail": f"{tranche['nombre']} facture{'s' if tranche['nombre'] > 1 else ''}",
                    "url": f"{reverse('billing:factures')}?echues=on" if tranche["echu"] and tranche["nombre"] else "",
                }
                for tranche in billing_services.creances_par_anciennete(jour)
            ],
            unite="FCFA",
        )
        return resultat

    return _en_cache(f"finances:{jour.isoformat()}:{mois}", calculer)


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


def tableau_de_bord(utilisateur, *, aujourd_hui: date | None = None, mois: int = MOIS_HISTORIQUE) -> dict:
    """Blocs à afficher pour cet utilisateur (``None`` = bloc non accessible à son rôle).

    ``mois`` : étendue des graphiques dans le temps (3, 6 ou 12 mois).
    """
    role = utilisateur.role_effectif
    aujourd_hui = aujourd_hui or timezone.localdate()
    alertes = centre_alertes(role, aujourd_hui=aujourd_hui)
    return {
        "role": role,
        "exploitation": exploitation(jour=aujourd_hui, mois=mois) if role in ROLES_EXPLOITATION else None,
        "alertes": alertes,
        "nombre_alertes": sum(g["nombre"] for g in alertes) if alertes else 0,
        "ressources_humaines": (
            ressources_humaines(jour=aujourd_hui) if role in ROLES_RH else None
        ),
        "clientele": clientele() if role in ROLES_CLIENTELE else None,
        "finances": finances(jour=aujourd_hui, mois=mois) if role in ROLES_FINANCES else None,
        "periode": mois,
        "periodes": PERIODES,
        "graphiques_dans_le_temps": role in ROLES_FINANCES or (role in ROLES_EXPLOITATION and role != Role.PARCAUTO),
        "espace_mobile": role == Role.CHAUFFEUR,
    }
```

Lisez-le de bas en haut :

1. **`tableau_de_bord(utilisateur)`** : l'orchestre ; décide quels blocs assembler d'après le rôle.
2. **`centre_alertes(role)`** : construit la liste des groupes d'alertes (`_alertes_documents`,
   `_alertes_chauffeurs`, `_alertes_stock`, `_alertes_carburant`, `_alertes_factures`, `_alertes_incidents`,
   `_alertes_conges`) et n'en garde que les non vides.
3. **`exploitation`**, **`ressources_humaines`**, **`clientele`**, **`finances`** : un bloc chacun, qui appelle des
   services des autres apps.

#### `apps/dashboard/views.py`

*48 lignes* — Tableau de bord : page d'accueil après connexion, adaptée au rôle.

```python
"""Tableau de bord : page d'accueil après connexion, adaptée au rôle."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views.generic import TemplateView

from apps.accounts.models import Role
from apps.core.rapports import contexte_rapport
from apps.drivers import services as drivers_services

from . import services


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/index.html"

    def get(self, request, *args, **kwargs):
        # Un chauffeur n'a pas de tableau de bord de bureau : son espace mobile est sa page d'accueil.
        utilisateur = request.user
        if (
            utilisateur.is_authenticated
            and utilisateur.role_effectif == Role.CHAUFFEUR
            and drivers_services.chauffeur_de(utilisateur) is not None
        ):
            return redirect("chauffeur:accueil")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        mois = services.periode_valide(self.request.GET.get("periode"))
        contexte.update(services.tableau_de_bord(self.request.user, mois=mois))
        return contexte


class DashboardImprimerView(LoginRequiredMixin, TemplateView):
    """Rapport imprimable du tableau de bord de l'utilisateur connecté (mêmes blocs, mêmes droits)."""

    template_name = "dashboard/index_print.html"

    def get_context_data(self, **kwargs):
        mois = services.periode_valide(self.request.GET.get("periode"))
        tableau = services.tableau_de_bord(self.request.user, mois=mois)
        contexte = contexte_rapport(
            self.request, titre="Tableau de bord",
            sous_titre=self.request.user.get_role_display() or "Administrateur",
        )
        contexte.update(tableau)
        return contexte
```

`DashboardView` est **la page d'accueil** (`name="home"`). Le chauffeur, lui, est **redirigé vers son espace
mobile** (chapitre 27).

#### `apps/dashboard/templates/dashboard/index.html`

*225 lignes*

```django
{% extends "base.html" %}
{% load ui humanize graphiques %}
{% block titre %}Tableau de bord{% endblock %}
{% block entete %}Tableau de bord{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-7xl">
  <div class="flex flex-wrap items-start justify-between gap-3">
    <div>
      <h1 class="text-2xl font-bold text-slate-900">Bonjour {{ user.first_name|default:user.username }}</h1>
      <p class="mt-1 text-sm text-slate-600">
        Connecté en tant que <strong>{{ user.get_role_display|default:"Administrateur" }}</strong>
        · {% now "l j F Y" %}
      </p>
    </div>
    <a href="{% url 'home_imprimer' %}?periode={{ periode }}" target="_blank" rel="noopener"
       class="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
      <i class="fa-solid fa-print" aria-hidden="true"></i> Imprimer
    </a>
  </div>

  {% if graphiques_dans_le_temps %}
    <nav class="mt-4 flex flex-wrap items-center gap-2 text-sm" aria-label="Période des graphiques">
      <span class="text-slate-600">Graphiques dans le temps :</span>
      {% for p in periodes %}
        <a href="?periode={{ p }}"
           class="rounded-lg border px-3 py-1.5 font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 {% if p == periode %}border-slate-900 bg-slate-900 text-white{% else %}border-slate-300 bg-white text-slate-800 hover:bg-slate-50{% endif %}"
           {% if p == periode %}aria-current="true"{% endif %}>{{ p }} mois</a>
      {% endfor %}
    </nav>
  {% endif %}

  {% if espace_mobile %}
    <div class="mt-8 rounded-xl border border-dashed border-slate-300 bg-white p-6 text-sm text-slate-700">
      <p class="font-medium text-slate-900">Aucun écran n'est encore disponible pour votre rôle.</p>
      <p class="mt-1">Les chauffeurs utiliseront l'espace mobile dédié : missions, plein de carburant, signalement de panne.</p>
    </div>
  {% endif %}

  {% if alertes is not None %}
    <section class="mt-8" aria-labelledby="titre-alertes">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h2 id="titre-alertes" class="text-lg font-semibold text-slate-900">Centre d'alertes</h2>
        {% if nombre_alertes %}<span class="text-sm text-slate-600">{{ nombre_alertes }} alerte{{ nombre_alertes|pluralize }}</span>{% endif %}
      </div>
      {% if alertes %}
        <div class="mt-3 grid grid-cols-1 gap-4 lg:grid-cols-2">
          {% for groupe in alertes %}
            <article class="rounded-xl border bg-white p-5 shadow-sm {% if groupe.niveau == 'URGENT' %}border-red-300{% else %}border-amber-300{% endif %}" aria-labelledby="alerte-{{ groupe.code }}">
              <div class="flex items-start justify-between gap-3">
                <h3 id="alerte-{{ groupe.code }}" class="flex items-center gap-2 text-base font-semibold text-slate-900">
                  <i class="fa-solid {{ groupe.icone }} {% if groupe.niveau == 'URGENT' %}text-red-700{% else %}text-amber-700{% endif %}" aria-hidden="true"></i>
                  {{ groupe.titre }}
                </h3>
                {% badge groupe.niveau groupe.nombre %}
              </div>
              <ul class="mt-3 divide-y divide-slate-100 text-sm">
                {% for ligne in groupe.lignes %}
                  <li class="flex flex-wrap items-center justify-between gap-2 py-2">
                    <a href="{{ ligne.url }}" class="font-medium text-marque-700 underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">{{ ligne.libelle }}</a>
                    <span class="{% if ligne.etat == 'EXPIRE' or ligne.etat == 'RUPTURE' or ligne.etat == 'ROUGE' or ligne.etat == 'ANOMALIE' or ligne.etat == 'URGENT' %}font-semibold text-red-800{% else %}text-slate-700{% endif %}">{{ ligne.detail }}</span>
                  </li>
                {% endfor %}
              </ul>
              {% if groupe.autres %}
                <p class="mt-2 text-xs text-slate-600">et {{ groupe.autres }} autre{{ groupe.autres|pluralize }}…</p>
              {% endif %}
              <a href="{{ groupe.voir_tout }}" class="mt-3 inline-block text-sm font-medium text-marque-700 underline-offset-2 hover:underline">Voir tout</a>
            </article>
          {% endfor %}
        </div>
      {% else %}
        <p class="mt-3 rounded-xl border border-emerald-300 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
          <i class="fa-solid fa-circle-check mr-2" aria-hidden="true"></i>Aucune alerte : documents, stock, carburant et congés sont à jour.
        </p>
      {% endif %}
    </section>
  {% endif %}

  {% if exploitation %}
    <section class="mt-8" aria-labelledby="titre-exploitation">
      <h2 id="titre-exploitation" class="text-lg font-semibold text-slate-900">Exploitation</h2>
      <dl class="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Camions disponibles</dt><dd class="mt-1 text-2xl font-bold text-emerald-800">{{ exploitation.camions.disponibles }} <span class="text-sm font-medium text-slate-600">/ {{ exploitation.camions.total }}</span></dd></div>
        <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">En mission</dt><dd class="mt-1 text-2xl font-bold text-slate-900">{{ exploitation.camions.en_mission }}</dd></div>
        <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Au garage</dt><dd class="mt-1 text-2xl font-bold text-slate-900">{{ exploitation.camions.au_garage }}</dd>{% if exploitation.camions.immobilises or exploitation.camions.hors_service %}<dd class="mt-1 text-xs text-slate-600">+ {{ exploitation.camions.immobilises }} immobilisé{{ exploitation.camions.immobilises|pluralize }}, {{ exploitation.camions.hors_service }} hors service</dd>{% endif %}</div>
        <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Consommation moyenne</dt><dd class="mt-1 text-2xl font-bold text-slate-900">{% if exploitation.consommation %}{{ exploitation.consommation|floatformat:1 }} <span class="text-sm font-medium text-slate-600">L/100 km</span>{% else %}<span class="text-base font-medium text-slate-600">Pas encore de plein</span>{% endif %}</dd></div>
      </dl>
      <div class="mt-4 grid gap-4 {% if user.role_effectif != "PARCAUTO" %}lg:grid-cols-2{% endif %}">
        <div class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 class="text-base font-semibold text-slate-900">Camions par statut</h3>
          <p class="mt-1 mb-3 text-xs text-slate-600">{{ exploitation.camions.total }} camion{{ exploitation.camions.total|pluralize }} au parc.</p>
          {% graphique_barres exploitation.graphique_camions "Aucun camion au parc." %}
        </div>
        {% if user.role_effectif != "PARCAUTO" %}
          <div class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h3 class="text-base font-semibold text-slate-900">Missions par statut</h3>
            <p class="mt-1 mb-3 text-xs text-slate-600">Toutes les missions, de la planification à la clôture.</p>
            {% graphique_barres exploitation.graphique_missions "Aucune mission enregistrée." %}
          </div>
        {% endif %}
      </div>
      {% if user.role_effectif != "PARCAUTO" %}
        <div class="mt-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 class="text-base font-semibold text-slate-900">Missions créées et livrées</h3>
          <p class="mt-1 mb-3 text-xs text-slate-600">Par mois, sur les {{ periode }} derniers mois (« livrées » : livrées ou clôturées).</p>
          {% graphique_colonnes exploitation.graphique_missions_mois "missions-mois" "Aucune mission sur la période." %}
        </div>
      {% endif %}
      {% if user.role_effectif != "PARCAUTO" %}
        <dl class="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Missions en cours</dt><dd class="mt-1 text-2xl font-bold text-slate-900">{{ exploitation.missions_en_cours }}</dd></div>
          <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Planifiées, à affecter</dt><dd class="mt-1 text-2xl font-bold text-slate-900">{{ exploitation.missions_a_affecter }}</dd></div>
          <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Livrées, à clôturer</dt><dd class="mt-1 text-2xl font-bold text-slate-900">{{ exploitation.missions_a_cloturer }}</dd></div>
        </dl>
      {% endif %}
    </section>
  {% endif %}

  {% if ressources_humaines %}
    <section class="mt-8" aria-labelledby="titre-rh">
      <h2 id="titre-rh" class="text-lg font-semibold text-slate-900">Ressources humaines</h2>
      <dl class="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Effectif</dt><dd class="mt-1 text-2xl font-bold text-slate-900">{{ ressources_humaines.effectif }}</dd></div>
        <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Absents aujourd'hui</dt><dd class="mt-1 text-2xl font-bold text-slate-900">{{ ressources_humaines.nombre_absents }}</dd></div>
        <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Demandes à valider (N1)</dt><dd class="mt-1 text-2xl font-bold text-slate-900">{{ ressources_humaines.en_attente.n1 }}</dd></div>
        <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Demandes à valider (RH, N2)</dt><dd class="mt-1 text-2xl font-bold text-slate-900">{{ ressources_humaines.en_attente.n2 }}</dd></div>
      </dl>
      <div class="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 class="text-base font-semibold text-slate-900">Effectif par département</h3>
          <div class="mt-3">{% graphique_barres ressources_humaines.graphique_departements "Aucun employé enregistré." %}</div>
        </div>
        <div class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 class="text-base font-semibold text-slate-900">Absents aujourd'hui</h3>
          {% if ressources_humaines.absents %}
            <ul class="mt-3 space-y-1 text-sm">
              {% for c in ressources_humaines.absents %}<li class="flex justify-between gap-2"><a href="{% url 'hr:conges_detail' c.pk %}" class="text-marque-700 underline-offset-2 hover:underline">{{ c.employe.prenom }} {{ c.employe.nom }}</a><span class="text-slate-600">jusqu'au {{ c.date_fin|date:"d/m" }}</span></li>{% endfor %}
            </ul>
          {% else %}<p class="mt-3 text-sm text-slate-600">Personne n'est en congé aujourd'hui.</p>{% endif %}
        </div>
        <div class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 class="text-base font-semibold text-slate-900">Prochains départs en congé (30 jours)</h3>
          {% if ressources_humaines.prochains %}
            <ul class="mt-3 space-y-1 text-sm">
              {% for c in ressources_humaines.prochains %}<li class="flex justify-between gap-2"><a href="{% url 'hr:conges_detail' c.pk %}" class="text-marque-700 underline-offset-2 hover:underline">{{ c.employe.prenom }} {{ c.employe.nom }}</a><span class="text-slate-600">le {{ c.date_debut|date:"d/m" }}</span></li>{% endfor %}
            </ul>
          {% else %}<p class="mt-3 text-sm text-slate-600">Aucun départ prévu.</p>{% endif %}
        </div>
      </div>
    </section>
  {% endif %}

  {% if clientele %}
    <section class="mt-8" aria-labelledby="titre-clientele">
      <h2 id="titre-clientele" class="text-lg font-semibold text-slate-900">Clientèle</h2>
      <dl class="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Clients actifs</dt><dd class="mt-1 text-2xl font-bold text-slate-900">{{ clientele.clients_actifs }}</dd><dd class="mt-1 text-xs text-slate-600">au moins une mission sur les 90 derniers jours</dd></div>
        <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Réclamations</dt><dd class="mt-1 text-2xl font-bold {% if clientele.reclamations %}text-red-800{% else %}text-slate-900{% endif %}">{{ clientele.reclamations }}</dd><dd class="mt-1 text-xs text-slate-600">sur les 30 derniers jours</dd></div>
      </dl>
      <div class="mt-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h3 class="text-base font-semibold text-slate-900">Top 3 des clients</h3>
        <p class="mt-1 text-xs text-slate-600">Montant des missions livrées ou clôturées sur 12 mois, en FCFA.</p>
        {% if clientele.meilleurs %}
          <div class="mt-3">{% graphique_barres clientele.graphique_clients %}</div>
        {% else %}<p class="mt-3 text-sm text-slate-600">Aucune mission livrée sur la période.</p>{% endif %}
      </div>
    </section>
  {% endif %}

  {% if finances %}
    <section class="mt-8" aria-labelledby="titre-finances">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h2 id="titre-finances" class="text-lg font-semibold text-slate-900">Finances du mois</h2>
        <a href="{% url 'finance:tresorerie' %}" class="text-sm font-medium text-marque-700 underline-offset-2 hover:underline">Voir la trésorerie</a>
      </div>
      <dl class="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">CA facturé (HT)</dt><dd class="mt-1 text-2xl font-bold text-slate-900">{{ finances.chiffre_affaires|floatformat:0|intcomma }} <span class="text-sm font-medium text-slate-600">FCFA</span></dd></div>
        <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Total encaissé</dt><dd class="mt-1 text-2xl font-bold text-slate-900">{{ finances.encaisse|floatformat:0|intcomma }} <span class="text-sm font-medium text-slate-600">FCFA</span></dd></div>
        <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Charges du mois</dt><dd class="mt-1 text-2xl font-bold text-slate-900">{{ finances.charges.total|floatformat:0|intcomma }} <span class="text-sm font-medium text-slate-600">FCFA</span></dd><dd class="mt-1 text-xs text-slate-600">carburant {{ finances.charges.carburant|floatformat:0|intcomma }} · pièces {{ finances.charges.pieces|floatformat:0|intcomma }} · main-d'œuvre {{ finances.charges.main_oeuvre|floatformat:0|intcomma }} · autres {{ finances.charges.depenses|floatformat:0|intcomma }}</dd></div>
        <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Marge nette</dt><dd class="mt-1 text-2xl font-bold {% if finances.marge_nette < 0 %}text-red-800{% else %}text-emerald-800{% endif %}">{{ finances.marge_nette|floatformat:0|intcomma }} <span class="text-sm font-medium text-slate-600">FCFA</span></dd><dd class="mt-1 text-xs text-slate-600">CA HT − charges</dd></div>
      </dl>
      <dl class="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Créances clients</dt><dd class="mt-1 text-2xl font-bold text-slate-900">{{ finances.creances.total|floatformat:0|intcomma }} <span class="text-sm font-medium text-slate-600">FCFA</span></dd><dd class="mt-1 text-xs text-slate-600">{{ finances.creances.nombre }} facture{{ finances.creances.nombre|pluralize }} à recouvrer</dd></div>
        <div class="rounded-xl border {% if finances.creances.nombre_echues %}border-red-300{% else %}border-slate-200{% endif %} bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Dont échues</dt><dd class="mt-1 text-2xl font-bold {% if finances.creances.nombre_echues %}text-red-800{% else %}text-slate-900{% endif %}">{{ finances.creances.echu|floatformat:0|intcomma }} <span class="text-sm font-medium text-slate-600">FCFA</span></dd><dd class="mt-1 text-xs text-slate-600">{{ finances.creances.nombre_echues }} facture{{ finances.creances.nombre_echues|pluralize }}</dd></div>
        <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Trésorerie</dt><dd class="mt-1 text-2xl font-bold {% if finances.tresorerie < 0 %}text-red-800{% else %}text-slate-900{% endif %}">{{ finances.tresorerie|floatformat:0|intcomma }} <span class="text-sm font-medium text-slate-600">FCFA</span></dd><dd class="mt-1 text-xs text-slate-600">solde en temps réel</dd></div>
      </dl>
      <div class="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm lg:col-span-2">
          <h3 class="text-base font-semibold text-slate-900">Facturé, encaissé et charges</h3>
          <p class="mt-1 mb-3 text-xs text-slate-600">Les {{ periode }} derniers mois, en FCFA. Le mois en cours s'arrête à aujourd'hui.</p>
          {% graphique_colonnes finances.graphique_mensuel "historique-mensuel" %}
        </div>
        <div class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 class="text-base font-semibold text-slate-900">Charges du mois</h3>
          <p class="mt-1 mb-3 text-xs text-slate-600">Où part l'argent ce mois-ci.</p>
          {% graphique_barres finances.graphique_charges "Aucune charge ce mois-ci." %}
        </div>
      </div>
      <div class="mt-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h3 class="text-base font-semibold text-slate-900">Créances par ancienneté</h3>
        <p class="mt-1 mb-3 text-xs text-slate-600">Reste à recouvrer selon le retard de paiement. Cliquez sur une tranche en retard pour voir les factures.</p>
        {% graphique_barres finances.graphique_creances "Aucune créance à recouvrer." %}
      </div>
    </section>
  {% endif %}

  {% if menu|length > 1 %}
    <section class="mt-8" aria-labelledby="titre-acces">
      <h2 id="titre-acces" class="text-lg font-semibold text-slate-900">Accès rapides</h2>
      <div class="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {% for entree in menu %}
          {% if entree.url != "/" %}
            <a href="{{ entree.url }}"
               class="group flex items-center gap-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm hover:border-marque-300 hover:shadow focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
              <span class="flex h-10 w-10 items-center justify-center rounded-lg bg-marque-50 text-marque-700 group-hover:bg-marque-100"><i class="fa-solid {{ entree.icone }}" aria-hidden="true"></i></span>
              <span class="font-semibold text-slate-900">{{ entree.libelle }}</span>
            </a>
          {% endif %}
        {% endfor %}
      </div>
    </section>
  {% endif %}
</div>
{% endblock %}
```

#### `apps/dashboard/apps.py`

*7 lignes*

```python
from django.apps import AppConfig


class DashboardConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.dashboard'
    label = 'dashboard'
```

#### `apps/dashboard/README.md`

*45 lignes* — dashboard

```markdown
# dashboard

Rôle : tableau de bord d'accueil, adapté au rôle — cahier-des-charges.md:225-239. Couche
haute : `services.py` assemble les lectures des apps métier (`fleet.repartition_statuts`,
`fuel.consommation_moyenne`, `hr.absents_du_jour`, `missions.meilleurs_clients`...) et décide
qui voit quoi ; il ne calcule rien lui-même.

Blocs (selon les droits déjà définis dans chaque app) :
- **Centre d'alertes** : documents des camions à 30 jours ou expirés, permis et visites des
  chauffeurs, pièces sous le seuil, surconsommation des 30 derniers jours, validations de
  congés en retard. Seuls les groupes non vides apparaissent, avec les 5 premières lignes.
- **Exploitation** (ADMIN, DIRECTION, PARCAUTO) : camions disponibles / en mission / au garage,
  consommation moyenne globale, missions en cours, à affecter, à clôturer.
- **Ressources humaines** (ADMIN, DIRECTION, RH) : effectif par département, absents du jour,
  prochains départs en congé, demandes à valider.
- **Finances du mois** (ADMIN, DIRECTION, FINANCES) : CA HT facturé, encaissé, charges (carburant,
  pièces, main-d'œuvre, autres dépenses : toutes les dépenses, parc auto compris), marge nette, créances dont échues, trésorerie ; groupe d'alertes
  « factures impayées échues ».
- **Clientèle** (ADMIN, DIRECTION, CHARGE_CLIENTELE) : clients actifs (mission sur 90 jours),
  réclamations (30 jours), top 3 des clients (missions livrées ou clôturées sur 12 mois).

Graphiques (`apps/core/graphiques.py`, balises `graphique_barres` / `graphique_colonnes`, styles `viz-*` de
`frontend/input.css`) : camions et missions par statut, effectif par département, top des clients, charges du
mois, créances par ancienneté, missions créées / livrées par mois, et facturé / encaissé / charges par mois.
Un sélecteur de période (3, 6 ou 12 mois, `?periode=`) au-dessus des blocs règle tous les graphiques dans le temps ;
chaque barre de statut ou de département mène à la liste filtrée correspondante (drill-down). HTML et CSS seulement (aucun script, donc compatible avec la
CSP stricte). Règles suivies : palette bleu, orange, aqua validée avec `validate_palette.js` ; barres
horizontales pour comparer des catégories, colonnes groupées pour suivre 3 séries dans le temps ; valeur
écrite au bout de chaque barre ; infobulle au survol et au focus clavier ; tableau équivalent sous le
graphique des mois ; un seul axe ; pas de camembert. L'interface n'a pas de thème sombre, donc un seul jeu de
couleurs. Ajouter un graphique : préparer les données avec `graphiques.barres_horizontales` ou
`colonnes_groupees` dans le service, puis `{% graphique_barres ... %}` dans le gabarit.

Performance : 80 requêtes SQL au plus pour l'ADMIN (le CA, les encaissements, les dépenses et les missions se
lisent par mois en une requête chacun, quel que soit le nombre de mois), indépendamment du volume de données
(testé). Les blocs
exploitation, clientèle et finances sont mis en cache `DASHBOARD_CACHE_SECONDS` (60 s par défaut, 0 en
test) via le cache Django, donc partagé entre processus dès que Redis est configuré ; le
centre d'alertes est toujours recalculé.

Reste à faire :
- Dashboard **chauffeur** (course du jour, km, conso, prochaine mission) : espace mobile, étape 6.
- Clientèle : **satisfaction** et **contrats à renouveler** (aucune donnée ne les porte encore).

Rapport imprimable (`/imprimer/`, bouton « Imprimer » sur l'écran) : mêmes blocs et mêmes droits que le tableau de bord de l'utilisateur connecté, en tableaux (voir `apps/core/README.md`).
```

#### `apps/dashboard/templates/dashboard/index_print.html`

*119 lignes*

```django
{% load static humanize %}<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Tableau de bord · {{ entreprise.nom }}</title>
  {% include "rapports/_style_impression.html" %}
</head>
<body>
  {% include "rapports/_entete_impression.html" %}

  {% if espace_mobile %}
    <p>Aucun rapport de bureau pour ce rôle.</p>
  {% endif %}

  {% if alertes is not None %}
    <h2>Centre d'alertes{% if nombre_alertes %} ({{ nombre_alertes }}){% endif %}</h2>
    {% if alertes %}
      {% for groupe in alertes %}
        <p class="petit" style="margin-top:.75rem"><strong>{{ groupe.titre }}</strong> — {{ groupe.nombre }} élément{{ groupe.nombre|pluralize }}{% if groupe.autres %} (+{{ groupe.autres }} non affiché{{ groupe.autres|pluralize }}){% endif %}</p>
        <table>
          <thead><tr><th>Élément</th><th>Détail</th></tr></thead>
          <tbody>{% for ligne in groupe.lignes %}<tr><td>{{ ligne.libelle }}</td><td>{{ ligne.detail }}</td></tr>{% endfor %}</tbody>
        </table>
      {% endfor %}
    {% else %}
      <p>Aucune alerte : documents, stock, carburant et congés sont à jour.</p>
    {% endif %}
  {% endif %}

  {% if exploitation %}
    <h2>Exploitation</h2>
    <div class="cartouche">
      <div><dt>Camions disponibles</dt><dd>{{ exploitation.camions.disponibles }} / {{ exploitation.camions.total }}</dd></div>
      <div><dt>En mission</dt><dd>{{ exploitation.camions.en_mission }}</dd></div>
      <div><dt>Au garage</dt><dd>{{ exploitation.camions.au_garage }}</dd></div>
      <div><dt>Consommation moyenne</dt><dd>{% if exploitation.consommation %}{{ exploitation.consommation|floatformat:1 }} L/100 km{% else %}—{% endif %}</dd></div>
      {% if exploitation.missions_en_cours is not None and user.role_effectif != "PARCAUTO" %}
        <div><dt>Missions en cours</dt><dd>{{ exploitation.missions_en_cours }}</dd></div>
        <div><dt>Planifiées, à affecter</dt><dd>{{ exploitation.missions_a_affecter }}</dd></div>
        <div><dt>Livrées, à clôturer</dt><dd>{{ exploitation.missions_a_cloturer }}</dd></div>
      {% endif %}
    </div>

    <table>
      <thead><tr><th>Camions par statut</th><th class="droite">Nombre</th></tr></thead>
      <tbody>{% for l in exploitation.graphique_camions.lignes %}<tr><td>{{ l.libelle }}</td><td class="droite">{{ l.valeur_texte }}</td></tr>{% endfor %}</tbody>
    </table>

    {% if user.role_effectif != "PARCAUTO" %}
      <table>
        <thead><tr><th>Missions par statut</th><th class="droite">Nombre</th></tr></thead>
        <tbody>{% for l in exploitation.graphique_missions.lignes %}<tr><td>{{ l.libelle }}</td><td class="droite">{{ l.valeur_texte }}</td></tr>{% endfor %}</tbody>
      </table>

      <table>
        <thead><tr><th>Mois</th>{% for e in exploitation.graphique_missions_mois.tableau.entetes %}<th class="droite">{{ e }}</th>{% endfor %}</tr></thead>
        <tbody>{% for l in exploitation.graphique_missions_mois.tableau.lignes %}<tr><td>{{ l.libelle }}</td>{% for v in l.valeurs %}<td class="droite">{{ v }}</td>{% endfor %}</tr>{% endfor %}</tbody>
      </table>
    {% endif %}
  {% endif %}

  {% if ressources_humaines %}
    <h2>Ressources humaines</h2>
    <div class="cartouche">
      <div><dt>Effectif</dt><dd>{{ ressources_humaines.effectif }}</dd></div>
      <div><dt>Absents aujourd'hui</dt><dd>{{ ressources_humaines.nombre_absents }}</dd></div>
      <div><dt>Demandes à valider (N1)</dt><dd>{{ ressources_humaines.en_attente.n1 }}</dd></div>
      <div><dt>Demandes à valider (RH, N2)</dt><dd>{{ ressources_humaines.en_attente.n2 }}</dd></div>
    </div>
    <table>
      <thead><tr><th>Département</th><th class="droite">Effectif</th></tr></thead>
      <tbody>{% for l in ressources_humaines.graphique_departements.lignes %}<tr><td>{{ l.libelle }}</td><td class="droite">{{ l.valeur_texte }}</td></tr>{% endfor %}</tbody>
    </table>
  {% endif %}

  {% if clientele %}
    <h2>Clientèle</h2>
    <div class="cartouche">
      <div><dt>Clients actifs (90 j)</dt><dd>{{ clientele.clients_actifs }}</dd></div>
      <div><dt>Réclamations (30 j)</dt><dd>{{ clientele.reclamations }}</dd></div>
    </div>
    <table>
      <thead><tr><th>Top clients (12 mois)</th><th class="droite">Montant</th></tr></thead>
      <tbody>{% for l in clientele.graphique_clients.lignes %}<tr><td>{{ l.libelle }}</td><td class="droite">{{ l.valeur_texte }} FCFA</td></tr>{% endfor %}</tbody>
    </table>
  {% endif %}

  {% if finances %}
    <h2>Finances du mois</h2>
    <div class="cartouche">
      <div><dt>CA facturé (HT)</dt><dd>{{ finances.chiffre_affaires|floatformat:0|intcomma }} FCFA</dd></div>
      <div><dt>Total encaissé</dt><dd>{{ finances.encaisse|floatformat:0|intcomma }} FCFA</dd></div>
      <div><dt>Charges du mois</dt><dd>{{ finances.charges.total|floatformat:0|intcomma }} FCFA</dd></div>
      <div><dt>Marge nette</dt><dd>{{ finances.marge_nette|floatformat:0|intcomma }} FCFA</dd></div>
      <div><dt>Créances (dont échues)</dt><dd>{{ finances.creances.total|floatformat:0|intcomma }} ({{ finances.creances.echu|floatformat:0|intcomma }}) FCFA</dd></div>
      <div><dt>Trésorerie</dt><dd>{{ finances.tresorerie|floatformat:0|intcomma }} FCFA</dd></div>
    </div>

    <table>
      <thead><tr><th>Mois</th>{% for e in finances.graphique_mensuel.tableau.entetes %}<th class="droite">{{ e }}</th>{% endfor %}</tr></thead>
      <tbody>{% for l in finances.graphique_mensuel.tableau.lignes %}<tr><td>{{ l.libelle }}</td>{% for v in l.valeurs %}<td class="droite">{{ v }}</td>{% endfor %}</tr>{% endfor %}</tbody>
    </table>

    <table>
      <thead><tr><th>Charges du mois</th><th class="droite">Montant</th></tr></thead>
      <tbody>{% for l in finances.graphique_charges.lignes %}<tr><td>{{ l.libelle }}</td><td class="droite">{{ l.valeur_texte }} FCFA</td></tr>{% endfor %}</tbody>
    </table>

    <table>
      <thead><tr><th>Créances par ancienneté</th><th class="droite">Montant</th></tr></thead>
      <tbody>{% for l in finances.graphique_creances.lignes %}<tr><td>{{ l.libelle }}</td><td class="droite">{{ l.valeur_texte }} FCFA</td></tr>{% endfor %}</tbody>
    </table>
  {% endif %}

  {% include "rapports/_pied_impression.html" %}
  <script src="{% static 'js/app.js' %}" defer></script>
</body>
</html>
```

#### `apps/dashboard/tests/test_dashboard.py`

*588 lignes* — Tableau de bord : visibilité par rôle, centre d'alertes, indicateurs, cache, performance.

```python
"""Tableau de bord : visibilité par rôle, centre d'alertes, indicateurs, cache, performance."""

from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.customers.tests.factories import ClientFactory
from apps.dashboard import services
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.models import StatutVehicule, TypeDocument
from apps.fleet.tests.factories import DocumentReglementaireFactory, VehiculeFactory
from apps.fuel import services as fuel_services
from apps.hr import services as hr_services
from apps.hr.models import Conge, StatutConge
from apps.hr.tests.factories import PersonnelFactory
from apps.inventory.tests.factories import ArticleFactory
from apps.missions.models import StatutMission
from apps.missions.tests.factories import MissionFactory

pytestmark = pytest.mark.django_db

AUJOURD_HUI = date(2026, 9, 1)


def _utilisateur(role):
    return UserFactory(role=role)


def _page(client, role):
    client.force_login(_utilisateur(role))
    return client.get(reverse("home"))


# --- accès et visibilité ---


@pytest.mark.parametrize("role", list(Role.values))
def test_tous_les_roles_ouvrent_le_tableau_de_bord(client, role):
    assert _page(client, role).status_code == 200


def test_le_tableau_de_bord_exige_la_connexion(client):
    assert client.get(reverse("home")).status_code == 302


VISIBLE = {
    #  exploitation, alertes, rh, clientele, finances
    Role.ADMIN: (True, True, True, True, True),
    Role.DIRECTION: (True, True, True, True, True),
    # Retour réunion : la RH fait tout ce que fait la FINANCES, y compris ce bloc.
    Role.RH: (False, True, True, False, True),
    Role.CHARGE_CLIENTELE: (False, False, False, True, False),
    Role.PARCAUTO: (True, True, False, False, False),
    Role.FINANCES: (False, True, False, False, True),
    Role.CHAUFFEUR: (False, False, False, False, False),
}


@pytest.mark.parametrize("role", list(VISIBLE))
def test_chaque_role_ne_voit_que_ses_blocs(role):
    tableau = services.tableau_de_bord(_utilisateur(role), aujourd_hui=AUJOURD_HUI)

    attendu = VISIBLE[role]
    assert (
        tableau["exploitation"] is not None,
        tableau["alertes"] is not None,
        tableau["ressources_humaines"] is not None,
        tableau["clientele"] is not None,
        tableau["finances"] is not None,
    ) == attendu
    assert tableau["espace_mobile"] == (role == Role.CHAUFFEUR)


def test_un_superutilisateur_sans_role_voit_le_tableau_de_bord_de_l_admin(client):
    client.force_login(UserFactory(role="", is_superuser=True, is_staff=True))

    reponse = client.get(reverse("home"))

    assert reponse.status_code == 200 and reponse.context["exploitation"] is not None


def test_le_chauffeur_est_renvoye_vers_l_espace_mobile(client):
    texte = _page(client, Role.CHAUFFEUR).content.decode()

    assert "espace mobile" in texte and "Centre d'alertes" not in texte


def test_les_finances_voient_leurs_indicateurs_du_mois(client):
    texte = _page(client, Role.FINANCES).content.decode()

    for libelle in ("Finances du mois", "CA facturé (HT)", "Total encaissé", "Charges du mois",
                    "Marge nette", "Créances clients", "Trésorerie"):
        assert libelle in texte
    assert "Centre d'alertes" in texte


def test_les_autres_roles_ne_voient_pas_les_finances(client):
    for role in (Role.PARCAUTO, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR):
        assert "Finances du mois" not in _page(client, role).content.decode()


def test_les_blocs_interdits_ne_sont_pas_dans_la_page_du_charge_clientele(client):
    texte = _page(client, Role.CHARGE_CLIENTELE).content.decode()

    assert "Clientèle" in texte
    for titre in ("Centre d'alertes", "Ressources humaines", "Indicateurs financiers"):
        assert titre not in texte


# --- exploitation ---


def test_indicateurs_d_exploitation():
    for statut in (StatutVehicule.DISPONIBLE, StatutVehicule.DISPONIBLE, StatutVehicule.EN_MISSION,
                   StatutVehicule.EN_MAINTENANCE, StatutVehicule.IMMOBILISE):
        VehiculeFactory(statut=statut)
    MissionFactory(statut=StatutMission.PLANIFIEE)
    MissionFactory(statut=StatutMission.LIVREE, vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory())

    exploitation = services.exploitation()

    assert exploitation["camions"] == {
        "total": 6, "disponibles": 3, "en_mission": 1, "au_garage": 1,
        "immobilises": 1, "hors_service": 0,
    }
    assert exploitation["missions_a_affecter"] == 1 and exploitation["missions_a_cloturer"] == 1
    assert exploitation["missions_en_cours"] == 0
    assert exploitation["consommation"] is None


def test_la_consommation_moyenne_globale_s_affiche(client):
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    jour = timezone.localdate() - timedelta(days=10)
    for rang, (km, litres) in enumerate([(1000, 100), (1400, 120)]):
        fuel_services.enregistrer_plein(
            vehicule=camion, chauffeur=chauffeur, date_plein=jour + timedelta(days=rang),
            station="T", quantite_litres=Decimal(litres), prix_unitaire=Decimal("655"),
            km_compteur=km, numero_ticket=f"C-{rang}",
        )

    texte = _page(client, Role.PARCAUTO).content.decode()

    assert "30,0" in texte and "L/100 km" in texte


def test_sans_donnees_la_page_reste_lisible(client):
    texte = _page(client, Role.ADMIN).content.decode()

    assert "Pas encore de plein" in texte
    assert "Aucune alerte" in texte
    assert "Personne n" in texte and "Aucun départ prévu" in texte


# --- centre d'alertes ---


def _groupes(role, **kwargs):
    return {g["code"]: g for g in services.centre_alertes(role, aujourd_hui=AUJOURD_HUI, **kwargs)}


def test_alerte_documents_avec_niveau_et_comptes():
    DocumentReglementaireFactory(
        type_document=TypeDocument.ASSURANCE, date_expiration=AUJOURD_HUI + timedelta(days=10)
    )
    DocumentReglementaireFactory(date_expiration=AUJOURD_HUI + timedelta(days=200))  # pas concerné

    groupe = _groupes(Role.PARCAUTO)["documents"]

    assert groupe["nombre"] == 1 and groupe["niveau"] == "ATTENTION"
    assert groupe["lignes"][0]["detail"] == "expire dans 10 j"
    assert groupe["lignes"][0]["libelle"].startswith("Assurance · ")


def test_un_document_expire_rend_l_alerte_urgente():
    DocumentReglementaireFactory(date_expiration=AUJOURD_HUI - timedelta(days=4))

    groupe = _groupes(Role.PARCAUTO)["documents"]

    assert groupe["niveau"] == "URGENT" and groupe["lignes"][0]["detail"] == "expiré depuis 4 j"


def test_un_groupe_n_affiche_que_5_lignes_mais_compte_toutes_les_alertes():
    for i in range(8):
        DocumentReglementaireFactory(date_expiration=AUJOURD_HUI + timedelta(days=i + 1))

    groupe = _groupes(Role.PARCAUTO)["documents"]

    assert groupe["nombre"] == 8 and len(groupe["lignes"]) == 5 and groupe["autres"] == 3
    delais = [ligne["detail"] for ligne in groupe["lignes"]]
    assert delais[0] == "expire dans 1 j"  # les plus proches d'abord


def test_alerte_chauffeurs_par_document_les_plus_proches_d_abord():
    ChauffeurFactory(
        date_expiration_permis=AUJOURD_HUI + timedelta(days=20),
        date_expiration_visite_medicale=AUJOURD_HUI + timedelta(days=3),
    )

    groupe = _groupes(Role.RH)["chauffeurs"]

    assert groupe["nombre"] == 2
    assert groupe["lignes"][0]["libelle"].startswith("Visite médicale · ")
    assert groupe["lignes"][1]["libelle"].startswith("Permis · ")


def test_un_chauffeur_inactif_n_apparait_pas_dans_les_alertes():
    ChauffeurFactory(statut="INACTIF", date_expiration_permis=AUJOURD_HUI - timedelta(days=9))

    assert "chauffeurs" not in _groupes(Role.RH)


def test_alerte_stock_rupture_urgente_et_stock_bas_attention():
    ArticleFactory(designation="Filtre", reference="F-1", quantite=3, seuil_minimal=5)
    assert _groupes(Role.PARCAUTO)["stock"]["niveau"] == "ATTENTION"

    ArticleFactory(designation="Courroie", reference="C-1", quantite=0, seuil_minimal=2)
    groupe = _groupes(Role.PARCAUTO)["stock"]

    assert groupe["niveau"] == "URGENT" and groupe["nombre"] == 2
    assert groupe["lignes"][0]["detail"] == "rupture"  # les ruptures d'abord
    assert "3 en stock, seuil 5" in groupe["lignes"][1]["detail"]


def test_un_article_sans_seuil_n_est_pas_surveille():
    ArticleFactory(quantite=0, seuil_minimal=0)

    assert "stock" not in _groupes(Role.PARCAUTO)


def _plein_a_surveiller(jours_avant, litres_second=200):
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    aujourd_hui = timezone.localdate()
    fuel_services.enregistrer_plein(
        vehicule=camion, chauffeur=chauffeur, date_plein=aujourd_hui - timedelta(days=jours_avant + 5),
        station="T", quantite_litres=Decimal("100"), prix_unitaire=Decimal("655"),
        km_compteur=1000, numero_ticket=f"K-{camion.pk}-0",
    )
    fuel_services.enregistrer_plein(
        vehicule=camion, chauffeur=chauffeur, date_plein=aujourd_hui - timedelta(days=jours_avant),
        station="T", quantite_litres=Decimal(litres_second), prix_unitaire=Decimal("655"),
        km_compteur=1400, numero_ticket=f"K-{camion.pk}-1", confirmer_alerte_saisie=True,
    )
    return camion


def test_alerte_carburant_sur_les_30_derniers_jours_seulement():
    recent = _plein_a_surveiller(5)  # 50 L/100 km : anomalie
    _plein_a_surveiller(50)

    groupes = services.centre_alertes(Role.PARCAUTO, aujourd_hui=timezone.localdate())
    carburant = next(g for g in groupes if g["code"] == "carburant")

    assert carburant["nombre"] == 1 and carburant["niveau"] == "URGENT"
    assert carburant["lignes"][0]["libelle"].startswith(recent.immatriculation)
    assert "50,0 L/100 km" in carburant["lignes"][0]["detail"]


def test_alerte_conges_en_retard_pour_la_rh_la_direction_et_l_admin():
    employe = PersonnelFactory(nom="Bamba", prenom="Issa")
    Conge.objects.create(
        employe=employe, date_debut=date(2026, 10, 1), date_fin=date(2026, 10, 5), jours=5,
        motif="x", statut=StatutConge.DEMANDE,
        date_limite_n1=timezone.now() - timedelta(hours=5),
    )

    for role in (Role.RH, Role.DIRECTION, Role.ADMIN):
        groupe = _groupes(role)["conges"]
        assert groupe["lignes"][0]["libelle"] == "Issa Bamba"
        assert groupe["lignes"][0]["detail"] == "validation N1 en retard"


def test_chaque_role_ne_recoit_que_les_alertes_de_ses_ecrans():
    DocumentReglementaireFactory(date_expiration=AUJOURD_HUI + timedelta(days=2))
    ChauffeurFactory(date_expiration_permis=AUJOURD_HUI + timedelta(days=2))
    ArticleFactory(quantite=0, seuil_minimal=2)

    assert set(_groupes(Role.PARCAUTO)) == {"documents", "stock"}
    assert set(_groupes(Role.RH)) == {"chauffeurs"}
    assert set(_groupes(Role.DIRECTION)) == {"documents", "chauffeurs", "stock"}
    assert services.centre_alertes(Role.FINANCES, aujourd_hui=AUJOURD_HUI) == []  # aucune facture échue
    assert services.centre_alertes(Role.CHARGE_CLIENTELE, aujourd_hui=AUJOURD_HUI) is None
    assert services.centre_alertes(Role.CHAUFFEUR, aujourd_hui=AUJOURD_HUI) is None


def test_la_page_liste_les_alertes_avec_liens_et_voir_tout(client):
    document = DocumentReglementaireFactory(
        date_expiration=timezone.localdate() + timedelta(days=5)
    )

    texte = _page(client, Role.PARCAUTO).content.decode()

    assert "Centre d'alertes" in texte and "Documents des camions à renouveler" in texte
    assert reverse("fleet:detail", args=[document.vehicule_id]) in texte
    assert f"{reverse('fleet:liste')}?alerte=1" in texte
    assert "Aucune alerte" not in texte


def test_les_textes_saisis_sont_echappes_dans_les_alertes(client):
    ArticleFactory(designation="<script>alert(1)</script>", quantite=0, seuil_minimal=2)

    texte = _page(client, Role.PARCAUTO).content.decode()

    assert "<script>alert(1)</script>" not in texte
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in texte


# --- ressources humaines ---


def test_bloc_ressources_humaines(client):
    aujourd_hui = timezone.localdate()
    absent, futur, demandeur = PersonnelFactory(nom="Absent"), PersonnelFactory(nom="Futur"), PersonnelFactory()
    Conge.objects.create(employe=absent, date_debut=aujourd_hui - timedelta(days=1),
                         date_fin=aujourd_hui + timedelta(days=2), jours=3, motif="x",
                         statut=StatutConge.EN_COURS)
    Conge.objects.create(employe=futur, date_debut=aujourd_hui + timedelta(days=10),
                         date_fin=aujourd_hui + timedelta(days=14), jours=5, motif="x",
                         statut=StatutConge.APPROUVE)
    Conge.objects.create(employe=demandeur, date_debut=aujourd_hui + timedelta(days=40),
                         date_fin=aujourd_hui + timedelta(days=44), jours=5, motif="x",
                         statut=StatutConge.DEMANDE)

    reponse = _page(client, Role.RH)
    rh = reponse.context["ressources_humaines"]

    assert rh["effectif"] == 3 and rh["nombre_absents"] == 1
    assert [c.employe.nom for c in rh["absents"]] == ["Absent"]
    assert [c.employe.nom for c in rh["prochains"]] == ["Futur"]
    assert rh["en_attente"] == {"n1": 1, "n2": 0}
    texte = reponse.content.decode()
    assert "Absents aujourd" in texte and "Prochains départs en congé" in texte


# --- clientèle ---


def test_bloc_clientele(client):
    gros, petit = ClientFactory(raison_sociale="Gros Client"), ClientFactory(raison_sociale="Petit Client")
    for client_mission, montant in ((gros, "900000"), (petit, "100000")):
        mission = MissionFactory(
            client=client_mission, statut=StatutMission.LIVREE, prix_convenu=Decimal(montant),
            vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory(),
        )
        type(mission).objects.filter(pk=mission.pk).update(date_livraison=timezone.now())

    reponse = _page(client, Role.CHARGE_CLIENTELE)

    assert reponse.context["clientele"]["clients_actifs"] == 2
    texte = reponse.content.decode()
    assert texte.index("Gros Client") < texte.index("Petit Client")
    assert "900 000" in " ".join(texte.replace(" ", " ").replace(" ", " ").split())  # valeur au bout de la barre
    assert "Top 3 des clients" in texte


# --- cache ---


def test_les_indicateurs_sont_mis_en_cache_selon_le_reglage(settings):
    settings.DASHBOARD_CACHE_SECONDS = 60
    cache.clear()
    VehiculeFactory(statut=StatutVehicule.DISPONIBLE)
    premier = services.exploitation()

    VehiculeFactory(statut=StatutVehicule.DISPONIBLE)
    en_cache = services.exploitation()

    assert premier["camions"]["total"] == 1 and en_cache["camions"]["total"] == 1
    cache.clear()
    assert services.exploitation()["camions"]["total"] == 2


def test_sans_cache_les_indicateurs_sont_toujours_a_jour(settings):
    settings.DASHBOARD_CACHE_SECONDS = 0
    VehiculeFactory()
    assert services.exploitation()["camions"]["total"] == 1
    VehiculeFactory()
    assert services.exploitation()["camions"]["total"] == 2


def test_le_centre_d_alertes_n_est_jamais_mis_en_cache(settings):
    settings.DASHBOARD_CACHE_SECONDS = 60
    cache.clear()
    assert services.centre_alertes(Role.PARCAUTO, aujourd_hui=AUJOURD_HUI) == []

    DocumentReglementaireFactory(date_expiration=AUJOURD_HUI + timedelta(days=1))

    assert len(services.centre_alertes(Role.PARCAUTO, aujourd_hui=AUJOURD_HUI)) == 1
    cache.clear()


# --- performance ---


def test_le_tableau_de_bord_de_l_admin_reste_a_requetes_constantes(client, django_assert_max_num_queries):
    for i in range(15):
        VehiculeFactory()
        DocumentReglementaireFactory(date_expiration=timezone.localdate() + timedelta(days=i))
        ArticleFactory(quantite=0, seuil_minimal=2)
        ChauffeurFactory(date_expiration_permis=timezone.localdate() + timedelta(days=i))
        MissionFactory(client=ClientFactory())
    client.force_login(_utilisateur(Role.ADMIN))

    with django_assert_max_num_queries(80):
        assert client.get(reverse("home")).status_code == 200


# --- finances et factures échues ---


def _facture_emise(prix="1000000", jour=date(2026, 9, 1), **surcharges):
    from apps.billing.tests.helpers import emise

    return emise(prix=prix, aujourd_hui=jour, **surcharges)


def test_le_bloc_finances_reprend_les_indicateurs_du_mois():
    from apps.billing import services as billing
    from apps.billing.models import ModePaiement
    from apps.billing.tests.helpers import finances as compte_finances

    facture = _facture_emise(prix="1000000", jour=date(2026, 9, 3))
    billing.enregistrer_reglement(
        facture, compte_finances(), montant=Decimal("400000"), mode=ModePaiement.WAVE,
        date_reglement=date(2026, 9, 10),
    )
    billing.enregistrer_depense(
        compte_finances(), categorie="PEAGES", date_depense=date(2026, 9, 5), libelle="Péage",
        montant=Decimal("50000"), mode=ModePaiement.ESPECES,
    )

    kpi = services.finances(jour=date(2026, 9, 15))

    assert kpi["chiffre_affaires"] == Decimal("1000000")
    assert kpi["encaisse"] == Decimal("400000")
    assert kpi["charges"]["depenses"] == Decimal("50000")
    assert kpi["marge_nette"] == Decimal("950000")
    assert kpi["creances"]["total"] == Decimal("780000")
    assert kpi["tresorerie"] == Decimal("350000")


def test_alerte_des_factures_impayees_echues_pour_finances_direction_et_admin():
    _facture_emise(jour=date(2026, 8, 1))  # échéance 2026-08-31, dépassée au 1er septembre

    for role in (Role.FINANCES, Role.DIRECTION, Role.ADMIN):
        groupe = _groupes(role)["factures"]
        assert groupe["niveau"] == "URGENT" and groupe["nombre"] == 1
        assert "reste 1 180 000 FCFA" in groupe["lignes"][0]["detail"].replace("\u202f", " ").replace("\xa0", " ")
        assert "échue depuis 1 j" in groupe["lignes"][0]["detail"]
    assert "factures" not in _groupes(Role.PARCAUTO)


def test_pas_d_alerte_pour_une_facture_non_echue_ou_soldee():
    from apps.billing import services as billing
    from apps.billing.models import ModePaiement
    from apps.billing.tests.helpers import finances as compte_finances

    _facture_emise(jour=date(2026, 8, 25))  # échéance 24/09 : pas encore
    soldee = _facture_emise(jour=date(2026, 8, 1), prix="1000")
    billing.enregistrer_reglement(
        soldee, compte_finances(), montant=Decimal("1180"), mode=ModePaiement.VIREMENT,
        date_reglement=date(2026, 8, 5),
    )

    assert "factures" not in _groupes(Role.FINANCES)


def test_les_indicateurs_financiers_peuvent_etre_mis_en_cache(settings):
    settings.DASHBOARD_CACHE_SECONDS = 60
    cache.clear()
    premier = services.finances(jour=date(2026, 9, 15))
    _facture_emise(jour=date(2026, 9, 3))

    assert services.finances(jour=date(2026, 9, 15)) == premier
    cache.clear()
    assert services.finances(jour=date(2026, 9, 15))["chiffre_affaires"] == Decimal("1000000")


# --- graphiques ---


def _texte_page(reponse):
    return reponse.content.decode().replace("\u202f", " ").replace("\xa0", " ")


def test_l_historique_mensuel_couvre_six_mois_et_le_mois_en_cours_s_arrete_a_aujourd_hui():
    from apps.billing import services as billing
    from apps.billing.models import ModePaiement
    from apps.billing.tests.helpers import finances as compte_finances

    facture = _facture_emise(prix="1000000", jour=date(2026, 8, 12))  # émise en août
    billing.enregistrer_reglement(
        facture, compte_finances(), montant=Decimal("500000"), mode=ModePaiement.WAVE, date_reglement=date(2026, 9, 2)
    )

    historique = services.finances(jour=date(2026, 9, 15))["graphique_mensuel"]

    assert [g["libelle"] for g in historique["grappes"]] == ["avr. 26", "mai 26", "juin 26", "juil. 26", "août 26", "sept. 26"]
    ca, encaisse, charges = historique["tableau"]["entetes"]
    assert (ca, encaisse, charges) == ("CA facturé (HT)", "Encaissé", "Charges")
    lignes = {l["libelle"]: [v.replace("\u202f", " ").replace("\xa0", " ") for v in l["valeurs"]] for l in historique["tableau"]["lignes"]}
    assert lignes["août 26"] == ["1 000 000", "0", "0"]
    assert lignes["sept. 26"] == ["0", "500 000", "0"]
    assert lignes["avr. 26"] == ["0", "0", "0"]


def test_l_historique_du_mois_en_cours_reprend_les_indicateurs_sans_les_relire(django_assert_num_queries):
    from apps.finance import services as finance_services

    courant = {"chiffre_affaires": Decimal("7"), "encaisse": Decimal("8"), "charges": Decimal("9")}

    lignes = finance_services.historique_mensuel(date(2026, 1, 20), mois=1, courant=courant)

    assert [(l["debut"], l["fin"]) for l in lignes] == [(date(2026, 1, 1), date(2026, 1, 20))]
    assert (lignes[0]["chiffre_affaires"], lignes[0]["encaisse"], lignes[0]["charges"]) == (7, 8, 9)


def test_l_historique_mensuel_traverse_le_changement_d_annee():
    from apps.finance import services as finance_services

    lignes = finance_services.historique_mensuel(date(2026, 2, 10), mois=4)

    assert [l["debut"] for l in lignes] == [date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1), date(2026, 2, 1)]
    assert lignes[0]["fin"] == date(2025, 11, 30) and lignes[-1]["fin"] == date(2026, 2, 10)


def test_le_bloc_finances_affiche_les_graphiques(client):
    _facture_emise(prix="1000000", jour=timezone.localdate())

    texte = _texte_page(_page(client, Role.FINANCES))

    assert "Facturé, encaissé et charges" in texte and "viz-grappe" in texte
    assert "Charges du mois" in texte and "Voir en tableau" in texte


def test_les_graphiques_d_exploitation_suivent_les_statuts(client):
    VehiculeFactory(statut=StatutVehicule.DISPONIBLE)
    VehiculeFactory(statut=StatutVehicule.EN_MISSION)
    MissionFactory(client=ClientFactory(), statut=StatutMission.PLANIFIEE)

    reponse = _page(client, Role.DIRECTION)

    camions = {l["libelle"]: l["valeur_texte"] for l in reponse.context["exploitation"]["graphique_camions"]["lignes"]}
    missions = {l["libelle"]: l["valeur_texte"] for l in reponse.context["exploitation"]["graphique_missions"]["lignes"]}
    assert camions["Disponible"] == "1" and camions["En mission"] == "1" and camions["Hors service"] == "0"
    assert missions["Planifiée"] == "1"
    texte = _texte_page(reponse)
    assert "Camions par statut" in texte and "Missions par statut" in texte


def test_le_parc_auto_ne_voit_pas_le_graphique_des_missions(client):
    VehiculeFactory()

    texte = _texte_page(_page(client, Role.PARCAUTO))

    assert "Camions par statut" in texte and "Missions par statut" not in texte


def test_le_graphique_de_l_effectif_reprend_les_departements(client):
    PersonnelFactory(departement="EXPLOITATION")
    PersonnelFactory(departement="EXPLOITATION")
    PersonnelFactory(departement="DIRECTION")

    reponse = _page(client, Role.RH)

    lignes = {l["libelle"]: (l["valeur_texte"], l["largeur"]) for l in reponse.context["ressources_humaines"]["graphique_departements"]["lignes"]}
    assert lignes["Exploitation"] == ("2", 100) and lignes["Direction"] == ("1", 50) and lignes["Comptabilité"] == ("0", 0)


def test_le_graphique_des_clients_renvoie_a_la_fiche_client(client):
    gros = ClientFactory(raison_sociale="Gros Client")
    mission = MissionFactory(
        client=gros, statut=StatutMission.LIVREE, prix_convenu=Decimal("900000"),
        vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory(),
    )
    type(mission).objects.filter(pk=mission.pk).update(date_livraison=timezone.now())

    reponse = _page(client, Role.CHARGE_CLIENTELE)

    ligne = reponse.context["clientele"]["graphique_clients"]["lignes"][0]
    assert ligne["url"] == reverse("customers:detail", args=[gros.pk]) and ligne["detail"] == "1 mission"
    assert ligne["url"] in reponse.content.decode()
```

#### `apps/dashboard/tests/test_impression.py`

*83 lignes* — Rapport imprimable du tableau de bord : mêmes blocs et mêmes droits que l'écran.

```python
"""Rapport imprimable du tableau de bord : mêmes blocs et mêmes droits que l'écran."""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing.tests.helpers import emise
from apps.customers.tests.factories import ClientFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.missions.models import StatutMission
from apps.missions.tests.factories import MissionFactory

pytestmark = pytest.mark.django_db


def _texte(reponse) -> str:
    return reponse.content.decode().replace(" ", " ").replace("\xa0", " ")


def test_impression_du_tableau_de_bord_direction(client):
    client.force_login(UserFactory(role=Role.DIRECTION))
    VehiculeFactory(statut="DISPONIBLE")
    MissionFactory(client=ClientFactory(), statut=StatutMission.PLANIFIEE)

    reponse = client.get(reverse("home_imprimer"))

    assert reponse.status_code == 200
    texte = _texte(reponse)
    assert "Tableau de bord" in texte and "Direction" in texte
    assert "Exploitation" in texte and "Camions par statut" in texte
    assert "Finances du mois" in texte


def test_le_tableau_de_bord_du_chauffeur_n_est_pas_imprime_comme_un_bureau(client):
    from apps.hr.tests.factories import PersonnelFactory

    chauffeur = ChauffeurFactory(personnel=PersonnelFactory(utilisateur=UserFactory(role=Role.CHAUFFEUR)))
    client.force_login(chauffeur.personnel.utilisateur)

    texte = _texte(client.get(reverse("home_imprimer")))

    assert "Aucun rapport de bureau" in texte


def test_le_role_parcauto_ne_voit_pas_les_missions_dans_le_rapport(client):
    client.force_login(UserFactory(role=Role.PARCAUTO))
    VehiculeFactory(statut="DISPONIBLE")

    texte = _texte(client.get(reverse("home_imprimer")))

    assert "Camions par statut" in texte and "Missions par statut" not in texte


def test_le_rapport_suit_la_periode_demandee(client):
    client.force_login(UserFactory(role=Role.FINANCES))
    emise(prix="1000000", aujourd_hui=date(2026, 9, 1))

    reponse = client.get(reverse("home_imprimer"), {"periode": "12"})

    assert len(reponse.context["finances"]["graphique_mensuel"]["grappes"]) == 12


def test_un_role_sans_acces_financier_n_a_pas_ce_bloc(client):
    # Retour réunion : la RH fait désormais tout ce que fait la FINANCES (bloc inclus) ; le Parc
    # Auto, lui, n'y a jamais eu accès.
    client.force_login(UserFactory(role=Role.PARCAUTO))

    texte = _texte(client.get(reverse("home_imprimer")))

    assert "Finances du mois" not in texte and "Exploitation" in texte


def test_le_lien_imprimer_est_sur_le_tableau_de_bord(client):
    client.force_login(UserFactory(role=Role.DIRECTION))

    page = client.get(reverse("home")).content.decode()

    assert reverse("home_imprimer") in page
```

#### `apps/dashboard/tests/test_lectures_metier.py`

*231 lignes* — Lectures des apps métier qui alimentent le tableau de bord.

```python
"""Lectures des apps métier qui alimentent le tableau de bord."""

from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.customers import services as customers_services
from apps.customers.models import TypeInteraction
from apps.customers.tests.factories import ClientFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet import services as fleet_services
from apps.fleet.models import StatutVehicule
from apps.fleet.tests.factories import VehiculeFactory
from apps.fuel import services as fuel_services
from apps.hr import services as hr_services
from apps.hr.models import Conge, Departement, StatutConge
from apps.hr.tests.factories import PersonnelFactory
from apps.missions import services as missions_services
from apps.missions.models import StatutMission
from apps.missions.tests.factories import MissionFactory

pytestmark = pytest.mark.django_db

AUJOURD_HUI = date(2026, 9, 1)
MAINTENANT = datetime(2026, 9, 1, 8, 0, tzinfo=dt_timezone.utc)


# --- flotte ---


def test_repartition_des_camions_par_statut_avec_zeros_et_total():
    for statut in (StatutVehicule.DISPONIBLE, StatutVehicule.DISPONIBLE, StatutVehicule.EN_MAINTENANCE):
        VehiculeFactory(statut=statut)

    repartition = fleet_services.repartition_statuts()

    assert repartition[StatutVehicule.DISPONIBLE] == 2
    assert repartition[StatutVehicule.EN_MAINTENANCE] == 1
    assert repartition[StatutVehicule.HORS_SERVICE] == 0
    assert repartition["total"] == 3


def test_repartition_sans_camion():
    assert fleet_services.repartition_statuts()["total"] == 0


# --- missions ---


def test_repartition_des_missions_par_statut():
    MissionFactory(statut=StatutMission.PLANIFIEE)
    MissionFactory(statut=StatutMission.PLANIFIEE)
    MissionFactory(statut=StatutMission.BROUILLON)

    repartition = missions_services.repartition_par_statut()

    assert repartition[StatutMission.PLANIFIEE] == 2
    assert repartition[StatutMission.BROUILLON] == 1
    assert repartition[StatutMission.LIVREE] == 0


def test_clients_actifs_compte_les_clients_distincts_sur_90_jours():
    actif, autre, ancien = ClientFactory(), ClientFactory(), ClientFactory()
    MissionFactory(client=actif)
    MissionFactory(client=actif)  # deux missions, un seul client
    MissionFactory(client=autre)
    vieille = MissionFactory(client=ancien)
    type(vieille).objects.filter(pk=vieille.pk).update(created_at=timezone.now() - timedelta(days=120))

    assert missions_services.clients_actifs() == 2


def _livree(client, montant, *, jours=10, statut=StatutMission.LIVREE):
    mission = MissionFactory(
        client=client, statut=statut, prix_convenu=Decimal(montant),
        vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory(),
    )
    type(mission).objects.filter(pk=mission.pk).update(
        date_livraison=timezone.now() - timedelta(days=jours)
    )
    return mission


def test_meilleurs_clients_classes_par_montant_livre_ou_cloture():
    petit, gros, moyen, quatrieme = (ClientFactory(raison_sociale=n) for n in ("Petit", "Gros", "Moyen", "Quatrième"))
    _livree(gros, "900000")
    _livree(gros, "300000", statut=StatutMission.CLOTUREE)
    _livree(moyen, "800000")
    _livree(petit, "100000")
    _livree(quatrieme, "50000")

    classement = missions_services.meilleurs_clients(limite=3)

    assert [c["client"] for c in classement] == ["Gros", "Moyen", "Petit"]
    assert classement[0]["montant"] == Decimal("1200000") and classement[0]["missions"] == 2


def test_meilleurs_clients_ignore_les_missions_non_livrees_et_trop_anciennes():
    client = ClientFactory()
    MissionFactory(client=client, statut=StatutMission.PLANIFIEE, prix_convenu=Decimal("5000000"))
    _livree(client, "700000", jours=400)  # plus de 12 mois

    assert missions_services.meilleurs_clients() == []


def test_meilleurs_clients_departage_les_egalites_par_nom():
    b, a = ClientFactory(raison_sociale="Beta"), ClientFactory(raison_sociale="Alpha")
    _livree(b, "500000")
    _livree(a, "500000")

    assert [c["client"] for c in missions_services.meilleurs_clients()] == ["Alpha", "Beta"]


# --- clients ---


def test_reclamations_recentes_ne_compte_que_les_reclamations_des_30_derniers_jours():
    client, auteur = ClientFactory(), UserFactory(role=Role.CHARGE_CLIENTELE)
    for type_interaction, age in (
        (TypeInteraction.RECLAMATION, 2),
        (TypeInteraction.RECLAMATION, 20),
        (TypeInteraction.RECLAMATION, 45),  # trop ancienne
        (TypeInteraction.APPEL, 1),  # pas une réclamation
    ):
        customers_services.enregistrer_interaction(
            client, auteur, type_interaction=type_interaction, resume="x",
            date_interaction=timezone.now() - timedelta(days=age),
        )

    assert customers_services.reclamations_recentes() == 2


# --- RH ---


def _personnel(**surcharges):
    return PersonnelFactory(**surcharges)


def _conge(employe, statut, debut, fin, **surcharges):
    return Conge.objects.create(
        employe=employe, date_debut=debut, date_fin=fin, jours=5, motif="x", statut=statut, **surcharges
    )


def test_effectif_par_departement_avec_zeros():
    _personnel(departement=Departement.COMMERCIAL)
    _personnel(departement=Departement.COMMERCIAL)
    _personnel(departement=Departement.PARC_AUTO)

    effectif = {d["code"]: d["nombre"] for d in hr_services.effectif_par_departement()}

    assert effectif[Departement.COMMERCIAL] == 2 and effectif[Departement.PARC_AUTO] == 1
    assert effectif[Departement.DIRECTION] == 0
    assert len(effectif) == len(Departement.choices)


def test_absents_du_jour_inclut_les_conges_approuves_ou_en_cours_qui_couvrent_la_date():
    a, b, c, d = (_personnel() for _ in range(4))
    _conge(a, StatutConge.EN_COURS, date(2026, 8, 31), date(2026, 9, 4))
    _conge(b, StatutConge.APPROUVE, date(2026, 9, 1), date(2026, 9, 1))  # le jour même
    _conge(c, StatutConge.APPROUVE, date(2026, 9, 2), date(2026, 9, 5))  # pas encore
    _conge(d, StatutConge.REFUSE, date(2026, 8, 31), date(2026, 9, 4))  # refusé

    assert {x.employe for x in hr_services.absents_du_jour(AUJOURD_HUI)} == {a, b}


def test_prochains_conges_dans_les_30_jours_tries_par_date():
    a, b, c = _personnel(), _personnel(), _personnel()
    _conge(a, StatutConge.APPROUVE, date(2026, 9, 20), date(2026, 9, 25))
    _conge(b, StatutConge.APPROUVE, date(2026, 9, 5), date(2026, 9, 9))
    _conge(c, StatutConge.APPROUVE, date(2026, 12, 1), date(2026, 12, 5))  # trop loin

    assert [x.employe for x in hr_services.prochains_conges(AUJOURD_HUI)] == [b, a]


def test_conges_en_attente_par_niveau():
    a, b = _personnel(), _personnel()
    _conge(a, StatutConge.DEMANDE, date(2026, 10, 1), date(2026, 10, 5))
    _conge(a, StatutConge.DEMANDE, date(2026, 11, 1), date(2026, 11, 5))
    _conge(b, StatutConge.VALIDATION_N1, date(2026, 10, 1), date(2026, 10, 5))
    _conge(b, StatutConge.APPROUVE, date(2026, 12, 1), date(2026, 12, 5))

    assert hr_services.conges_en_attente() == {"n1": 2, "n2": 1}


def test_conges_en_retard_selon_le_delai_du_niveau_en_cours():
    a, b, c = _personnel(), _personnel(), _personnel()
    passe, futur = MAINTENANT - timedelta(hours=1), MAINTENANT + timedelta(hours=1)
    retard_n1 = _conge(a, StatutConge.DEMANDE, date(2026, 10, 1), date(2026, 10, 5), date_limite_n1=passe)
    _conge(b, StatutConge.DEMANDE, date(2026, 10, 1), date(2026, 10, 5), date_limite_n1=futur)
    retard_n2 = _conge(c, StatutConge.VALIDATION_N1, date(2026, 10, 1), date(2026, 10, 5), date_limite_n2=passe)
    _conge(a, StatutConge.APPROUVE, date(2026, 12, 1), date(2026, 12, 5), date_limite_n1=passe)

    assert set(hr_services.conges_en_retard(MAINTENANT)) == {retard_n1, retard_n2}


# --- carburant ---


def _plein_alerte(jours_avant):
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    debut = timezone.localdate() - timedelta(days=jours_avant + 5)
    fuel_services.enregistrer_plein(
        vehicule=camion, chauffeur=chauffeur, date_plein=debut, station="T",
        quantite_litres=Decimal("100"), prix_unitaire=Decimal("655"), km_compteur=1000,
        numero_ticket=f"D-{camion.pk}-0",
    )
    return fuel_services.enregistrer_plein(
        vehicule=camion, chauffeur=chauffeur, date_plein=timezone.localdate() - timedelta(days=jours_avant),
        station="T", quantite_litres=Decimal("200"), prix_unitaire=Decimal("655"),
        km_compteur=1400, numero_ticket=f"D-{camion.pk}-1", confirmer_alerte_saisie=True,
    )


def test_pleins_a_surveiller_peut_se_limiter_aux_pleins_recents():
    recent = _plein_alerte(3)
    ancien = _plein_alerte(60)  # 50 L/100 km : anomalie

    tous = set(fuel_services.pleins_a_surveiller())
    recents = set(
        fuel_services.pleins_a_surveiller(depuis=timezone.localdate() - timedelta(days=30))
    )

    assert {recent, ancien} <= tous
    assert recent in recents and ancien not in recents
```

#### `apps/dashboard/tests/test_series_mensuelles.py`

*194 lignes* — Séries mensuelles, créances par ancienneté et sélecteur de période des graphiques du tableau de bord.

```python
"""Séries mensuelles, créances par ancienneté et sélecteur de période des graphiques du tableau de bord."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services as billing
from apps.billing.models import ModePaiement
from apps.billing.tests.helpers import emise, finances
from apps.core import services as core
from apps.customers.tests.factories import ClientFactory
from apps.dashboard import services
from apps.finance import services as finance_services
from apps.fuel import services as fuel_services
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.missions import services as missions_services
from apps.missions.models import Mission, StatutMission
from apps.missions.tests.factories import MissionFactory

pytestmark = pytest.mark.django_db


# --- mois ---


def test_les_debuts_de_mois_remontent_de_douze_mois_a_travers_l_annee():
    assert core.debuts_de_mois(date(2026, 2, 10), 4) == [date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1), date(2026, 2, 1)]
    assert core.debuts_de_mois(date(2026, 9, 24), 1) == [date(2026, 9, 1)]


def test_la_fin_de_mois_tient_compte_de_fevrier_et_des_annees_bissextiles():
    assert core.fin_de_mois(date(2026, 2, 1)) == date(2026, 2, 28)
    assert core.fin_de_mois(date(2028, 2, 1)) == date(2028, 2, 29)
    assert core.fin_de_mois(date(2026, 12, 1)) == date(2026, 12, 31)


# --- totaux par mois ---


def test_les_totaux_par_mois_sont_ceux_des_lectures_mois_par_mois():
    """Le graphique doit donner les mêmes chiffres que les indicateurs du mois (pas de logique en double)."""
    finance = finances()
    for jour, prix in ((date(2026, 7, 5), "1000000"), (date(2026, 8, 12), "2000000")):
        facture = emise(prix=prix, aujourd_hui=jour)
        billing.enregistrer_reglement(
            facture, finance, montant=Decimal("400000"), mode=ModePaiement.VIREMENT, date_reglement=jour
        )
        billing.enregistrer_depense(
            finance, categorie="PEAGES", date_depense=jour, libelle="Péage", montant=Decimal("30000"), mode=ModePaiement.ESPECES
        )
    fuel_services.enregistrer_plein(  # devient tout seul une dépense « carburant » (finance.receivers)
        vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory(), date_plein=date(2026, 8, 20), station="T",
        quantite_litres=Decimal("120"), prix_unitaire=Decimal("655"), km_compteur=1000, numero_ticket="T-1",
    )

    historique = finance_services.historique_mensuel(date(2026, 9, 15), mois=3)

    assert [ligne["debut"] for ligne in historique] == [date(2026, 7, 1), date(2026, 8, 1), date(2026, 9, 1)]
    for ligne in historique[:2]:
        direct = finance_services.indicateurs(ligne["debut"], ligne["fin"], aujourd_hui=ligne["fin"])
        assert ligne["chiffre_affaires"] == direct["chiffre_affaires"]
        assert ligne["encaisse"] == direct["encaisse"]
        assert ligne["charges"] == direct["charges"]["total"]
    assert historique[1]["charges"] == Decimal("30000") + Decimal("120") * Decimal("655")


def test_les_missions_creees_et_livrees_sont_comptees_par_mois():
    from apps.drivers.tests.factories import ChauffeurFactory
    from apps.fleet.tests.factories import VehiculeFactory

    client = ClientFactory()
    ancienne = MissionFactory(client=client)
    Mission.objects.filter(pk=ancienne.pk).update(created_at=timezone.now() - timedelta(days=45))
    MissionFactory(client=client)
    livree = MissionFactory(
        client=client, statut=StatutMission.LIVREE, vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory()
    )
    Mission.objects.filter(pk=livree.pk).update(date_livraison=timezone.now())
    aujourd_hui = timezone.localdate()

    par_mois = missions_services.missions_par_mois(aujourd_hui - timedelta(days=90), aujourd_hui)

    courant = (aujourd_hui.year, aujourd_hui.month)
    assert par_mois["creees"][courant] == 2 and sum(par_mois["creees"].values()) == 3
    assert par_mois["livrees"] == {courant: 1}


def test_creances_par_anciennete_repartit_le_reste_a_recouvrer_par_retard():
    emise(prix="100000", aujourd_hui=date(2026, 8, 25))  # échéance 24/09 : pas encore échue
    emise(prix="200000", aujourd_hui=date(2026, 8, 1))  # échue depuis 24 j
    emise(prix="300000", aujourd_hui=date(2026, 7, 1))  # échue depuis 55 j
    emise(prix="400000", aujourd_hui=date(2026, 5, 1))  # échue depuis plus de 60 j

    tranches = billing.creances_par_anciennete(date(2026, 9, 24))

    assert [t["libelle"] for t in tranches] == [
        "Pas encore échu", "En retard de 1 à 30 jours", "En retard de 31 à 60 jours", "En retard de plus de 60 jours",
    ]
    assert [t["montant"] for t in tranches] == [Decimal("118000"), Decimal("236000"), Decimal("354000"), Decimal("472000")]
    assert [t["nombre"] for t in tranches] == [1, 1, 1, 1]
    assert [t["echu"] for t in tranches] == [False, True, True, True]


def test_un_reglement_reduit_la_tranche_de_la_creance():
    facture = emise(prix="1000000", aujourd_hui=date(2026, 8, 1))
    billing.enregistrer_reglement(
        facture, finances(), montant=Decimal("500000"), mode=ModePaiement.WAVE, date_reglement=date(2026, 8, 10)
    )

    tranches = billing.creances_par_anciennete(date(2026, 9, 24))

    assert tranches[1]["montant"] == Decimal("680000") and tranches[1]["nombre"] == 1


# --- sélecteur de période ---


@pytest.mark.parametrize("valeur, attendu", [("3", 3), ("6", 6), ("12", 12), ("24", 6), ("abc", 6), (None, 6), ("", 6)])
def test_la_periode_n_accepte_que_3_6_ou_12_mois(valeur, attendu):
    assert services.periode_valide(valeur) == attendu


def test_le_tableau_de_bord_suit_la_periode_choisie(client):
    client.force_login(UserFactory(role=Role.DIRECTION))

    reponse = client.get(reverse("home"), {"periode": "12"})

    assert reponse.context["periode"] == 12
    assert len(reponse.context["finances"]["graphique_mensuel"]["grappes"]) == 12
    assert len(reponse.context["exploitation"]["graphique_missions_mois"]["grappes"]) == 12
    assert 'aria-current="true"' in reponse.content.decode()


def test_une_periode_invalide_revient_a_six_mois(client):
    client.force_login(UserFactory(role=Role.DIRECTION))

    reponse = client.get(reverse("home"), {"periode": "9999"})

    assert reponse.context["periode"] == 6


def test_le_selecteur_de_periode_n_apparait_que_s_il_y_a_des_graphiques_dans_le_temps(client):
    # Retour réunion : la RH fait désormais tout ce que fait la FINANCES (graphiques inclus).
    client.force_login(UserFactory(role=Role.PARCAUTO))

    assert "Graphiques dans le temps" not in client.get(reverse("home")).content.decode()

    client.force_login(UserFactory(role=Role.FINANCES))

    assert "Graphiques dans le temps" in client.get(reverse("home")).content.decode()


# --- drill-down et nouveaux graphiques ---


def test_chaque_barre_de_statut_mene_a_la_liste_filtree(client):
    client.force_login(UserFactory(role=Role.DIRECTION))
    MissionFactory(client=ClientFactory(), statut=StatutMission.PLANIFIEE)

    reponse = client.get(reverse("home"))

    exploitation = reponse.context["exploitation"]
    camions = {l["libelle"]: l["url"] for l in exploitation["graphique_camions"]["lignes"]}
    missions = {l["libelle"]: l["url"] for l in exploitation["graphique_missions"]["lignes"]}
    assert camions["Disponible"] == f"{reverse('fleet:liste')}?statut=DISPONIBLE"
    assert missions["Planifiée"] == f"{reverse('missions:liste')}?statut=PLANIFIEE"
    assert client.get(missions["Planifiée"]).status_code == 200


def test_le_graphique_des_creances_est_affiche_a_la_finance(client):
    client.force_login(UserFactory(role=Role.FINANCES))
    emise(prix="1000000", aujourd_hui=date(2026, 8, 1))

    reponse = client.get(reverse("home"))

    lignes = reponse.context["finances"]["graphique_creances"]["lignes"]
    assert lignes[1]["detail"] == "1 facture"
    assert lignes[1]["url"] == f"{reverse('billing:factures')}?echues=on"
    assert lignes[0]["url"] == ""  # rien d'échu dans la première tranche : pas de lien
    assert "Créances par ancienneté" in reponse.content.decode()


def test_le_graphique_des_comptes_a_un_axe_entier():
    from apps.core import graphiques

    g = graphiques.colonnes_groupees(["a"], [{"nom": "Créées", "valeurs": [10]}], entier=True)

    assert [t["etiquette"] for t in g["graduations"]] == ["20", "15", "10", "5", "0"]
```

#### `apps/notifications/tests/test_terrain.py`

*112 lignes* — Notifications des signalements du chauffeur, et alerte du tableau de bord.

```python
"""Notifications des signalements du chauffeur, et alerte du tableau de bord."""

from datetime import date

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.dashboard import services as dashboard
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.garage import terrain
from apps.garage.models import CODES_CHECKLIST, GraviteIncident, TypeIncident
from apps.missions.models import StatutMission
from apps.missions.tests.factories import MissionFactory
from apps.notifications.models import CategorieNotification, NiveauNotification, Notification

pytestmark = pytest.mark.django_db


def _de(utilisateur):
    return list(Notification.objects.filter(destinataire=utilisateur).order_by("pk"))


def _mission():
    chauffeur = ChauffeurFactory()
    return MissionFactory(statut=StatutMission.AFFECTEE, vehicule=VehiculeFactory(), chauffeur=chauffeur)


def _declarer(gravite=GraviteIncident.MOYENNE, **surcharges):
    mission = _mission()
    donnees = dict(chauffeur=mission.chauffeur, mission=mission, type_incident=TypeIncident.PANNE,
                   gravite=gravite, description="Moteur qui chauffe", lieu="Bouaké")
    donnees.update(surcharges)
    return terrain.declarer_incident(**donnees)


def test_un_incident_previent_le_parc_auto_et_la_direction():
    parc, chef, rh = (UserFactory(role=r) for r in (Role.PARCAUTO, Role.DIRECTION, Role.RH))

    incident = _declarer()

    for compte in (parc, chef):
        (notification,) = _de(compte)
        assert notification.categorie == CategorieNotification.INCIDENT
        assert notification.niveau == NiveauNotification.ATTENTION
        assert notification.titre == f"Panne signalé : {incident.vehicule.immatriculation}"
        assert "Moteur qui chauffe" in notification.message and "(Bouaké)" in notification.message
        assert notification.url == reverse("garage:incident", args=[incident.pk])
    assert _de(rh) == []


def test_un_incident_grave_est_urgent():
    parc = UserFactory(role=Role.PARCAUTO)

    _declarer(gravite=GraviteIncident.GRAVE)

    assert _de(parc)[0].niveau == NiveauNotification.URGENT


def test_une_checklist_avec_ko_previent_le_parc_auto_seulement():
    parc, chef = UserFactory(role=Role.PARCAUTO), UserFactory(role=Role.DIRECTION)
    mission = _mission()
    resultats = [{"code": c, "ok": True, "remarque": ""} for c in CODES_CHECKLIST]
    resultats[0].update(ok=False, remarque="Pneu usé")
    resultats[1].update(ok=False, remarque="Frein mou")

    terrain.enregistrer_checklist(chauffeur=mission.chauffeur, mission=mission, resultats=resultats)

    (notification,) = _de(parc)
    assert "2 points KO" in notification.titre
    assert "Pneus" in notification.message and "Freins" in notification.message
    assert notification.url == reverse("garage:checklists")
    assert _de(chef) == []


def test_une_checklist_sans_ko_ne_notifie_personne():
    parc = UserFactory(role=Role.PARCAUTO)
    mission = _mission()

    terrain.enregistrer_checklist(
        chauffeur=mission.chauffeur, mission=mission,
        resultats=[{"code": c, "ok": True, "remarque": ""} for c in CODES_CHECKLIST],
    )

    assert _de(parc) == []


# --- tableau de bord ---


def test_les_incidents_a_traiter_apparaissent_au_centre_d_alertes():
    _declarer(gravite=GraviteIncident.GRAVE, description="Crevaison")
    traite = _declarer(description="Feu cassé")
    terrain.prendre_en_compte(traite, UserFactory(role=Role.PARCAUTO))

    for role in (Role.PARCAUTO, Role.DIRECTION, Role.ADMIN):
        groupes = {g["code"]: g for g in dashboard.centre_alertes(role, aujourd_hui=date(2026, 9, 1))}
        groupe = groupes["incidents"]
        assert groupe["nombre"] == 1 and groupe["niveau"] == "URGENT"
        assert groupe["lignes"][0]["libelle"].startswith("Panne · ")
        assert groupe["voir_tout"].endswith("?statut=SIGNALE")


def test_pas_d_alerte_d_incident_pour_les_autres_roles_ni_sans_incident():
    _declarer()

    assert "incidents" not in {g["code"] for g in dashboard.centre_alertes(Role.RH, aujourd_hui=date(2026, 9, 1))}
    assert "incidents" not in {
        g["code"] for g in dashboard.centre_alertes(Role.FINANCES, aujourd_hui=date(2026, 9, 1))
    }
```

## Étape 3 — Retirer la page provisoire

Supprimez le fichier provisoire du chapitre 16 (il n'a plus d'utilité) :

```bash
rm templates/accueil_provisoire.html
```

> Sous PowerShell : `Remove-Item templates/accueil_provisoire.html`.

Et remplacez, dans `config/urls.py`, la page provisoire par le vrai tableau de bord (la variante « avant » utilise
`TemplateView`, la variante « après » importe `DashboardView`). Déclarez aussi l'application dans les réglages :

#### `config/settings/base.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/settings/base.py (avant)
+++ config/settings/base.py (après)
@@ -66,4 +66,5 @@
     "apps.finance",
     "apps.notifications",
+    "apps.dashboard",
 ]
 
```

#### `config/urls.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/urls.py (avant)
+++ config/urls.py (après)
@@ -8,9 +8,10 @@
 from django.contrib import admin
 from django.urls import include, path
-from django.views.generic import RedirectView, TemplateView
+from django.views.generic import RedirectView
 
+from apps.dashboard.views import DashboardImprimerView, DashboardView
 
 urlpatterns = [
-    path("", TemplateView.as_view(template_name="accueil_provisoire.html"), name="home"),
+    path("", DashboardView.as_view(), name="home"),
     path("imprimer/", DashboardImprimerView.as_view(), name="home_imprimer"),
     # Les navigateurs (et l'administration Django) réclament /favicon.ico : on renvoie vers l'icône du site.
```

```bash
cd frontend
npm run build:css
cd ..
```

## Vérifier le chapitre

```bash
python manage.py check
```

```bash
python -m pytest apps/dashboard/tests/test_dashboard.py apps/dashboard/tests/test_impression.py apps/dashboard/tests/test_lectures_metier.py apps/dashboard/tests/test_series_mensuelles.py apps/notifications/tests/test_terrain.py -q --no-cov
```

**Résultat attendu :** `65 passed` (pour les 3 fichier(s) de tests présentés dans ce chapitre).

Les cinq tests qui échouaient au chapitre 21 (`test_web.py` : accueil, menu par rôle, déconnexion, chauffeur
renvoyé vers son espace) **passent enfin**.

**Dans le navigateur** : reconnectez-vous avec chacun des sept comptes (la MFA pour ADMIN et DIRECTION) et
comparez les tableaux de bord :

1. **`demo_direction`** : tous les blocs ; le **centre d'alertes** affiche par exemple le document d'un camion à
   renouveler, l'alerte de surconsommation du chapitre 24, l'incident éventuel.
2. **`demo_rh`** : effectif, absents du jour, demandes à valider.
3. **`demo_charge`** : clients actifs, réclamations, top 3.
4. **`demo_parcauto`** : exploitation, alertes de documents, de stock, de carburant.
5. **`demo_finances`** : finances du mois, factures échues.
6. Le **menu** de chacun ne contient que ses écrans, et **tous existent maintenant**.

## Ce qu'il faut retenir

- Une page de synthèse **n'invente aucune règle** : elle appelle celles des autres apps.
- Les **droits** se réutilisent par **import** plutôt que de se recopier.
- Un **cache court** sur les blocs coûteux, **aucun cache** sur ce qui est urgent.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 26 : tableau de bord par rôle (centre d'alertes, indicateurs)"
```

---

[← Chapitre 25](25-ecrans-finances.md) · [Sommaire](README.md) · [Chapitre 27 →](27-mobile.md)
