from hashlib import sha256
from typing import Iterable, Literal

from django.core.validators import MinLengthValidator, ValidationError
from django.db import models

from hermes import CONFIG_TYPES, CONFIG_SIZE
from hermes import SPACECRAFTS_NAMES
from hhelm.settings import AUTH_USER_MODEL
from .validators import crc16

CustomUser = AUTH_USER_MODEL


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
    delivered = models.BooleanField(default=False)
    deliver_time = models.DateTimeField(null=True, blank=True)
    uploaded = models.BooleanField(default=False)
    upload_time = models.DateTimeField(null=True, blank=True)
    model = models.CharField(max_length=2, choices=MODELS)
    acq0 = models.BinaryField(max_length=CONFIG_SIZE["acq0"], null=True, blank=True, validators=[MinLengthValidator(CONFIG_SIZE["acq0"])])
    acq = models.BinaryField(max_length=CONFIG_SIZE["acq"], null=True, blank=True, validators=[MinLengthValidator(CONFIG_SIZE["acq"])])
    asic0 = models.BinaryField(max_length=CONFIG_SIZE["asic0"], null=True, blank=True, validators=[MinLengthValidator(CONFIG_SIZE["asic0"])])
    asic1 = models.BinaryField(max_length=CONFIG_SIZE["asic1"], null=True, blank=True, validators=[MinLengthValidator(CONFIG_SIZE["asic1"])])
    bee = models.BinaryField(max_length=CONFIG_SIZE["bee"], null=True, blank=True, validators=[MinLengthValidator(CONFIG_SIZE["bee"])])
    liktrg = models.BinaryField(max_length=CONFIG_SIZE["liktrg"], null=True, blank=True, validators=[MinLengthValidator(CONFIG_SIZE["liktrg"])])
    obs = models.BinaryField(max_length=CONFIG_SIZE["obs"], null=True, blank=True, validators=[MinLengthValidator(CONFIG_SIZE["obs"])])

    def clean(self):
        """Validate that at least one configuration file is provided"""
        configs = [getattr(self, ftype) for ftype in CONFIG_TYPES]

        if not any(configs):
            raise ValidationError(
                "At least one configuration file must be provided."
            )

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
