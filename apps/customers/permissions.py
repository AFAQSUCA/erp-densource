"""Qui peut consulter et gérer les clients.

Cahier-des-charges.md:44-55 : le CHARGE_CLIENTELE tient le « portefeuille clients,
historique, devis, réclamations, notes d'échange » ; la DIRECTION a une « lecture seule
sur RH/Clientèle » ; l'ADMIN a tous les droits. La RH n'a « pas d'accès clients » ; le
PARCAUTO et le CHAUFFEUR n'y ont pas accès non plus. L'accès des FINANCES (factures) se
décidera avec la facturation (étape 4).
"""

from apps.accounts.models import Role

CONSULTATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.CHARGE_CLIENTELE})
MODIFICATION = frozenset({Role.ADMIN, Role.CHARGE_CLIENTELE})
