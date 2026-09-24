"""Logique métier du carburant — cahier-des-charges.md:147-157.

    Conso (L/100 km) = (Litres ÷ (Km actuel − Km précédent)) × 100

Alertes (écart de la conso à la moyenne des 3 derniers pleins) :
jaune > +20 %, rouge > +40 %, alerte de saisie > ±60 %. Anomalie : conso
> 45 ou < 20 L/100 km. Tous les seuils sont stricts (« > »).
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Q, QuerySet

from apps.core.search import filtrer_par_texte
from apps.drivers.models import Chauffeur
from apps.fleet import services as fleet_services
from apps.fleet.models import Vehicule

from .exceptions import (
    HorsChronologie,
    KilometrageInvalide,
    SaisieInvalide,
    SaisieSuspecte,
    TicketDejaEnregistre,
)
from .models import NiveauAlerte, Plein
from .signals import alerte_consommation

CENTIME = Decimal("0.01")
NB_PLEINS_REFERENCE = 3
SEUIL_JAUNE = Decimal("20")
SEUIL_ROUGE = Decimal("40")
SEUIL_SAISIE = Decimal("60")
CONSO_MAX = Decimal("45")
CONSO_MIN = Decimal("20")

logger = logging.getLogger(__name__)


def calculer_consommation(litres: Decimal, distance_km: int) -> Decimal:
    """Consommation en L/100 km, arrondie au centième."""
    return (Decimal(litres) / Decimal(distance_km) * 100).quantize(
        CENTIME, rounding=ROUND_HALF_UP
    )


def moyenne_reference(vehicule: Vehicule) -> Decimal | None:
    """Moyenne des consommations des 3 derniers pleins du camion.

    Moyenne arithmétique des consommations (lecture littérale du CDC). S'il y
    en a moins de 3, on utilise celles qui existent ; aucune → ``None``.
    """
    consommations = list(
        Plein.objects.filter(vehicule=vehicule, consommation__isnull=False)
        .order_by("-date_plein", "-pk")
        .values_list("consommation", flat=True)[:NB_PLEINS_REFERENCE]
    )
    if not consommations:
        return None
    return (sum(consommations) / len(consommations)).quantize(
        CENTIME, rounding=ROUND_HALF_UP
    )


def evaluer_ecart(
    consommation: Decimal, moyenne: Decimal
) -> tuple[Decimal, str, bool]:
    """Retourne ``(écart %, niveau d'alerte, alerte de saisie)``.

    Les deux alertes sont indépendantes : un écart de +65 % est à la fois
    rouge (> +40 %) et une alerte de saisie (> ±60 %).
    """
    ecart = (consommation - moyenne) / moyenne * 100
    if ecart > SEUIL_ROUGE:
        niveau = NiveauAlerte.ROUGE
    elif ecart > SEUIL_JAUNE:
        niveau = NiveauAlerte.JAUNE
    else:
        niveau = NiveauAlerte.AUCUNE
    return ecart.quantize(CENTIME, rounding=ROUND_HALF_UP), niveau, abs(ecart) > SEUIL_SAISIE


def est_anomalie(consommation: Decimal) -> bool:
    """Consommation hors de la plage plausible 20-45 L/100 km."""
    return consommation > CONSO_MAX or consommation < CONSO_MIN


@transaction.atomic
def enregistrer_plein(
    *,
    vehicule: Vehicule,
    chauffeur: Chauffeur,
    date_plein: date,
    station: str,
    quantite_litres: Decimal,
    prix_unitaire: Decimal,
    km_compteur: int,
    numero_ticket: str,
    confirmer_alerte_saisie: bool = False,
) -> Plein:
    """Enregistre un plein et calcule consommation, écart et alertes.

    - Les pleins d'un camion se saisissent dans l'ordre : date >= dernier plein
      et km strictement supérieur (sinon la formule n'a pas de sens).
    - Si l'écart dépasse ±60 %, :class:`SaisieSuspecte` est levée et rien n'est
      enregistré ; l'utilisateur vérifie puis renvoie avec
      ``confirmer_alerte_saisie=True``.
    - Le compteur du camion est relevé si ce km est supérieur.
    """
    quantite_litres, prix_unitaire = Decimal(quantite_litres), Decimal(prix_unitaire)
    if quantite_litres <= 0:
        raise SaisieInvalide("La quantité doit être strictement positive.")
    if prix_unitaire <= 0:
        raise SaisieInvalide("Le prix unitaire doit être strictement positif.")
    numero_ticket = numero_ticket.strip()
    if not numero_ticket:
        raise SaisieInvalide("Le n° de ticket est obligatoire.")
    if Plein.objects.filter(numero_ticket=numero_ticket).exists():
        raise TicketDejaEnregistre(f"Le ticket {numero_ticket} est déjà enregistré.")

    type(vehicule)._base_manager.select_for_update().filter(pk=vehicule.pk).first()
    vehicule.refresh_from_db()

    precedent = (
        Plein.objects.filter(vehicule=vehicule).order_by("-date_plein", "-pk").first()
    )
    champs_calcules: dict = {}
    if precedent is not None:
        if date_plein < precedent.date_plein:
            raise HorsChronologie(
                f"Le dernier plein de ce camion date du {precedent.date_plein} : "
                "saisissez les pleins dans l'ordre."
            )
        if km_compteur <= precedent.km_compteur:
            raise KilometrageInvalide(
                f"Le km compteur ({km_compteur}) doit dépasser celui du plein "
                f"précédent ({precedent.km_compteur})."
            )
        distance = km_compteur - precedent.km_compteur
        consommation = calculer_consommation(quantite_litres, distance)
        champs_calcules.update(
            km_precedent=precedent.km_compteur,
            distance_km=distance,
            consommation=consommation,
            anomalie=est_anomalie(consommation),
        )
        moyenne = moyenne_reference(vehicule)
        if moyenne is not None and moyenne > 0:
            ecart, niveau, saisie_suspecte = evaluer_ecart(consommation, moyenne)
            if saisie_suspecte and not confirmer_alerte_saisie:
                raise SaisieSuspecte(ecart, consommation, moyenne)
            champs_calcules.update(
                moyenne_reference=moyenne,
                ecart_pct=ecart,
                niveau_alerte=niveau,
                alerte_saisie=saisie_suspecte,
            )

    plein = Plein.objects.create(
        date_plein=date_plein,
        vehicule=vehicule,
        chauffeur=chauffeur,
        station=station,
        quantite_litres=quantite_litres,
        prix_unitaire=prix_unitaire,
        km_compteur=km_compteur,
        numero_ticket=numero_ticket,
        **champs_calcules,
    )
    if km_compteur > vehicule.kilometrage:
        fleet_services.enregistrer_kilometrage(vehicule, km_compteur)
    if (
        plein.niveau_alerte != NiveauAlerte.AUCUNE
        or plein.anomalie
        or plein.alerte_saisie
    ):
        _emettre(alerte_consommation, plein=plein)
    return plein


def _emettre(signal, **arguments) -> None:
    """Un récepteur en erreur ne doit pas faire échouer la saisie du plein."""
    for recepteur, resultat in signal.send_robust(sender=Plein, **arguments):
        if isinstance(resultat, Exception):
            logger.error("Récepteur %r en erreur", recepteur, exc_info=resultat)


# --- analyse (cahier-des-charges.md:156) ---


def consommation_moyenne(
    *, vehicule: Vehicule | None = None, chauffeur: Chauffeur | None = None
) -> Decimal | None:
    """Consommation moyenne en L/100 km : total des litres ÷ total des km x 100.

    Pondérée par la distance (un plein sur 50 km pèse moins que sur 900 km).
    Filtrable par camion et/ou par chauffeur ; sans filtre, c'est la moyenne
    globale de la flotte (tableau de bord, cahier-des-charges.md:229-230).
    ``None`` s'il n'y a encore aucune consommation calculée.
    """
    pleins = Plein.objects.filter(consommation__isnull=False)
    if vehicule is not None:
        pleins = pleins.filter(vehicule=vehicule)
    if chauffeur is not None:
        pleins = pleins.filter(chauffeur=chauffeur)
    lignes = list(pleins.values_list("quantite_litres", "distance_km"))
    distance = sum(d for _, d in lignes)
    if not distance:
        return None
    litres = sum(l for l, _ in lignes)
    return calculer_consommation(litres, distance)


def pleins_a_surveiller(*, depuis: date | None = None) -> QuerySet[Plein]:
    """Pleins en alerte (jaune/rouge), en anomalie ou à saisie suspecte confirmée.

    ``depuis`` : ne garde que les pleins de cette date ou plus récents (le centre d'alertes
    du tableau de bord n'affiche que les alertes récentes).
    """
    pleins = Plein.objects.select_related("vehicule", "chauffeur__personnel").filter(
        Q(niveau_alerte__in=[NiveauAlerte.JAUNE, NiveauAlerte.ROUGE])
        | Q(anomalie=True)
        | Q(alerte_saisie=True)
    )
    if depuis is not None:
        pleins = pleins.filter(date_plein__gte=depuis)
    return pleins


# --- lecture pour les écrans ---

ALERTES_FILTRABLES = ("JAUNE", "ROUGE", "ANOMALIE", "SAISIE", "A_SURVEILLER")


def pleins_queryset() -> QuerySet[Plein]:
    """Pleins avec camion et chauffeur chargés (évite les requêtes en boucle)."""
    return Plein.objects.select_related("vehicule", "chauffeur__personnel")


def rechercher_pleins(
    *,
    vehicule: Vehicule | None = None,
    chauffeur: Chauffeur | None = None,
    date_debut: date | None = None,
    date_fin: date | None = None,
    alerte: str = "",
    recherche: str = "",
) -> QuerySet[Plein]:
    """Pleins filtrés par camion, chauffeur, période, alerte et texte (station, ticket).

    ``alerte`` : ``JAUNE``, ``ROUGE``, ``ANOMALIE``, ``SAISIE`` (saisie suspecte
    confirmée) ou ``A_SURVEILLER`` (l'un des précédents).
    """
    pleins = pleins_queryset()
    if vehicule is not None:
        pleins = pleins.filter(vehicule=vehicule)
    if chauffeur is not None:
        pleins = pleins.filter(chauffeur=chauffeur)
    if date_debut is not None:
        pleins = pleins.filter(date_plein__gte=date_debut)
    if date_fin is not None:
        pleins = pleins.filter(date_plein__lte=date_fin)
    if alerte == "JAUNE":
        pleins = pleins.filter(niveau_alerte=NiveauAlerte.JAUNE)
    elif alerte == "ROUGE":
        pleins = pleins.filter(niveau_alerte=NiveauAlerte.ROUGE)
    elif alerte == "ANOMALIE":
        pleins = pleins.filter(anomalie=True)
    elif alerte == "SAISIE":
        pleins = pleins.filter(alerte_saisie=True)
    elif alerte == "A_SURVEILLER":
        pleins = pleins.filter(
            Q(niveau_alerte__in=[NiveauAlerte.JAUNE, NiveauAlerte.ROUGE])
            | Q(anomalie=True)
            | Q(alerte_saisie=True)
        )
    pleins = filtrer_par_texte(pleins, recherche, "station", "numero_ticket")
    return pleins


def _consommation_par_groupe(cle: str, *libelles: str) -> list[dict]:
    """Regroupe les consommations calculées par ``cle`` (camion ou chauffeur).

    Chaque groupe : litres et km cumulés, consommation moyenne pondérée par la
    distance, écart en % à la moyenne de la flotte. Trié du plus gourmand au plus
    économe. Sommes en Python : SQLite passerait par des flottants.
    """
    lignes = Plein.objects.filter(consommation__isnull=False).values_list(
        cle, *libelles, "quantite_litres", "distance_km"
    )
    groupes: dict[int, dict] = {}
    for identifiant, *noms, litres, distance in lignes:
        g = groupes.setdefault(
            identifiant,
            {
                "id": identifiant,
                "libelle": " ".join(noms),
                "litres": Decimal("0"),
                "distance": 0,
                "pleins": 0,
            },
        )
        g["litres"] += litres
        g["distance"] += distance
        g["pleins"] += 1
    moyenne_flotte = consommation_moyenne()
    resultat = []
    for g in groupes.values():
        g["consommation"] = calculer_consommation(g["litres"], g["distance"])
        g["ecart_flotte_pct"] = (
            ((g["consommation"] - moyenne_flotte) / moyenne_flotte * 100).quantize(
                CENTIME, rounding=ROUND_HALF_UP
            )
            if moyenne_flotte
            else None
        )
        g["anomalie"] = est_anomalie(g["consommation"])
        resultat.append(g)
    return sorted(resultat, key=lambda g: g["consommation"], reverse=True)


def consommation_par_vehicule() -> list[dict]:
    """Consommation moyenne de chaque camion (cahier-des-charges.md:156)."""
    return _consommation_par_groupe("vehicule_id", "vehicule__immatriculation")


def consommation_par_chauffeur() -> list[dict]:
    """Consommation moyenne de chaque chauffeur (cahier-des-charges.md:156)."""
    return _consommation_par_groupe(
        "chauffeur_id", "chauffeur__personnel__prenom", "chauffeur__personnel__nom"
    )


def cout_carburant_par_mois(debut: date, fin: date) -> dict[tuple[int, int], Decimal]:
    """Valeur des pleins par mois (``(année, mois)``) : une requête, somme faite en Python (comme ``cout_carburant``)."""
    totaux: dict[tuple[int, int], Decimal] = {}
    lignes = Plein.objects.filter(date_plein__range=(debut, fin)).values_list(
        "date_plein", "quantite_litres", "prix_unitaire"
    )
    for jour, litres, prix in lignes:
        cle = (jour.year, jour.month)
        totaux[cle] = totaux.get(cle, Decimal("0")) + litres * prix
    return totaux


def cout_carburant(debut: date, fin: date) -> Decimal:
    """Valeur des pleins de la période (litres x prix unitaire), en FCFA.

    Calculée en Python : l'arithmétique décimale de SQLite passerait par des flottants.
    Alimente les charges du mois (cahier-des-charges.md:227).
    """
    lignes = Plein.objects.filter(date_plein__range=(debut, fin)).values_list(
        "quantite_litres", "prix_unitaire"
    )
    return sum((litres * prix for litres, prix in lignes), Decimal("0"))
