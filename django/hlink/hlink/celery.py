import os

from celery import Celery
import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hlink.settings")

app = Celery("hlink")

app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


# we have no influxdb2 in development environment
if not settings.DEBUG:
    app.conf.beat_schedule = {
        'add-every-30-seconds': {
            'task': 'configs.tasks.generate_sensor_data',
            'schedule': 30.0,
        },
    }
    app.conf.timezone = settings.TIME_ZONE
