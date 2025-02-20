from django.urls import path

from . import views

app_name = "configs"
urlpatterns = [
    path("upload/", views.upload, name="upload"),
    path("test/", views.test, name="test"),
    path("deliver/", views.deliver, name="deliver"),
    path("history/", views.history, name="history"),
    path("pending/", views.pending, name="pending"),
    path("download/<int:config_id>/<str:format>/", views.download, name="download"),
    path("commit/<int:config_id>/", views.commit, name="commit"),
]
