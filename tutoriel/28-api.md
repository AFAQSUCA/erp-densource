# Chapitre 28 — L'API REST

> 19 fichier(s) dans ce chapitre, 2548 lignes de code.

## Ce que vous allez construire

L'**API REST**, sous `/api/v1/` : la porte d'entrée pour d'autres logiciels (une application native, un partenaire).

| Route | Rôle |
|---|---|
| `POST /api/v1/auth/token/` | identifiant + mot de passe (+ code `otp` pour ADMIN et DIRECTION) → **jeton d'accès (15 min)** et **jeton de renouvellement (7 jours)** |
| `POST /api/v1/auth/token/refresh/`, `/auth/logout/` | renouveler, se déconnecter (le jeton de renouvellement est **révoqué**) |
| `GET /api/v1/moi/` | qui suis-je ? (rôle, chauffeur) |
| `GET /api/v1/missions/`, `camions/`, `chauffeurs/`, `clients/`, `factures/` | **lecture seule**, paginée par 20, filtres, recherche |
| `/api/v1/mobile/…` | l'**API du chauffeur** (chapitre 27) : ses missions, démarrer, récupérer, livrer, plein, check-list, incident |
| `GET /api/v1/docs/`, `/schema/` | documentation interactive (Swagger) et schéma OpenAPI : **ADMIN et DIRECTION** connectés |

Garanties : un rôle **n'obtient pas par l'API ce que l'écran lui refuse** ; les **codes secrets des missions n'y
figurent jamais** ; les erreurs métier deviennent des réponses `{"code", "detail"}` (400, 403, 404, 409).

## Prérequis

- Chapitres 1 à 27 terminés.

## Notions Django REST Framework (DRF)

- **Sérialiseur** (`Serializer`) : transforme un objet en **JSON** (et inversement). On y **liste chaque champ**
  exposé : jamais `fields = "__all__"`, pour ne pas révéler une colonne ajoutée plus tard.
- **`ViewSet`** : une classe qui regroupe liste et détail d'une ressource ; `ReadOnlyModelViewSet` n'expose que la
  lecture. Un **routeur** (`SimpleRouter`) fabrique les adresses.
- **Filtres** (`django-filter`) : `FilterSet` déclare les paramètres acceptés (`?statut=LIVREE&q=ciment`).
- **Permissions DRF** : une classe qui décide si la requête passe. Ici on **réutilise** les ensembles de rôles de
  chaque app (`CONSULTATION`) : un seul endroit à changer.
- **Authentification JWT** (`simplejwt`) : après connexion, le client présente `Authorization: Bearer <jeton>`.
  Un jeton d'accès **court** (15 minutes) limite les dégâts en cas de vol.
- **Limitation de débit** (*throttling*) : `ScopedRateThrottle` avec la portée `connexion` (10 essais par minute).
- **Gestionnaire d'exceptions** : traduit nos exceptions métier (`MissionError`, `SaisieSuspecte`…) en codes
  HTTP lisibles.
- **OpenAPI / Swagger** (`drf-spectacular`) : la documentation est **générée** depuis le code.
- **CORS** : n'autoriser que des domaines connus (`CORS_ALLOWED_ORIGINS`), et seulement pour `/api/`.

## Étape 1 — Créer l'application

```bash
mkdir -p apps/api/v1 apps/api/tests
```

#### Fichiers vides à créer

Ces fichiers n'ont aucun contenu ; ils servent à faire de leur dossier un *paquet Python* (sans eux, `import apps.xxx` échouerait). Créez d'abord les dossiers, puis les fichiers :

```bash
mkdir -p apps\api apps\api\tests apps\api\v1
touch apps/api/__init__.py
touch apps/api/v1/__init__.py
touch apps/api/tests/__init__.py
```

> Sous PowerShell, `mkdir -p` s'écrit `New-Item -ItemType Directory -Force <dossier>` et `touch fichier` s'écrit `New-Item -ItemType File -Force fichier`. Vous pouvez aussi créer ces fichiers avec votre éditeur.

## Étape 2 — Erreurs, droits, connexion

#### `apps/api/exceptions.py`

*71 lignes* — Traduction des erreurs métier en réponses HTTP claires.

```python
"""Traduction des erreurs métier en réponses HTTP claires.

Les services lèvent des exceptions métier (``MissionError``, ``CarburantError``...). L'API les
transforme en JSON ``{"code": ..., "detail": ...}`` :

- 403 : l'utilisateur n'a pas le droit (``ChauffeurNonAutorise``, ``ActionFactureNonAutorisee``...) ;
- 409 : ``SaisieSuspecte`` (plein à confirmer), avec les chiffres à afficher ;
- 404 : mission introuvable ou d'un autre chauffeur (on ne révèle pas son existence) ;
- 400 : toute autre règle métier refusée (statut incompatible, code faux, solde insuffisant...).

Le ``code`` est le nom de la classe en minuscules avec soulignés (``code_invalide``) : un client
mobile peut s'en servir pour réagir sans lire le message.
"""

import re

from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as gestionnaire_drf

from apps.billing.exceptions import ActionFactureNonAutorisee, BillingError
from apps.customers.exceptions import ClientError
from apps.drivers.exceptions import ChauffeurError
from apps.fleet.exceptions import FlotteError
from apps.fuel.exceptions import CarburantError, SaisieSuspecte
from apps.garage.exceptions import ChauffeurNonAutorise, GarageError
from apps.hr.exceptions import ActionNonAutorisee, CongeError, PersonnelError
from apps.inventory.exceptions import StockError
from apps.missions.exceptions import MissionError
from apps.mobile_api.exceptions import MissionIntrouvable, MobileError

ERREURS_METIER = (
    BillingError, ClientError, ChauffeurError, FlotteError, CarburantError, GarageError,
    CongeError, PersonnelError, StockError, MissionError, MobileError,
)
ERREURS_DE_DROIT = (ChauffeurNonAutorise, ActionFactureNonAutorisee, ActionNonAutorisee)


CODES_MFA = frozenset({"mfa_requise", "mfa_non_activee", "mfa_invalide"})


def _code(exc: Exception) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", type(exc).__name__).lower()


def gestionnaire_erreurs(exc, context):
    if isinstance(exc, SaisieSuspecte):
        return Response(
            {
                "code": _code(exc),
                "detail": str(exc),
                "consommation": str(exc.consommation),
                "moyenne": str(exc.moyenne),
                "ecart_pct": str(exc.ecart_pct),
                "confirmer": "Renvoyez la même demande avec confirmer=true si les valeurs sont exactes.",
            },
            status=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, MissionIntrouvable):
        return Response({"code": _code(exc), "detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
    if isinstance(exc, ERREURS_DE_DROIT):
        return Response({"code": _code(exc), "detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
    if isinstance(exc, ERREURS_METIER):
        return Response({"code": _code(exc), "detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    reponse = gestionnaire_drf(exc, context)
    # Erreurs de double authentification : le code lisible par une machine accompagne le message.
    if isinstance(exc, exceptions.AuthenticationFailed) and reponse is not None:
        code = getattr(exc.detail, "code", "")
        if code in CODES_MFA:
            reponse.data["code"] = code
    return reponse
```

#### `apps/api/permissions.py`

*37 lignes* — Permissions DRF fondées sur les mêmes ensembles de rôles que les écrans web.

```python
"""Permissions DRF fondées sur les mêmes ensembles de rôles que les écrans web.

Chaque app définit déjà qui peut la consulter (``permissions.CONSULTATION``) : l'API réutilise
ces ensembles, pour qu'un rôle n'obtienne jamais par l'API ce que l'écran lui refuse.
"""

from rest_framework.permissions import BasePermission

from apps.accounts.models import Role


def role_requis(roles: frozenset[str]) -> type[BasePermission]:
    """Fabrique une permission qui exige un rôle parmi ``roles`` (superutilisateur = ADMIN)."""

    class RoleRequis(BasePermission):
        message = "Votre rôle n'a pas accès à cette ressource."

        def has_permission(self, request, view):
            utilisateur = request.user
            return bool(
                utilisateur and utilisateur.is_authenticated and utilisateur.role_effectif in roles
            )

    RoleRequis.__name__ = "RoleRequis"
    return RoleRequis


class EstAdminOuDirection(BasePermission):
    """Documentation de l'API : réservée à l'ADMIN et à la DIRECTION connectés."""

    def has_permission(self, request, view):
        utilisateur = request.user
        return bool(
            utilisateur
            and utilisateur.is_authenticated
            and utilisateur.role_effectif in (Role.ADMIN, Role.DIRECTION)
        )
```

#### `apps/api/auth.py`

*139 lignes* — Authentification JWT : connexion, renouvellement, déconnexion, profil.

```python
"""Authentification JWT : connexion, renouvellement, déconnexion, profil.

Jeton d'accès de 15 minutes, jeton de renouvellement de 7 jours qui change à chaque usage et
qui est révoqué à la déconnexion (cahier-des-charges.md:275, 285). La connexion est limitée à
10 essais par minute et par adresse (anti force brute). Les connexions réussies et échouées
sont inscrites au journal d'audit, comme celles de l'interface web.
"""

from django.contrib.auth.signals import user_logged_in, user_logged_out
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.accounts import mfa, throttle
from apps.accounts.signals import mfa_evenement
from apps.drivers import services as drivers_services


class ConnexionSerializer(TokenObtainPairSerializer):
    """Identifiant, mot de passe et, pour l'ADMIN et la DIRECTION, code de la double authentification.

    Le code (``otp``) est celui de l'application d'authentification, ou un code de secours. Un
    compte soumis à la MFA qui ne l'a pas encore activée doit d'abord le faire sur le site.
    """

    otp = serializers.CharField(required=False, allow_blank=True, write_only=True)

    def validate(self, attrs):
        otp = attrs.pop("otp", "")
        donnees = super().validate(attrs)  # vérifie le mot de passe, renseigne self.user
        utilisateur = self.user
        if not mfa.mfa_requise(utilisateur):
            return donnees
        requete = self.context.get("request")
        if mfa.appareil_actif(utilisateur) is None:
            raise exceptions.AuthenticationFailed(
                "Ce compte doit d'abord activer la double authentification sur le site.",
                code="mfa_non_activee",
            )
        if throttle.mfa_secondes_restantes(utilisateur):
            raise exceptions.Throttled(throttle.mfa_secondes_restantes(utilisateur))
        if not otp:
            raise exceptions.AuthenticationFailed(
                "Code de double authentification requis (champ « otp »).", code="mfa_requise"
            )
        if not mfa.verifier_code(utilisateur, otp):
            throttle.mfa_enregistrer_echec(utilisateur)
            mfa_evenement.send(
                sender=type(self), request=requete, utilisateur=utilisateur,
                evenement="api_code_refuse", succes=False,
            )
            raise exceptions.AuthenticationFailed(
                "Code de double authentification incorrect ou déjà utilisé.", code="mfa_invalide"
            )
        throttle.mfa_reinitialiser(utilisateur)
        return donnees


class ConnexionView(TokenObtainPairView):
    """Identifiant et mot de passe (+ code MFA pour ADMIN et DIRECTION) → jeton d'accès et de renouvellement."""

    serializer_class = ConnexionSerializer
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "connexion"

    def post(self, request, *args, **kwargs):
        # Un échec est déjà signalé par ``django.contrib.auth.authenticate`` (signal
        # ``user_login_failed``, donc inscrit à l'audit) : on n'ajoute que la réussite.
        reponse = super().post(request, *args, **kwargs)
        utilisateur = getattr(getattr(self, "serializer", None), "user", None)
        if utilisateur is not None:
            user_logged_in.send(sender=type(utilisateur), request=request, user=utilisateur)
        return reponse

    def get_serializer(self, *args, **kwargs):
        self.serializer = super().get_serializer(*args, **kwargs)
        return self.serializer


class RenouvellementView(TokenRefreshView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "connexion"


class RefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class DeconnexionView(APIView):
    """Révoque le jeton de renouvellement : il ne peut plus servir à obtenir un accès."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=RefreshSerializer, responses={204: None})
    def post(self, request):
        serializer = RefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            RefreshToken(serializer.validated_data["refresh"]).blacklist()
        except TokenError as erreur:
            raise InvalidToken(str(erreur)) from erreur
        user_logged_out.send(sender=type(request.user), request=request, user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProfilSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    identifiant = serializers.CharField(source="username")
    nom = serializers.SerializerMethodField()
    role = serializers.CharField(source="role_effectif")
    chauffeur_id = serializers.SerializerMethodField()

    def get_nom(self, utilisateur) -> str:
        return utilisateur.get_full_name() or utilisateur.username

    def get_chauffeur_id(self, utilisateur) -> int | None:
        fiche = drivers_services.chauffeur_de(utilisateur)
        return fiche.pk if fiche else None


class ProfilView(APIView):
    """Qui suis-je ? Utile à une application pour adapter son affichage au rôle."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=ProfilSerializer)
    def get(self, request):
        return Response(ProfilSerializer(request.user).data)
```

`ConnexionSerializer` ajoute au formulaire de connexion de `simplejwt` le champ `otp`. Pour un ADMIN ou une
DIRECTION : compte sans MFA activée → `401 mfa_non_activee` ; sans code → `401 mfa_requise` ; code faux → `401
mfa_invalide` (et inscription au journal d'audit) ; 5 codes faux → `429`. Le nouveau jeton est délivré **seulement**
si tout est bon. Les erreurs d'authentification sont aussi comptées par l'anti force brute du chapitre 3.

#### `apps/api/apps.py`

*7 lignes*

```python
from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.api'
    label = 'api'
```

## Étape 3 — Les ressources

#### `apps/api/v1/serializers.py`

*123 lignes* — Représentation JSON des ressources de l'API bureau (lecture seule).

```python
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
```

#### `apps/api/v1/filters.py`

*82 lignes* — Filtres des listes de l'API : mêmes critères que les écrans (statut, texte sans accents...).

```python
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
```

#### `apps/api/v1/views.py`

*100 lignes* — Ressources de l'API bureau, en lecture seule.

```python
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
```

Chaque `ViewSet` **réutilise le queryset du service** de l'écran correspondant (la même règle de soft delete, de
recherche) et l'ensemble de rôles `CONSULTATION` de son app.

#### `apps/api/urls.py`

*33 lignes* — Routes de l'API versionnée ``/api/v1/`` (architecture.md, ADR-007).

```python
"""Routes de l'API versionnée ``/api/v1/`` (architecture.md, ADR-007)."""

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.authentication import SessionAuthentication
from rest_framework.routers import SimpleRouter

from . import auth
from .permissions import EstAdminOuDirection
from .v1 import views

app_name = "api"

routeur = SimpleRouter()
routeur.register("missions", views.MissionViewSet, basename="mission")
routeur.register("camions", views.VehiculeViewSet, basename="camion")
routeur.register("chauffeurs", views.ChauffeurViewSet, basename="chauffeur")
routeur.register("clients", views.ClientViewSet, basename="client")
routeur.register("factures", views.FactureViewSet, basename="facture")

# La documentation décrit toute l'API : réservée à l'ADMIN et à la DIRECTION, connectés à l'interface web.
_protection = {"authentication_classes": [SessionAuthentication], "permission_classes": [EstAdminOuDirection]}

urlpatterns = [
    path("auth/token/", auth.ConnexionView.as_view(), name="token"),
    path("auth/token/refresh/", auth.RenouvellementView.as_view(), name="token_refresh"),
    path("auth/logout/", auth.DeconnexionView.as_view(), name="logout"),
    path("moi/", auth.ProfilView.as_view(), name="moi"),
    path("schema/", SpectacularAPIView.as_view(**_protection), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api:schema", **_protection), name="docs"),
    path("mobile/", include("apps.mobile_api.urls")),
    path("", include(routeur.urls)),
]
```

#### `apps/api/README.md`

*30 lignes* — api

```markdown
# api

Rôle : API REST versionnée `/api/v1/` — cahier-des-charges.md:250, 267, 275 ; architecture.md, ADR-007.
Couche haute : elle lit les mêmes services et applique les mêmes rôles que les écrans.

**Authentification** (`auth.py`, JWT via simplejwt) :
- `POST /api/v1/auth/token/` : identifiant + mot de passe → jeton d'accès (15 min) et de renouvellement (7 jours) ;
- `POST /api/v1/auth/token/refresh/` : nouveau couple ; l'ancien renouvellement est révoqué ;
- `POST /api/v1/auth/logout/` : révoque le renouvellement ; `GET /api/v1/moi/` : profil et rôle.
La connexion est limitée à 10 essais par minute et par adresse (anti force brute). Connexions et
déconnexions sont inscrites au journal d'audit comme celles du site.
**Double authentification** (étape 7) : pour l'ADMIN et la DIRECTION, `POST /api/v1/auth/token/` exige aussi le
champ `otp` (code de l'application ou code de secours) ; un compte qui n'a pas encore activé la MFA sur le site
reçoit une erreur `401` avec `code` = `mfa_non_activee` (`mfa_requise` ou `mfa_invalide` sinon).

**Ressources en lecture seule** (`v1/`) : `missions`, `camions`, `chauffeurs`, `clients`, `factures`
(liste paginée par 20, détail, filtres). Chaque ressource réutilise le queryset du service de l'écran
correspondant et son ensemble `permissions.CONSULTATION` : un rôle n'obtient pas par l'API ce que
l'écran lui refuse. Les champs sont listés un à un (jamais `__all__`) ; **les codes secrets des
missions n'apparaissent jamais**. La recherche `q` ignore accents et casse, comme à l'écran.
Les écritures restent sur les écrans web.

**Erreurs** (`exceptions.py`) : les exceptions métier des services deviennent `{"code", "detail"}` :
400 règle refusée, 403 droit insuffisant, 404 mission introuvable, 409 saisie de plein suspecte.

**Documentation** : `/api/v1/docs/` (Swagger) et `/api/v1/schema/` (OpenAPI), réservées à l'ADMIN
et à la DIRECTION connectés. CORS limité à `/api/` et aux domaines de `CORS_ALLOWED_ORIGINS`.

Pas encore fait : écriture depuis l'API bureau, limitation de débit au niveau du serveur web (étape 7,
lot 3), pagination par curseur.
```

#### `apps/accounts/tests/test_mfa.py`

*606 lignes* — Double authentification : règles (mfa.py), porte (middleware) et écrans.

```python
"""Double authentification : règles (mfa.py), porte (middleware) et écrans."""

import io

import pyotp
import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.urls import reverse
from PIL import Image

from apps.accounts import mfa
from apps.accounts.models import AppareilMFA, CodeSecours, Role, User
from apps.audit.models import AuditLog, StatutChoices

from .factories import UserFactory
from .helpers_mfa import activer_mfa, code_frais

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def mfa_imposee(settings):
    """Dans ce fichier la MFA est imposée (les autres tests du projet la laissent désactivée)."""
    settings.MFA_ENFORCED = True
    cache.clear()


@pytest.fixture
def direction():
    return UserFactory(role=Role.DIRECTION)


def _connecte(client, utilisateur):
    client.force_login(utilisateur)
    return utilisateur


# --- qui est soumis à la MFA ---


@pytest.mark.parametrize("role, attendu", [
    (Role.ADMIN, True), (Role.DIRECTION, True), (Role.RH, False), (Role.CHARGE_CLIENTELE, False),
    (Role.PARCAUTO, False), (Role.FINANCES, False), (Role.CHAUFFEUR, False),
])
def test_seuls_l_admin_et_la_direction_sont_soumis_a_la_mfa(role, attendu):
    assert mfa.mfa_requise(UserFactory(role=role)) is attendu


def test_un_superutilisateur_sans_role_est_soumis_a_la_mfa():
    assert mfa.mfa_requise(UserFactory(role="", is_superuser=True)) is True


def test_la_mfa_peut_etre_desactivee_par_reglage(settings, direction):
    settings.MFA_ENFORCED = False
    assert mfa.mfa_requise(direction) is False


# --- règles du service ---


def test_activation_avec_un_bon_code_donne_dix_codes_de_secours(direction):
    appareil = mfa.preparer_activation(direction)

    codes = mfa.confirmer_activation(direction, pyotp.TOTP(appareil.secret).now())

    assert len(codes) == 10 and len(set(codes)) == 10
    assert all(len(c) == 11 and c[5] == "-" for c in codes)
    direction.refresh_from_db()
    assert direction.mfa_enabled is True and mfa.appareil_actif(direction) is not None


def test_activation_avec_un_mauvais_code_est_refusee(direction):
    mfa.preparer_activation(direction)

    with pytest.raises(mfa.CodeInvalide):
        mfa.confirmer_activation(direction, "000000")

    direction.refresh_from_db()
    assert direction.mfa_enabled is False and mfa.appareil_actif(direction) is None


def test_on_ne_peut_pas_activer_deux_fois(direction):
    activer_mfa(direction)

    with pytest.raises(mfa.DejaActive):
        mfa.preparer_activation(direction)


def test_les_codes_de_secours_ne_sont_pas_conserves_en_clair(direction):
    _, codes = activer_mfa(direction)

    empreintes = set(CodeSecours.objects.filter(utilisateur=direction).values_list("empreinte", flat=True))

    assert len(empreintes) == 10
    assert all(c.replace("-", "") not in " ".join(empreintes) for c in codes)


def test_un_code_totp_ne_sert_qu_une_fois(direction):
    activer_mfa(direction)
    code = code_frais(direction)

    assert mfa.verifier_code(direction, code) is True
    assert mfa.verifier_code(direction, code) is False  # rejeu refusé


def test_un_code_totp_faux_ou_mal_forme_est_refuse(direction):
    activer_mfa(direction)

    for code in ("", "abcdef", "12345", "1234567", "000000"):
        assert mfa.verifier_code(direction, code) is False, code


def test_un_code_de_secours_ne_sert_qu_une_fois_meme_mal_saisi(direction):
    _, codes = activer_mfa(direction)
    code = codes[0]

    assert mfa.verifier_code(direction, code.lower().replace("-", " ")) is True
    assert mfa.verifier_code(direction, code) is False
    assert mfa.codes_secours_restants(direction) == 9


def test_verifier_sans_appareil_actif_est_refuse(direction):
    assert mfa.verifier_code(direction, "123456") is False


def test_regenerer_les_codes_exige_un_code_totp_et_annule_les_anciens(direction):
    _, anciens = activer_mfa(direction)

    with pytest.raises(mfa.CodeInvalide):
        mfa.regenerer_codes_secours(direction, anciens[0])  # un code de secours ne suffit pas
    nouveaux = mfa.regenerer_codes_secours(direction, code_frais(direction))

    assert set(nouveaux).isdisjoint(anciens)
    assert mfa.verifier_code(direction, anciens[1]) is False
    assert mfa.verifier_code(direction, nouveaux[0]) is True


def test_reinitialiser_supprime_l_appareil_et_les_codes(direction):
    activer_mfa(direction)

    mfa.reinitialiser(direction)

    direction.refresh_from_db()
    assert direction.mfa_enabled is False
    assert not AppareilMFA.objects.filter(utilisateur=direction).exists()
    assert not CodeSecours.objects.filter(utilisateur=direction).exists()


# --- la porte : refus par défaut tant que la MFA n'est pas passée ---

PAGES_DE_BUREAU = [
    "/", "/missions/", "/clients/", "/flotte/", "/rh/personnel/", "/rh/conges/", "/chauffeurs/",
    "/garage/", "/carburant/", "/stock/", "/facturation/", "/finances/", "/notifications/",
    "/admin/", "/api/v1/docs/",
]


@pytest.mark.parametrize("chemin", PAGES_DE_BUREAU)
def test_sans_appareil_toute_page_renvoie_vers_l_activation(client, direction, chemin):
    _connecte(client, direction)

    reponse = client.get(chemin)

    assert reponse.status_code == 302
    assert reponse["Location"].startswith(reverse("accounts:mfa_activer"))


@pytest.mark.parametrize("chemin", PAGES_DE_BUREAU)
def test_avec_appareil_toute_page_renvoie_vers_la_verification(client, direction, chemin):
    activer_mfa(direction)
    _connecte(client, direction)

    reponse = client.get(chemin)

    assert reponse.status_code == 302
    assert reponse["Location"].startswith(reverse("accounts:mfa_verifier"))


def test_la_page_demandee_est_conservee_pour_apres_la_verification(client, direction):
    activer_mfa(direction)
    _connecte(client, direction)

    reponse = client.get("/missions/?q=abc")

    assert "next=/missions/%3Fq%3Dabc" in reponse["Location"]


def test_un_post_est_aussi_bloque(client, direction):
    activer_mfa(direction)
    _connecte(client, direction)

    reponse = client.post("/missions/nouvelle/", {})

    assert reponse.status_code == 302 and "mfa/verifier" in reponse["Location"]


def test_l_api_repond_403_json_plutot_qu_une_redirection(client, direction):
    _connecte(client, direction)

    reponse = client.get("/api/v1/moi/")

    assert reponse.status_code == 403 and reponse.json()["code"] == "mfa_requise"


def test_les_fichiers_statiques_et_la_deconnexion_restent_accessibles(client, direction):
    _connecte(client, direction)

    assert client.post(reverse("accounts:logout")).status_code == 302
    assert client.get("/static/img/favicon.png").status_code != 403  # jamais bloqué par la porte


def test_apres_verification_les_pages_s_ouvrent(client, direction):
    activer_mfa(direction)
    _connecte(client, direction)
    reponse = client.post(reverse("accounts:mfa_verifier"), {"code": code_frais(direction)})

    assert reponse.status_code == 302 and reponse["Location"] == reverse("home")
    assert client.get("/missions/").status_code == 200


def test_les_autres_roles_ne_sont_pas_concernes(client):
    for role in (Role.RH, Role.CHARGE_CLIENTELE, Role.PARCAUTO, Role.FINANCES):
        client.force_login(UserFactory(role=role))
        assert client.get("/").status_code == 200, role
        for nom in ("mfa_verifier", "mfa_activer", "mfa_qr", "mfa_codes"):
            assert client.get(reverse(f"accounts:{nom}")).status_code == 404, (role, nom)


def test_une_nouvelle_ouverture_de_session_demande_a_nouveau_la_mfa(client, direction):
    activer_mfa(direction)
    _connecte(client, direction)
    client.post(reverse("accounts:mfa_verifier"), {"code": code_frais(direction)})
    assert client.get("/missions/").status_code == 200

    client.force_login(direction)  # même personne, nouvelle ouverture de session

    assert client.get("/missions/").status_code == 302


def test_la_verification_change_l_identifiant_de_session(client, direction):
    activer_mfa(direction)
    _connecte(client, direction)
    avant = client.session.session_key

    client.post(reverse("accounts:mfa_verifier"), {"code": code_frais(direction)})

    assert client.session.session_key != avant


# --- écran de vérification ---


def test_un_code_faux_est_refuse_et_rien_n_est_ouvert(client, direction):
    activer_mfa(direction)
    _connecte(client, direction)

    reponse = client.post(reverse("accounts:mfa_verifier"), {"code": "000000"})

    assert reponse.status_code == 200 and "Code incorrect" in reponse.content.decode()
    assert client.get("/missions/").status_code == 302


def test_un_code_de_secours_ouvre_la_session_une_seule_fois(client, direction):
    _, codes = activer_mfa(direction)
    _connecte(client, direction)

    reponse = client.post(reverse("accounts:mfa_verifier"), {"code": codes[0]})
    assert reponse.status_code == 302 and client.get("/missions/").status_code == 200

    client.force_login(direction)
    reponse = client.post(reverse("accounts:mfa_verifier"), {"code": codes[0]})
    assert reponse.status_code == 200 and client.get("/missions/").status_code == 302


def test_apres_cinq_codes_faux_meme_le_bon_code_est_refuse(client, direction):
    activer_mfa(direction)
    _connecte(client, direction)
    for _ in range(5):
        client.post(reverse("accounts:mfa_verifier"), {"code": "000000"})

    reponse = client.post(reverse("accounts:mfa_verifier"), {"code": code_frais(direction)})

    assert reponse.status_code == 429 and "Trop de codes incorrects" in reponse.content.decode()
    assert client.get("/missions/").status_code == 302


def test_un_bon_code_efface_les_echecs(client, direction):
    activer_mfa(direction)
    _connecte(client, direction)
    for _ in range(4):
        client.post(reverse("accounts:mfa_verifier"), {"code": "000000"})
    client.post(reverse("accounts:mfa_verifier"), {"code": code_frais(direction)})
    client.force_login(direction)
    for _ in range(4):
        client.post(reverse("accounts:mfa_verifier"), {"code": "000000"})

    reponse = client.post(reverse("accounts:mfa_verifier"), {"code": code_frais(direction)})

    assert reponse.status_code == 302  # 4 + 4 échecs, mais le compteur avait été remis à zéro


@pytest.mark.parametrize("cible", ["https://pirate.example/", "//pirate.example/", "javascript:alert(1)"])
def test_la_redirection_apres_verification_refuse_les_adresses_externes(client, direction, cible):
    activer_mfa(direction)
    _connecte(client, direction)

    reponse = client.post(
        reverse("accounts:mfa_verifier") + f"?next={cible}", {"code": code_frais(direction)}
    )

    assert reponse["Location"] == reverse("home")


def test_la_verification_redirige_vers_la_page_demandee(client, direction):
    activer_mfa(direction)
    _connecte(client, direction)

    reponse = client.post(
        reverse("accounts:mfa_verifier") + "?next=/flotte/", {"code": code_frais(direction)}
    )

    assert reponse["Location"] == "/flotte/"


def test_la_page_de_verification_sans_appareil_renvoie_vers_l_activation(client, direction):
    _connecte(client, direction)

    reponse = client.get(reverse("accounts:mfa_verifier"))

    assert reponse["Location"] == reverse("accounts:mfa_activer")


def test_la_page_de_verification_est_protegee_par_csrf(direction):
    from django.test import Client

    activer_mfa(direction)
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(direction)

    assert strict.post(reverse("accounts:mfa_verifier"), {"code": code_frais(direction)}).status_code == 403


def test_un_anonyme_est_renvoye_vers_la_connexion(client):
    assert client.get(reverse("accounts:mfa_verifier"))["Location"].startswith(reverse("accounts:login"))


# --- écran d'activation ---


def test_la_page_d_activation_montre_le_qr_et_la_cle(client, direction):
    _connecte(client, direction)

    reponse = client.get(reverse("accounts:mfa_activer"))
    texte = reponse.content.decode()

    secret = AppareilMFA.objects.get(utilisateur=direction).secret
    assert reponse.status_code == 200
    assert reverse("accounts:mfa_qr") in texte and secret[:4] in texte


def test_le_secret_reste_le_meme_si_on_recharge_la_page(client, direction):
    _connecte(client, direction)
    client.get(reverse("accounts:mfa_activer"))
    premier = AppareilMFA.objects.get(utilisateur=direction).secret

    client.get(reverse("accounts:mfa_activer"))

    assert AppareilMFA.objects.get(utilisateur=direction).secret == premier


def test_le_qr_est_une_image_png_jamais_mise_en_cache(client, direction):
    _connecte(client, direction)
    client.get(reverse("accounts:mfa_activer"))

    reponse = client.get(reverse("accounts:mfa_qr"))

    assert reponse.status_code == 200 and reponse["Content-Type"] == "image/png"
    assert reponse["Cache-Control"] == "no-store, private"
    assert Image.open(io.BytesIO(reponse.content)).size[0] > 100


def test_le_qr_disparait_une_fois_la_mfa_activee(client, direction):
    activer_mfa(direction)
    _connecte(client, direction)

    assert client.get(reverse("accounts:mfa_qr")).status_code == 404


def test_l_activation_affiche_les_codes_de_secours_une_seule_fois(client, direction):
    _connecte(client, direction)
    client.get(reverse("accounts:mfa_activer"))
    secret = AppareilMFA.objects.get(utilisateur=direction).secret

    reponse = client.post(reverse("accounts:mfa_activer"), {"code": pyotp.TOTP(secret).now()})
    texte = reponse.content.decode()

    assert reponse.status_code == 200 and reponse["Cache-Control"] == "no-store, private"
    assert texte.count("<li class=\"rounded-lg bg-slate-100") == 10
    direction.refresh_from_db()
    assert direction.mfa_enabled is True
    assert client.get("/missions/").status_code == 200  # la session est vérifiée d'emblée
    assert "bg-slate-100 px-3 py-2 text-center" not in client.get(reverse("accounts:mfa_activer")).content.decode()


def test_un_mauvais_code_d_activation_n_active_rien(client, direction):
    _connecte(client, direction)
    client.get(reverse("accounts:mfa_activer"))

    reponse = client.post(reverse("accounts:mfa_activer"), {"code": "111111"})

    assert reponse.status_code == 200 and "pas valable" in reponse.content.decode()
    direction.refresh_from_db()
    assert direction.mfa_enabled is False


def test_activer_une_mfa_deja_active_renvoie_vers_la_verification(client, direction):
    activer_mfa(direction)
    _connecte(client, direction)

    assert client.get(reverse("accounts:mfa_activer"))["Location"] == reverse("accounts:mfa_verifier")
    assert client.post(reverse("accounts:mfa_activer"), {"code": "123456"})["Location"] == reverse(
        "accounts:mfa_verifier"
    )


# --- codes de secours ---


def test_la_page_des_codes_est_inaccessible_tant_que_la_mfa_n_est_pas_passee(client, direction):
    activer_mfa(direction)
    _connecte(client, direction)

    assert client.get(reverse("accounts:mfa_codes"))["Location"].startswith(reverse("accounts:mfa_verifier"))


def test_regenerer_les_codes_depuis_l_interface(client, direction):
    _, anciens = activer_mfa(direction)
    _connecte(client, direction)
    client.post(reverse("accounts:mfa_verifier"), {"code": code_frais(direction)})

    page = client.get(reverse("accounts:mfa_codes"))
    assert page.status_code == 200 and "10</strong> codes" in page.content.decode()
    refus = client.post(reverse("accounts:mfa_codes"), {"code": anciens[0]})
    assert refus.status_code == 200 and "Code incorrect" in refus.content.decode()
    reponse = client.post(reverse("accounts:mfa_codes"), {"code": code_frais(direction)})

    assert reponse.status_code == 200 and reponse.content.decode().count('<li class="rounded-lg bg-slate-100') == 10
    assert mfa.verifier_code(direction, anciens[2]) is False


def test_le_lien_codes_de_secours_apparait_pour_les_roles_soumis_a_la_mfa(client, direction):
    activer_mfa(direction)
    _connecte(client, direction)
    client.post(reverse("accounts:mfa_verifier"), {"code": code_frais(direction)})

    assert reverse("accounts:mfa_codes") in client.get("/").content.decode()
    client.force_login(UserFactory(role=Role.RH))
    assert reverse("accounts:mfa_codes") not in client.get("/").content.decode()


# --- réinitialisation ---


def test_l_administrateur_reinitialise_la_mfa_depuis_l_administration(client):
    perdu = UserFactory(role=Role.DIRECTION)
    activer_mfa(perdu)
    admin = UserFactory(role=Role.ADMIN, is_staff=True, is_superuser=True)
    activer_mfa(admin)
    client.force_login(admin)
    client.post(reverse("accounts:mfa_verifier"), {"code": code_frais(admin)})

    reponse = client.post(
        reverse("admin:accounts_user_changelist"),
        {"action": "reinitialiser_mfa", "_selected_action": [perdu.pk]},
        follow=True,
    )

    assert reponse.status_code == 200
    perdu.refresh_from_db()
    assert perdu.mfa_enabled is False and not AppareilMFA.objects.filter(utilisateur=perdu).exists()
    assert AuditLog.objects.filter(entite="MFA", entite_id=perdu.pk, nouvelle_valeur__evenement__startswith="reinitialisation_par_").exists()


def test_la_commande_reinitialise_la_mfa(direction):
    activer_mfa(direction)

    call_command("reinitialiser_mfa", direction.username)

    direction.refresh_from_db()
    assert direction.mfa_enabled is False


def test_la_commande_refuse_un_compte_inconnu():
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command("reinitialiser_mfa", "personne")


def test_le_champ_mfa_active_n_est_pas_modifiable_a_la_main(client):
    admin = UserFactory(role=Role.ADMIN, is_staff=True, is_superuser=True)
    activer_mfa(admin)
    client.force_login(admin)
    client.post(reverse("accounts:mfa_verifier"), {"code": code_frais(admin)})
    autre = UserFactory(role=Role.RH)

    page = client.get(reverse("admin:accounts_user_change", args=[autre.pk]))

    assert page.status_code == 200
    assert 'name="mfa_enabled"' not in page.content.decode()


# --- journal d'audit ---


def test_les_etapes_de_la_mfa_sont_inscrites_sans_secret(client, direction):
    _connecte(client, direction)
    client.get(reverse("accounts:mfa_activer"))
    secret = AppareilMFA.objects.get(utilisateur=direction).secret
    client.post(reverse("accounts:mfa_activer"), {"code": "111111"})
    client.post(reverse("accounts:mfa_activer"), {"code": pyotp.TOTP(secret).now()})

    lignes = AuditLog.objects.filter(entite="MFA", entite_id=direction.pk).order_by("pk")

    assert [(l.nouvelle_valeur["evenement"], l.statut) for l in lignes] == [
        ("activation_refusee", StatutChoices.FAILED), ("activation", StatutChoices.SUCCESS),
    ]
    assert secret not in str([l.nouvelle_valeur for l in lignes])


def test_l_admin_django_utilise_la_page_de_connexion_du_site(client):
    reponse = client.get("/admin/login/?next=/admin/accounts/user/")

    assert reponse.status_code == 302
    assert reponse["Location"].startswith(reverse("accounts:login"))
    assert "next=/admin/accounts/user/" in reponse["Location"]
    assert User.objects.count() == 0


def test_un_compte_de_role_admin_non_superutilisateur_peut_reinitialiser_la_mfa(client):
    perdu = UserFactory(role=Role.DIRECTION)
    activer_mfa(perdu)
    admin = UserFactory(role=Role.ADMIN, is_staff=True)  # ni superutilisateur, ni permissions Django
    activer_mfa(admin)
    client.force_login(admin)
    client.post(reverse("accounts:mfa_verifier"), {"code": code_frais(admin)})

    liste = client.get(reverse("admin:accounts_user_changelist"))
    reponse = client.post(
        reverse("admin:accounts_user_changelist"),
        {"action": "reinitialiser_mfa", "_selected_action": [perdu.pk]},
        follow=True,
    )

    assert liste.status_code == 200
    perdu.refresh_from_db()
    assert perdu.mfa_enabled is False and reponse.status_code == 200


def test_un_compte_de_role_admin_ne_peut_pas_modifier_un_utilisateur(client):
    autre = UserFactory(role=Role.RH)
    admin = UserFactory(role=Role.ADMIN, is_staff=True)
    activer_mfa(admin)
    client.force_login(admin)
    client.post(reverse("accounts:mfa_verifier"), {"code": code_frais(admin)})

    page = client.get(reverse("admin:accounts_user_change", args=[autre.pk]))
    envoi = client.post(reverse("admin:accounts_user_change", args=[autre.pk]), {"role": Role.ADMIN})

    assert page.status_code == 200 and "Enregistrer" not in page.content.decode()  # lecture seule
    autre.refresh_from_db()
    assert autre.role == Role.RH and envoi.status_code in (302, 403)


@pytest.mark.parametrize("role", [Role.DIRECTION, Role.RH, Role.FINANCES])
def test_les_autres_roles_meme_staff_ne_voient_pas_les_utilisateurs(client, role):
    membre = UserFactory(role=role, is_staff=True)
    if mfa.mfa_requise(membre):
        activer_mfa(membre)
        client.force_login(membre)
        client.post(reverse("accounts:mfa_verifier"), {"code": code_frais(membre)})
    else:
        client.force_login(membre)

    assert client.get(reverse("admin:accounts_user_changelist")).status_code == 403


def test_le_favicon_redirige_vers_l_icone_du_site(client):
    reponse = client.get("/favicon.ico")

    assert reponse.status_code == 301 and reponse["Location"].endswith("/static/img/favicon.png")


def test_les_titres_des_pages_de_mfa_sont_ceux_attendus(client, direction):
    _connecte(client, direction)
    activation = client.get(reverse("accounts:mfa_activer")).content.decode()
    _, _codes = activer_mfa(UserFactory(role=Role.DIRECTION))
    autre = UserFactory(role=Role.DIRECTION)
    activer_mfa(autre)
    client.force_login(autre)
    verification = client.get(reverse("accounts:mfa_verifier")).content.decode()

    assert "<h1 class=\"mt-3 text-xl font-bold text-slate-900\">Activez la double authentification</h1>" in activation
    assert "Vérification en deux étapes</h1>" in verification
    assert "SOUS" not in activation + verification  # trace d'un gabarit mal généré
```

#### `apps/accounts/tests/test_securite_connexion.py`

*204 lignes* — Anti force brute sur la connexion, hachage Argon2 et longueur des mots de passe.

```python
"""Anti force brute sur la connexion, hachage Argon2 et longueur des mots de passe."""

import pytest
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts import throttle
from apps.accounts.models import Role, User
from apps.audit.models import ActionChoices, AuditLog, StatutChoices

from .factories import UserFactory

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "Test-Passw0rd!"


@pytest.fixture(autouse=True)
def cache_vide():
    cache.clear()


def _essai(client, identifiant, mot_de_passe="faux", **extra):
    return client.post(reverse("accounts:login"), {"username": identifiant, "password": mot_de_passe}, **extra)


# --- limitation par couple (adresse, identifiant) ---


def test_apres_cinq_echecs_meme_le_bon_mot_de_passe_est_refuse(client):
    UserFactory(username="awa", role=Role.RH)
    for _ in range(5):
        assert _essai(client, "awa").status_code == 200

    reponse = _essai(client, "awa", MOT_DE_PASSE)

    assert reponse.status_code == 429
    assert "Trop de tentatives" in reponse.content.decode()
    assert "_auth_user_id" not in client.session


def test_le_blocage_ne_verifie_meme_pas_le_mot_de_passe(client):
    """Pas de nouvelle ligne d'audit « échec » pendant le blocage : rien n'a été tenté."""
    for _ in range(5):
        _essai(client, "awa")
    avant = AuditLog.objects.filter(action=ActionChoices.LOGIN, statut=StatutChoices.FAILED).count()

    _essai(client, "awa")

    assert AuditLog.objects.filter(action=ActionChoices.LOGIN, statut=StatutChoices.FAILED).count() == avant


def test_un_autre_identifiant_depuis_la_meme_adresse_n_est_pas_bloque(client):
    UserFactory(username="moussa", role=Role.RH)
    for _ in range(5):
        _essai(client, "awa")

    assert _essai(client, "moussa", MOT_DE_PASSE).status_code == 302


def test_un_autre_client_n_est_pas_bloque_par_les_echecs_d_une_adresse(client):
    UserFactory(username="awa", role=Role.RH)
    for _ in range(5):
        _essai(client, "awa", REMOTE_ADDR="198.51.100.7")

    assert _essai(Client(), "awa", MOT_DE_PASSE, REMOTE_ADDR="198.51.100.8").status_code == 302


def test_la_casse_et_les_espaces_ne_contournent_pas_la_limite(client):
    UserFactory(username="awa", role=Role.RH)
    for variante in ("awa", "AWA", " Awa ", "aWa", "awa"):
        _essai(client, variante)

    assert _essai(client, "awa", MOT_DE_PASSE).status_code == 429


def test_un_en_tete_x_forwarded_for_forge_ne_contourne_pas_la_limite(client):
    UserFactory(username="awa", role=Role.RH)
    for i in range(5):
        _essai(client, "awa", HTTP_X_FORWARDED_FOR=f"203.0.113.{i}")

    assert _essai(client, "awa", MOT_DE_PASSE, HTTP_X_FORWARDED_FOR="203.0.113.99").status_code == 429


def test_une_connexion_reussie_remet_le_compteur_a_zero(client):
    UserFactory(username="awa", role=Role.RH)
    for _ in range(4):
        _essai(client, "awa")
    assert _essai(client, "awa", MOT_DE_PASSE).status_code == 302
    client.post(reverse("accounts:logout"))

    for _ in range(4):
        _essai(client, "awa")

    assert _essai(client, "awa", MOT_DE_PASSE).status_code == 302  # 4 + 4 échecs, mais remis à zéro entre


def test_le_blocage_prend_fin_avec_la_fenetre(client, monkeypatch):
    UserFactory(username="awa", role=Role.RH)
    for _ in range(5):
        _essai(client, "awa")
    assert _essai(client, "awa", MOT_DE_PASSE).status_code == 429

    instant = throttle.time.time()
    monkeypatch.setattr(throttle.time, "time", lambda: instant + 15 * 60 + 1)

    assert _essai(client, "awa", MOT_DE_PASSE).status_code == 302


# --- limitation par adresse ---


def test_vingt_echecs_depuis_une_adresse_la_bloquent_quel_que_soit_l_identifiant(client):
    UserFactory(username="awa", role=Role.RH)
    for i in range(20):
        _essai(client, f"inconnu{i}")

    assert _essai(client, "awa", MOT_DE_PASSE).status_code == 429


def test_la_phrase_d_attente_est_en_minutes_arrondies_vers_le_haut():
    assert throttle.phrase_attente(1) == "1 minute"
    assert throttle.phrase_attente(61) == "2 minutes"
    assert throttle.phrase_attente(15 * 60) == "15 minutes"


def test_le_message_ne_revele_pas_si_le_compte_existe(client):
    UserFactory(username="reel", role=Role.RH)
    for _ in range(5):
        _essai(client, "reel")
        _essai(client, "fantome")

    reel = _essai(client, "reel").content.decode()
    fantome = _essai(client, "fantome").content.decode()

    assert "Trop de tentatives" in reel and "Trop de tentatives" in fantome


def test_les_echecs_de_l_api_comptent_aussi(client):
    from rest_framework.test import APIClient

    UserFactory(username="awa", role=Role.RH)
    api = APIClient()
    for _ in range(5):
        api.post(reverse("api:token"), {"username": "awa", "password": "faux"}, format="json")

    assert _essai(client, "awa", MOT_DE_PASSE).status_code == 429


# --- Argon2 et mots de passe ---


def test_argon2_est_le_premier_hacheur_de_la_configuration_de_production():
    from config.settings import base

    assert base.PASSWORD_HASHERS[0] == "django.contrib.auth.hashers.Argon2PasswordHasher"
    assert "django.contrib.auth.hashers.PBKDF2PasswordHasher" in base.PASSWORD_HASHERS


ARGON2_PUIS_PBKDF2 = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]


@override_settings(PASSWORD_HASHERS=ARGON2_PUIS_PBKDF2)
def test_un_ancien_hachage_pbkdf2_est_converti_en_argon2_a_la_connexion():
    ancien = make_password(MOT_DE_PASSE, hasher="pbkdf2_sha256")
    utilisateur = UserFactory(username="awa", role=Role.RH)
    User.objects.filter(pk=utilisateur.pk).update(password=ancien)
    assert User.objects.get(pk=utilisateur.pk).password.startswith("pbkdf2_sha256$")

    assert authenticate(username="awa", password=MOT_DE_PASSE) is not None

    assert User.objects.get(pk=utilisateur.pk).password.startswith("argon2$")


@override_settings(PASSWORD_HASHERS=ARGON2_PUIS_PBKDF2)
def test_un_nouveau_mot_de_passe_est_hache_en_argon2():
    utilisateur = UserFactory(role=Role.RH)
    utilisateur.set_password("Nouveau-Mot-de-passe-9")

    assert utilisateur.password.startswith("argon2$")
    assert utilisateur.check_password("Nouveau-Mot-de-passe-9")


def test_un_mot_de_passe_de_moins_de_dix_caracteres_est_refuse():
    with pytest.raises(ValidationError):
        validate_password("Court-1aB")  # 9 caractères
    validate_password("Assez-long-42x")  # 14 : accepté


# --- administration ---


def test_l_echec_sur_l_admin_django_passe_par_la_page_du_site(client):
    reponse = client.post("/admin/login/", {"username": "awa", "password": "faux"})

    assert reponse.status_code == 302 and reponse["Location"].startswith(reverse("accounts:login"))
```

#### `apps/api/tests/test_auth.py`

*146 lignes* — Authentification JWT : connexion, renouvellement, déconnexion, limitation, audit.

```python
"""Authentification JWT : connexion, renouvellement, déconnexion, limitation, audit."""

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.audit.models import ActionChoices, AuditLog, StatutChoices
from apps.drivers.tests.factories import ChauffeurFactory

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "Test-Passw0rd!"  # défini par UserFactory


@pytest.fixture
def api():
    cache.clear()
    return APIClient()


def _connexion(api, utilisateur, mot_de_passe=MOT_DE_PASSE):
    return api.post(
        reverse("api:token"), {"username": utilisateur.username, "password": mot_de_passe}, format="json"
    )


def test_la_connexion_donne_un_acces_et_un_renouvellement(api):
    utilisateur = UserFactory(role=Role.CHAUFFEUR)

    reponse = _connexion(api, utilisateur)

    assert reponse.status_code == 200 and set(reponse.data) == {"access", "refresh"}
    utilisateur.refresh_from_db()
    assert utilisateur.last_login is not None


def test_le_jeton_d_acces_dure_15_minutes_et_le_renouvellement_7_jours(api):
    utilisateur = UserFactory()
    donnees = _connexion(api, utilisateur).data

    acces, renouvellement = AccessToken(donnees["access"]), RefreshToken(donnees["refresh"])

    assert acces["exp"] - acces["iat"] == 15 * 60
    assert renouvellement["exp"] - renouvellement["iat"] == 7 * 24 * 3600


def test_un_mauvais_mot_de_passe_ou_un_compte_inactif_est_refuse(api):
    actif, inactif = UserFactory(), UserFactory(is_active=False)

    assert _connexion(api, actif, "faux").status_code == 401
    assert _connexion(api, inactif).status_code == 401
    assert _connexion(api, UserFactory(username="inconnu"), "x").status_code == 401


def test_la_connexion_est_inscrite_au_journal_d_audit(api):
    utilisateur = UserFactory()

    _connexion(api, utilisateur)
    _connexion(api, utilisateur, "faux")

    reussie = AuditLog.objects.get(action=ActionChoices.LOGIN, statut=StatutChoices.SUCCESS)
    echouee = AuditLog.objects.get(action=ActionChoices.LOGIN, statut=StatutChoices.FAILED)
    assert reussie.entite_id == utilisateur.pk and reussie.module == "AUTH"
    assert echouee.nouvelle_valeur == {"username_tente": utilisateur.username}


def test_un_acces_valide_ouvre_le_profil_avec_le_role_et_l_id_chauffeur(api):
    fiche = ChauffeurFactory()
    compte = UserFactory(role=Role.CHAUFFEUR)
    fiche.personnel.utilisateur = compte
    fiche.personnel.save()
    acces = _connexion(api, compte).data["access"]

    reponse = api.get(reverse("api:moi"), HTTP_AUTHORIZATION=f"Bearer {acces}")

    assert reponse.status_code == 200
    assert reponse.data["role"] == Role.CHAUFFEUR and reponse.data["chauffeur_id"] == fiche.pk
    assert reponse.data["identifiant"] == compte.username


def test_le_profil_d_un_superutilisateur_sans_role_est_admin_sans_chauffeur(api):
    api.force_authenticate(UserFactory(role="", is_superuser=True))

    reponse = api.get(reverse("api:moi"))

    assert reponse.data["role"] == Role.ADMIN and reponse.data["chauffeur_id"] is None


def test_sans_jeton_ou_avec_un_jeton_invalide_ou_expire_l_acces_est_refuse(api):
    utilisateur = UserFactory()
    expire = AccessToken.for_user(utilisateur)
    expire.set_exp(lifetime=-timedelta(seconds=1))

    assert api.get(reverse("api:moi")).status_code == 401
    assert api.get(reverse("api:moi"), HTTP_AUTHORIZATION="Bearer nimportequoi").status_code == 401
    assert api.get(reverse("api:moi"), HTTP_AUTHORIZATION=f"Bearer {expire}").status_code == 401


def test_le_renouvellement_change_le_jeton_et_revoque_l_ancien(api):
    donnees = _connexion(api, UserFactory()).data

    premier = api.post(reverse("api:token_refresh"), {"refresh": donnees["refresh"]}, format="json")
    rejoue = api.post(reverse("api:token_refresh"), {"refresh": donnees["refresh"]}, format="json")

    assert premier.status_code == 200 and premier.data["refresh"] != donnees["refresh"]
    assert rejoue.status_code == 401  # l'ancien jeton de renouvellement est révoqué


def test_la_deconnexion_revoque_le_renouvellement(api):
    utilisateur = UserFactory()
    donnees = _connexion(api, utilisateur).data
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {donnees['access']}")

    sortie = api.post(reverse("api:logout"), {"refresh": donnees["refresh"]}, format="json")
    api.credentials()
    apres = api.post(reverse("api:token_refresh"), {"refresh": donnees["refresh"]}, format="json")

    assert sortie.status_code == 204 and apres.status_code == 401
    assert AuditLog.objects.filter(action=ActionChoices.LOGOUT).exists()


def test_la_deconnexion_exige_un_acces_et_un_renouvellement_valide(api):
    donnees = _connexion(api, UserFactory()).data

    assert api.post(reverse("api:logout"), {"refresh": donnees["refresh"]}, format="json").status_code == 401
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {donnees['access']}")
    assert api.post(reverse("api:logout"), {}, format="json").status_code == 400
    assert api.post(reverse("api:logout"), {"refresh": "faux"}, format="json").status_code == 401


def test_la_connexion_est_limitee_contre_la_force_brute(api, monkeypatch):
    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"connexion": "3/min"})
    utilisateur = UserFactory()

    codes = [_connexion(api, utilisateur, "faux").status_code for _ in range(5)]

    assert codes[:3] == [401, 401, 401] and codes[3:] == [429, 429]
    assert _connexion(api, utilisateur).status_code == 429  # même le bon mot de passe est bloqué
    cache.clear()
```

#### `apps/api/tests/test_auth_mfa.py`

*132 lignes* — Double authentification sur l'émission des jetons de l'API (ADMIN et DIRECTION).

```python
"""Double authentification sur l'émission des jetons de l'API (ADMIN et DIRECTION)."""

import pytest
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts import mfa
from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers_mfa import activer_mfa, code_frais
from apps.audit.models import AuditLog, StatutChoices

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "Test-Passw0rd!"


@pytest.fixture(autouse=True)
def mfa_imposee(settings):
    settings.MFA_ENFORCED = True
    cache.clear()


@pytest.fixture
def api():
    return APIClient()


def _connexion(api, utilisateur, **extra):
    return api.post(
        reverse("api:token"), {"username": utilisateur.username, "password": MOT_DE_PASSE, **extra}, format="json"
    )


def test_un_compte_sans_mfa_active_ne_recoit_pas_de_jeton(api):
    utilisateur = UserFactory(role=Role.DIRECTION)

    reponse = _connexion(api, utilisateur)

    assert reponse.status_code == 401 and reponse.data["code"] == "mfa_non_activee"
    assert "access" not in reponse.data


def test_sans_code_le_jeton_est_refuse(api):
    utilisateur = UserFactory(role=Role.DIRECTION)
    activer_mfa(utilisateur)

    reponse = _connexion(api, utilisateur)

    assert reponse.status_code == 401 and reponse.data["code"] == "mfa_requise"


def test_avec_un_bon_code_le_jeton_est_delivre(api):
    utilisateur = UserFactory(role=Role.ADMIN)
    activer_mfa(utilisateur)

    reponse = _connexion(api, utilisateur, otp=code_frais(utilisateur))

    assert reponse.status_code == 200 and set(reponse.data) == {"access", "refresh"}


def test_un_code_faux_est_refuse_et_inscrit_au_journal(api):
    utilisateur = UserFactory(role=Role.DIRECTION)
    activer_mfa(utilisateur)

    reponse = _connexion(api, utilisateur, otp="000000")

    assert reponse.status_code == 401 and reponse.data["code"] == "mfa_invalide"
    ligne = AuditLog.objects.get(entite="MFA", entite_id=utilisateur.pk, statut=StatutChoices.FAILED)
    assert ligne.nouvelle_valeur == {"evenement": "api_code_refuse"}


def test_un_code_ne_sert_qu_une_fois_sur_l_api(api):
    utilisateur = UserFactory(role=Role.DIRECTION)
    activer_mfa(utilisateur)
    code = code_frais(utilisateur)

    assert _connexion(api, utilisateur, otp=code).status_code == 200
    assert _connexion(api, utilisateur, otp=code).status_code == 401


def test_un_code_de_secours_fonctionne_une_seule_fois(api):
    utilisateur = UserFactory(role=Role.DIRECTION)
    _, codes = activer_mfa(utilisateur)

    assert _connexion(api, utilisateur, otp=codes[0]).status_code == 200
    assert _connexion(api, utilisateur, otp=codes[0]).status_code == 401
    assert mfa.codes_secours_restants(utilisateur) == 9


def test_apres_cinq_codes_faux_la_connexion_est_limitee(api):
    utilisateur = UserFactory(role=Role.DIRECTION)
    activer_mfa(utilisateur)
    for _ in range(5):
        _connexion(api, utilisateur, otp="000000")

    reponse = _connexion(api, utilisateur, otp=code_frais(utilisateur))

    assert reponse.status_code == 429


def test_un_mauvais_mot_de_passe_reste_refuse_avant_tout_controle_mfa(api):
    utilisateur = UserFactory(role=Role.DIRECTION)
    activer_mfa(utilisateur)

    reponse = api.post(
        reverse("api:token"),
        {"username": utilisateur.username, "password": "faux", "otp": code_frais(utilisateur)},
        format="json",
    )

    assert reponse.status_code == 401 and reponse.data.get("code") != "mfa_requise"


@pytest.mark.parametrize("role", [Role.RH, Role.CHARGE_CLIENTELE, Role.PARCAUTO, Role.FINANCES, Role.CHAUFFEUR])
def test_les_autres_roles_n_ont_pas_besoin_de_code(api, role):
    assert _connexion(api, UserFactory(role=role)).status_code == 200


def test_le_champ_otp_est_documente_dans_le_schema(api):
    admin = UserFactory(role=Role.ADMIN, is_superuser=True)
    activer_mfa(admin)
    from django.test import Client

    web = Client()
    web.force_login(admin)
    web.post(reverse("accounts:mfa_verifier"), {"code": code_frais(admin)})

    schema = web.get("/api/v1/schema/?format=json")

    assert schema.status_code == 200 and '"otp"' in schema.content.decode()
```

#### `apps/api/tests/test_v1.py`

*278 lignes* — API bureau /api/v1 : droits par rôle, pagination, filtres, champs exposés, documentation.

```python
"""API bureau /api/v1 : droits par rôle, pagination, filtres, champs exposés, documentation."""

from datetime import date
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.test import Client as HttpClient
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services as billing
from apps.billing.models import ModePaiement
from apps.billing.tests.helpers import brouillon, emise
from apps.billing.tests.helpers import finances as compte_finances
from apps.customers.tests.factories import ClientFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.missions.models import StatutMission
from apps.missions.tests.factories import MissionFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _vider_le_cache():
    cache.clear()


def _api(role=Role.ADMIN):
    client = APIClient()
    client.force_authenticate(UserFactory(role=role))
    return client


RESSOURCES = {
    "api:mission-list": {Role.ADMIN, Role.DIRECTION, Role.CHARGE_CLIENTELE},
    "api:camion-list": {Role.ADMIN, Role.DIRECTION, Role.PARCAUTO},
    "api:chauffeur-list": {Role.ADMIN, Role.DIRECTION, Role.RH},
    "api:client-list": {Role.ADMIN, Role.DIRECTION, Role.CHARGE_CLIENTELE},
    "api:facture-list": {Role.ADMIN, Role.DIRECTION, Role.FINANCES},
}


@pytest.mark.parametrize("nom", list(RESSOURCES))
@pytest.mark.parametrize("role", list(Role.values))
def test_chaque_ressource_suit_les_droits_de_l_ecran_correspondant(nom, role):
    reponse = _api(role).get(reverse(nom))

    assert reponse.status_code == (200 if role in RESSOURCES[nom] else 403), (nom, role)


@pytest.mark.parametrize("nom", list(RESSOURCES))
def test_sans_authentification_l_acces_est_refuse(nom):
    assert APIClient().get(reverse(nom)).status_code == 401


def test_un_vrai_jeton_jwt_ouvre_l_api():
    compte = UserFactory(role=Role.DIRECTION)
    client = APIClient()

    reponse = client.get(
        reverse("api:mission-list"), HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(compte)}"
    )

    assert reponse.status_code == 200


def test_l_api_est_en_lecture_seule():
    api = _api(Role.ADMIN)
    mission = MissionFactory()

    assert api.post(reverse("api:mission-list"), {}, format="json").status_code == 405
    assert api.put(reverse("api:mission-detail", args=[mission.pk]), {}, format="json").status_code == 405
    assert api.delete(reverse("api:mission-detail", args=[mission.pk])).status_code == 405


# --- missions ---


def test_une_mission_n_expose_jamais_ses_codes_secrets():
    mission = MissionFactory(code_expediteur="ABCD2345", code_destinataire="WXYZ6789")
    api = _api(Role.ADMIN)

    detail = api.get(reverse("api:mission-detail", args=[mission.pk]))
    liste = api.get(reverse("api:mission-list"))

    for reponse in (detail, liste):
        texte = reponse.content.decode()
        assert "ABCD2345" not in texte and "WXYZ6789" not in texte
        assert "code_expediteur" not in texte and "code_destinataire" not in texte


def test_le_detail_d_une_mission_donne_les_libelles():
    mission = MissionFactory(
        client=ClientFactory(raison_sociale="Cimaf CI"), statut=StatutMission.AFFECTEE,
        vehicule=VehiculeFactory(immatriculation="1234 AB 01"),
        chauffeur=ChauffeurFactory(),
    )

    donnees = _api(Role.DIRECTION).get(reverse("api:mission-detail", args=[mission.pk])).data

    assert donnees["numero"] == mission.numero and donnees["client"] == "Cimaf CI"
    assert donnees["vehicule"] == "1234 AB 01" and donnees["statut_libelle"] == "Affectée"
    assert donnees["chauffeur"] == f"{mission.chauffeur.personnel.prenom} {mission.chauffeur.personnel.nom}"


def test_les_missions_sont_paginees_par_20():
    for _ in range(25):
        MissionFactory()
    api = _api(Role.ADMIN)

    premiere = api.get(reverse("api:mission-list"))
    seconde = api.get(reverse("api:mission-list"), {"page": 2})

    assert premiere.data["count"] == 25 and len(premiere.data["results"]) == 20
    assert len(seconde.data["results"]) == 5 and premiere.data["next"] and seconde.data["previous"]


def test_les_missions_se_filtrent():
    cimaf = ClientFactory(raison_sociale="Cimaf Côte d'Ivoire")
    a = MissionFactory(client=cimaf, statut=StatutMission.PLANIFIEE, date_depart_prevue=date(2026, 10, 5))
    b = MissionFactory(statut=StatutMission.BROUILLON, date_depart_prevue=date(2026, 12, 1))
    api = _api(Role.ADMIN)
    url = reverse("api:mission-list")

    def numeros(**params):
        return {m["id"] for m in api.get(url, params).data["results"]}

    assert numeros(q="CIMAF") == {a.pk}  # accents et casse ignorés, comme à l'écran
    assert numeros(statut="PLANIFIEE") == {a.pk}
    assert numeros(client=cimaf.pk) == {a.pk}
    assert numeros(depart_apres="2026-11-01") == {b.pk}
    assert numeros(depart_avant="2026-10-31") == {a.pk}
    assert api.get(url, {"statut": "N_IMPORTE_QUOI"}).status_code == 400


def test_la_liste_des_missions_est_a_requetes_constantes(django_assert_max_num_queries):
    for _ in range(15):
        MissionFactory(vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory(), statut=StatutMission.AFFECTEE)
    api = _api(Role.ADMIN)

    with django_assert_max_num_queries(6):
        assert api.get(reverse("api:mission-list")).status_code == 200


# --- camions, chauffeurs, clients ---


def test_camions_filtres_par_statut_et_texte():
    a = VehiculeFactory(immatriculation="1111 AA 01", statut="DISPONIBLE", marque="Renault")
    VehiculeFactory(immatriculation="2222 BB 01", statut="EN_MISSION", marque="Volvo")
    api = _api(Role.PARCAUTO)
    url = reverse("api:camion-list")

    assert [v["id"] for v in api.get(url, {"statut": "DISPONIBLE"}).data["results"]] == [a.pk]
    assert [v["id"] for v in api.get(url, {"q": "renault"}).data["results"]] == [a.pk]
    assert api.get(reverse("api:camion-detail", args=[a.pk])).data["immatriculation"] == "1111 AA 01"


def test_chauffeurs_avec_leur_identite_et_recherche_sans_accent():
    fiche = ChauffeurFactory(personnel__nom="Traoré", personnel__prenom="Moussa")
    ChauffeurFactory(personnel__nom="Bamba")
    api = _api(Role.RH)

    resultats = api.get(reverse("api:chauffeur-list"), {"q": "traore"}).data["results"]

    assert [c["id"] for c in resultats] == [fiche.pk]
    assert resultats[0]["nom"] == "Traoré" and resultats[0]["matricule"] == fiche.personnel.matricule


def test_clients_filtre_exonere_et_charge_clientele():
    normal = ClientFactory(raison_sociale="Normal")
    exonere = ClientFactory(raison_sociale="Exonéré", taux_tva=Decimal("0"), motif_exoneration="ONG")
    api = _api(Role.CHARGE_CLIENTELE)
    url = reverse("api:client-list")

    assert [c["id"] for c in api.get(url, {"exonere": "true"}).data["results"]] == [exonere.pk]
    assert [c["id"] for c in api.get(url, {"exonere": "false"}).data["results"]] == [normal.pk]
    assert {c["raison_sociale"] for c in api.get(url).data["results"]} == {"Normal", "Exonéré"}
    assert api.get(url).data["results"][0]["delai_paiement_jours"] == 30


# --- factures ---


def test_facture_avec_reste_a_recouvrer_et_lignes_au_detail():
    facture = emise(prix="1000000", aujourd_hui=date(2026, 7, 1))
    billing.enregistrer_reglement(
        facture, compte_finances(), montant=Decimal("400000"), mode=ModePaiement.WAVE,
        date_reglement=date(2026, 7, 5),
    )
    api = _api(Role.FINANCES)

    liste = api.get(reverse("api:facture-list")).data["results"][0]
    detail = api.get(reverse("api:facture-detail", args=[facture.pk])).data

    assert liste["numero"] == facture.numero and "lignes" not in liste
    assert Decimal(detail["montant_ttc"]) == Decimal("1180000")
    assert Decimal(detail["montant_regle"]) == Decimal("400000")
    assert Decimal(detail["reste_a_recouvrer"]) == Decimal("780000")
    assert detail["echue"] is True and detail["statut"] == "PARTIELLEMENT_PAYEE"
    assert len(detail["lignes"]) == 1 and Decimal(detail["lignes"][0]["montant_ht"]) == Decimal("1000000")


def test_factures_filtrees_par_statut_echeance_et_texte():
    echue = emise(aujourd_hui=date(2026, 7, 1))
    a_jour = emise(aujourd_hui=date.today())
    brouillon()
    api = _api(Role.DIRECTION)
    url = reverse("api:facture-list")

    assert [f["id"] for f in api.get(url, {"echues": "true"}).data["results"]] == [echue.pk]
    assert {f["id"] for f in api.get(url, {"statut": "EMISE"}).data["results"]} == {echue.pk, a_jour.pk}
    assert [f["id"] for f in api.get(url, {"q": a_jour.numero.lower()}).data["results"]] == [a_jour.pk]
    assert len(api.get(url, {"echues": "false"}).data["results"]) == 3


def test_la_liste_des_factures_est_a_requetes_constantes(django_assert_max_num_queries):
    for _ in range(10):
        emise()
    api = _api(Role.FINANCES)

    with django_assert_max_num_queries(6):
        assert api.get(reverse("api:facture-list")).status_code == 200


# --- documentation ---


def test_la_documentation_est_reservee_a_l_admin_et_a_la_direction_connectes():
    def acces(role=None):
        http = HttpClient()
        if role:
            http.force_login(UserFactory(role=role))
        return http.get(reverse("api:schema")).status_code

    assert acces(Role.ADMIN) == 200 and acces(Role.DIRECTION) == 200
    assert acces(Role.CHAUFFEUR) == 403 and acces(Role.FINANCES) == 403
    assert acces() == 403


def test_le_schema_openapi_decrit_les_ressources_sans_erreur():
    http = HttpClient()
    http.force_login(UserFactory(role=Role.ADMIN))

    reponse = http.get(reverse("api:schema"), {"format": "json"})

    chemins = reponse.json()["paths"]
    for attendu in ("/api/v1/missions/", "/api/v1/factures/{id}/", "/api/v1/auth/token/", "/api/v1/moi/"):
        assert attendu in chemins, attendu
    assert "code_expediteur" not in reponse.content.decode()
    assert http.get(reverse("api:docs")).status_code == 200


# --- traduction des erreurs métier ---


def test_les_erreurs_metier_deviennent_des_reponses_http_claires():
    from rest_framework.response import Response  # noqa: F401

    from apps.api.exceptions import gestionnaire_erreurs
    from apps.billing.exceptions import ActionFactureNonAutorisee
    from apps.fuel.exceptions import SaisieSuspecte
    from apps.missions.exceptions import CodeInvalide

    refus = gestionnaire_erreurs(CodeInvalide("Code incorrect."), {})
    droit = gestionnaire_erreurs(ActionFactureNonAutorisee("Interdit."), {})
    suspecte = gestionnaire_erreurs(SaisieSuspecte(Decimal("70.5"), Decimal("51"), Decimal("30")), {})

    assert (refus.status_code, refus.data) == (400, {"code": "code_invalide", "detail": "Code incorrect."})
    assert droit.status_code == 403 and droit.data["code"] == "action_facture_non_autorisee"
    assert suspecte.status_code == 409 and suspecte.data["consommation"] == "51"
    assert "confirmer=true" in suspecte.data["confirmer"]
    assert gestionnaire_erreurs(ValueError("autre"), {}) is None  # les autres erreurs restent gérées par DRF
```

#### `apps/core/tests/test_csp.py`

*199 lignes* — Politique de sécurité du contenu (CSP), ressources locales et absence de code écrit dans les pages.

```python
"""Politique de sécurité du contenu (CSP), ressources locales et absence de code écrit dans les pages."""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.staticfiles import finders
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.mobile_api.tests.helpers import chauffeur_avec_compte

pytestmark = pytest.mark.django_db

RACINE = Path(settings.BASE_DIR)
GABARITS = [
    *RACINE.glob("templates/**/*.html"),
    *RACINE.glob("apps/**/templates/**/*.html"),
    *RACINE.glob("apps/**/templates/**/*.js"),
]


# --- en-têtes ---


def test_la_csp_est_posee_sur_les_pages(client):
    reponse = client.get(reverse("accounts:login"))

    csp = reponse["Content-Security-Policy"]
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
    assert "base-uri 'self'" in csp and "form-action 'self'" in csp


def test_la_csp_n_autorise_aucun_hote_externe_ni_script_en_ligne(client):
    csp = client.get(reverse("accounts:login"))["Content-Security-Policy"]

    assert "http" not in csp and "*" not in csp
    script = next(d for d in csp.split("; ") if d.startswith("script-src"))
    assert "'unsafe-inline'" not in script  # seul 'unsafe-eval' est toléré (Alpine.js)


def test_la_documentation_de_l_api_a_sa_propre_politique(client):
    from apps.accounts.tests.helpers_mfa import activer_mfa  # noqa: F401

    client.force_login(UserFactory(role=Role.DIRECTION))

    csp = client.get("/api/v1/docs/")["Content-Security-Policy"]

    assert "script-src 'self' 'unsafe-inline'" in csp and "http" not in csp


def test_les_pages_d_erreur_ont_aussi_la_csp(client):
    client.force_login(UserFactory(role=Role.RH))

    reponse = client.get("/facturation/")  # 403

    assert reponse.status_code == 403 and "Content-Security-Policy" in reponse


def test_le_mode_observation_change_le_nom_de_l_en_tete(client, settings):
    settings.CSP_REPORT_ONLY = True

    reponse = client.get(reverse("accounts:login"))

    assert "Content-Security-Policy-Report-Only" in reponse and "Content-Security-Policy" not in reponse


def test_la_camera_reste_permise_pour_le_scan_des_qr(client):
    politique = client.get(reverse("accounts:login"))["Permissions-Policy"]

    assert "camera=(self)" in politique and "microphone=()" in politique and "geolocation=()" in politique


# --- les pages ne contiennent pas de code et ne chargent rien d'externe ---

PAGES = ["/", "/missions/", "/clients/", "/flotte/", "/rh/personnel/", "/rh/conges/", "/chauffeurs/",
         "/garage/", "/garage/incidents/", "/carburant/", "/stock/", "/facturation/", "/finances/", "/notifications/"]


def _pages_rendues(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    for chemin in PAGES:
        reponse = client.get(chemin)
        assert reponse.status_code == 200, chemin
        yield chemin, reponse.content.decode()
    fiche, compte = chauffeur_avec_compte()
    client.force_login(compte)
    for chemin in ("/chauffeur/", "/chauffeur/plein/", "/chauffeur/incident/", "/chauffeur/hors-ligne/"):
        reponse = client.get(chemin)
        assert reponse.status_code == 200, chemin
        yield chemin, reponse.content.decode()
    client.logout()
    yield "/connexion/", client.get("/connexion/").content.decode()


def test_aucune_page_ne_charge_de_ressource_externe(client):
    for chemin, html in _pages_rendues(client):
        externes = re.findall(r"""(?:src|href|action)=["'](https?://[^"']+)""", html)
        assert not externes, (chemin, externes)
        assert "cdn." not in html, chemin


def test_aucune_page_rendue_ne_contient_de_script_ou_de_gestionnaire_en_ligne(client):
    for chemin, html in _pages_rendues(client):
        en_ligne = [
            m for m in re.findall(r"<script\b([^>]*)>", html) if "src=" not in m and "application/json" not in m
        ]
        assert not en_ligne, (chemin, en_ligne)
        assert not re.search(r"""\son[a-z]+\s*=\s*["']""", html), chemin
        assert "javascript:" not in html, chemin


@pytest.mark.parametrize("gabarit", GABARITS, ids=lambda p: str(p.relative_to(RACINE)))
def test_les_gabarits_n_ecrivent_ni_script_ni_gestionnaire_en_ligne(gabarit):
    texte = gabarit.read_text(encoding="utf-8")
    if gabarit.suffix == ".js":  # sw.js : servi comme fichier, pas inclus dans une page
        return
    sans_commentaires = re.sub(r"\{% comment %\}.*?\{% endcomment %\}|\{#.*?#\}", "", texte, flags=re.S)
    assert not [
        m for m in re.findall(r"<script\b([^>]*)>", sans_commentaires) if "src=" not in m and "application/json" not in m
    ], "script écrit dans la page"
    assert not re.search(r"""\son(?:click|submit|change|load|error|input|focus|blur|keyup|keydown)\s*=""", sans_commentaires), (
        "gestionnaire d'événement écrit dans la page (utiliser data-confirm / data-imprimer)"
    )
    assert "javascript:" not in sans_commentaires
    assert not re.search(r"(?:cdn\.|cdnjs\.|jsdelivr|googleapis|unpkg)", sans_commentaires, re.I), "ressource externe"


# --- ressources locales ---


@pytest.mark.parametrize("chemin", [
    "css/tailwind.css", "js/app.js", "js/sw-register.js", "js/scanner.js", "vendor/alpine/alpine.min.js",
    "vendor/fontawesome/css/all.min.css", "vendor/fontawesome/webfonts/fa-solid-900.woff2",
    "vendor/fontawesome/webfonts/fa-regular-400.woff2", "img/logo-emblem.jpg", "img/favicon.png",
])
def test_les_ressources_locales_existent(chemin):
    assert finders.find(chemin), chemin


def test_le_css_compile_contient_les_couleurs_de_la_marque():
    css = Path(finders.find("css/tailwind.css")).read_text(encoding="utf-8")

    assert "#8b0319" in css.lower() and "#f28a14" in css.lower()  # marque-700 et accent-500
    assert ".bg-marque-600" in css and ".bg-accent-500" in css


def test_les_classes_tailwind_des_gabarits_sont_dans_le_css_compile():
    """Filet contre un css compilé périmé : chaque classe simple écrite dans un gabarit doit exister."""
    css = Path(finders.find("css/tailwind.css")).read_text(encoding="utf-8")
    manquantes = set()
    motif_classe = re.compile(r'class="([^"{}%]*)"')
    for gabarit in GABARITS:
        if gabarit.suffix != ".html":
            continue
        for attribut in motif_classe.findall(gabarit.read_text(encoding="utf-8")):
            for classe in attribut.split():
                if re.fullmatch(r"(?:hover:|focus:|sm:|lg:|md:)*(?:bg|text|border|ring)-(?:marque|accent)-\d{2,3}", classe):
                    base = classe.replace(":", r"\:")
                    if f".{base}" not in css and base.split("\\:")[-1] not in css:
                        manquantes.add(classe)
    assert not manquantes, sorted(manquantes)[:10]


def test_app_js_gere_la_confirmation_et_l_impression():
    js = Path(finders.find("js/app.js")).read_text(encoding="utf-8")

    assert "dataset.confirm" in js and "data-imprimer" in js and "window.print" in js


def test_le_service_worker_est_enregistre_sans_code_en_ligne(client):
    fiche, compte = chauffeur_avec_compte()
    client.force_login(compte)

    html = client.get("/chauffeur/").content.decode()

    assert 'src="/static/js/sw-register.js"' in html and 'data-sw="/chauffeur/sw.js"' in html


def test_la_page_hors_connexion_reste_autonome_sans_script(client):
    html = client.get(reverse("chauffeur:hors_ligne")).content.decode()

    assert "<script" not in html and 'href="/chauffeur/"' in html


def test_les_formulaires_a_confirmation_utilisent_data_confirm(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    from apps.missions.tests.factories import MissionFactory
    from apps.missions.models import StatutMission
    from apps.fleet.tests.factories import VehiculeFactory

    mission = MissionFactory(statut=StatutMission.AFFECTEE, vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory())

    html = client.get(reverse("missions:detail", args=[mission.pk])).content.decode()

    assert 'data-confirm="Démarrer la mission ?' in html and "onsubmit" not in html
```

#### `apps/mobile_api/tests/test_api.py`

*342 lignes* — API mobile /api/v1/mobile/ : accès, isolement entre chauffeurs, secrets, cycle, erreurs HTTP.

```python
"""API mobile /api/v1/mobile/ : accès, isolement entre chauffeurs, secrets, cycle, erreurs HTTP."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.garage.models import Incident
from apps.missions.models import StatutMission

from .helpers import CODE_DESTINATAIRE, CODE_EXPEDITEUR, checklist_ok, chauffeur_avec_compte, mission_de

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _vider_le_cache():
    cache.clear()


def _api(compte):
    client = APIClient()
    client.force_authenticate(compte)
    return client


@pytest.fixture
def chauffeur():
    fiche, compte = chauffeur_avec_compte()
    return fiche, compte, _api(compte)


# --- accès ---


URLS_SANS_ARGUMENT = [
    "api:mobile:missions", "api:mobile:pleins", "api:mobile:incidents",
]


@pytest.mark.parametrize("nom", URLS_SANS_ARGUMENT)
def test_les_ressources_mobiles_exigent_un_compte_chauffeur(nom):
    assert APIClient().get(reverse(nom)).status_code == 401
    for role in (Role.ADMIN, Role.DIRECTION, Role.PARCAUTO, Role.RH, Role.FINANCES, Role.CHARGE_CLIENTELE):
        assert _api(UserFactory(role=role)).get(reverse(nom)).status_code == 403, (nom, role)


def test_un_compte_chauffeur_sans_fiche_du_personnel_est_refuse():
    orphelin = UserFactory(role=Role.CHAUFFEUR)

    assert _api(orphelin).get(reverse("api:mobile:missions")).status_code == 403


def test_un_vrai_jeton_jwt_de_chauffeur_ouvre_l_api_mobile():
    fiche, compte = chauffeur_avec_compte()
    mission_de(fiche)

    reponse = APIClient().get(
        reverse("api:mobile:missions"), HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(compte)}"
    )

    assert reponse.status_code == 200 and len(reponse.data) == 1


# --- missions ---


def test_le_chauffeur_ne_voit_que_ses_missions(chauffeur):
    fiche, _, api = chauffeur
    a_moi = mission_de(fiche)
    mission_de(ChauffeurFactory())

    reponse = api.get(reverse("api:mobile:missions"))

    assert [m["id"] for m in reponse.data] == [a_moi.pk]
    assert reponse.data[0]["actions"]["demarrer"] is True and reponse.data[0]["checklist_faite"] is False


def test_les_codes_secrets_et_le_prix_ne_sont_jamais_exposes(chauffeur):
    fiche, _, api = chauffeur
    mission = mission_de(fiche)

    for reponse in (api.get(reverse("api:mobile:missions")), api.get(reverse("api:mobile:mission", args=[mission.pk]))):
        texte = reponse.content.decode()
        assert CODE_EXPEDITEUR not in texte and CODE_DESTINATAIRE not in texte
        assert "code_expediteur" not in texte and "prix_convenu" not in texte and "850000" not in texte


def test_la_mission_d_un_autre_chauffeur_est_un_404_partout(chauffeur):
    _, _, api = chauffeur
    autre = mission_de(ChauffeurFactory())

    assert api.get(reverse("api:mobile:mission", args=[autre.pk])).status_code == 404
    for nom, corps in (
        ("demarrer", {}), ("recuperation", {"code": CODE_EXPEDITEUR}),
        ("livraison", {"code": CODE_DESTINATAIRE, "km_arrivee": 999999}), ("checklist", {"points": []}),
    ):
        reponse = api.post(reverse(f"api:mobile:{nom}", args=[autre.pk]), corps, format="json")
        assert reponse.status_code == 404, nom
        assert reponse.data["code"] == "mission_introuvable"
    autre.refresh_from_db()
    assert autre.statut == StatutMission.AFFECTEE  # rien n'a bougé


def test_cycle_de_la_mission_par_l_api(chauffeur):
    fiche, _, api = chauffeur
    mission = mission_de(fiche)
    km_depart = mission.vehicule.kilometrage

    demarrage = api.post(reverse("api:mobile:demarrer", args=[mission.pk]))
    recuperation = api.post(
        reverse("api:mobile:recuperation", args=[mission.pk]), {"code": CODE_EXPEDITEUR}, format="json"
    )
    livraison = api.post(
        reverse("api:mobile:livraison", args=[mission.pk]),
        {"code": CODE_DESTINATAIRE, "km_arrivee": km_depart + 400}, format="json",
    )

    assert [demarrage.status_code, recuperation.status_code, livraison.status_code] == [200, 200, 200]
    assert demarrage.data["statut"] == "EN_COURS_DEPART"
    assert recuperation.data["statut"] == "EN_COURS_COLIS_RECUPERE"
    assert livraison.data["statut"] == "LIVREE" and livraison.data["km_arrivee"] == km_depart + 400
    assert livraison.data["actions"] == {
        "checklist": False, "demarrer": False, "recuperation": False, "livraison": False,
    }


def test_les_refus_metier_donnent_un_400_avec_un_code_lisible(chauffeur):
    fiche, _, api = chauffeur
    mission = mission_de(fiche)

    trop_tot = api.post(reverse("api:mobile:recuperation", args=[mission.pk]), {"code": CODE_EXPEDITEUR}, format="json")
    api.post(reverse("api:mobile:demarrer", args=[mission.pk]))
    faux = api.post(reverse("api:mobile:recuperation", args=[mission.pk]), {"code": "FAUX0000"}, format="json")
    deja = api.post(reverse("api:mobile:demarrer", args=[mission.pk]))

    assert trop_tot.status_code == 400 and trop_tot.data["code"] == "transition_mission_interdite"
    assert faux.status_code == 400 and faux.data["code"] == "code_invalide"
    assert deja.status_code == 400 and "detail" in deja.data


def test_donnees_mal_formees_donnent_un_400_de_validation(chauffeur):
    fiche, _, api = chauffeur
    mission = mission_de(fiche, StatutMission.EN_COURS_COLIS_RECUPERE)

    sans_code = api.post(reverse("api:mobile:livraison", args=[mission.pk]), {"km_arrivee": 100}, format="json")
    km_negatif = api.post(
        reverse("api:mobile:livraison", args=[mission.pk]), {"code": CODE_DESTINATAIRE, "km_arrivee": -5}, format="json"
    )

    assert sans_code.status_code == 400 and "code" in sans_code.data
    assert km_negatif.status_code == 400 and "km_arrivee" in km_negatif.data


# --- check-list ---


def test_checklist_par_l_api_puis_refus_du_doublon(chauffeur):
    fiche, _, api = chauffeur
    mission = mission_de(fiche)
    corps = {"points": checklist_ok(PNEUS="Usé"), "remarque": "À surveiller"}

    premiere = api.post(reverse("api:mobile:checklist", args=[mission.pk]), corps, format="json")
    seconde = api.post(reverse("api:mobile:checklist", args=[mission.pk]), corps, format="json")

    assert premiere.status_code == 201 and premiere.data["nb_anomalies"] == 1
    assert seconde.status_code == 400 and seconde.data["code"] == "checklist_deja_remplie"
    detail = api.get(reverse("api:mobile:mission", args=[mission.pk]))
    assert detail.data["checklist_faite"] is True and detail.data["actions"]["checklist"] is False


def test_checklist_incomplete_ou_ko_sans_remarque_refusee(chauffeur):
    fiche, _, api = chauffeur
    mission = mission_de(fiche)
    url = reverse("api:mobile:checklist", args=[mission.pk])

    incomplete = api.post(url, {"points": checklist_ok()[:3]}, format="json")
    ko_muet = api.post(url, {"points": [{**p, "remarque": ""} for p in checklist_ok(FREINS="x")]}, format="json")

    assert incomplete.status_code == 400 and incomplete.data["code"] == "checklist_invalide"
    assert ko_muet.status_code == 400 and "Freins" in ko_muet.data["detail"]


# --- plein ---


def _plein_corps(**surcharges):
    corps = {"station": "Total Yopougon", "quantite_litres": "100.00", "prix_unitaire": "655",
             "km_compteur": 1000, "numero_ticket": "T-001"}
    corps.update(surcharges)
    return corps


def test_saisie_d_un_plein_par_l_api(chauffeur):
    fiche, _, api = chauffeur
    mission = mission_de(fiche)

    reponse = api.post(reverse("api:mobile:pleins"), _plein_corps(), format="json")

    assert reponse.status_code == 201
    assert reponse.data["vehicule"] == mission.vehicule.immatriculation and reponse.data["consommation"] is None
    assert [p["id"] for p in api.get(reverse("api:mobile:pleins")).data] == [reponse.data["id"]]


def test_un_plein_sans_camion_donne_un_400(chauffeur):
    _, _, api = chauffeur

    reponse = api.post(reverse("api:mobile:pleins"), _plein_corps(), format="json")

    assert reponse.status_code == 400 and reponse.data["code"] == "aucun_camion"


def test_plein_suspect_409_puis_confirmation(chauffeur):
    fiche, _, api = chauffeur
    mission_de(fiche)
    aujourd_hui = timezone.localdate()
    url = reverse("api:mobile:pleins")
    api.post(url, _plein_corps(numero_ticket="T-1", date_plein=str(aujourd_hui - timedelta(days=10))), format="json")
    for rang, km in enumerate((1400, 1800, 2200), start=2):
        api.post(url, _plein_corps(km_compteur=km, quantite_litres="120", numero_ticket=f"T-{rang}",
                                   date_plein=str(aujourd_hui - timedelta(days=10 - rang))), format="json")
    suspect = _plein_corps(km_compteur=2600, quantite_litres="300", numero_ticket="T-9")

    refuse = api.post(url, suspect, format="json")
    confirme = api.post(url, {**suspect, "confirmer": True}, format="json")

    assert refuse.status_code == 409 and refuse.data["code"] == "saisie_suspecte"
    assert Decimal(refuse.data["consommation"]) == Decimal("75.00") and "confirmer=true" in refuse.data["confirmer"]
    assert confirme.status_code == 201


def test_regles_du_plein_ticket_double_et_km_decroissant(chauffeur):
    fiche, _, api = chauffeur
    mission_de(fiche)
    url = reverse("api:mobile:pleins")
    api.post(url, _plein_corps(), format="json")

    double = api.post(url, _plein_corps(km_compteur=1500), format="json")
    recul = api.post(url, _plein_corps(km_compteur=900, numero_ticket="T-2"), format="json")

    assert double.status_code == 400 and double.data["code"] == "ticket_deja_enregistre"
    assert recul.status_code == 400 and recul.data["code"] == "kilometrage_invalide"


def test_plein_avec_donnees_invalides(chauffeur):
    fiche, _, api = chauffeur
    mission_de(fiche)

    reponse = api.post(reverse("api:mobile:pleins"), _plein_corps(quantite_litres="-3", station=""), format="json")

    assert reponse.status_code == 400 and {"quantite_litres", "station"} <= set(reponse.data)


def test_le_chauffeur_ne_declare_pas_de_plein_sur_le_camion_d_un_autre(chauffeur):
    fiche, _, api = chauffeur
    mission_de(fiche)
    etranger = VehiculeFactory()

    reponse = api.post(reverse("api:mobile:pleins"), _plein_corps(vehicule=etranger.pk), format="json")

    assert reponse.status_code == 400 and "n'est pas le vôtre" in reponse.data["detail"]


# --- incidents ---


def test_signalement_d_un_incident_par_l_api_et_liste(chauffeur):
    fiche, _, api = chauffeur
    mission = mission_de(fiche)

    reponse = api.post(
        reverse("api:mobile:incidents"),
        {"type_incident": "PANNE", "gravite": "GRAVE", "description": "Moteur qui chauffe",
         "lieu": "Km 120", "mission": mission.pk},
        format="json",
    )

    assert reponse.status_code == 201
    assert reponse.data["vehicule"] == mission.vehicule.immatriculation and reponse.data["statut"] == "SIGNALE"
    assert reponse.data["gravite_libelle"].startswith("Grave")
    assert [i["id"] for i in api.get(reverse("api:mobile:incidents")).data] == [reponse.data["id"]]
    assert Incident.objects.count() == 1


def test_incident_avec_donnees_invalides_ou_mission_etrangere(chauffeur):
    fiche, _, api = chauffeur
    autre = mission_de(ChauffeurFactory())
    url = reverse("api:mobile:incidents")

    mauvais_type = api.post(url, {"type_incident": "VOL", "gravite": "GRAVE", "description": "x"}, format="json")
    sans_description = api.post(url, {"type_incident": "PANNE", "gravite": "GRAVE", "description": ""}, format="json")
    mission_etrangere = api.post(
        url, {"type_incident": "PANNE", "gravite": "GRAVE", "description": "x", "mission": autre.pk}, format="json"
    )

    assert mauvais_type.status_code == 400 and "type_incident" in mauvais_type.data
    assert sans_description.status_code == 400
    assert mission_etrangere.status_code == 404 and not Incident.objects.exists()


def test_un_chauffeur_ne_voit_pas_les_incidents_d_un_autre(chauffeur):
    fiche, _, api = chauffeur
    VehiculeFactory(chauffeur_habituel=fiche)
    autre, compte_autre = chauffeur_avec_compte()
    VehiculeFactory(chauffeur_habituel=autre)
    _api(compte_autre).post(
        reverse("api:mobile:incidents"),
        {"type_incident": "AUTRE", "gravite": "FAIBLE", "description": "Chez l'autre"}, format="json",
    )

    assert api.get(reverse("api:mobile:incidents")).data == []


def test_la_liste_des_missions_mobiles_est_a_requetes_constantes(chauffeur, django_assert_max_num_queries):
    fiche, _, api = chauffeur
    for _ in range(10):
        mission_de(fiche)

    with django_assert_max_num_queries(30):
        assert len(api.get(reverse("api:mobile:missions")).data) == 10


def test_la_documentation_decrit_l_api_mobile():
    from django.test import Client

    http = Client()
    http.force_login(UserFactory(role=Role.ADMIN))

    chemins = http.get(reverse("api:schema"), {"format": "json"}).json()["paths"]

    for attendu in ("/api/v1/mobile/missions/", "/api/v1/mobile/missions/{id}/demarrer/",
                    "/api/v1/mobile/pleins/", "/api/v1/mobile/incidents/"):
        assert attendu in chemins, attendu
```

Ce chapitre présente aussi plusieurs fichiers de tests qui ont besoin de l'API : les tests de la
**double authentification** et de l'**anti force brute** (`accounts/tests/test_mfa.py`,
`test_securite_connexion.py`), ceux de la **politique de sécurité du contenu** (`core/tests/test_csp.py`) et ceux de
l'**API mobile** (`mobile_api/tests/test_api.py`).

## Étape 4 — Brancher dans les réglages et les adresses

#### `config/settings/base.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/settings/base.py (avant)
+++ config/settings/base.py (après)
@@ -64,4 +64,5 @@
     "apps.notifications",
     "apps.dashboard",
+    "apps.api",
     "apps.mobile_api",
 ]
```

#### `config/urls.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/urls.py (avant)
+++ config/urls.py (après)
@@ -28,4 +28,5 @@
     path("finances/", include("apps.finance.urls")),
     path("notifications/", include("apps.notifications.urls")),
+    path("api/v1/", include("apps.api.urls")),
     path("chauffeur/", include("apps.mobile_api.urls_web")),
     path("admin/", admin.site.urls),
```

Les réglages `REST_FRAMEWORK`, `SIMPLE_JWT`, `SPECTACULAR_SETTINGS` et `CORS_…` étaient déjà écrits au chapitre 1 ;
il ne restait qu'à **déclarer l'app** et à **monter** les adresses.

```bash
cd frontend
npm run build:css
cd ..
```

(La compilation finale est **nécessaire** : un test du chapitre vérifie que les couleurs de la marque figurent dans
le fichier de styles.)

## Vérifier le chapitre

```bash
python manage.py check
```

```bash
python -m pytest apps/accounts/tests/test_mfa.py apps/accounts/tests/test_securite_connexion.py apps/api/tests/test_auth.py apps/api/tests/test_auth_mfa.py apps/api/tests/test_v1.py apps/core/tests/test_csp.py apps/mobile_api/tests/test_api.py -q --no-cov
```

**Résultat attendu :** `304 passed` (pour les 7 fichier(s) de tests présentés dans ce chapitre).

**Essayez l'API à la main** (avec `python manage.py runserver` dans un autre terminal). Le compte `demo_chauffeur`
n'est pas soumis à la MFA :

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/token/ -H "Content-Type: application/json" -d '{"username": "demo_chauffeur", "password": "VOTRE_MOT_DE_PASSE"}'
```

**Résultat attendu :** un JSON `{"refresh": "…", "access": "…"}`. Puis (en remplaçant `<ACCES>`) :

```bash
curl -s http://localhost:8000/api/v1/moi/ -H "Authorization: Bearer <ACCES>"
curl -s http://localhost:8000/api/v1/mobile/missions/ -H "Authorization: Bearer <ACCES>"
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/v1/missions/ -H "Authorization: Bearer <ACCES>"
```

**Résultats attendus :** le profil (`role: CHAUFFEUR`), la liste des missions du chauffeur, puis **`403`** : un chauffeur n'a
pas accès aux missions du bureau.

Avec un compte **ADMIN** ou **DIRECTION** : sans `otp`, la même requête donne `401` avec
`"code": "mfa_requise"` ; avec `"otp": "123456"` (le code de votre application) elle donne les jetons.

**La documentation :** ouvrez **http://localhost:8000/api/v1/docs/** connecté en tant que `demo_direction` (avec sa
double authentification) : l'interface Swagger liste toutes les routes, et **vous pouvez les essayer** depuis la
page.

## Ce qu'il faut retenir

- Une API **n'a pas ses propres règles** : elle expose les **services** existants avec les **mêmes rôles**.
- On **liste les champs** exposés ; on n'expose jamais un modèle entier.
- Une **authentification forte** (MFA) doit aussi protéger l'API, pas seulement les écrans.
- La documentation se **génère** : elle ne peut pas mentir sur le code.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 28 : API REST (JWT + MFA, ressources en lecture seule, documentation)"
```

---

[← Chapitre 27](27-mobile.md) · [Sommaire](README.md) · [Chapitre 29 →](29-finalisation.md)
