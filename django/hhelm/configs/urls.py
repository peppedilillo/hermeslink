from django.urls import path

from . import views

app_name = "configs"
urlpatterns = [
    path("upload/", views.image_upload, name="image_upload"),
]