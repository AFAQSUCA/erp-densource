class ErreurMetier(Exception):
    """Base des erreurs métier d'une app dont le message est destiné à l'utilisateur.

    Une opération peut échouer à cause d'une autre app (ex. un plein refusé parce que l'enveloppe de
    dépense est dépassée) : l'erreur traverse alors l'écran d'origine, qui ne connaît pas cette famille
    d'erreurs. ``ErreurMetierMiddleware`` la transforme en message plutôt qu'en erreur 500.
    """
