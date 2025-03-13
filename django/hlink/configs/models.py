from hashlib import sha256
from typing import Iterable, Literal

from django.core.validators import MinLengthValidator
from django.core.validators import ValidationError
from django.db import models
from django.db.models import CheckConstraint
from django.db.models import F
from django.db.models import Q
from django.utils import timezone
from hermes import CONFIG_SIZE
from hermes import CONFIG_TYPES
from hermes import SPACECRAFTS_NAMES
from hlink.settings import AUTH_USER_MODEL

from .validators import crc16

CustomUser = AUTH_USER_MODEL


def validate_not_future(value):
    if value is not None and value > timezone.now():
        raise ValidationError("Date cannot be in the future.")


class Configuration(models.Model):
    """
    Core configuration model. Stores configurations as binary blobs, as well as
    a few metadata informations, including authors, creation date, submit status.
    The uplink field is inteded to be modified later, once we get a confirmation
    on the uplinked status, which should supposedly come with a timestamp (`uplink_time`)
    """

    MODELS = tuple(zip(SPACECRAFTS_NAMES, SPACECRAFTS_NAMES))

    # we have no drafts yet implemented but having separate date and submit_time
    # could come handy in the future.
    date = models.DateTimeField(
        auto_now_add=True,
    )
    author = models.ForeignKey(
        to=CustomUser,
        related_name="submitted_configurations",
        on_delete=models.PROTECT,
    )
    # these field is for when a configuration is first sent to the MOC.
    # i considered if having a submit_by field would be useful for anything but symmetry and i don't think so
    submitted = models.BooleanField(
        default=False,
    )
    submit_time = models.DateTimeField(
        null=True,
        blank=True,
        validators=[validate_not_future],
    )
    # these fields is for when a configuration is uplink on-board by the MOC
    uplinked_by = models.ForeignKey(
        to=CustomUser,
        null=True,
        blank=True,
        related_name="uplinked_configurations",
        on_delete=models.PROTECT,
    )
    uplinked = models.BooleanField(
        default=False,
    )
    uplink_time = models.DateTimeField(
        null=True,
        blank=True,
        validators=[validate_not_future],
    )
    model = models.CharField(
        max_length=2,
        choices=MODELS,
    )
    acq0 = models.BinaryField(
        max_length=CONFIG_SIZE["acq0"],
        null=True,
        blank=True,
        validators=[
            MinLengthValidator(CONFIG_SIZE["acq0"]),
        ],
    )
    acq = models.BinaryField(
        max_length=CONFIG_SIZE["acq"],
        null=True,
        blank=True,
        validators=[
            MinLengthValidator(CONFIG_SIZE["acq"]),
        ],
    )
    asic0 = models.BinaryField(
        max_length=CONFIG_SIZE["asic0"],
        null=True,
        blank=True,
        validators=[
            MinLengthValidator(CONFIG_SIZE["asic0"]),
        ],
    )
    asic1 = models.BinaryField(
        max_length=CONFIG_SIZE["asic1"],
        null=True,
        blank=True,
        validators=[
            MinLengthValidator(CONFIG_SIZE["asic1"]),
        ],
    )
    bee = models.BinaryField(
        max_length=CONFIG_SIZE["bee"],
        null=True,
        blank=True,
        validators=[
            MinLengthValidator(CONFIG_SIZE["bee"]),
        ],
    )
    liktrg = models.BinaryField(
        max_length=CONFIG_SIZE["liktrg"],
        null=True,
        blank=True,
        validators=[
            MinLengthValidator(CONFIG_SIZE["liktrg"]),
        ],
    )
    obs = models.BinaryField(
        max_length=CONFIG_SIZE["obs"],
        null=True,
        blank=True,
        validators=[
            MinLengthValidator(CONFIG_SIZE["obs"]),
        ],
    )

    class Meta:
        constraints = [
            # CONSTRAINT 1: At least one configuration field should be non-null
            CheckConstraint(
                check=(
                    # fmt: off
                        Q(acq__isnull=False) |
                        Q(acq0__isnull=False) |
                        Q(asic0__isnull=False) |
                        Q(asic1__isnull=False) |
                        Q(bee__isnull=False) |
                        Q(liktrg__isnull=False) |
                        Q(obs__isnull=False)
                    # fmt:on
                ),
                name="at_least_one_config_field",
            ),
            # CONSTRAINT 2: uplink_time must be later than uplink_time if both exist
            CheckConstraint(
                check=Q(submit_time__isnull=True) | Q(uplink_time__isnull=True) | Q(uplink_time__gt=F("submit_time")),
                name="uplink_after_submit",
            ),
            # we can imagine edge scenarios in which the `submitted` or `uplinked` flags are set but
            # their respective time is not. for example, when the datetime is uncertain or if an error
            # occurred with the user timestamping system. on the other hand, a scenario in which
            # the times are known but the flags aren't set should never happen.
            #
            # CONSTRAINT 3: submit time can't have a value if submitted isn't set
            CheckConstraint(
                #   equivalent expression:
                #   check=(Q(submit_time__isnull=False) & Q(submitted=True)) | Q(submit_time__isnull=True),
                check=Q(submit_time__isnull=True) | Q(submitted=True),
                name="submit_time_requires_submitted",
            ),
            # CONSTRAINT 4: uplink time can't have a value if uploeaded isn't set
            CheckConstraint(
                #   equivalent expression:
                #   check=(Q(uplink_time__isnull=False) & Q(uplinked=True)) | Q(uplink_time__isnull=True),
                check=Q(uplink_time__isnull=True) | Q(uplinked=True),
                name="uplink_time_requires_uplinked",
            ),
            # CONSTRAINT 5: uplinked can't be true if submitted isn't too
            CheckConstraint(
                #   equivalent expression:
                #   check=Q(submitted=True) | (Q(submitted=False) & Q(uplinked=False)),
                check=Q(submitted=True) | Q(uplinked=False),
                name="uplinked_requires_submitted",
            ),
            # CONSTRAINT 6: uplinked always come with uplinked_by
            CheckConstraint(
                check=(
                    Q(uplinked=False) & Q(uplinked_by__isnull=True) | Q(uplinked=True) & Q(uplinked_by__isnull=False)
                ),
                name="uplinked_iff_uplinked_by",
            ),
        ]

    def non_null_configs_keys(self) -> list[str]:
        """Returns a list of configuration types that have content."""
        return [ftype for ftype in CONFIG_TYPES if getattr(self, ftype) is not None]

    def get_config_data(self) -> dict[str, bytes]:
        """Returns a dictionary mapping configuration types to their binary content."""
        return {ftype: getattr(self, ftype) for ftype in self.non_null_configs_keys()}

    def get_encoded_config_data(self) -> dict[str, str]:
        """Returns a dictionary of hex-encoded configuration data for serialization."""
        return {ftype: content.hex() for ftype, content in self.get_config_data().items()}

    def filestring(self) -> str:
        """Generates a standardized filename string for this configuration.
        Format: hermes_{model}_config_id{id:04d}_{date:%Y%m%d}"""
        return f"hermes_{self.model}_config_id{self.id:04d}_{self.date:%Y%m%d}"


def config_to_crc16(
    config: Configuration,
) -> dict[str, str]:
    """
    Computes CRC16 for non-null configuration entries.
    """
    crcs = {}
    for ftype in CONFIG_TYPES:
        if (data := getattr(config, ftype)) is not None:
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
