import logging

from django.http import HttpRequest
from django.utils import timezone
from redis import Redis

from hlink import settings

logger = logging.getLogger("hlink")


STATUS_ON = 0
STATUS_OFF = 1
STATUS_UNCERTAIN = 2

UNCERTAIN_STATUS = {
    "services": [
        ("web", STATUS_ON),
        ("cache", STATUS_OFF),
        ("database", STATUS_UNCERTAIN),
        ("dashboards", STATUS_UNCERTAIN),
    ],
    "status_timestamp": timezone.now().strftime("%H:%M:%S"),
}


def boold(r: dict, key: str) -> bool:
    """Helper function transforming a Redis binary key into a boolean value.
    Returns True if the key exists and its value is '1', False otherwise."""
    if (k := key.encode()) in r:
        return r[k] == b"1"
    return False


def vald(r: dict, key: str) -> int:
    """Helper function transforming a Redis value into a service status code.
    Returns STATUS_ON if the key exists and is true, STATUS_OFF otherwise."""
    return STATUS_ON if boold(r, key) else STATUS_OFF


def service_status(request: HttpRequest) -> dict:
    """
    Context processor providing service status information for the site header.
    Retrieves status information from Redis for web, cache, database, and dashboard services.

    Returns a dictionary with service status information or UNCERTAIN_STATUS if Redis is unavailable.
    """
    try:
        redis_default = Redis.from_url(url=settings.CACHES["default"]["LOCATION"])
    except Exception:
        # if redis is off we don't know the status of the services
        return UNCERTAIN_STATUS

    r = redis_default.hgetall("service_status")
    return (
        {
            "services": [
                ("web", vald(r, "status_web")),
                ("cache", vald(r, "status_cache")),
                ("database", vald(r, "status_db")),
                ("dashboards", vald(r, "status_dashboards")),
            ],
            "services_ts": r[b"status_timestamp"].decode(),
        }
        if r
        else {}
    )
