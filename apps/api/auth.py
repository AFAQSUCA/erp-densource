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
