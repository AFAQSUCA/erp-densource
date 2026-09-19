"""Requêtes de lecture des clients (utilisées par les écrans)."""

from django.db.models import QuerySet

from .models import Client


def clients_pour_selection() -> QuerySet[Client]:
    """Clients triés par raison sociale, pour les listes déroulantes."""
    return Client.objects.order_by("raison_sociale")
