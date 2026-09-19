import factory

from apps.inventory.models import Article


class ArticleFactory(factory.django.DjangoModelFactory):
    """Article à stock nul et PUMP nul (comme ``creer_article``)."""

    class Meta:
        model = Article

    reference = factory.Sequence(lambda n: f"REF-{n:04d}")
    designation = factory.Sequence(lambda n: f"Plaquettes de frein {n}")
    categorie = "Freinage"
    emplacement = "Rayon A1"
