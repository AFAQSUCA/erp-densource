"""Logique métier des clients : fiche, TVA, portefeuille et historique commercial.

Réf. cahier-des-charges.md:119-124, 185-188.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Max, Q, QuerySet
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.core.search import filtrer_par_texte
from apps.parametres import services as parametres_services

from .exceptions import ClientError
from .models import Client, Interaction, TypeInteraction

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
    "delai_paiement_jours",
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
    resultat = filtrer_par_texte(
        resultat, recherche, "raison_sociale", "ncc_nif", "contact_principal", "telephone"
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


def cle_ncc(ncc_nif: str) -> str:
    """NCC / NIF sans séparateur, en majuscules : « ci-123 », « CI 123 » et « CI123 » sont le même client
    (audit M4-02)."""
    return re.sub(r"[^0-9A-Z]", "", ncc_nif.upper())


def client_par_ncc(ncc_nif: str, *, sauf: Client | None = None) -> Client | None:
    """Le client (supprimé logiquement compris) qui porte déjà ce NCC / NIF, quelle que soit son écriture."""
    cle = cle_ncc(ncc_nif)
    candidats = Client.all_objects.exclude(pk=sauf.pk if sauf else None).only("pk", "ncc_nif", "raison_sociale")
    return next((c for c in candidats if cle_ncc(c.ncc_nif) == cle), None)


def _controler(champs: dict, *, client: Client | None = None) -> dict:
    """Vérifie et normalise les champs d'une fiche client."""
    taux = Decimal(champs["taux_tva"])
    if not Decimal(0) <= taux <= Decimal(100):
        raise ClientError("Le taux de TVA doit être compris entre 0 et 100 %.")
    if taux == 0 and not champs.get("motif_exoneration"):
        raise ClientError("Un motif d'exonération est obligatoire quand la TVA est à 0 %.")
    delai = champs["delai_paiement_jours"]
    if not 1 <= delai <= 365:
        raise ClientError("Le délai de paiement doit être compris entre 1 et 365 jours.")
    resultat = dict(champs, taux_tva=taux, delai_paiement_jours=delai)
    if taux > 0:
        resultat["motif_exoneration"] = ""  # sans exonération, aucun motif n'a de sens
    charge = champs.get("charge_clientele")
    inchange = client is not None and charge is not None and client.charge_clientele_id == charge.pk
    if charge is not None and not inchange and (charge.role != Role.CHARGE_CLIENTELE or not charge.is_active):
        # Garder le chargé actuel reste permis même s'il a été désactivé depuis : seul un NOUVEAU choix doit
        # être un compte actif de ce rôle (sinon modifier une autre information du client échouait).
        raise ClientError("Le chargé clientèle attitré doit être un compte actif de ce rôle.")
    ncc = " ".join(str(champs["ncc_nif"]).split()).upper()  # majuscules, espaces superflus retirés
    if not cle_ncc(ncc):
        raise ClientError("Le NCC / NIF est obligatoire.")
    resultat["ncc_nif"] = ncc
    doublon = client_par_ncc(ncc, sauf=client)
    if doublon is not None:
        raise ClientError(
            f"Le NCC / NIF {ncc} est déjà utilisé par un autre client ({doublon.raison_sociale}, {doublon.ncc_nif})."
        )
    return resultat


@transaction.atomic
def creer_client(**champs) -> Client:
    """Crée un client. Taux de TVA et délai de paiement non fournis : ceux des paramètres (18 % et 30 jours dans
    le cahier des charges) ; à 0 %, le motif d'exonération est obligatoire."""
    reglages = parametres_services.parametres()
    champs.setdefault("taux_tva", reglages.tva_defaut)
    champs.setdefault("delai_paiement_jours", reglages.delai_paiement_defaut_jours)
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


def reclamations_recentes(*, jours: int = 30, maintenant: datetime | None = None) -> int:
    """Nombre de réclamations enregistrées sur les ``jours`` derniers jours."""
    depuis = (maintenant or timezone.now()) - timedelta(days=jours)
    return Interaction.objects.filter(
        type_interaction=TypeInteraction.RECLAMATION, date_interaction__gte=depuis
    ).count()
