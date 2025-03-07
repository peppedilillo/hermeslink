from math import sqrt

from django.contrib.auth.decorators import login_required
import django.db as db
from django.shortcuts import render
from influxdb_client import InfluxDBClient
from logger.handlers import get_cached_info_logs
from redis import Redis

from hlink import settings

COLOR_LIST = [
    c1
    for cs in [
        [c] * int(sqrt(i))
        for i, c in enumerate(
            [
                "text-green-200",
                "text-green-300",
                "text-green-400",
                "text-green-500",
                "text-green-600",
                "text-green-700",
                "text-green-800",
                "text-green-900",
                "text-green-950",
            ]
        )
    ]
    for c1 in cs
]


def greens() -> str:
    for i in range(len(COLOR_LIST)):
        yield COLOR_LIST[i]
    yield COLOR_LIST[-1]


def test_services() -> list[str]:
    results = {}

    # database connection
    try:
        db.connection.ensure_connection()
    except Exception:
        results["database"] = False
    else:
        results["database"] = True

    # database connection
    try:
        Redis.from_url(url=settings.CACHES["default"]["LOCATION"])
    except Exception:
        results["cache"] = False
    else:
        results["cache"] = True

    # web. if you are here..
    results["web"] = True

    # influxdb
    try:
        client = InfluxDBClient(url=settings.INFLUXDB_URL, token=settings.INFLUXDB_TOKEN, org=settings.INFLUXDB_ORG)
        client.api_client.call_api("/ping", "GET")
    except Exception:
        results["influxdb"] = False
    else:
        results["influxdb"] = True
    return results


@login_required
def index(request):
    logs = get_cached_info_logs()
    colors = greens()
    return render(
        request,
        "main/index.html",
        context={
            "logs": [(log, c) for log, c in zip(logs, colors)],
            "services": test_services(),
        },
    )
