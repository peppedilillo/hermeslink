import logging

from celery import shared_task
import django.db as db
from django.utils import timezone
from influxdb_client import InfluxDBClient
from redis import Redis

from hlink import settings

logger = logging.getLogger("hlink")


@shared_task
def check_services():
    """An asynchronous task checking on hlink services and reporting their
    status through redis."""
    # web. if you are here...
    status_web = 1

    # database connection
    try:
        db.connection.ensure_connection()
    except Exception:
        status_db = 0
        logging.warning("Database not available.")
    else:
        status_db = 1

    # influxdb
    try:
        client = InfluxDBClient(url=settings.INFLUXDB_URL, token=settings.INFLUXDB_TOKEN, org=settings.INFLUXDB_ORG)
        client.api_client.call_api("/ping", "GET")
    except Exception:
        status_influx = 0
        logging.warning("Influxdb not available.")
    else:
        status_influx = 1

    # cache status
    try:
        redis_default = Redis.from_url(url=settings.CACHES["default"]["LOCATION"])
    except Exception:
        # we will not be able to store in redis, so we return early
        logging.warning("Redis not available.")
        return
    else:
        status_redis = 1

    return redis_default.hset(
        "service_status",
        mapping={
            "status_web": status_web,
            "status_db": status_db,
            "status_dashboards": status_influx,
            "status_cache": status_redis,
            "status_timestamp": timezone.now().strftime("%H:%M:%S"),
        },
    )
