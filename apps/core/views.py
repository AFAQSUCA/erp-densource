"""Aides communes aux vues."""


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
