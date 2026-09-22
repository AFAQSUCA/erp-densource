"""Recherche texte insensible aux accents et à la casse (« traore » trouve « Traoré »).

``icontains`` ne suffit pas : sur SQLite il ne gère la casse que pour l'ASCII (« TRAORÉ » ne
trouve pas « Traoré ») et, partout, « Kone » ne trouve pas « Koné ». On compare donc des
valeurs normalisées (minuscules, sans accents) des deux côtés :

- PostgreSQL : ``LOWER(TRANSLATE(champ, accents, lettres))``, sans extension à installer ;
- SQLite (développement, tests) : fonction ``NORMALISER`` enregistrée à la connexion
  (:func:`enregistrer_fonction_sqlite`).

Le texte cherché est normalisé avec la même table (:func:`normaliser`), pour que les deux
côtés restent identiques. Plusieurs mots : chacun doit se trouver dans au moins un des champs
(« moussa traore » trouve Moussa Traoré).
"""

from django.db.models import CharField, Func, Q, QuerySet, Value
from django.db.models.functions import Lower

ACCENTS = "àâäáãåçéèêëíìîïñóòôöõúùûüýÿ"
SANS_ACCENT = "aaaaaaceeeeiiiinooooouuuuyy"


def normaliser(texte: str) -> str:
    """Minuscules sans accents, avec la même table que la requête SQL."""
    return (texte or "").lower().translate(str.maketrans(ACCENTS, SANS_ACCENT))


class Normalise(Func):
    """Valeur d'un champ texte normalisée pour la recherche (voir le module)."""

    arity = 1

    def __init__(self, expression):
        super().__init__(expression, output_field=CharField())

    def as_sqlite(self, compiler, connection, **contexte):
        return super().as_sql(compiler, connection, function="NORMALISER", **contexte)

    def as_sql(self, compiler, connection, **contexte):
        # Minuscules d'abord, puis suppression des accents : la table ACCENTS/SANS_ACCENT n'a que
        # des lettres minuscules, donc « TRANSLATE » avant « LOWER » laisserait passer un accent
        # majuscule (« É » → toujours « É » après TRANSLATE, puis « é » après LOWER : l'accent
        # reste). Même ordre que `normaliser()` ci-dessus (``.lower().translate(...)``).
        (expression,) = self.get_source_expressions()
        minuscule = Lower(expression)
        traduit = Func(minuscule, Value(ACCENTS), Value(SANS_ACCENT), function="TRANSLATE")
        return traduit.as_sql(compiler, connection)


def enregistrer_fonction_sqlite(sender, connection, **kwargs):
    """Signal ``connection_created`` : rend ``NORMALISER`` disponible dans SQLite."""
    if connection.vendor == "sqlite":
        connection.connection.create_function("NORMALISER", 1, normaliser, deterministic=True)


def filtrer_par_texte(queryset: QuerySet, recherche: str, *champs: str) -> QuerySet:
    """Garde les lignes où chaque mot de ``recherche`` figure dans l'un des ``champs``.

    Les champs peuvent traverser des relations (``"client__raison_sociale"``). Une recherche
    vide ne filtre rien. Les ``%`` et ``_`` saisis sont traités comme du texte.
    """
    mots = normaliser(recherche).split()
    if not mots:
        return queryset
    alias = {f"_recherche_{i}": Normalise(champ) for i, champ in enumerate(champs)}
    queryset = queryset.alias(**alias)
    for mot in mots:
        conditions = Q()
        for nom in alias:
            conditions |= Q(**{f"{nom}__contains": mot})
        queryset = queryset.filter(conditions)
    return queryset
