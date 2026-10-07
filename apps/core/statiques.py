"""Fichiers statiques à noms versionnés, tolérants aux ressources absentes.

``ManifestStaticFilesStorage`` renomme chaque fichier avec une empreinte de son contenu
(``tailwind.css`` → ``tailwind.4f2a9c1b7e3d.css``) : le nom change dès que le contenu change, donc un cache à longue durée
(Nginx : 30 jours) ne sert jamais un fichier périmé. Il refuse pourtant de collecter un fichier qui en cite un autre
introuvable : la feuille de style de Font Awesome cite des polices (``fa-brands-400.woff2``…) que ``frontend/vendor.js``
ne copie pas, car l'interface n'utilise que les icônes « solid » et « regular ». Ici, une référence introuvable reste
telle quelle au lieu de faire échouer ``collectstatic`` (et donc le démarrage du conteneur).
"""

from django.contrib.staticfiles.storage import ManifestStaticFilesStorage


class StockageStatiqueVersionne(ManifestStaticFilesStorage):
    manifest_strict = False  # une page qui cite un fichier absent du manifeste garde son URL au lieu de lever une erreur

    def hashed_name(self, name, content=None, filename=None):
        try:
            return super().hashed_name(name, content, filename)
        except ValueError:
            return name
