from django.urls import path
from .views import upload_goodreads

urlpatterns = [
    path("upload_goodreads/", upload_goodreads),
]
