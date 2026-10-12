"""Écran « Paramètres » (ADMIN, DIRECTION). Les règles sont dans ``parametres.services`` ; la vue n'ajoute que
l'affichage."""

from django.contrib import messages
from django.shortcuts import redirect
from django.views.generic import FormView

from apps.accounts.mixins import RoleRequiredMixin

from . import permissions, services
from .forms import ParametresForm
from .models import Parametres

SECTIONS = (
    ("Alertes d'expiration", ("delai_alerte_jours",)),
    (
        "Carburant et compteur",
        (
            "seuil_conso_jaune_pct",
            "seuil_conso_rouge_pct",
            "seuil_conso_saisie_pct",
            "conso_min_l100",
            "conso_max_l100",
            "ecart_km_max",
        ),
    ),
    ("Clients et facturation", ("tva_defaut", "delai_paiement_defaut_jours")),
    ("Congés", ("delai_validation_n1_heures", "delai_validation_n2_heures", "droit_annuel_jours")),
)
assert sorted(c for _, champs in SECTIONS for c in champs) == sorted(services.CHAMPS)


class ParametresView(RoleRequiredMixin, FormView):
    roles = permissions.MODIFICATION
    template_name = "parametres/parametres.html"
    form_class = ParametresForm

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "instance": services.parametres()}

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(en_vigueur=services.parametres(), **kwargs)
        form, defauts = contexte["form"], Parametres()  # valeurs du cahier des charges
        contexte["sections"] = [
            {"titre": titre, "champs": [(form[champ], getattr(defauts, champ)) for champ in champs]}
            for titre, champs in SECTIONS
        ]
        return contexte

    def form_valid(self, form):
        try:
            services.modifier_parametres(
                self.request.user, **{champ: form.cleaned_data[champ] for champ in services.CHAMPS}
            )
        except services.ParametresInvalides as erreur:
            for champ, messages_champ in erreur.erreurs.items():
                for message in messages_champ:
                    form.add_error(champ if champ in form.fields else None, message)
            return self.form_invalid(form)
        messages.success(self.request, "Paramètres enregistrés : ils s'appliquent dès maintenant.")
        return redirect("parametres:modifier")
