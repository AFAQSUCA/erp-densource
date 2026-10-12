"""Lecture et modification des paramètres de l'application (cahier-des-charges.md:48 « config, seuils d'alerte » ;
décision du 12/10/2026 : avenant-parametres.md).

Les autres apps lisent toujours la valeur ici (``parametres()``), jamais une constante : un changement fait à
l'écran s'applique dès l'opération suivante, sans redémarrage. Il ne s'applique **jamais rétroactivement** à ce
qui a déjà été enregistré (niveau d'alerte d'un plein, date limite de validation d'un congé déjà demandé), sauf le
droit annuel de congé, qui est recalculé à chaque lecture du solde.

Pas de cache partagé : une lecture coûte une requête sur une table d'une ligne, et un cache survivrait à
l'annulation d'une transaction (valeur fantôme).
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.exceptions import ErreurMetier

from . import permissions
from .models import PK_UNIQUE, Parametres

CHAMPS = (
    "delai_alerte_jours",
    "seuil_conso_jaune_pct",
    "seuil_conso_rouge_pct",
    "seuil_conso_saisie_pct",
    "conso_min_l100",
    "conso_max_l100",
    "ecart_km_max",
    "tva_defaut",
    "delai_paiement_defaut_jours",
    "delai_validation_n1_heures",
    "delai_validation_n2_heures",
    "droit_annuel_jours",
)


class ParametresError(ErreurMetier):
    """Erreur métier sur les paramètres (message affichable tel quel)."""


class ModificationNonAutorisee(ParametresError):
    """L'acteur n'a pas le droit de modifier les paramètres."""


class ParametresInvalides(ParametresError):
    """Une valeur est hors bornes ou incohérente avec une autre ; ``erreurs`` : champ -> messages."""

    def __init__(self, erreurs: dict[str, list[str]]):
        self.erreurs = erreurs
        super().__init__(" ".join(m for messages in erreurs.values() for m in messages))


def parametres() -> Parametres:
    """Les paramètres en vigueur ; ceux du cahier des charges tant que rien n'a été enregistré (sans rien écrire)."""
    return Parametres.objects.filter(pk=PK_UNIQUE).first() or Parametres(pk=PK_UNIQUE)


def delai_alerte(jours: int | None = None) -> int:
    """Délai d'alerte avant expiration : ``jours`` s'il est fourni (tests, appel explicite), sinon le paramètre."""
    return parametres().delai_alerte_jours if jours is None else jours


def peut_modifier(utilisateur) -> bool:
    return getattr(utilisateur, "role_effectif", None) in permissions.MODIFICATION


def _verifier_coherence(p: Parametres) -> dict[str, list[str]]:
    erreurs: dict[str, list[str]] = {}
    if p.seuil_conso_rouge_pct <= p.seuil_conso_jaune_pct:
        erreurs.setdefault("seuil_conso_rouge_pct", []).append(
            "Le seuil de l'alerte rouge doit être supérieur à celui de l'alerte jaune."
        )
    if p.seuil_conso_saisie_pct <= p.seuil_conso_rouge_pct:
        erreurs.setdefault("seuil_conso_saisie_pct", []).append(
            "Le seuil de saisie suspecte doit être supérieur à celui de l'alerte rouge."
        )
    if p.conso_max_l100 <= p.conso_min_l100:
        erreurs.setdefault("conso_max_l100", []).append(
            "La consommation maximale doit être supérieure à la consommation minimale."
        )
    return erreurs


@transaction.atomic
def modifier_parametres(acteur, **valeurs) -> Parametres:
    """Enregistre de nouvelles valeurs (ADMIN, DIRECTION). Tout est vérifié avant d'écrire : bornes de chaque champ
    et cohérence entre seuils. Seuls les champs de ``CHAMPS`` sont acceptés ; un champ absent garde sa valeur.
    Journalisé (``audit_model``, module ``PARAMETRES``) avec l'ancienne et la nouvelle valeur."""
    if not peut_modifier(acteur):
        raise ModificationNonAutorisee("Seuls l'administrateur et la direction modifient les paramètres.")
    inconnus = set(valeurs) - set(CHAMPS)
    if inconnus:
        raise ParametresError(f"Paramètre inconnu : {', '.join(sorted(inconnus))}.")

    p = Parametres.objects.select_for_update().filter(pk=PK_UNIQUE).first() or Parametres(pk=PK_UNIQUE)
    for champ, valeur in valeurs.items():
        setattr(p, champ, valeur)
    try:
        p.full_clean(exclude=["modifie_par"], validate_unique=False, validate_constraints=False)
    except ValidationError as erreur:
        raise ParametresInvalides(erreur.message_dict) from None
    erreurs = _verifier_coherence(p)
    if erreurs:
        raise ParametresInvalides(erreurs)
    p.modifie_par = acteur
    p.save()
    return p
