"""Branchement de l'audit automatique sur les modèles sensibles.

ADR-003 (architecture.md:488-493) : signaux ``pre_save``/``post_save``.
Chaque app appelle ``audit_model(MonModele, module="...")`` dans son
``AppConfig.ready()`` ; toute création, modification ou suppression
logique produit alors une ligne ``audit_log`` avec les valeurs avant/après.
"""

from __future__ import annotations

import json
from decimal import Decimal

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import DecimalField, Model
from django.db.models.signals import post_save, pre_save

from apps.core.middleware import get_current_request, get_current_user

from . import services
from .models import ActionChoices

# Bruit sans valeur d'audit : les horodatages techniques changent à chaque save.
CHAMPS_IGNORES = {"created_at", "updated_at"}


def _valeur(field, valeur):
    """Normalise une décimale comme la base la relira (250000 → 250000.00).

    Sans cela, l'instance en mémoire (Decimal("250000")) et la ligne relue
    en base (Decimal("250000.00")) paraîtraient différentes à chaque save().
    """
    if isinstance(field, DecimalField) and valeur is not None:
        return Decimal(valeur).quantize(Decimal(1).scaleb(-field.decimal_places))
    return valeur


def _snapshot(instance: Model, exclure: frozenset[str] = frozenset()) -> dict:
    """Valeurs des colonnes de l'instance, sérialisables en JSON."""
    data = {
        f.attname: _valeur(f, getattr(instance, f.attname))
        for f in instance._meta.concrete_fields
        if f.attname not in CHAMPS_IGNORES and f.attname not in exclure
    }
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))


def audit_model(
    model: type[Model], module: str, exclure: tuple[str, ...] = ()
) -> None:
    """Active l'audit automatique de ``model`` sous le nom de module ``module``.

    ``exclure`` liste les champs à ne jamais écrire dans le journal (secrets :
    codes de mission, etc.). Un changement sur ces seuls champs ne produit
    aucune entrée.
    """
    label = model._meta.label
    exclus = frozenset(exclure)
    entite = model.__name__

    def capturer_avant(sender, instance, raw=False, **kwargs):
        if raw:
            return
        instance._audit_avant = None
        if instance.pk:
            ancien = sender._base_manager.filter(pk=instance.pk).first()
            if ancien is not None:
                instance._audit_avant = _snapshot(ancien, exclus)

    def journaliser(sender, instance, created, raw=False, **kwargs):
        if raw:
            return
        apres = _snapshot(instance, exclus)
        avant = getattr(instance, "_audit_avant", None)

        if created or avant is None:
            action = ActionChoices.CREATE
            ancienne, nouvelle = None, apres
        else:
            changes = [k for k in apres if avant.get(k) != apres[k]]
            if not changes:
                return
            supprime = not avant.get("is_deleted") and apres.get("is_deleted")
            action = ActionChoices.DELETE if supprime else ActionChoices.UPDATE
            ancienne = {k: avant.get(k) for k in changes}
            nouvelle = {k: apres[k] for k in changes}

        services.log_action(
            action=action,
            module=module,
            entite=entite,
            entite_id=instance.pk,
            utilisateur=get_current_user(),
            ancienne_valeur=ancienne,
            nouvelle_valeur=nouvelle,
            request=get_current_request(),
        )

    pre_save.connect(
        capturer_avant, sender=model, weak=False, dispatch_uid=f"audit-pre-{label}"
    )
    post_save.connect(
        journaliser, sender=model, weak=False, dispatch_uid=f"audit-post-{label}"
    )
