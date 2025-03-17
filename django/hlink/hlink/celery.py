import os

from celery import Celery

from hlink import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hlink.settings")

app = Celery("hlink")

app.conf.timezone = settings.TIME_ZONE
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "add-every-5-minutes": {
        "task": "main.tasks.check_services",
        "schedule": 300.0,
    },
}
