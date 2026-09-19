"""Ressources de l'API bureau, en lecture seule.

Chaque ressource s'appuie sur le même queryset de service que l'écran correspondant et sur les
mêmes rôles (``permissions.CONSULTATION`` de l'app). Les écritures restent sur les écrans web.
"""

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.api.permissions import role_requis
from apps.billing import permissions as billing_permissions
from apps.billing import services as billing_services
from apps.customers import permissions as customers_permissions
from apps.customers import services as customers_services
from apps.drivers import permissions as drivers_permissions
from apps.drivers import services as drivers_services
from apps.fleet import permissions as fleet_permissions
from apps.fleet import services as fleet_services
from apps.missions import permissions as missions_permissions
from apps.missions import services as missions_services

from .filters import ChauffeurFilter, ClientFilter, FactureFilter, MissionFilter, VehiculeFilter
from .serializers import (
    ChauffeurSerializer,
    ClientSerializer,
    FactureDetailSerializer,
    FactureSerializer,
    MissionSerializer,
    VehiculeSerializer,
)


@extend_schema_view(
    list=extend_schema(tags=["missions"], summary="Liste des missions"),
    retrieve=extend_schema(tags=["missions"], summary="Détail d'une mission"),
)
class MissionViewSet(ReadOnlyModelViewSet):
    """Missions (les codes secrets ne sont jamais exposés)."""

    permission_classes = [IsAuthenticated, role_requis(missions_permissions.CONSULTATION)]
    serializer_class = MissionSerializer
    filterset_class = MissionFilter

    def get_queryset(self):
        return missions_services.missions_queryset()


@extend_schema_view(
    list=extend_schema(tags=["camions"], summary="Liste des camions"),
    retrieve=extend_schema(tags=["camions"], summary="Détail d'un camion"),
)
class VehiculeViewSet(ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, role_requis(fleet_permissions.CONSULTATION)]
    serializer_class = VehiculeSerializer
    filterset_class = VehiculeFilter

    def get_queryset(self):
        return fleet_services.vehicules_queryset().order_by("immatriculation")


@extend_schema_view(
    list=extend_schema(tags=["chauffeurs"], summary="Liste des chauffeurs"),
    retrieve=extend_schema(tags=["chauffeurs"], summary="Détail d'un chauffeur"),
)
class ChauffeurViewSet(ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, role_requis(drivers_permissions.CONSULTATION)]
    serializer_class = ChauffeurSerializer
    filterset_class = ChauffeurFilter

    def get_queryset(self):
        return drivers_services.chauffeurs_queryset().order_by("personnel__nom", "personnel__prenom")


@extend_schema_view(
    list=extend_schema(tags=["clients"], summary="Liste des clients"),
    retrieve=extend_schema(tags=["clients"], summary="Détail d'un client"),
)
class ClientViewSet(ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, role_requis(customers_permissions.CONSULTATION)]
    serializer_class = ClientSerializer
    filterset_class = ClientFilter

    def get_queryset(self):
        return customers_services.clients_queryset()


@extend_schema_view(
    list=extend_schema(tags=["factures"], summary="Liste des factures"),
    retrieve=extend_schema(tags=["factures"], summary="Détail d'une facture avec ses lignes"),
)
class FactureViewSet(ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, role_requis(billing_permissions.CONSULTATION)]
    filterset_class = FactureFilter

    def get_queryset(self):
        return billing_services.factures_queryset().prefetch_related("lignes")

    def get_serializer_class(self):
        return FactureDetailSerializer if self.action == "retrieve" else FactureSerializer
