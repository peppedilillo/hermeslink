from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    class Gang(models.TextChoices):
        MOC = "m", "MOC"
        SOC = "s", "SOC"
        VISITOR = "v", "visitor"

    gang = models.CharField(
        max_length=1,
        choices=Gang,
        default=Gang.VISITOR,
    )
