from django.contrib.auth import logout as auth_logout
from django.shortcuts import render


def logout(request):
    auth_logout(request)
    return render(request, "registration/logout.html")
