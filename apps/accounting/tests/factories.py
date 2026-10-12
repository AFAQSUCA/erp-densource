from contextlib import contextmanager

import factory
from django.db import connection, models

from apps.accounting.models import Compte, NatureCompte


class CompteFactory(factory.django.DjangoModelFactory):
    """Compte de test, indépendant du plan comptable seedé (migration 0002)."""

    class Meta:
        model = Compte

    numero = factory.Sequence(lambda n: f"9{n:05d}")
    libelle = factory.Sequence(lambda n: f"Compte de test {n}")
    nature = NatureCompte.CHARGE


@contextmanager
def sans_verrou_comptable():
    """Tests seulement : simule des données d'avant une règle (écriture ancienne, annulation sans
    contre-passation) en levant le verrou des écritures validées, côté Django (``forcer_update``,
    ``forcer_delete``) et côté PostgreSQL (déclencheurs de la migration 0005, audit AV-06)."""
    postgresql = connection.vendor == "postgresql"
    if postgresql:
        with connection.cursor() as curseur:
            curseur.execute("SET session_replication_role = replica")
    try:
        yield
    finally:
        if postgresql:
            with connection.cursor() as curseur:
                curseur.execute("SET session_replication_role = DEFAULT")


def forcer_update(queryset, **valeurs):
    with sans_verrou_comptable():
        return models.QuerySet.update(queryset, **valeurs)


def forcer_delete(queryset):
    with sans_verrou_comptable():
        return models.QuerySet.delete(queryset)
