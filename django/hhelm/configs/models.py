from hashlib import sha256
from typing import Iterable, Literal

from django.db.models import CheckConstraint, Q, F
from django.utils import timezone

from django.core.validators import MinLengthValidator, ValidationError
from django.db import models

from hermes import CONFIG_TYPES, CONFIG_SIZE
from hermes import SPACECRAFTS_NAMES
from hhelm.settings import AUTH_USER_MODEL
from .validators import crc16

CustomUser = AUTH_USER_MODEL


def validate_not_future(value):
    if value is not None and value > timezone.now():
        raise ValidationError("Date cannot be in the future.")


class Configuration(models.Model):
    """
    Core configuration model. Stores configurations as binary blobs, as well as
    a few metadata informations, including authors, creation date, delivery status.
    The upload field is inteded to be modified later, once we get a confirmation
    on the uploaded status, which should supposedly come with a timestamp (`upload_time`)
    """
    MODELS = tuple(zip(SPACECRAFTS_NAMES, SPACECRAFTS_NAMES))

    date = models.DateTimeField(auto_now_add=True)
    author = models.ForeignKey(to=CustomUser, related_name="configurations", on_delete=models.PROTECT)
    # this field is for when a configuration is first sent to the MOC
    delivered = models.BooleanField(default=False)
    deliver_time = models.DateTimeField(null=True, blank=True, validators=[validate_not_future])
    # this field is for when a configuration is upload on-board by the MOC
    uploaded = models.BooleanField(default=False)
    upload_time = models.DateTimeField(null=True, blank=True, validators=[validate_not_future])
    model = models.CharField(max_length=2, choices=MODELS)
    acq0 = models.BinaryField(max_length=CONFIG_SIZE["acq0"], null=True, blank=True, validators=[MinLengthValidator(CONFIG_SIZE["acq0"])])
    acq = models.BinaryField(max_length=CONFIG_SIZE["acq"], null=True, blank=True, validators=[MinLengthValidator(CONFIG_SIZE["acq"])])
    asic0 = models.BinaryField(max_length=CONFIG_SIZE["asic0"], null=True, blank=True, validators=[MinLengthValidator(CONFIG_SIZE["asic0"])])
    asic1 = models.BinaryField(max_length=CONFIG_SIZE["asic1"], null=True, blank=True, validators=[MinLengthValidator(CONFIG_SIZE["asic1"])])
    bee = models.BinaryField(max_length=CONFIG_SIZE["bee"], null=True, blank=True, validators=[MinLengthValidator(CONFIG_SIZE["bee"])])
    liktrg = models.BinaryField(max_length=CONFIG_SIZE["liktrg"], null=True, blank=True, validators=[MinLengthValidator(CONFIG_SIZE["liktrg"])])
    obs = models.BinaryField(max_length=CONFIG_SIZE["obs"], null=True, blank=True, validators=[MinLengthValidator(CONFIG_SIZE["obs"])])

    class Meta:
        constraints = [
            # CONSTRAINT 1: At least one configuration field should be non-null
            CheckConstraint(
                check=(
                    #fmt: off
                        Q(acq__isnull=False) |
                        Q(acq0__isnull=False) |
                        Q(asic0__isnull=False) |
                        Q(asic1__isnull=False) |
                        Q(bee__isnull=False) |
                        Q(liktrg__isnull=False) |
                        Q(obs__isnull=False)
                    # fmt:on
                ),
                name="at_least_one_config_field"
            ),
            # CONSTRAINT 2: upload_time must be later than upload_time if both exist
            CheckConstraint(
                check=Q(deliver_time__isnull=True) | Q(upload_time__isnull=True) |
                      Q(upload_time__gt=F('deliver_time')),
                name="upload_after_deliver"
            ),

            # we can imagine edge scenarios in which the `delivered` or `uploaded` flags are set but
            # their respective time is not. for example, when the datetime is uncertain or if an error
            # occurred with the user timestamping system. on the other hand, a scenario in which
            # the times are known but the flags aren't set should never happen.

            # CONSTRAINT 3: deliver time can't have a value if delivered isn't set
            CheckConstraint(
            #   equivalent expression:
            #   check=(Q(deliver_time__isnull=False) & Q(delivered=True)) | Q(deliver_time__isnull=True),
                check=Q(deliver_time__isnull=True) | Q(delivered=True),
                name="deliver_time_requires_delivered"
            ),
            # CONSTRAINT 4: upload time can't have a value if uploeaded isn't set
            CheckConstraint(
            #   equivalent expression:
            #   check=(Q(upload_time__isnull=False) & Q(uploaded=True)) | Q(upload_time__isnull=True),
                check=Q(upload_time__isnull=True) | Q(uploaded=True),
                name="upload_time_requires_uploaded"
            ),
            # CONSTRAINT 5: uploaded can't be true if delivered isn't too
            CheckConstraint(
            #   equivalent expression:
            #   check=Q(delivered=True) | (Q(delivered=False) & Q(uploaded=False)),
                check=Q(delivered=True) | Q(uploaded=False),
                name="uploaded_requires_delivered"
            ),

        ]

    def non_null_configs_keys(self) -> list[str]:
        """Returns a list of configuration types that have content."""
        return [ftype for ftype in CONFIG_TYPES if getattr(self, ftype) is not None]

    def get_config_data(self) -> dict[str, bytes]:
        """Returns a dictionary mapping configuration types to their binary content."""
        return {ftype: getattr(self, ftype) for ftype in self.non_null_configs_keys()}

    def get_encoded_config_data(self) -> dict[str, str]:
        return {ftype: content.hex() for ftype, content in self.get_config_data().items()}

    def filestring(self) -> str:
        return f"hermes_{self.id:03d}_{self.model}_{self.date:%Y%m%d}"


def config_to_crc16(
    config: Configuration,
) -> dict[str, str]:
    """
    Computes CRC16 for non-null configuration entries.
    """
    crcs = {}
    for ftype in CONFIG_TYPES:
        if (data := getattr(config,  ftype)) is not None:
            crcs[ftype] = crc16(data).hex()
    return crcs


def config_to_sha256(
    config: Configuration,
    ordered_keys: Iterable[Literal[*CONFIG_TYPES]] = CONFIG_TYPES,
) -> tuple[str, Iterable]:
    """
    Sequentially encodes a configuration, returns the config 256 hash and the
    sequence used for encoding it.
    Will raise ValueError if `config` has no valid configuration entries.
    """
    non_null_configs = config.non_null_configs_keys()
    if not all([k in non_null_configs for k in ordered_keys]):
        raise ValueError("Missing one or more configuration files.")

    hasher = sha256()
    for config_type in ordered_keys:
        hasher.update(getattr(config, config_type))
    return hasher.hexdigest(), ordered_keys
