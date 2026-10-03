"""Écran « Utilisateurs » (ADMIN) : liste, création, modification, activation. Les règles sont dans
``accounts.services`` ; ces vues n'ajoutent que l'affichage."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import FormView, ListView

from apps.core.views import PaginationTolerante

from . import permissions, services
from .forms import FiltreUtilisateursForm, UtilisateurCreationForm, UtilisateurModificationForm
from .mixins import RoleRequiredMixin
from .models import User


class UtilisateurListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.GESTION_UTILISATEURS
    template_name = "accounts/utilisateur_list.html"
    context_object_name = "comptes"
    paginate_by = 25

    def get_filtre(self):
        return FiltreUtilisateursForm(self.request.GET)

    def get_queryset(self):
        filtre = self.get_filtre()
        donnees = filtre.cleaned_data if filtre.is_valid() else {}
        return services.utilisateurs(
            recherche=donnees.get("q", ""), role=donnees.get("role", ""), actif=donnees.get("actif", "")
        )

    def get_context_data(self, **kwargs):
        return super().get_context_data(filtre=self.get_filtre(), moi=self.request.user, **kwargs)


class UtilisateurCreateView(RoleRequiredMixin, FormView):
    roles = permissions.GESTION_UTILISATEURS
    template_name = "accounts/utilisateur_form.html"
    form_class = UtilisateurCreationForm

    def form_valid(self, form):
        try:
            donnees = dict(form.cleaned_data)
            donnees["password"] = donnees.pop("password1")
            donnees.pop("password2")
            compte = services.creer_utilisateur(self.request.user, **donnees)
        except services.UtilisateurError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, f"Compte {compte.username} créé.")
        return redirect("accounts:utilisateurs")


class UtilisateurUpdateView(RoleRequiredMixin, FormView):
    roles = permissions.GESTION_UTILISATEURS
    template_name = "accounts/utilisateur_form.html"
    form_class = UtilisateurModificationForm

    def dispatch(self, request, *args, **kwargs):
        self.compte = get_object_or_404(User, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        c = self.compte
        return {"first_name": c.first_name, "last_name": c.last_name, "email": c.email, "telephone": c.telephone, "role": c.role}

    def get_context_data(self, **kwargs):
        return super().get_context_data(compte=self.compte, **kwargs)

    def form_valid(self, form):
        try:
            services.modifier_utilisateur(self.request.user, self.compte, **form.cleaned_data)
        except services.UtilisateurError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, f"Compte {self.compte.username} modifié.")
        return redirect("accounts:utilisateurs")


class UtilisateurActivationView(RoleRequiredMixin, View):
    roles = permissions.GESTION_UTILISATEURS
    http_method_names = ["post"]

    def post(self, request, pk):
        compte = get_object_or_404(User, pk=pk)
        actif = request.POST.get("actif") == "oui"
        try:
            services.definir_actif(request.user, compte, actif)
        except services.UtilisateurError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(request, f"Compte {compte.username} {'activé' if actif else 'désactivé'}.")
        return redirect("accounts:utilisateurs")
