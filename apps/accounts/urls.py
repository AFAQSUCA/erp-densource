from django.urls import path

from . import views, views_mfa

app_name = "accounts"

urlpatterns = [
    path("connexion/", views.ConnexionView.as_view(), name="login"),
    path("deconnexion/", views.DeconnexionView.as_view(), name="logout"),
    # Double authentification (ADMIN et DIRECTION) : pages ouvertes avant la vérification.
    path("mfa/verifier/", views_mfa.MFAVerifierView.as_view(), name="mfa_verifier"),
    path("mfa/activer/", views_mfa.MFAActiverView.as_view(), name="mfa_activer"),
    path("mfa/qr/", views_mfa.MFAQrView.as_view(), name="mfa_qr"),
    path("mfa/codes/", views_mfa.MFACodesView.as_view(), name="mfa_codes"),
]
