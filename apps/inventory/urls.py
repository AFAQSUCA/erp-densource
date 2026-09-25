from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    path("", views.ArticleListView.as_view(), name="articles"),
    path("imprimer/", views.ArticleImprimerView.as_view(), name="articles_imprimer"),
    path("articles/nouveau/", views.ArticleCreateView.as_view(), name="article_creer"),
    path("articles/<int:pk>/", views.ArticleDetailView.as_view(), name="article_detail"),
    path("articles/<int:pk>/modifier/", views.ArticleUpdateView.as_view(), name="article_modifier"),
    path("articles/<int:pk>/entree/", views.EntreeView.as_view(), name="entree"),
    path("articles/<int:pk>/ajustement/", views.AjustementView.as_view(), name="ajustement"),
    path("mouvements/", views.MouvementListView.as_view(), name="mouvements"),
    path("or/<int:pk>/sortie/", views.SortieOrView.as_view(), name="sortie_or"),
]
