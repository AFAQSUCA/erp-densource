"""Filtres des listes de l'API : mêmes critères que les écrans (statut, texte sans accents...)."""

import django_filters as filtres

from apps.billing import services as billing_services
from apps.billing.models import Facture, StatutFacture
from apps.customers import services as customers_services
from apps.customers.models import Client
from apps.drivers import services as drivers_services
from apps.drivers.models import Chauffeur, StatutChauffeur
from apps.fleet import services as fleet_services
from apps.fleet.models import StatutVehicule, Vehicule
from apps.missions import services as missions_services
from apps.missions.models import Mission, StatutMission


def _recherche(services_recherche):
    """Filtre texte qui réutilise la recherche des écrans (accents et casse ignorés)."""

    def methode(queryset, nom, valeur):
        trouves = services_recherche(recherche=valeur)
        return queryset.filter(pk__in=trouves.values("pk"))

    return methode


class MissionFilter(filtres.FilterSet):
    q = filtres.CharFilter(method=_recherche(missions_services.rechercher_missions), label="Recherche")
    statut = filtres.ChoiceFilter(choices=StatutMission.choices)
    client = filtres.NumberFilter(field_name="client_id")
    depart_apres = filtres.DateFilter(field_name="date_depart_prevue", lookup_expr="gte")
    depart_avant = filtres.DateFilter(field_name="date_depart_prevue", lookup_expr="lte")

    class Meta:
        model = Mission
        fields = ["q", "statut", "client", "depart_apres", "depart_avant"]


class VehiculeFilter(filtres.FilterSet):
    q = filtres.CharFilter(method=_recherche(fleet_services.rechercher_vehicules), label="Recherche")
    statut = filtres.ChoiceFilter(choices=StatutVehicule.choices)

    class Meta:
        model = Vehicule
        fields = ["q", "statut"]


class ChauffeurFilter(filtres.FilterSet):
    q = filtres.CharFilter(method=_recherche(drivers_services.rechercher_chauffeurs), label="Recherche")
    statut = filtres.ChoiceFilter(choices=StatutChauffeur.choices)

    class Meta:
        model = Chauffeur
        fields = ["q", "statut"]


class ClientFilter(filtres.FilterSet):
    q = filtres.CharFilter(method=_recherche(customers_services.rechercher_clients), label="Recherche")
    exonere = filtres.BooleanFilter(field_name="taux_tva", method="filtrer_exonere")

    def filtrer_exonere(self, queryset, nom, valeur):
        return queryset.filter(taux_tva=0) if valeur else queryset.exclude(taux_tva=0)

    class Meta:
        model = Client
        fields = ["q", "exonere"]


class FactureFilter(filtres.FilterSet):
    q = filtres.CharFilter(method=_recherche(billing_services.rechercher_factures), label="Recherche")
    statut = filtres.ChoiceFilter(choices=StatutFacture.choices)
    client = filtres.NumberFilter(field_name="client_id")
    echues = filtres.BooleanFilter(method="filtrer_echues", label="Échues seulement")

    def filtrer_echues(self, queryset, nom, valeur):
        if not valeur:
            return queryset
        return queryset.filter(pk__in=billing_services.factures_echues().values("pk"))

    class Meta:
        model = Facture
        fields = ["q", "statut", "client", "echues"]
