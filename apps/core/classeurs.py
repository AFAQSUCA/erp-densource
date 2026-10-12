"""Classeurs Excel déposés par les utilisateurs : contrôle avant ouverture — audit AV-16.

Un ``.xlsx`` est une archive zip. Une archive piégée (« bombe zip ») pèse quelques ko et se décompresse en
plusieurs Go : ouverte par openpyxl, elle saturerait la mémoire du serveur. On lit donc d'abord le sommaire de
l'archive et on refuse ce qui se décompresserait trop. La taille annoncée suffit : le module ``zipfile`` de
Python ne décompresse jamais un élément au-delà de la taille qu'il annonce.
"""

from __future__ import annotations

import zipfile

from .exceptions import ErreurMetier

# Un classeur de collecte (quelques milliers de lignes au plus) tient en quelques Mo une fois décompressé.
TAILLE_DECOMPRESSEE_MAX = 50 * 1024 * 1024
ELEMENTS_MAX = 500


class ClasseurSuspect(ErreurMetier):
    """Archive refusée avant ouverture : trop volumineuse une fois décompressée, ou trop d'éléments."""


def exiger_classeur_raisonnable(fichier) -> None:
    """Refuse (``ClasseurSuspect``) une archive trop volumineuse une fois décompressée ; remet ``fichier`` au début.
    Un fichier qui n'est pas une archive est laissé au lecteur Excel, qui le refusera avec son propre message."""
    try:
        with zipfile.ZipFile(fichier) as archive:
            elements = archive.infolist()
    except zipfile.BadZipFile:
        return
    finally:
        fichier.seek(0)
    if len(elements) > ELEMENTS_MAX:
        raise ClasseurSuspect("Ce fichier contient trop d'éléments pour un classeur de collecte : il est refusé.")
    if sum(element.file_size for element in elements) > TAILLE_DECOMPRESSEE_MAX:
        raise ClasseurSuspect(
            "Ce fichier est trop volumineux une fois décompressé pour un classeur de collecte : il est refusé."
        )
