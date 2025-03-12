import logging

from django.http import HttpRequest
from django.utils import timezone
from redis import Redis

from hlink import settings

logger = logging.getLogger("hlink")


STATUS_ON=0
STATUS_OFF=1
STATUS_UNCERTAIN=2

UNCERTAIN_STATUS = {
    "services": [
        ('web', STATUS_ON),
        ('cache', STATUS_OFF),
        ('database', STATUS_UNCERTAIN),
        ('dashboards', STATUS_UNCERTAIN),
    ],
    "status_timestamp": timezone.now().strftime("%H:%M:%S"),
}

def boold(r: dict, key: str) -> bool:
    """Helper function transforming a redis binary key into a bool."""
    if (k := key.encode()) in r:
        return r[k] == b"1"
    return False

def vald(r: dict, key: str) -> int:
    """Helper function transforming a redis value into a status."""
    return STATUS_ON if boold(r, key) else STATUS_OFF


def service_status(request: HttpRequest) -> dict:
    """A context preprocessor providing useful info on service status."""
    try:
        redis_default = Redis.from_url(url=settings.CACHES["default"]["LOCATION"])
    except Exception:
        # if redis is off we don't know the status of the services
        return UNCERTAIN_STATUS

    r = redis_default.hgetall("service_status")
    return {
        "services": [
            ('web', vald(r, "status_web")),
            ('cache', vald(r, "status_cache")),
            ('database', vald(r, "status_db")),
            ('dashboards', vald(r, "status_dashboards")),
        ],
        "services_ts": r[b"status_timestamp"].decode(),
    } if r else {}

