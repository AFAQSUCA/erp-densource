"""Représentation JSON des ressources de l'API bureau (lecture seule).

Liste explicite des champs (jamais ``__all__``) : un champ sensible ajouté plus tard au modèle
ne fuit pas dans l'API. En particulier, **les codes secrets des missions n'y figurent jamais**.
"""

from rest_framework import serializers

from apps.billing import services as billing_services
from apps.billing.models import Facture, LigneFacture
from apps.customers.models import Client
from apps.drivers.models import Chauffeur
from apps.fleet.models import Vehicule
from apps.missions.models import Mission


def _nom_chauffeur(chauffeur) -> str | None:
    if chauffeur is None:
        return None
    return f"{chauffeur.personnel.prenom} {chauffeur.personnel.nom}"


class MissionSerializer(serializers.ModelSerializer):
    client = serializers.CharField(source="client.raison_sociale")
    client_id = serializers.IntegerField()
    vehicule = serializers.CharField(source="vehicule.immatriculation", default=None)
    chauffeur = serializers.SerializerMethodField()
    statut_libelle = serializers.CharField(source="get_statut_display")

    class Meta:
        model = Mission
        fields = (
            "id", "numero", "client", "client_id", "vehicule", "chauffeur", "lieu_chargement",
            "lieu_livraison", "nature_marchandise", "poids_t", "prix_convenu", "date_depart_prevue",
            "statut", "statut_libelle", "km_depart", "km_arrivee", "date_depart",
            "date_recuperation", "date_livraison", "date_cloture",
        )
        read_only_fields = fields

    def get_chauffeur(self, mission) -> str | None:
        return _nom_chauffeur(mission.chauffeur)


class VehiculeSerializer(serializers.ModelSerializer):
    statut_libelle = serializers.CharField(source="get_statut_display")

    class Meta:
        model = Vehicule
        fields = (
            "id", "immatriculation", "marque", "modele", "annee", "vin", "kilometrage",
            "capacite_charge_t", "reservoir_l", "statut", "statut_libelle",
        )
        read_only_fields = fields


class ChauffeurSerializer(serializers.ModelSerializer):
    matricule = serializers.CharField(source="personnel.matricule")
    nom = serializers.CharField(source="personnel.nom")
    prenom = serializers.CharField(source="personnel.prenom")
    statut_libelle = serializers.CharField(source="get_statut_display")

    class Meta:
        model = Chauffeur
        fields = (
            "id", "matricule", "nom", "prenom", "telephone", "numero_permis", "categories_permis",
            "date_expiration_permis", "date_expiration_visite_medicale", "statut", "statut_libelle",
        )
        read_only_fields = fields


class ClientSerializer(serializers.ModelSerializer):
    charge_clientele = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = (
            "id", "raison_sociale", "ncc_nif", "contact_principal", "telephone", "email", "adresse",
            "charge_clientele", "taux_tva", "motif_exoneration", "delai_paiement_jours",
        )
        read_only_fields = fields

    def get_charge_clientele(self, client) -> str | None:
        charge = client.charge_clientele
        return (charge.get_full_name() or charge.username) if charge else None


class LigneFactureSerializer(serializers.ModelSerializer):
    class Meta:
        model = LigneFacture
        fields = ("designation", "quantite", "prix_unitaire_ht", "montant_ht")
        read_only_fields = fields


class FactureSerializer(serializers.ModelSerializer):
    client = serializers.CharField(source="client.raison_sociale")
    client_id = serializers.IntegerField()
    mission = serializers.CharField(source="mission.numero")
    statut_libelle = serializers.CharField(source="get_statut_display")
    montant_regle = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    reste_a_recouvrer = serializers.DecimalField(
        source="reste", max_digits=14, decimal_places=2, read_only=True
    )
    echue = serializers.SerializerMethodField()

    class Meta:
        model = Facture
        fields = (
            "id", "numero", "client", "client_id", "mission", "statut", "statut_libelle",
            "taux_tva", "motif_exoneration", "montant_ht", "montant_tva", "montant_ttc",
            "montant_regle", "reste_a_recouvrer", "date_emission", "date_echeance", "echue",
        )
        read_only_fields = fields

    def get_echue(self, facture) -> bool:
        return billing_services.est_echue(facture)


class FactureDetailSerializer(FactureSerializer):
    lignes = LigneFactureSerializer(many=True, read_only=True)

    class Meta(FactureSerializer.Meta):
        fields = FactureSerializer.Meta.fields + ("lignes",)
        read_only_fields = fields
