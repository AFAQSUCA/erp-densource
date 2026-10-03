from django.urls import path

from . import views, views_mfa, views_utilisateurs

app_name = "accounts"

urlpatterns = [
    path("connexion/", views.ConnexionView.as_view(), name="login"),
    path("deconnexion/", views.DeconnexionView.as_view(), name="logout"),
    # Double authentification (ADMIN et DIRECTION) : pages ouvertes avant la vérification.
    path("mfa/verifier/", views_mfa.MFAVerifierView.as_view(), name="mfa_verifier"),
    path("mfa/activer/", views_mfa.MFAActiverView.as_view(), name="mfa_activer"),
    path("mfa/qr/", views_mfa.MFAQrView.as_view(), name="mfa_qr"),
    path("mfa/codes/", views_mfa.MFACodesView.as_view(), name="mfa_codes"),
    # Gestion des comptes (ADMIN).
    path("utilisateurs/", views_utilisateurs.UtilisateurListView.as_view(), name="utilisateurs"),
    path("utilisateurs/nouveau/", views_utilisateurs.UtilisateurCreateView.as_view(), name="utilisateur_nouveau"),
    path("utilisateurs/<int:pk>/modifier/", views_utilisateurs.UtilisateurUpdateView.as_view(), name="utilisateur_modifier"),
    path(
        "utilisateurs/<int:pk>/activation/",
        views_utilisateurs.UtilisateurActivationView.as_view(),
        name="utilisateur_activation",
    ),
    # Mot de passe oublié : ouvert à tous, avant connexion.
    path("mot-de-passe/", views.ReinitialiserMotDePasseView.as_view(), name="password_reset"),
    path(
        "mot-de-passe/envoye/",
        views.ReinitialiserMotDePasseEnvoyeView.as_view(),
        name="password_reset_done",
    ),
    path(
        "mot-de-passe/confirmer/<uidb64>/<token>/",
        views.ReinitialiserMotDePasseConfirmerView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "mot-de-passe/termine/",
        views.ReinitialiserMotDePasseTermineeView.as_view(),
        name="password_reset_complete",
    ),
]
