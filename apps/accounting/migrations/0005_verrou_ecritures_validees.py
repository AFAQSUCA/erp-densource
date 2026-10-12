"""Verrou en base des écritures validées (audit AV-06), PostgreSQL seulement (la production).

Django refuse déjà de modifier ou supprimer une écriture validée, ligne à ligne comme en masse
(``EcritureQuerySet``, ``LigneQuerySet``). Ces déclencheurs refusent aussi un accès direct à la base qui
contournerait Django : une écriture validée ne se modifie ni ne se supprime ; une ligne ne se modifie jamais
et ne se supprime que dans un brouillon. Une erreur se corrige par contre-passation.
"""

from django.db import migrations

VERROU = """
CREATE OR REPLACE FUNCTION accounting_verrou_ecriture() RETURNS trigger AS $$
BEGIN
    IF OLD.statut = 'VALIDEE' THEN
        RAISE EXCEPTION 'Écriture comptable validée % : ni modification ni suppression, contre-passez-la.', OLD.id;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER accounting_ecriture_verrou
    BEFORE UPDATE OR DELETE ON accounting_ecriturecomptable
    FOR EACH ROW EXECUTE FUNCTION accounting_verrou_ecriture();

CREATE OR REPLACE FUNCTION accounting_verrou_ligne() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'Ligne d''écriture % : ne se modifie jamais, contre-passez.', OLD.id;
    END IF;
    IF EXISTS (SELECT 1 FROM accounting_ecriturecomptable e WHERE e.id = OLD.ecriture_id AND e.statut = 'VALIDEE') THEN
        RAISE EXCEPTION 'Ligne % d''une écriture validée : ne se supprime pas, contre-passez.', OLD.id;
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER accounting_ligne_verrou
    BEFORE UPDATE OR DELETE ON accounting_ligneecriture
    FOR EACH ROW EXECUTE FUNCTION accounting_verrou_ligne();
"""

RETRAIT = """
DROP TRIGGER IF EXISTS accounting_ligne_verrou ON accounting_ligneecriture;
DROP FUNCTION IF EXISTS accounting_verrou_ligne();
DROP TRIGGER IF EXISTS accounting_ecriture_verrou ON accounting_ecriturecomptable;
DROP FUNCTION IF EXISTS accounting_verrou_ecriture();
"""


def poser(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(VERROU, params=None)  # sans paramètres : les « % » de RAISE ne sont pas des emplacements


def retirer(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(RETRAIT, params=None)  # sans paramètres : les « % » de RAISE ne sont pas des emplacements


class Migration(migrations.Migration):
    dependencies = [("accounting", "0004_piece_reference_100")]

    operations = [migrations.RunPython(poser, retirer)]
