"""Aides communes aux vues."""

from . import pdf
from .rapports import contexte_rapport, url_pdf


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


class TelechargementPdfMixin:
    """Ajoute à une page de document imprimable (facture, devis, rapport de mission, tableau de bord) sa version
    PDF générée par le serveur : ``?format=pdf`` (avenant-export-pdf.md). La sous-classe décrit le document dans
    ``blocs_pdf(contexte)`` (blocs de :mod:`apps.core.pdf`) ; titre, sous-titre et en-tête viennent du contexte
    du rapport (``contexte_rapport``), comme la page HTML. À placer avant la vue dans les classes parentes."""

    def blocs_pdf(self, contexte: dict) -> list:
        raise NotImplementedError

    def get(self, request, *args, **kwargs):
        if request.GET.get("format") != "pdf":
            return super().get(request, *args, **kwargs)
        if hasattr(self, "get_object"):
            self.object = self.get_object()
        contexte = self.get_context_data(**kwargs)
        contenu = pdf.generer_pdf(
            titre=contexte["titre"], sous_titre=contexte.get("sous_titre", ""), blocs=self.blocs_pdf(contexte),
            entreprise=contexte["entreprise"], genere_par=contexte["genere_par"], genere_le=contexte["genere_le"],
        )
        return pdf.reponse_pdf(contenu, contexte["titre"])

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "url_pdf": url_pdf(self.request)}


def fcfa(montant) -> str:
    """Montant pour un document PDF : « 1 250 000 FCFA »."""
    return f"{pdf.cellule(montant)} FCFA"


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

    def get(self, request, *args, **kwargs):
        """``?format=pdf`` : le même rapport en vrai PDF, généré par le serveur (avenant-export-pdf.md)."""
        if request.GET.get("format") != "pdf":
            return super().get(request, *args, **kwargs)
        self.object_list = self.get_queryset()
        contexte = self.get_context_data()
        nombre = contexte["nombre"]
        resume = f"{nombre} ligne{'s' if nombre > 1 else ''}"
        if contexte["tronque"]:
            resume += f" — limité aux {nombre} premières ; affinez la recherche pour voir le reste"
        contenu = pdf.generer_pdf(
            titre=contexte["titre"], sous_titre=contexte["sous_titre"], entreprise=contexte["entreprise"],
            genere_par=contexte["genere_par"], genere_le=contexte["genere_le"],
            blocs=[pdf.Texte(resume, discret=True), pdf.Tableau(entetes=contexte["entetes"], lignes=contexte["lignes"])],
        )
        return pdf.reponse_pdf(contenu, contexte["titre"])

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
            url_pdf=url_pdf(self.request),
        )
        return contexte
