from django.urls import path
from . import views

urlpatterns = [
    path("upload_goodreads/", views.upload_goodreads),
    path("upload_progress/", views.upload_progress_view),
    path("graph/<str:book_id>/", views.book_graph_view),
    path("covers/", views.book_covers_view),
    path("universe_graph/", views.universe_graph_view),
    path("cluster_graph/", views.cluster_graph_view),
    path("full_network/", views.full_network_view),
    path("book_details/<str:book_id>/", views.book_details_view),
    path("best_recommendation/", views.best_recommendation_view),
    path("filter_options/", views.filter_options_view),
]
