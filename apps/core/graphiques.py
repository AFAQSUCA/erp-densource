"""Préparation des graphiques du tableau de bord : des données à ce que le gabarit affiche.

Aucun calcul métier ici : on reçoit des séries déjà calculées (par les services des apps) et on
en tire les proportions, les graduations et les libellés. Le rendu est du HTML/CSS (classes
``viz-*`` de ``frontend/input.css``), donc sans script, compatible avec la CSP stricte, et le
texte reste du vrai texte (lisible, sélectionnable, lu par les lecteurs d'écran).

Deux formes seulement, choisies selon le travail à faire :
- ``barres_horizontales`` : comparer des grandeurs par catégorie (statuts, départements, clients) ;
- ``colonnes_groupees`` : suivre 2 ou 3 séries dans le temps (CA, encaissé, charges par mois).
Les deux portent une équivalence en tableau (``tableau``) : rien n'est lisible uniquement à la souris.
"""

from __future__ import annotations

from decimal import Decimal

from .formats import nombre

# Palette catégorielle validée (dataviz/scripts/validate_palette.js, surface #ffffff) : le bleu,
# l'orange et l'aqua, dans cet ordre. Les codes couleur vivent dans frontend/input.css.
MAX_SERIES = 3
GRADUATIONS = 4  # nombre d'intervalles de l'axe vertical

_PAS = (1, 2, 2.5, 5, 10)
_PAS_ENTIERS = (1, 2, 5, 10)  # des comptes (missions...) : pas de graduation à virgule


def _pas_lisible(brut: float, pas=_PAS) -> float:
    """Plus petit pas « rond » (1, 2, 2,5, 5 × 10^n) supérieur ou égal à ``brut``."""
    if brut <= 0:
        return 1
    puissance = 10 ** (len(str(int(brut))) - 1) if brut >= 1 else 1
    for facteur in pas:
        if facteur * puissance >= brut:
            return facteur * puissance
    return 10 * puissance


def compact(valeur) -> str:
    """Valeur d'axe courte : ``0``, ``500 k``, ``1,5 M``, ``2 Md``."""
    valeur = Decimal(valeur)
    for seuil, suffixe in ((Decimal(10) ** 9, "Md"), (Decimal(10) ** 6, "M"), (Decimal(10) ** 3, "k")):
        if abs(valeur) >= seuil:
            reduit = valeur / seuil
            decimales = 0 if reduit == reduit.to_integral_value() else 1
            return f"{nombre(reduit, decimales)} {suffixe}"
    return nombre(valeur)


def barres_horizontales(lignes, *, unite: str = "", maximum=None) -> dict:
    """Barres horizontales, une par catégorie, valeur au bout de la barre.

    ``lignes`` : suite de dicts ``libelle``, ``valeur`` et, facultatif, ``url`` (lien du libellé) et
    ``detail`` (texte secondaire). L'échelle part de 0 ; ``maximum`` la fixe (sinon : la plus grande
    valeur). Retourne ``{"lignes": [...], "unite": ..., "vide": bool}`` ; chaque ligne reçoit
    ``valeur_texte`` et ``largeur`` (pourcentage entier de la piste, 0 pour une valeur nulle).
    """
    lignes = [dict(ligne) for ligne in lignes]
    plus_grand = Decimal(maximum) if maximum is not None else max((Decimal(l["valeur"]) for l in lignes), default=0)
    for ligne in lignes:
        valeur = Decimal(ligne["valeur"])
        ligne["valeur_texte"] = nombre(valeur)
        if valeur > 0 and plus_grand > 0:
            # jamais moins de 1 % : une valeur non nulle doit rester visible
            ligne["largeur"] = max(1, min(100, round(valeur / plus_grand * 100)))
        else:
            ligne["largeur"] = 0
    return {
        "lignes": lignes,
        "unite": unite,
        "vide": not any(Decimal(l["valeur"]) for l in lignes),
    }


def colonnes_groupees(categories, series, *, unite: str = "", entier: bool = False) -> dict:
    """Colonnes groupées : une grappe par catégorie (un mois), une colonne par série.

    ``categories`` : libellés de l'axe horizontal. ``series`` : suite de dicts ``nom`` et ``valeurs``
    (une par catégorie, ≥ 0), 3 au plus (au-delà, regrouper ou faire deux graphiques : la palette
    validée ne garantit pas davantage). La couleur suit la série (rang 1, 2, 3), jamais sa valeur.
    ``entier`` : des comptes, l'axe ne graduera qu'en nombres entiers.

    Retourne :
    - ``graduations`` : de haut en bas, ``etiquette`` et ``position`` (% depuis le bas) ;
    - ``grappes`` : ``libelle`` (+ ``libelle_court`` et ``sous_libelle`` pour l'axe), ``colonnes`` (``serie``, ``rang``, ``hauteur`` %, ``valeur_texte``) et
      ``bord`` (``debut``/``milieu``/``fin`` : de quel côté l'infobulle s'aligne pour ne pas déborder) ;
    - ``legende`` : ``nom`` et ``rang`` ; ``tableau`` : ``entetes`` et ``lignes`` ; ``vide``.
    """
    series = list(series)
    if len(series) > MAX_SERIES:
        raise ValueError(f"{MAX_SERIES} séries au plus par graphique")
    valeurs = [[Decimal(v) for v in s["valeurs"]] for s in series]
    plus_grand = max((v for serie in valeurs for v in serie), default=Decimal(0))
    pas = _pas_lisible(float(plus_grand) / GRADUATIONS, _PAS_ENTIERS if entier else _PAS) if plus_grand > 0 else 1
    haut = Decimal(str(pas)) * GRADUATIONS

    graduations = [
        {"etiquette": compact(haut * i / GRADUATIONS), "position": round(100 * i / GRADUATIONS)}
        for i in range(GRADUATIONS, -1, -1)
    ]

    grappes = []
    dernier = len(categories) - 1
    for i, libelle in enumerate(categories):
        colonnes = []
        for rang, (serie, valeurs_serie) in enumerate(zip(series, valeurs), start=1):
            valeur = valeurs_serie[i]
            colonnes.append({
                "serie": serie["nom"],
                "rang": rang,
                # jamais moins de 1 % : une valeur non nulle doit rester visible
                "hauteur": max(1.0, round(float(valeur / haut * 100), 1)) if valeur > 0 else 0,
                "valeur_texte": nombre(valeur),
            })
        court, _, suffixe = libelle.rpartition(" ")
        grappes.append({
            "libelle": libelle,
            # sur l'axe, le dernier mot (l'année) passe à la ligne : 6 mois tiennent sur un écran de téléphone
            "libelle_court": court or libelle,
            "sous_libelle": suffixe if court else "",
            "colonnes": colonnes,
            "bord": "debut" if i == 0 else "fin" if i == dernier else "milieu",
        })

    return {
        "graduations": graduations,
        "grappes": grappes,
        "legende": [{"nom": s["nom"], "rang": rang} for rang, s in enumerate(series, start=1)],
        "unite": unite,
        "tableau": {
            "entetes": [s["nom"] for s in series],
            "lignes": [
                {"libelle": libelle, "valeurs": [nombre(valeurs[j][i]) for j in range(len(series))]}
                for i, libelle in enumerate(categories)
            ],
        },
        "vide": plus_grand == 0,
    }
