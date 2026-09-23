"""Mot de passe oublié : les 4 étapes, sans jamais révéler si une adresse a un compte."""

import re

import pytest
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.accounts.models import Role, User
from apps.audit.models import ActionChoices, AuditLog

from .factories import UserFactory

pytestmark = pytest.mark.django_db

NOUVEAU_MOT_DE_PASSE = "Un-Nouveau-Mot-2-Passe"


def _lien_confirmation(compte):
    """Construit l'URL de confirmation directement (sans dépendre du format de l'e-mail)."""
    uid = urlsafe_base64_encode(force_bytes(compte.pk))
    token = default_token_generator.make_token(compte)
    return reverse("accounts:password_reset_confirm", kwargs={"uidb64": uid, "token": token})


def _page_confirmation(client, compte):
    """Ouvre le lien (GET) : Django range le jeton en session et redirige vers l'URL réellement
    soumise par le formulaire (le jeton n'apparaît plus dans l'adresse). Un navigateur fait la
    même chose avant de pouvoir poster le nouveau mot de passe."""
    reponse = client.get(_lien_confirmation(compte), follow=True)
    return reponse.redirect_chain[-1][0]


# --- demande ---


def test_la_page_de_demande_est_ouverte_a_tous(client):
    assert client.get(reverse("accounts:password_reset")).status_code == 200


def test_une_adresse_existante_recoit_un_e_mail(client):
    UserFactory(role=Role.RH, email="marie@densourcegroup.ci")

    reponse = client.post(
        reverse("accounts:password_reset"), {"email": "marie@densourcegroup.ci"}, follow=True
    )

    assert reponse.redirect_chain[-1][0] == reverse("accounts:password_reset_done")
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["marie@densourcegroup.ci"]
    assert "mot de passe" in mail.outbox[0].subject.lower()


def test_une_adresse_inconnue_ne_revele_rien(client):
    reponse = client.post(
        reverse("accounts:password_reset"), {"email": "personne@densourcegroup.ci"}, follow=True
    )

    assert reponse.redirect_chain[-1][0] == reverse("accounts:password_reset_done")
    assert len(mail.outbox) == 0


def test_l_e_mail_contient_un_lien_qui_fonctionne(client):
    UserFactory(role=Role.RH, email="marie@densourcegroup.ci", username="marie")

    client.post(reverse("accounts:password_reset"), {"email": "marie@densourcegroup.ci"})

    lien = re.search(r"https?://\S+/mot-de-passe/confirmer/\S+/", mail.outbox[0].body)
    assert lien is not None
    chemin = lien.group(0).split("://", 1)[1].split("/", 1)[1]
    reponse = client.get("/" + chemin, follow=True)
    assert reponse.status_code == 200
    assert reponse.context["validlink"] is True


# --- confirmation ---


def test_un_nouveau_mot_de_passe_valide_fonctionne_ensuite(client):
    compte = UserFactory(role=Role.RH)
    page = _page_confirmation(client, compte)

    reponse = client.post(
        page,
        {"new_password1": NOUVEAU_MOT_DE_PASSE, "new_password2": NOUVEAU_MOT_DE_PASSE},
        follow=True,
    )

    compte.refresh_from_db()
    assert reponse.redirect_chain[-1][0] == reverse("accounts:password_reset_complete")
    assert compte.check_password(NOUVEAU_MOT_DE_PASSE)


def test_deux_mots_de_passe_differents_sont_refuses(client):
    compte = UserFactory(role=Role.RH)
    page = _page_confirmation(client, compte)

    reponse = client.post(
        page, {"new_password1": NOUVEAU_MOT_DE_PASSE, "new_password2": "Autre-Chose-2026"}
    )

    assert reponse.status_code == 200
    compte.refresh_from_db()
    assert not compte.check_password(NOUVEAU_MOT_DE_PASSE)


def test_un_mot_de_passe_trop_court_est_refuse_comme_a_la_creation(client):
    compte = UserFactory(role=Role.RH)
    page = _page_confirmation(client, compte)

    reponse = client.post(page, {"new_password1": "court1", "new_password2": "court1"})

    assert reponse.status_code == 200
    compte.refresh_from_db()
    assert not compte.check_password("court1")


def test_un_lien_deja_utilise_est_refuse(client):
    compte = UserFactory(role=Role.RH)
    lien = _lien_confirmation(compte)
    page = _page_confirmation(client, compte)
    client.post(page, {"new_password1": NOUVEAU_MOT_DE_PASSE, "new_password2": NOUVEAU_MOT_DE_PASSE})

    reponse = client.get(lien, follow=True)

    assert reponse.context["validlink"] is False
    assert "plus valable" in reponse.content.decode()


def test_un_lien_invalide_affiche_l_erreur_sans_planter(client):
    reponse = client.get(
        reverse("accounts:password_reset_confirm", kwargs={"uidb64": "invalide", "token": "invalide"})
    )

    assert reponse.status_code == 200
    assert reponse.context["validlink"] is False


def test_la_reinitialisation_est_tracee_au_journal_d_audit(client):
    compte = UserFactory(role=Role.RH)
    page = _page_confirmation(client, compte)

    client.post(page, {"new_password1": NOUVEAU_MOT_DE_PASSE, "new_password2": NOUVEAU_MOT_DE_PASSE})

    entree = AuditLog.objects.filter(entite="User", entite_id=compte.pk, action=ActionChoices.UPDATE).first()
    assert entree is not None
    assert entree.utilisateur_id == compte.pk


def test_un_administrateur_peut_aussi_reinitialiser_son_mot_de_passe(client):
    """La MFA (ADMIN/DIRECTION) ne bloque pas ce parcours : la personne n'est pas encore connectée."""
    compte = UserFactory(role=Role.ADMIN)
    page = _page_confirmation(client, compte)

    reponse = client.post(
        page,
        {"new_password1": NOUVEAU_MOT_DE_PASSE, "new_password2": NOUVEAU_MOT_DE_PASSE},
        follow=True,
    )

    assert reponse.redirect_chain[-1][0] == reverse("accounts:password_reset_complete")


def test_le_lien_mot_de_passe_oublie_est_sur_la_page_de_connexion(client):
    reponse = client.get(reverse("accounts:login"))

    assert reverse("accounts:password_reset") in reponse.content.decode()
