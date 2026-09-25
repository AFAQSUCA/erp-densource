"""Aides communes aux vues."""

from .rapports import contexte_rapport


class PaginationTolerante:
    """Pagination qui ne renvoie pas d'erreur 404 sur un numéro de page inutilisable.

    Un lien enregistré vers la page 5, une page qui disparaît après un filtre ou un
    ``?page=abc`` amènent sur la première ou la dernière page existante au lieu d'une
    page d'erreur. ``?page=last`` reste accepté.
    """

    def paginate_queryset(self, queryset, page_size):
        paginator = self.get_paginator(
            queryset,
            page_size,
            orphans=self.get_paginate_orphans(),
            allow_empty_first_page=self.get_allow_empty(),
        )
        demande = self.request.GET.get(self.page_kwarg, "1")
        try:
            numero = paginator.num_pages if demande == "last" else int(demande)
        except ValueError:
            numero = 1
        numero = min(max(numero, 1), paginator.num_pages)
        page = paginator.page(numero)
        return paginator, page, page.object_list, page.has_other_pages()


class ImpressionListeMixin:
    """Transforme un ``ListView`` existant en rapport imprimable, sans dupliquer ses filtres.

    S'utilise en écrivant une sous-classe du ``ListView`` de la liste, mixin en premier pour que son
    ``get_context_data`` l'emporte : ``class XImprimerView(ImpressionListeMixin, XListView): ...``. Les
    droits (``roles``) et la recherche/les filtres (``get_queryset``) restent ceux de la liste ; seuls la
    pagination et le contexte d'affichage changent. Chaque sous-classe déclare ``titre_impression`` et
    ``colonnes`` : une suite de ``(libellé, clé)``, ``clé`` étant soit un chemin en pointillés résolu sur
    chaque objet (``"client.raison_sociale"``, méthodes get_FOO_display comprises), soit un callable
    ``clé(objet) -> str`` pour une valeur composée.
    """

    template_name = "rapports/liste_impression.html"
    titre_impression = ""
    colonnes: tuple = ()
    limite_impression = 500

    def get_titre_impression(self) -> str:
        return self.titre_impression

    def get_sous_titre_impression(self) -> str:
        return ""

    @staticmethod
    def _valeur(objet, cle):
        if callable(cle):
            return cle(objet)
        valeur = objet
        for morceau in cle.split("."):
            if valeur in (None, ""):
                return "—"
            valeur = getattr(valeur, morceau, "")
            if callable(valeur):
                valeur = valeur()
        return valeur if valeur not in (None, "") else "—"

    def get_context_data(self, **kwargs):
        objets = list(self.get_queryset()[: self.limite_impression + 1])
        tronque = len(objets) > self.limite_impression
        objets = objets[: self.limite_impression]
        contexte = contexte_rapport(
            self.request, titre=self.get_titre_impression(), sous_titre=self.get_sous_titre_impression()
        )
        contexte.update(
            entetes=[libelle for libelle, _ in self.colonnes],
            lignes=[[self._valeur(o, cle) for _, cle in self.colonnes] for o in objets],
            nombre=len(objets),
            tronque=tronque,
        )
        return contexte
