from django.core.validators import MinLengthValidator
from django.db import models

from hhelm.settings import AUTH_USER_MODEL

CustomUser = AUTH_USER_MODEL


# Create your models here.
class Configuration(models.Model):
    """
    Core configuration model. Stores configurations as binary blobs, as well as
    a few metadata informations, including authors, creation date, delivery status.
    The upload field is inteded to be modified later, once we get a confirmation
    on the uploaded status, which should supposedly come with a timestamp (`upload_time`)
    """
    MODELS = (
        ("1", "H1"),
        ("2", "H2"),
        ("3", "H3"),
        ("4", "H4"),
        ("5", "H5"),
        ("6", "H6"),
    )

    date = models.DateTimeField(auto_now_add=True)
    author = models.ForeignKey(to=CustomUser, related_name="configurations", on_delete=models.PROTECT)
    delivered = models.BooleanField(default=False)
    uploaded = models.BooleanField(default=False)
    upload_time = models.DateTimeField(null=True, default=None)
    model = models.CharField(max_length=1, choices=MODELS)
    acq = models.BinaryField(max_length=20, validators=[MinLengthValidator(20)])
    acq0 = models.BinaryField(max_length=20, validators=[MinLengthValidator(20)])
    asic0 = models.BinaryField(max_length=124, validators=[MinLengthValidator(124)])
    asic1 = models.BinaryField(max_length=124, validators=[MinLengthValidator(124)])
    bee = models.BinaryField(max_length=64, validators=[MinLengthValidator(64)])