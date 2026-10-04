from django.http import HttpResponse
from django.views import View
from django.views.generic import FormView

from apps.accounts.mixins import RoleRequiredMixin

from . import modele, permissions, services
from .forms import ImportForm


class ImportView(RoleRequiredMixin, FormView):
    """Dépose le classeur rempli ; le rapport (créés, déjà présents, erreurs par ligne) s'affiche sur la même page."""

    roles = permissions.IMPORT_DONNEES
    template_name = "importation/importer.html"
    form_class = ImportForm

    def form_valid(self, form):
        try:
            rapport = services.importer_classeur(
                form.cleaned_data["fichier"], self.request.user, simulation=form.cleaned_data["simulation"]
            )
        except services.ImportInvalide as erreur:
            form.add_error("fichier", str(erreur))
            return self.form_invalid(form)
        return self.render_to_response(self.get_context_data(form=ImportForm(), rapport=rapport))


class ModeleView(RoleRequiredMixin, View):
    """Télécharge le classeur modèle (généré à la volée : toujours aligné sur ce que l'import lit)."""

    roles = permissions.IMPORT_DONNEES

    def get(self, request):
        reponse = HttpResponse(
            modele.construire_modele(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        reponse["Content-Disposition"] = 'attachment; filename="modele-donnees-entreprise-DEN-Source.xlsx"'
        return reponse
