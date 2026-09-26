"""Événements du cycle de facturation (souscrits par ``notifications``).

Émis dans la transaction de l'action, avec ``send_robust`` : un récepteur en erreur ne doit
jamais empêcher une validation de facture.
"""

import logging

from django.dispatch import Signal

logger = logging.getLogger(__name__)

# La facture vient d'être soumise à la DIRECTION. Argument : ``facture``.
facture_a_valider = Signal()
# La DIRECTION vient de valider la facture (numéro attribué). Argument : ``facture``.
facture_validee = Signal()
# La DIRECTION a refusé la facture (retour en brouillon). Arguments : ``facture``, ``motif``.
facture_refusee = Signal()

# Le devis vient d'être soumis à la FINANCES. Argument : ``proforma``.
proforma_a_valider = Signal()
# La FINANCES a validé le devis mais le montant dépasse le seuil : la DIRECTION doit
# valider en plus. Argument : ``proforma``.
proforma_en_attente_direction = Signal()
# Le devis est validé (par la FINANCES seule, ou en plus par la DIRECTION). Argument : ``proforma``.
proforma_validee = Signal()
# Contre-proposition de la FINANCES ou de la DIRECTION. Arguments : ``proforma``, ``motif``.
proforma_contre_proposee = Signal()
# Le devis envoyé au client a dépassé sa date de validité sans réponse. Argument : ``proforma``.
proforma_expiree = Signal()

# Un règlement vient d'être enregistré (entrée de trésorerie). Argument : ``reglement``. Utile à
# ``missions`` (R4) pour refléter l'encaissement dans la prévision de trésorerie de la mission
# facturée, sans double saisie.
reglement_enregistre = Signal()


def emettre(signal: Signal, *, sender: type | None = None, **arguments) -> None:
    """Émet un signal en journalisant (sans propager) les erreurs des récepteurs."""
    from .models import Facture

    for recepteur, resultat in signal.send_robust(sender=sender or Facture, **arguments):
        if isinstance(resultat, Exception):
            logger.error("Récepteur %r en erreur", recepteur, exc_info=resultat)
