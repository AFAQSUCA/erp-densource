"""Gestion des comptes utilisateurs par l'administrateur (cahier-des-charges.md:48 « création/suppression
utilisateurs »).

L'ADMIN crée un compte, change son rôle et ses coordonnées, l'active ou le désactive. Jamais de suppression
physique : un compte désactivé ne se connecte plus mais son historique (journal d'audit, saisies) reste attribué
à son nom. Règles de sécurité, appliquées ici et non dans l'écran :

* un superutilisateur Django n'est jamais créé, modifié ni désactivé par cette voie (il se gère en ligne de
  commande) : l'ADMIN ne peut donc pas s'attribuer plus de pouvoir qu'il n'en a ;
* personne ne se désactive ni ne change son propre rôle (pas de compte qui s'enferme dehors) ;
* le mot de passe respecte les validateurs du projet ;
* toute modification est journalisée (``audit_model(User)``, module ``UTILISATEURS`` ; mot de passe : empreinte).
"""

from __future__ import annotations

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import QuerySet

from apps.core.exceptions import ErreurMetier
from apps.core.search import filtrer_par_texte

from . import permissions
from .models import Role, User


class UtilisateurError(ErreurMetier):
    """Erreur métier sur la gestion des comptes (message affichable tel quel)."""


class ActionUtilisateurNonAutorisee(UtilisateurError):
    """L'acteur n'a pas le droit de gérer les comptes."""


def _exiger_administrateur(acteur) -> None:
    if acteur.role_effectif not in permissions.GESTION_UTILISATEURS:
        raise ActionUtilisateurNonAutorisee("Seul l'administrateur peut gérer les comptes utilisateurs.")


def _exiger_modifiable(acteur, utilisateur: User) -> None:
    _exiger_administrateur(acteur)
    if utilisateur.is_superuser:
        raise UtilisateurError(
            "Un superutilisateur ne se gère pas depuis cet écran (ligne de commande « createsuperuser »)."
        )


def utilisateurs(*, recherche: str = "", role: str = "", actif: str = "") -> QuerySet[User]:
    """Liste des comptes (tous, superutilisateurs compris, en lecture), filtrable."""
    comptes = User.objects.order_by("last_name", "first_name", "username")
    if role in Role.values:
        comptes = comptes.filter(role=role)
    if actif in ("oui", "non"):
        comptes = comptes.filter(is_active=(actif == "oui"))
    return filtrer_par_texte(comptes, recherche, "username", "first_name", "last_name", "email")


def _verifier_champs(*, username: str | None, email: str, role: str, exclure: User | None = None) -> None:
    if role not in Role.values:
        raise UtilisateurError("Rôle inconnu.")
    if not email.strip():
        raise UtilisateurError("L'adresse e-mail est obligatoire (elle sert à réinitialiser le mot de passe).")
    doublons = User.objects.filter(email__iexact=email.strip())
    if username is not None:
        if User.objects.filter(username__iexact=username).exists():
            raise UtilisateurError(f"L'identifiant « {username} » est déjà pris.")
    if exclure is not None:
        doublons = doublons.exclude(pk=exclure.pk)
    if doublons.exists():
        raise UtilisateurError("Cette adresse e-mail est déjà utilisée par un autre compte.")


@transaction.atomic
def creer_utilisateur(
    acteur,
    *,
    username: str,
    first_name: str,
    last_name: str,
    email: str,
    telephone: str = "",
    role: str,
    password: str,
) -> User:
    """Crée un compte actif, jamais superutilisateur ni membre du staff Django."""
    _exiger_administrateur(acteur)
    username = username.strip()
    if not username:
        raise UtilisateurError("L'identifiant est obligatoire.")
    _verifier_champs(username=username, email=email, role=role)
    candidat = User(
        username=username, first_name=first_name.strip(), last_name=last_name.strip(), email=email.strip(),
        telephone=telephone.strip(), role=role,
    )
    try:
        validate_password(password, candidat)
    except ValidationError as erreur:
        raise UtilisateurError(" ".join(erreur.messages)) from erreur
    candidat.set_password(password)
    candidat.save()
    return candidat


@transaction.atomic
def modifier_utilisateur(
    acteur, utilisateur: User, *, first_name: str, last_name: str, email: str, telephone: str = "", role: str
) -> User:
    """Corrige les coordonnées et le rôle d'un compte. On ne change pas son propre rôle."""
    _exiger_modifiable(acteur, utilisateur)
    _verifier_champs(username=None, email=email, role=role, exclure=utilisateur)
    if utilisateur.pk == acteur.pk and role != utilisateur.role:
        raise UtilisateurError("Vous ne pouvez pas changer votre propre rôle.")
    utilisateur.first_name = first_name.strip()
    utilisateur.last_name = last_name.strip()
    utilisateur.email = email.strip()
    utilisateur.telephone = telephone.strip()
    utilisateur.role = role
    utilisateur.save()
    return utilisateur


@transaction.atomic
def definir_actif(acteur, utilisateur: User, actif: bool) -> User:
    """Active ou désactive un compte (jamais supprimé). On ne se désactive pas soi-même."""
    _exiger_modifiable(acteur, utilisateur)
    if utilisateur.pk == acteur.pk and not actif:
        raise UtilisateurError("Vous ne pouvez pas désactiver votre propre compte.")
    if utilisateur.is_active != actif:
        utilisateur.is_active = actif
        utilisateur.save(update_fields=["is_active"])
    return utilisateur
