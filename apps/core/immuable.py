"""Tables append-only (journal d'audit, journal des mouvements de stock) : protection en profondeur.

Une ligne de ces journaux ne se modifie ni ne se supprime jamais. ``save()`` / ``delete()`` du modèle
refusent déjà, mais ``QuerySet.update()``, ``QuerySet.delete()`` ou du SQL direct les contournaient
(audit M1-05 / M8-06). Deux protections s'ajoutent :

* :class:`AppendOnlyQuerySet` : le manager du modèle refuse ``update`` / ``delete`` / ``bulk_update`` ;
* un trigger PostgreSQL ``BEFORE UPDATE OR DELETE`` (migrations ``audit.0002`` et ``inventory.0002``) :
  même un accès SQL direct à la base lève une erreur. Sans effet sous SQLite (développement, tests).

Purge légale (rétention du journal d'audit : ≥ 5 ans, README de ``audit``) : elle se fait hors application,
par un administrateur de la base qui désactive explicitement le trigger le temps de l'opération.
"""

from django.db import models

FONCTION = "interdire_modification_append_only"


class AppendOnlyQuerySet(models.QuerySet):
    """QuerySet qui refuse toute modification ou suppression en masse."""

    def update(self, **kwargs):
        raise ValueError(f"{self.model.__name__} est append-only : modification interdite.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValueError(f"{self.model.__name__} est append-only : modification interdite.")

    def delete(self):
        raise ValueError(f"{self.model.__name__} est append-only : suppression interdite.")


def poser_triggers(schema_editor, table: str, *, tolere_detachement_utilisateur: bool = False) -> None:
    """Pose le trigger append-only sur ``table`` (PostgreSQL seulement, sinon ne fait rien).

    ``tolere_detachement_utilisateur`` : le journal d'audit garde ``on_delete=SET_NULL`` sur l'utilisateur ;
    le seul UPDATE admis est donc celui qui passe ``utilisateur_id`` à NULL sans toucher à rien d'autre.
    """
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        f"""
        CREATE OR REPLACE FUNCTION {FONCTION}() RETURNS trigger AS $fn$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION '% est append-only : suppression interdite', TG_TABLE_NAME;
            END IF;
            IF TG_OP = 'UPDATE' AND TG_ARGV[0] = 'detachement' AND NEW.utilisateur_id IS NULL
               AND (to_jsonb(NEW) - 'utilisateur_id') = (to_jsonb(OLD) - 'utilisateur_id') THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION '% est append-only : modification interdite', TG_TABLE_NAME;
        END;
        $fn$ LANGUAGE plpgsql;
        """,
        params=None,  # le « % » de RAISE EXCEPTION n'est pas un paramètre à substituer
    )
    argument = "detachement" if tolere_detachement_utilisateur else "strict"
    schema_editor.execute(f"DROP TRIGGER IF EXISTS append_only ON {table};")
    schema_editor.execute(
        f"CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON {table} "
        f"FOR EACH ROW EXECUTE FUNCTION {FONCTION}('{argument}');"
    )


def retirer_triggers(schema_editor, table: str) -> None:
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(f"DROP TRIGGER IF EXISTS append_only ON {table};")
