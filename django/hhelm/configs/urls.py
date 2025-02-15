from django.urls import path

from . import views

app_name = "configs"
urlpatterns = [
    path("upload/", views.upload, name="upload"),
    path("test/", views.test, name="test"),
    path("deliver/", views.deliver, name="deliver"),
    path("history/", views.history, name="history"),
    path("download/<int:config_id>/<str:format>/", views.download_config, name="download_config"),
]
