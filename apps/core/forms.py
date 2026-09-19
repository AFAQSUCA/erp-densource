from django import forms

CHAMP = (
    "block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm "
    "text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-marque-600 "
    "focus:outline-none focus:ring-2 focus:ring-marque-600/30"
)


class StyleTailwindMixin:
    """Applique le style Tailwind commun à tous les champs d'un formulaire."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for champ in self.fields.values():
            champ.widget.attrs.setdefault("class", CHAMP)
