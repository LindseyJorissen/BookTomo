from django.urls import path
from . import views

urlpatterns = [
    path("upload_goodreads/", views.upload_goodreads),
    path("upload_progress/", views.upload_progress_view),
    path("graph/<str:book_id>/", views.book_graph_view),
    path("covers/", views.book_covers_view),
]
