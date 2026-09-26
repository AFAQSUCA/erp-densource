"""Représentation JSON de l'espace chauffeur.

Le chauffeur ne voit ni le prix convenu (donnée commerciale) ni les codes secrets de la mission :
ce sont l'expéditeur et le destinataire qui les détiennent, le chauffeur ne fait que les saisir.
"""

from rest_framework import serializers

from apps.fuel.models import Plein
from apps.garage.models import GraviteIncident, Incident, TypeIncident
from apps.missions.models import FraisMission, Mission

from . import services


class MissionMobileSerializer(serializers.ModelSerializer):
    client = serializers.CharField(source="client.raison_sociale")
    vehicule = serializers.CharField(source="vehicule.immatriculation", default=None)
    statut_libelle = serializers.CharField(source="get_statut_display")
    checklist_faite = serializers.SerializerMethodField()
    actions = serializers.SerializerMethodField()

    class Meta:
        model = Mission
        fields = (
            "id", "numero", "client", "lieu_chargement", "lieu_livraison", "nature_marchandise",
            "poids_t", "date_depart_prevue", "statut", "statut_libelle", "vehicule", "km_depart",
            "km_arrivee", "checklist_faite", "actions",
        )
        read_only_fields = fields

    def get_checklist_faite(self, mission) -> bool:
        return services.checklist_faite(mission)

    def get_actions(self, mission) -> dict:
        return services.actions_possibles(mission)


class CodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=12, help_text="Code saisi ou lu sur le QR de l'expéditeur.")


class LivraisonSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=12, help_text="Code du destinataire.")
    km_arrivee = serializers.IntegerField(min_value=0, help_text="Compteur à l'arrivée.")


class PleinEntreeSerializer(serializers.Serializer):
    station = serializers.CharField(max_length=100)
    quantite_litres = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=0)
    prix_unitaire = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    km_compteur = serializers.IntegerField(min_value=0)
    numero_ticket = serializers.CharField(max_length=50)
    date_plein = serializers.DateField(required=False, help_text="Aujourd'hui par défaut.")
    vehicule = serializers.IntegerField(required=False, help_text="Camion courant par défaut.")
    confirmer = serializers.BooleanField(
        required=False, default=False,
        help_text="À vrai pour confirmer un plein dont l'écart dépasse 60 %.",
    )


class PleinSerializer(serializers.ModelSerializer):
    vehicule = serializers.CharField(source="vehicule.immatriculation")

    class Meta:
        model = Plein
        fields = (
            "id", "date_plein", "vehicule", "station", "quantite_litres", "prix_unitaire",
            "km_compteur", "consommation", "ecart_pct", "niveau_alerte", "anomalie",
        )
        read_only_fields = fields


class PointChecklistSerializer(serializers.Serializer):
    code = serializers.CharField()
    ok = serializers.BooleanField()
    remarque = serializers.CharField(required=False, allow_blank=True, default="")


class ChecklistEntreeSerializer(serializers.Serializer):
    points = PointChecklistSerializer(many=True)
    remarque = serializers.CharField(required=False, allow_blank=True, default="")


class ChecklistSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    nb_anomalies = serializers.IntegerField()
    points = serializers.ListField(child=serializers.DictField())
    remarque = serializers.CharField()


class IncidentEntreeSerializer(serializers.Serializer):
    type_incident = serializers.ChoiceField(choices=TypeIncident.choices)
    gravite = serializers.ChoiceField(choices=GraviteIncident.choices)
    description = serializers.CharField()
    lieu = serializers.CharField(required=False, allow_blank=True, default="")
    mission = serializers.IntegerField(required=False, help_text="Mission concernée (son camion est repris).")
    vehicule = serializers.IntegerField(required=False, help_text="Camion concerné, sans mission.")


class IncidentSerializer(serializers.ModelSerializer):
    vehicule = serializers.CharField(source="vehicule.immatriculation")
    type_libelle = serializers.CharField(source="get_type_incident_display")
    gravite_libelle = serializers.CharField(source="get_gravite_display")
    statut_libelle = serializers.CharField(source="get_statut_display")

    class Meta:
        model = Incident
        fields = (
            "id", "vehicule", "type_incident", "type_libelle", "gravite", "gravite_libelle",
            "description", "lieu", "statut", "statut_libelle", "created_at",
        )
        read_only_fields = fields


class FraisImprevuEntreeSerializer(serializers.Serializer):
    mission = serializers.IntegerField()
    montant = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    justificatif = serializers.FileField()


class FraisMissionSerializer(serializers.ModelSerializer):
    mission = serializers.CharField(source="mission.numero")
    type_libelle = serializers.CharField(source="get_type_frais_display")
    statut_libelle = serializers.CharField(source="get_statut_display")

    class Meta:
        model = FraisMission
        fields = (
            "id", "mission", "type_frais", "type_libelle", "montant", "description",
            "statut", "statut_libelle", "created_at",
        )
        read_only_fields = fields
