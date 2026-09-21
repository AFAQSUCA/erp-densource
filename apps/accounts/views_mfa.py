"""Écrans de la double authentification : activation, saisie du code, codes de secours.

Aucune règle ici : ``mfa.py`` décide, ``throttle.py`` limite les essais. Ces pages sont les seules
accessibles à un ADMIN ou une DIRECTION dont la session n'est pas encore vérifiée (voir
``middleware.py``). Elles n'ont de sens que pour les rôles soumis à la MFA : les autres reçoivent 404.
"""

from __future__ import annotations

import io

import qrcode
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import FormView

from . import mfa, throttle
from .forms import CodeMFAForm
from .signals import mfa_evenement


class _MFABase(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not mfa.mfa_requise(request.user):
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def prochaine_page(self) -> str:
        cible = self.request.GET.get("next") or self.request.POST.get("next") or ""
        if cible and url_has_allowed_host_and_scheme(
            cible, allowed_hosts={self.request.get_host()}, require_https=self.request.is_secure()
        ):
            return cible
        return reverse("home")

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["next"] = self.request.GET.get("next") or self.request.POST.get("next") or ""
        return contexte

    def _refus_si_bloque(self, form):
        """Réponse 429 si trop de codes faux récemment ; ``None`` sinon."""
        restant = throttle.mfa_secondes_restantes(self.request.user)
        if not restant:
            return None
        form.add_error(
            "code",
            f"Trop de codes incorrects. Réessayez dans {throttle.phrase_attente(restant)}.",
        )
        reponse = self.render_to_response(self.get_context_data(form=form))
        reponse.status_code = 429
        return reponse

    def _signaler(self, evenement: str, succes: bool = True):
        mfa_evenement.send(
            sender=type(self),
            request=self.request,
            utilisateur=self.request.user,
            evenement=evenement,
            succes=succes,
        )


class MFAVerifierView(_MFABase, FormView):
    """Saisie du code à chaque ouverture de session."""

    template_name = "accounts/mfa_verifier.html"
    form_class = CodeMFAForm

    def get(self, request, *args, **kwargs):
        if mfa.est_verifiee(request):
            return redirect(self.prochaine_page())
        if mfa.appareil_actif(request.user) is None:
            return redirect(reverse("accounts:mfa_activer"))
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if mfa.appareil_actif(request.user) is None:
            return redirect(reverse("accounts:mfa_activer"))
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        refus = self._refus_si_bloque(form)
        if refus is not None:
            return refus
        utilisateur = self.request.user
        if not mfa.verifier_code(utilisateur, form.cleaned_data["code"]):
            throttle.mfa_enregistrer_echec(utilisateur)
            self._signaler("code_refuse", succes=False)
            form.add_error("code", "Code incorrect ou déjà utilisé.")
            return self.form_invalid(form)
        throttle.mfa_reinitialiser(utilisateur)
        mfa.marquer_verifiee(self.request)
        self._signaler("code_accepte")
        return redirect(self.prochaine_page())


class MFAActiverView(_MFABase, FormView):
    """Première utilisation : scanner le QR code, confirmer avec un premier code, noter les codes de secours."""

    template_name = "accounts/mfa_activer.html"
    form_class = CodeMFAForm

    def get(self, request, *args, **kwargs):
        if mfa.appareil_actif(request.user) is not None:
            return redirect(self.prochaine_page() if mfa.est_verifiee(request) else reverse("accounts:mfa_verifier"))
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if mfa.appareil_actif(request.user) is not None:
            return redirect(reverse("accounts:mfa_verifier"))
        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        appareil = mfa.preparer_activation(self.request.user)
        contexte["secret"] = " ".join(appareil.secret[i : i + 4] for i in range(0, len(appareil.secret), 4))
        return contexte

    def form_valid(self, form):
        refus = self._refus_si_bloque(form)
        if refus is not None:
            return refus
        utilisateur = self.request.user
        try:
            codes = mfa.confirmer_activation(utilisateur, form.cleaned_data["code"])
        except mfa.CodeInvalide as erreur:
            throttle.mfa_enregistrer_echec(utilisateur)
            self._signaler("activation_refusee", succes=False)
            form.add_error("code", str(erreur))
            return self.form_invalid(form)
        throttle.mfa_reinitialiser(utilisateur)
        mfa.marquer_verifiee(self.request)
        self._signaler("activation")
        return _page_codes(self.request, codes, apres_activation=True, suite=self.prochaine_page())


class MFAQrView(_MFABase, View):
    """Image du QR code d'activation : seulement tant que l'appareil n'est pas confirmé, jamais mise en cache."""

    def get(self, request):
        try:
            appareil = mfa.preparer_activation(request.user)
        except mfa.DejaActive as erreur:
            raise Http404 from erreur
        tampon = io.BytesIO()
        qrcode.make(mfa.uri_provisionnement(appareil), box_size=8, border=2).save(tampon, format="PNG")
        reponse = HttpResponse(tampon.getvalue(), content_type="image/png")
        reponse["Cache-Control"] = "no-store, private"
        return reponse


class MFACodesView(_MFABase, FormView):
    """Régénérer les codes de secours (avec un code de l'application, pas un code de secours)."""

    template_name = "accounts/mfa_codes.html"
    form_class = CodeMFAForm

    def dispatch(self, request, *args, **kwargs):
        # Cette page fait partie des pages libres de la porte MFA : elle vérifie elle-même que la
        # session est vérifiée, pour qu'un mot de passe volé ne permette pas de toucher aux codes.
        utilisateur = request.user
        if utilisateur.is_authenticated and mfa.mfa_requise(utilisateur) and not mfa.est_verifiee(request):
            return redirect(reverse("accounts:mfa_verifier"))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["restants"] = mfa.codes_secours_restants(self.request.user)
        return contexte

    def get(self, request, *args, **kwargs):
        if mfa.appareil_actif(request.user) is None:
            return redirect(reverse("accounts:mfa_activer"))
        return super().get(request, *args, **kwargs)

    def form_valid(self, form):
        refus = self._refus_si_bloque(form)
        if refus is not None:
            return refus
        utilisateur = self.request.user
        try:
            codes = mfa.regenerer_codes_secours(utilisateur, form.cleaned_data["code"])
        except mfa.CodeInvalide:
            throttle.mfa_enregistrer_echec(utilisateur)
            self._signaler("codes_refuses", succes=False)
            form.add_error("code", "Code incorrect ou déjà utilisé.")
            return self.form_invalid(form)
        throttle.mfa_reinitialiser(utilisateur)
        self._signaler("codes_regeneres")
        return _page_codes(self.request, codes, apres_activation=False, suite=reverse("home"))


def _page_codes(request, codes, *, apres_activation: bool, suite: str):
    """Affiche les codes de secours une seule fois (réponse directe, jamais mise en cache)."""
    reponse = render(
        request,
        "accounts/mfa_codes_affiches.html",
        {"codes": codes, "apres_activation": apres_activation, "suite": suite},
    )
    reponse["Cache-Control"] = "no-store, private"
    return reponse
