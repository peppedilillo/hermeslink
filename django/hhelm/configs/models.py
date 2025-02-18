from hashlib import sha256
import io
import tarfile
from typing import Iterable, Literal
import zipfile

from django.core.validators import MinLengthValidator, ValidationError
from django.db import models
from hermes import CONFIG_TYPES
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
    acq0 = models.BinaryField(max_length=20, null=True, blank=True, validators=[MinLengthValidator(20)])
    acq = models.BinaryField(max_length=20, null=True, blank=True, validators=[MinLengthValidator(20)])
    asic0 = models.BinaryField(max_length=124, null=True, blank=True, validators=[MinLengthValidator(124)])
    asic1 = models.BinaryField(max_length=124, null=True, blank=True, validators=[MinLengthValidator(124)])
    bee = models.BinaryField(max_length=64, null=True, blank=True, validators=[MinLengthValidator(64)])
    liktrg = models.BinaryField(max_length=38, null=True, blank=True, validators=[MinLengthValidator(38)])
    obs = models.BinaryField(max_length=5, null=True, blank=True, validators=[MinLengthValidator(5)])

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

    def get_config_files(self) -> dict[str, bytes]:
        """Returns a dictionary mapping configuration types to their binary content."""
        return {ftype: getattr(self, ftype) for ftype in self.non_null_configs_keys()}


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


def config_to_readme(config: Configuration) -> str:
    """
    Generate a README file for a configuration archive.
    Will raise ValueError if `config` has no configuration files.
    """
    non_null_configs = config.non_null_configs_keys()
    sha256sum, order = config_to_sha256(config, ordered_keys=non_null_configs)

    sections = [
        f"Configuration ID: {config.id}",
        f"Payload model: {config.model}",
        f"Created on: {config.date}",
        f"Author: {config.author}",
        f"Delivered status: {config.delivered}",
        f"Included configurations: {', '.join(non_null_configs)}",
    ]

    if config.delivered:
        sections.append(f"Delivery time: {config.deliver_time}")

    sections.append(f"Upload status: {config.uploaded}")
    if config.uploaded:
        sections.append(f"Upload time: {config.upload_time}")

    sections.extend(
        [
            f"SHA256 hash: {sha256sum}",
            "",
            "Comments:",
            f"* Hash check with `cat {' '.join(map(lambda s: s + '.cfg', order))} | sha256sum`",
        ]
    )
    return "\n".join(sections)


def config_to_archive(config: Configuration, format: Literal["zip", "tar"] = "zip") -> bytes:
    """
    Creates an archive containing configuration files from a Configuration instance.
    """
    buffer = io.BytesIO()

    if format == "zip":
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for ftype in config.non_null_configs_keys():
                content = getattr(config, ftype)
                archive.writestr(f"{ftype}.cfg", content)
            archive.writestr("readme.txt", config_to_readme(config))

    elif format == "tar":
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            for ftype in config.non_null_configs_keys():
                content = getattr(config, ftype)
                content_buffer = io.BytesIO(content)
                info = tarfile.TarInfo(f"{ftype}.cfg")
                info.size = len(content)

                archive.addfile(info, content_buffer)
            readme_content = config_to_readme(config).encode("utf-8")
            info = tarfile.TarInfo("readme.txt")
            info.size = len(readme_content)
            archive.addfile(info, io.BytesIO(readme_content))
    else:
        raise ValueError(f"Unsupported format: {format}")
    return buffer.getvalue()
