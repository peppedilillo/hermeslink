from django.urls import path

from .views import logout

app_name = "accounts"
urlpatterns = [
    path("logout/", logout, name="logout"),
]
