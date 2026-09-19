from apps.core.sections import RegistreSections


def _bloc(nom):
    return lambda *args, **kwargs: {"template": f"{nom}.html", "contexte": {"args": args}}


def test_un_registre_vide_ne_donne_aucun_bloc():
    assert RegistreSections().sections("x") == []


def test_les_blocs_sont_retournes_dans_l_ordre_d_enregistrement():
    registre = RegistreSections()
    registre.enregistrer(_bloc("a"))
    registre.enregistrer(_bloc("b"))

    assert [b["template"] for b in registre.sections()] == ["a.html", "b.html"]


def test_les_arguments_sont_transmis_aux_fournisseurs():
    registre = RegistreSections()
    registre.enregistrer(_bloc("a"))

    assert registre.sections("camion", "utilisateur")[0]["contexte"]["args"] == (
        "camion",
        "utilisateur",
    )


def test_un_fournisseur_qui_retourne_none_est_ignore():
    registre = RegistreSections()
    registre.enregistrer(lambda *args, **kwargs: None)
    registre.enregistrer(_bloc("b"))

    assert [b["template"] for b in registre.sections()] == ["b.html"]


def test_enregistrer_deux_fois_le_meme_fournisseur_est_sans_effet():
    registre = RegistreSections()
    fournisseur = _bloc("a")

    registre.enregistrer(fournisseur)
    registre.enregistrer(fournisseur)

    assert len(registre.sections()) == 1
