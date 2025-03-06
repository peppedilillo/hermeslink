import logging
from django.utils import timezone
from hlink import settings
from redis import Redis

# we keep infos in a separate queue, these will be disposed to the user
CACHE_INFO_LOGS = "hlink_cache_info_logs"
CACHE_INFO_LOGS_LIMIT = 15

CACHE_LOGS = "hlink_cache_logs"
CACHE_LOGS_LIMIT = 100



class CacheHandler(logging.Handler):
    """A log handler towards a database."""
    def __init__(self,):

        super(CacheHandler, self).__init__()


    def emit(self, record):
        redis_default = Redis.from_url(url=settings.CACHES["default"]["LOCATION"])
        timestamp = timezone.now().strftime("%Y-%M-%d %H:%m")

        if record.levelno == logging.INFO:
            n = redis_default.lpush(CACHE_INFO_LOGS, f"{timestamp}: {record.msg}")
            if n > CACHE_INFO_LOGS_LIMIT:
                _ = redis_default.rpop(CACHE_INFO_LOGS)

        n = redis_default.lpush(CACHE_LOGS, f"{timestamp} {record.levelname}: {record.msg}")
        if n > CACHE_LOGS_LIMIT:
            _ = redis_default.rpop(CACHE_LOGS)


def get_cached_info_logs() -> list[str]:
    """Returns the cached info logs."""
    redis_default = Redis.from_url(url=settings.CACHES["default"]["LOCATION"])
    return [bs.decode() for bs in redis_default.lrange(CACHE_INFO_LOGS, 0, CACHE_INFO_LOGS_LIMIT - 1)]


def get_cached_logs() -> list[str]:
    """Returns all the cached logs."""
    redis_default = Redis.from_url(url=settings.CACHES["default"]["LOCATION"])
    return [bs.decode() for bs in redis_default.lrange(CACHE_LOGS, 0, CACHE_LOGS_LIMIT - 1)]
