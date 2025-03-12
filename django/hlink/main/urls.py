from django.contrib.staticfiles.storage import staticfiles_storage
from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "main"
urlpatterns = [
    path("", views.index, name="index"),
    path("favicon.ico", RedirectView.as_view(url=staticfiles_storage.url("pics/favicon.ico"))),
]
