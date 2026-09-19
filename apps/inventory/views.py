"""Écrans du stock : articles, fiche, entrées, ajustements, journal, sorties pour OR.

Aucune règle métier ici : les vues contrôlent le rôle, lisent le formulaire et
délèguent à ``services.py`` (conventions.md:19-23).
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from apps.accounts.mixins import RoleRequiredMixin
from apps.core.formats import nombre
from apps.garage import services as garage_services

from . import permissions, services
from .exceptions import StockError
from .forms import (
    AjustementForm,
    ArticleCreationForm,
    ArticleForm,
    EntreeForm,
    SortieForm,
)
from .models import TypeMouvement


def _alerter_si_seuil_bas(request, article) -> None:
    """Rend l'alerte de seuil visible (cahier-des-charges.md:337-338)."""
    if article.sous_seuil:
        messages.warning(
            request,
            f"Stock bas : il reste {article.quantite} x {article.reference} "
            f"(seuil minimal {article.seuil_minimal}). Pensez à réapprovisionner.",
        )


def _erreurs_du_formulaire(request, form) -> None:
    for erreurs in form.errors.values():
        for erreur in erreurs:
            messages.error(request, erreur)


class ArticleListView(RoleRequiredMixin, ListView):
    roles = permissions.CONSULTATION
    template_name = "inventory/article_list.html"
    context_object_name = "articles"
    paginate_by = 20

    def get_queryset(self):
        return services.rechercher_articles(
            recherche=self.request.GET.get("q", ""),
            categorie=self.request.GET.get("categorie", ""),
            sous_seuil=self.request.GET.get("alerte") == "1",
        )

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            recherche=self.request.GET.get("q", ""),
            categorie_choisie=self.request.GET.get("categorie", ""),
            alerte=self.request.GET.get("alerte") == "1",
            categories=services.categories_articles(),
            valeur_totale=services.valeur_totale_stock(),
            nombre_sous_seuil=services.articles_sous_seuil().count(),
            peut_modifier=self.request.user.role_effectif in permissions.MODIFICATION,
        )
        return contexte


class ArticleDetailView(RoleRequiredMixin, DetailView):
    roles = permissions.CONSULTATION
    template_name = "inventory/article_detail.html"
    context_object_name = "article"

    def get_queryset(self):
        return services.rechercher_articles()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        peut_modifier = self.request.user.role_effectif in permissions.MODIFICATION
        contexte.update(
            mouvements=services.mouvements_de_l_article(self.object),
            peut_modifier=peut_modifier,
            form_entree=EntreeForm() if peut_modifier else None,
            form_ajustement=AjustementForm() if peut_modifier else None,
        )
        return contexte


class ArticleCreateView(RoleRequiredMixin, FormView):
    roles = permissions.MODIFICATION
    form_class = ArticleCreationForm
    template_name = "inventory/article_form.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(titre="Nouvel article", bouton="Créer l'article")
        return contexte

    def form_valid(self, form):
        try:
            article = services.creer_article(**form.cleaned_data)
        except StockError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(
            self.request,
            f"Article {article.reference} créé. Son stock est à 0 : enregistrez une entrée d'achat.",
        )
        return redirect("inventory:article_detail", pk=article.pk)


class ArticleUpdateView(RoleRequiredMixin, FormView):
    roles = permissions.MODIFICATION
    form_class = ArticleForm
    template_name = "inventory/article_form.html"

    @property
    def article(self):
        if not hasattr(self, "_article"):
            self._article = get_object_or_404(services.rechercher_articles(), pk=self.kwargs["pk"])
        return self._article

    def get_initial(self):
        a = self.article
        return {
            "designation": a.designation,
            "categorie": a.categorie,
            "emplacement": a.emplacement,
            "seuil_minimal": a.seuil_minimal,
        }

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            titre=f"Modifier {self.article.reference}", bouton="Enregistrer", article=self.article
        )
        return contexte

    def form_valid(self, form):
        try:
            services.modifier_article(self.article, **form.cleaned_data)
        except StockError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, f"Article {self.article.reference} mis à jour.")
        return redirect("inventory:article_detail", pk=self.article.pk)


class EntreeView(RoleRequiredMixin, View):
    """Enregistre une entrée d'achat (POST) : le PUMP est recalculé."""

    roles = permissions.MODIFICATION
    http_method_names = ["post"]

    def post(self, request, pk):
        article = get_object_or_404(services.rechercher_articles(), pk=pk)
        form = EntreeForm(request.POST)
        if not form.is_valid():
            _erreurs_du_formulaire(request, form)
            return redirect("inventory:article_detail", pk=article.pk)
        try:
            services.enregistrer_entree(article, acteur=request.user, **form.cleaned_data)
        except StockError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(
                request,
                f"Entrée de {form.cleaned_data['quantite']} x {article.reference} enregistrée. "
                f"Stock : {article.quantite}, PUMP : {nombre(article.pump)} FCFA.",
            )
        return redirect("inventory:article_detail", pk=article.pk)


class AjustementView(RoleRequiredMixin, View):
    """Enregistre un ajustement d'inventaire (POST), toujours justifié."""

    roles = permissions.MODIFICATION
    http_method_names = ["post"]

    def post(self, request, pk):
        article = get_object_or_404(services.rechercher_articles(), pk=pk)
        form = AjustementForm(request.POST)
        if not form.is_valid():
            _erreurs_du_formulaire(request, form)
            return redirect("inventory:article_detail", pk=article.pk)
        try:
            services.ajuster_stock(article, acteur=request.user, **form.cleaned_data)
        except StockError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(
                request,
                f"Ajustement de {form.cleaned_data['variation']:+d} enregistré : "
                f"{article.quantite} x {article.reference} en stock.",
            )
            _alerter_si_seuil_bas(request, article)
        return redirect("inventory:article_detail", pk=article.pk)


class MouvementListView(RoleRequiredMixin, ListView):
    roles = permissions.CONSULTATION
    template_name = "inventory/mouvement_list.html"
    context_object_name = "mouvements"
    paginate_by = 30

    def get_queryset(self):
        return services.rechercher_mouvements(
            type_mouvement=self.request.GET.get("type"),
            recherche=self.request.GET.get("q", ""),
        )

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            types=TypeMouvement.choices,
            type_choisi=self.request.GET.get("type", ""),
            recherche=self.request.GET.get("q", ""),
        )
        return contexte


class SortieOrView(RoleRequiredMixin, View):
    """Sort des pièces du stock pour un OR ouvert (POST)."""

    roles = permissions.MODIFICATION
    http_method_names = ["post"]

    def post(self, request, pk):
        ordre = get_object_or_404(garage_services.ordres_queryset(), pk=pk)
        form = SortieForm(request.POST)
        if not form.is_valid():
            _erreurs_du_formulaire(request, form)
            return redirect("garage:detail", pk=ordre.pk)
        article, quantite = form.cleaned_data["article"], form.cleaned_data["quantite"]
        try:
            services.sortir_pour_or(article, quantite=quantite, ordre=ordre, acteur=request.user)
        except StockError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(
                request, f"{quantite} x {article.reference} sortie(s) pour l'OR {ordre.numero}."
            )
            _alerter_si_seuil_bas(request, article)
        return redirect("garage:detail", pk=ordre.pk)
