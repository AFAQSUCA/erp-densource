"""API mobile du chauffeur : ``/api/v1/mobile/``.

Aucune règle métier ici : chaque vue identifie le chauffeur du compte, valide les données reçues
et délègue à ``services.py`` (missions, plein, check-list, incident). Les erreurs métier sont
traduites en HTTP par ``apps.api.exceptions.gestionnaire_erreurs``.
"""

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.drivers import services as drivers_services

from . import services
from .permissions import EstChauffeur
from .serializers import (
    ChecklistEntreeSerializer,
    ChecklistSerializer,
    CodeSerializer,
    FraisImprevuEntreeSerializer,
    FraisMissionSerializer,
    IncidentEntreeSerializer,
    IncidentSerializer,
    LivraisonSerializer,
    MissionMobileSerializer,
    PleinEntreeSerializer,
    PleinSerializer,
)

TAG = ["mobile"]


class ChauffeurAPIView(APIView):
    """Base : réservée aux chauffeurs ; ``self.chauffeur`` est la fiche du compte connecté."""

    permission_classes = [IsAuthenticated, EstChauffeur]

    @property
    def chauffeur(self):
        return drivers_services.chauffeur_de(self.request.user)


class MissionsView(ChauffeurAPIView):
    @extend_schema(tags=TAG, summary="Mes missions (à faire, en cours, livrées cette semaine)",
                   responses=MissionMobileSerializer(many=True))
    def get(self, request):
        missions = services.missions_du_chauffeur(self.chauffeur)
        return Response(MissionMobileSerializer(missions, many=True).data)


class MissionView(ChauffeurAPIView):
    @extend_schema(tags=TAG, summary="Détail d'une de mes missions", responses=MissionMobileSerializer)
    def get(self, request, pk):
        return Response(MissionMobileSerializer(services.mission_du_chauffeur(self.chauffeur, pk)).data)


class DemarrerView(ChauffeurAPIView):
    @extend_schema(tags=TAG, summary="Démarrer la mission (Affectée → En cours : départ)",
                   request=None, responses=MissionMobileSerializer)
    def post(self, request, pk):
        return Response(MissionMobileSerializer(services.demarrer(self.chauffeur, pk)).data)


class RecuperationView(ChauffeurAPIView):
    @extend_schema(tags=TAG, summary="Confirmer la récupération du colis (code de l'expéditeur)",
                   request=CodeSerializer, responses=MissionMobileSerializer)
    def post(self, request, pk):
        donnees = CodeSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        mission = services.confirmer_recuperation(self.chauffeur, pk, code=donnees.validated_data["code"])
        return Response(MissionMobileSerializer(mission).data)


class LivraisonView(ChauffeurAPIView):
    @extend_schema(tags=TAG, summary="Confirmer la livraison (code du destinataire et compteur)",
                   request=LivraisonSerializer, responses=MissionMobileSerializer)
    def post(self, request, pk):
        donnees = LivraisonSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        mission = services.livrer(self.chauffeur, pk, **donnees.validated_data)
        return Response(MissionMobileSerializer(mission).data)


class ChecklistView(ChauffeurAPIView):
    @extend_schema(tags=TAG, summary="Remplir la check-list du véhicule avant le départ",
                   request=ChecklistEntreeSerializer, responses={201: ChecklistSerializer})
    def post(self, request, pk):
        donnees = ChecklistEntreeSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        checklist = services.enregistrer_checklist(
            self.chauffeur, pk,
            resultats=[dict(p) for p in donnees.validated_data["points"]],
            remarque=donnees.validated_data["remarque"],
        )
        return Response(ChecklistSerializer(checklist).data, status=status.HTTP_201_CREATED)


class PleinsView(ChauffeurAPIView):
    @extend_schema(tags=TAG, summary="Mes derniers pleins", responses=PleinSerializer(many=True))
    def get(self, request):
        return Response(PleinSerializer(services.pleins_du_chauffeur(self.chauffeur), many=True).data)

    @extend_schema(
        tags=TAG,
        summary="Saisir un plein de carburant",
        description=(
            "Un écart de plus de 60 % avec la moyenne renvoie 409 (`saisie_suspecte`) : vérifiez "
            "litres et kilométrage, puis renvoyez la même demande avec `confirmer=true`."
        ),
        request=PleinEntreeSerializer, responses={201: PleinSerializer},
    )
    def post(self, request):
        donnees = PleinEntreeSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        valeurs = dict(donnees.validated_data)
        plein = services.saisir_plein(
            self.chauffeur,
            station=valeurs["station"],
            quantite_litres=valeurs["quantite_litres"],
            prix_unitaire=valeurs["prix_unitaire"],
            km_compteur=valeurs["km_compteur"],
            numero_ticket=valeurs["numero_ticket"],
            date_plein=valeurs.get("date_plein"),
            vehicule_id=valeurs.get("vehicule"),
            confirmer=valeurs["confirmer"],
        )
        return Response(PleinSerializer(plein).data, status=status.HTTP_201_CREATED)


class IncidentsView(ChauffeurAPIView):
    @extend_schema(tags=TAG, summary="Mes incidents signalés", responses=IncidentSerializer(many=True))
    def get(self, request):
        return Response(IncidentSerializer(services.incidents_du_chauffeur(self.chauffeur), many=True).data)

    @extend_schema(tags=TAG, summary="Signaler une panne ou un incident",
                   description="Prévient le Parc Auto et la Direction ; aucune action automatique sur le camion.",
                   request=IncidentEntreeSerializer, responses={201: IncidentSerializer})
    def post(self, request):
        donnees = IncidentEntreeSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        valeurs = dict(donnees.validated_data)
        incident = services.declarer_incident(
            self.chauffeur,
            type_incident=valeurs["type_incident"],
            gravite=valeurs["gravite"],
            description=valeurs["description"],
            lieu=valeurs["lieu"],
            mission_id=valeurs.get("mission"),
            vehicule_id=valeurs.get("vehicule"),
        )
        return Response(IncidentSerializer(incident).data, status=status.HTTP_201_CREATED)


class FraisImprevusView(ChauffeurAPIView):
    parser_classes = [MultiPartParser]

    @extend_schema(tags=TAG, summary="Mes imprévus déclarés", responses=FraisMissionSerializer(many=True))
    def get(self, request):
        return Response(FraisMissionSerializer(services.frais_du_chauffeur(self.chauffeur), many=True).data)

    @extend_schema(
        tags=TAG, summary="Déclarer un imprévu (panne, incident) avec une preuve",
        description="Le Parc Auto valide en premier, puis la Finance confirme (double validation).",
        request=FraisImprevuEntreeSerializer, responses={201: FraisMissionSerializer},
    )
    def post(self, request):
        donnees = FraisImprevuEntreeSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        valeurs = dict(donnees.validated_data)
        frais = services.declarer_frais_imprevu(
            self.chauffeur,
            mission_id=valeurs["mission"],
            montant=valeurs["montant"],
            justificatif=valeurs["justificatif"],
            description=valeurs.get("description", ""),
        )
        return Response(FraisMissionSerializer(frais).data, status=status.HTTP_201_CREATED)
