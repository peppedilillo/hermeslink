import logging
import re

from django.utils import timezone
from redis import Redis

from hlink import settings

# we keep infos in a separate queue, these will be disposed to the user
CACHE_INFO_LOGS = "hlink_cache_info_logs"
CACHE_INFO_LOGS_LIMIT = 15

CACHE_LOGS = "hlink_cache_logs"
CACHE_LOGS_LIMIT = 100

TIMESTAMP_PATTERN = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}: .*"
TIMESTAMP_PATTERN_LEN = 18

class CacheHandler(logging.Handler):
    """A log handler towards a database."""

    def __init__(
        self,
    ):
        super(CacheHandler, self).__init__()

    def emit(self, record):
        """
        Logs a message to a finite-sized queue. Info message are also stored in a
        separate queue which can be displayed to the user.
        """
        redis_default = Redis.from_url(url=settings.CACHES["default"]["LOCATION"])
        if re.match(TIMESTAMP_PATTERN, record.msg):
            # for special messages, you can bypass the automatic timestamp by prepending
            # one to the log record. hack-ish, but who gives a fuck.
            ts, msg = record.msg[:TIMESTAMP_PATTERN_LEN], record.msg[TIMESTAMP_PATTERN_LEN:]
            ts = ts[:-2]  # spits out the `: ` separator
        else:
            # yes we could simply use record.asctime. but this guarantees we will be
            # displaying timestamps coherently to django timezone settings
            ts = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M")
            msg = record.msg

        # house rule: info message can be shared with the users
        if record.levelno == logging.INFO:
            n = redis_default.lpush(CACHE_INFO_LOGS, f"{ts}: {msg}")
            if n > CACHE_INFO_LOGS_LIMIT:
                _ = redis_default.rpop(CACHE_INFO_LOGS)

        n = redis_default.lpush(CACHE_LOGS, f"{ts} {record.levelname}: {msg}")
        if n > CACHE_LOGS_LIMIT:
            _ = redis_default.rpop(CACHE_LOGS)


def get_cached_info_logs() -> list[str]:
    """
    Returns the cached INFO-level log messages from Redis.
    Limited to the most recent CACHE_INFO_LOGS_LIMIT entries.
    """
    redis_default = Redis.from_url(url=settings.CACHES["default"]["LOCATION"])
    return [bs.decode() for bs in redis_default.lrange(CACHE_INFO_LOGS, 0, CACHE_INFO_LOGS_LIMIT - 1)]


def get_cached_logs() -> list[str]:
    """
    Returns all cached log messages from Redis regardless of log level.
    Limited to the most recent CACHE_LOGS_LIMIT entries.
    """
    redis_default = Redis.from_url(url=settings.CACHES["default"]["LOCATION"])
    return [bs.decode() for bs in redis_default.lrange(CACHE_LOGS, 0, CACHE_LOGS_LIMIT - 1)]
