"""Logique métier des clients : fiche, TVA, portefeuille et historique commercial.

Réf. cahier-des-charges.md:119-124, 185-188.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Max, Q, QuerySet
from django.utils import timezone

from apps.accounts.models import Role, User

from .exceptions import ClientError
from .models import TVA_DEFAUT, Client, Interaction, TypeInteraction

CHAMPS_MODIFIABLES = (
    "raison_sociale",
    "ncc_nif",
    "contact_principal",
    "telephone",
    "email",
    "adresse",
    "charge_clientele",
    "taux_tva",
    "motif_exoneration",
)


def clients_pour_selection() -> QuerySet[Client]:
    """Clients triés par raison sociale, pour les listes déroulantes."""
    return Client.objects.order_by("raison_sociale")


def clients_queryset() -> QuerySet[Client]:
    """Clients avec le nombre d'interactions, de réclamations et la dernière interaction."""
    actives = Q(interactions__is_deleted=False)
    # order_by explicite : l'agrégation ignore l'ordre par défaut du modèle.
    return Client.objects.select_related("charge_clientele").order_by("raison_sociale").annotate(
        nb_interactions=Count("interactions", filter=actives, distinct=True),
        nb_reclamations=Count(
            "interactions",
            filter=actives & Q(interactions__type_interaction=TypeInteraction.RECLAMATION),
            distinct=True,
        ),
        derniere_interaction=Max("interactions__date_interaction", filter=actives),
    )


def rechercher_clients(
    *, recherche: str = "", charge_clientele: User | None = None, exonere: bool = False
) -> QuerySet[Client]:
    """Clients filtrés par texte, chargé clientèle attitré et exonération de TVA."""
    resultat = clients_queryset()
    recherche = recherche.strip()
    if recherche:
        resultat = resultat.filter(
            Q(raison_sociale__icontains=recherche)
            | Q(ncc_nif__icontains=recherche)
            | Q(contact_principal__icontains=recherche)
            | Q(telephone__icontains=recherche)
        )
    if charge_clientele is not None:
        resultat = resultat.filter(charge_clientele=charge_clientele)
    if exonere:
        resultat = resultat.filter(taux_tva=0)
    return resultat


def charges_clientele() -> QuerySet[User]:
    """Comptes actifs pouvant être chargé clientèle attitré."""
    return User.objects.filter(role=Role.CHARGE_CLIENTELE, is_active=True).order_by(
        "last_name", "first_name", "username"
    )


def interactions_du_client(client: Client) -> QuerySet[Interaction]:
    return client.interactions.select_related("auteur").order_by("-date_interaction", "-pk")


def _controler(champs: dict, *, client: Client | None = None) -> dict:
    """Vérifie et normalise les champs d'une fiche client."""
    taux = Decimal(champs["taux_tva"])
    if not Decimal(0) <= taux <= Decimal(100):
        raise ClientError("Le taux de TVA doit être compris entre 0 et 100 %.")
    if taux == 0 and not champs.get("motif_exoneration"):
        raise ClientError("Un motif d'exonération est obligatoire quand la TVA est à 0 %.")
    resultat = dict(champs, taux_tva=taux)
    if taux > 0:
        resultat["motif_exoneration"] = ""  # sans exonération, aucun motif n'a de sens
    charge = champs.get("charge_clientele")
    if charge is not None and (charge.role != Role.CHARGE_CLIENTELE or not charge.is_active):
        raise ClientError("Le chargé clientèle attitré doit être un compte actif de ce rôle.")
    doublon = Client.all_objects.filter(ncc_nif=champs["ncc_nif"])
    if client is not None:
        doublon = doublon.exclude(pk=client.pk)
    if doublon.exists():
        raise ClientError(f"Le NCC / NIF {champs['ncc_nif']} est déjà utilisé par un autre client.")
    return resultat


@transaction.atomic
def creer_client(**champs) -> Client:
    """Crée un client. TVA à 18 % par défaut ; à 0 %, le motif d'exonération est obligatoire."""
    champs.setdefault("taux_tva", TVA_DEFAUT)
    champs.setdefault("charge_clientele", None)
    champs.setdefault("motif_exoneration", "")
    champs.setdefault("email", "")
    return Client.objects.create(**_controler(champs))


@transaction.atomic
def modifier_client(client: Client, **champs) -> Client:
    """Met à jour la fiche d'un client (mêmes contrôles qu'à la création)."""
    for nom in CHAMPS_MODIFIABLES:
        champs.setdefault(nom, getattr(client, nom))
    for nom, valeur in _controler(champs, client=client).items():
        if nom in CHAMPS_MODIFIABLES:
            setattr(client, nom, valeur)
    client.save()
    return client


@transaction.atomic
def enregistrer_interaction(
    client: Client,
    auteur: User,
    *,
    type_interaction: str,
    resume: str,
    date_interaction: datetime | None = None,
) -> Interaction:
    """Ajoute une interaction à l'historique commercial du client (date non future)."""
    if not resume.strip():
        raise ClientError("Le résumé de l'échange est obligatoire.")
    maintenant = timezone.now()
    date_interaction = date_interaction or maintenant
    if date_interaction > maintenant:
        raise ClientError("La date d'une interaction ne peut pas être dans le futur.")
    return Interaction.objects.create(
        client=client,
        type_interaction=type_interaction,
        resume=resume,
        date_interaction=date_interaction,
        auteur=auteur,
    )
