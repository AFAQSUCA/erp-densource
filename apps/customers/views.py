"""Écrans des clients : portefeuille, fiche, création, modification, interactions.

Aucune règle métier ici : les vues contrôlent le rôle, lisent le formulaire et
délèguent à ``services.py`` (conventions.md:19-23).
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from apps.accounts.mixins import RoleRequiredMixin
from apps.accounts.models import Role
from apps.core.views import PaginationTolerante

from . import permissions, sections, services
from .exceptions import ClientError
from .forms import ClientForm, FiltreClientsForm, InteractionForm
from .models import Client


class ClientListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.CONSULTATION
    template_name = "customers/client_list.html"
    context_object_name = "clients"
    paginate_by = 20

    def get_filtre(self):
        if not hasattr(self, "_filtre"):
            self._filtre = FiltreClientsForm(self.request.GET)
        return self._filtre

    def get_queryset(self):
        return services.rechercher_clients(**self.get_filtre().criteres(self.request.user))

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        criteres = self.get_filtre().criteres(self.request.user)
        utilisateur = self.request.user
        contexte.update(
            filtre=self.get_filtre(),
            filtres_actifs=any(criteres.values()),
            peut_modifier=utilisateur.role_effectif in permissions.MODIFICATION,
            a_un_portefeuille=utilisateur.role == Role.CHARGE_CLIENTELE,
        )
        return contexte


class ClientDetailView(RoleRequiredMixin, DetailView):
    roles = permissions.CONSULTATION
    template_name = "customers/client_detail.html"
    context_object_name = "client"

    def get_queryset(self):
        return services.clients_queryset()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        client, utilisateur = self.object, self.request.user
        peut_modifier = utilisateur.role_effectif in permissions.MODIFICATION
        contexte.update(
            peut_modifier=peut_modifier,
            interactions=services.interactions_du_client(client)[:50],
            form_interaction=InteractionForm() if peut_modifier else None,
            sections=sections.DETAIL_CLIENT.sections(client, utilisateur),
        )
        return contexte


class ClientCreateView(RoleRequiredMixin, FormView):
    roles = permissions.MODIFICATION
    form_class = ClientForm
    template_name = "customers/client_form.html"

    def form_valid(self, form):
        try:
            client = services.creer_client(**form.cleaned_data)
        except ClientError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, f"Client « {client.raison_sociale} » créé.")
        return redirect("customers:detail", pk=client.pk)


class ClientUpdateView(RoleRequiredMixin, FormView):
    roles = permissions.MODIFICATION
    form_class = ClientForm
    template_name = "customers/client_form.html"

    @property
    def client(self):
        if not hasattr(self, "_client"):
            self._client = get_object_or_404(Client, pk=self.kwargs["pk"])
        return self._client

    def get_initial(self):
        c = self.client
        return {
            "raison_sociale": c.raison_sociale,
            "ncc_nif": c.ncc_nif,
            "contact_principal": c.contact_principal,
            "telephone": c.telephone,
            "email": c.email,
            "adresse": c.adresse,
            "charge_clientele": c.charge_clientele,
            "taux_tva": c.taux_tva,
            "motif_exoneration": c.motif_exoneration,
        }

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["client"] = self.client
        return contexte

    def form_valid(self, form):
        try:
            services.modifier_client(self.client, **form.cleaned_data)
        except ClientError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, f"Fiche de « {self.client.raison_sociale} » mise à jour.")
        return redirect("customers:detail", pk=self.client.pk)


class InteractionCreateView(RoleRequiredMixin, View):
    """Ajoute une interaction à l'historique du client (POST)."""

    roles = permissions.MODIFICATION
    http_method_names = ["post"]

    def post(self, request, pk):
        client = get_object_or_404(Client, pk=pk)
        form = InteractionForm(request.POST)
        if not form.is_valid():
            for erreurs in form.errors.values():
                for erreur in erreurs:
                    messages.error(request, erreur)
            return redirect("customers:detail", pk=client.pk)
        try:
            services.enregistrer_interaction(client, request.user, **form.cleaned_data)
        except ClientError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(request, "Interaction ajoutée à l'historique.")
        return redirect("customers:detail", pk=client.pk)
