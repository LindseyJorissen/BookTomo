from django.urls import path
from .views import upload_goodreads
from . import views

urlpatterns = [
    path("upload_goodreads/", upload_goodreads), path("graph/<str:book_id>/", views.book_graph_view),
    path("graph/<str:book_id>/", views.book_graph_view),

]
