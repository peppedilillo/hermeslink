from math import sqrt

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest
from django.http import HttpResponse
from django.shortcuts import render
from logger.handlers import get_cached_info_logs

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
    """Helper returning shades of green one at a time"""
    for i in range(len(COLOR_LIST)):
        yield COLOR_LIST[i]
    yield COLOR_LIST[-1]


@login_required
def index(request: HttpRequest) -> HttpResponse:
    """Homepage view."""
    logs = get_cached_info_logs()
    colors = greens()
    return render(
        request,
        "main/index.html",
        context={
            "logs": [(log, c) for log, c in zip(logs, colors)],
        },
    )


@login_required
def auth_status(request):
    """Endpoint for nginx auth_request, returns 200 if user is authenticated
    and attach username to the header."""
    response = HttpResponse(status=200)
    response.headers["username"] = request.user.username
    return response
