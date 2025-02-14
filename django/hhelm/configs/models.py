from django.core.validators import MinLengthValidator
from django.db import models

import hermes.payloads
from hhelm.settings import AUTH_USER_MODEL

CustomUser = AUTH_USER_MODEL


class Configuration(models.Model):
    """
    Core configuration model. Stores configurations as binary blobs, as well as
    a few metadata informations, including authors, creation date, delivery status.
    The upload field is inteded to be modified later, once we get a confirmation
    on the uploaded status, which should supposedly come with a timestamp (`upload_time`)
    """

    MODELS = tuple(zip(hermes.payloads.NAMES, hermes.payloads.NAMES))

    date = models.DateTimeField(auto_now_add=True)
    author = models.ForeignKey(to=CustomUser, related_name="configurations", on_delete=models.PROTECT)
    delivered = models.BooleanField(default=False)
    deliver_time = models.DateTimeField(null=True, blank=True)
    uploaded = models.BooleanField(default=False)
    upload_time = models.DateTimeField(null=True, blank=True)
    model = models.CharField(max_length=2, choices=MODELS)
    acq0 = models.BinaryField(max_length=20, validators=[MinLengthValidator(20)])
    acq = models.BinaryField(max_length=20, validators=[MinLengthValidator(20)])
    asic0 = models.BinaryField(max_length=124, validators=[MinLengthValidator(124)])
    asic1 = models.BinaryField(max_length=124, validators=[MinLengthValidator(124)])
    bee = models.BinaryField(max_length=64, validators=[MinLengthValidator(64)])
