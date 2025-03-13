from django.contrib.staticfiles.storage import staticfiles_storage
from django.urls import path
from django.views.generic import RedirectView
from main.views import auth_status
from main.views import index

app_name = "main"
urlpatterns = [
    path("", index, name="index"),
    path("auth-status/", auth_status, name="auth_status"),
    path("favicon.ico", RedirectView.as_view(url=staticfiles_storage.url("pics/favicon.ico"))),
]
