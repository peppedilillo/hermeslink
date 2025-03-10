from django.urls import path

from . import views

app_name = "configs"
urlpatterns = [
    path("upload/", views.upload, name="upload"),
    path("test/", views.test, name="test"),
    path("submit/", views.submit, name="submit"),
    path("history/", views.history, name="history"),
    path("download/<int:config_id>/<str:format>/", views.download, name="download"),
    path("commit/<int:config_id>/", views.commit, name="commit"),
]
