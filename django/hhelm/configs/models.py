from typing import Literal, Iterable

from django.core.validators import MinLengthValidator
from django.db import models
from hashlib import sha256

from hermes import CONFIG_TYPES, SPACECRAFTS_NAMES
from hhelm.settings import AUTH_USER_MODEL
import zipfile, tarfile, io


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
    acq0 = models.BinaryField(max_length=20, validators=[MinLengthValidator(20)])
    acq = models.BinaryField(max_length=20, validators=[MinLengthValidator(20)])
    asic0 = models.BinaryField(max_length=124, validators=[MinLengthValidator(124)])
    asic1 = models.BinaryField(max_length=124, validators=[MinLengthValidator(124)])
    bee = models.BinaryField(max_length=64, validators=[MinLengthValidator(64)])


def config_to_sha256(
        config: Configuration,
        ordered_keys: Iterable[Literal[*CONFIG_TYPES]] = CONFIG_TYPES
) -> tuple[str, Iterable]:
    """
    Sequentially encodes a configuration, returns the config 256 hash and the
    sequence used for encoding it.
    """
    hasher = sha256()
    for config_type in ordered_keys:
        hasher.update(getattr(config, config_type))
    return hasher.hexdigest(), ordered_keys


def config_to_readme(config: Configuration) -> str:
    """
    Generate a README file for a configuration archive.
    """
    sha256sum, order = config_to_sha256(config)

    sections = [
        f"Configuration ID: {config.id}",
        f"Payload model: {config.model}",
        f"Created on: {config.date}",
        f"Author: {config.author}",
        f"Delivered status: {config.delivered}"
    ]

    if config.delivered:
        sections.append(f"Delivery time: {config.deliver_time}")

    sections.append(f"Upload status: {config.uploaded}")
    if config.uploaded:
        sections.append(f"Upload time: {config.upload_time}")

    sections.extend([
        f"SHA256 hash: {sha256sum}",
        "",
        "Comments:",
        f"* Hash check with `cat {' '.join(map(lambda s: s + '.cfg', order))} | sha256sum`"
    ])
    return "\n".join(sections)

def config_to_archive(
        config: Configuration,
        format: Literal["zip", "tar"] = "zip"
) -> bytes:
    """
    Creates an archive containing configuration files from a Configuration instance.
    """
    buffer = io.BytesIO()

    if format == "zip":
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            for config_type in CONFIG_TYPES:
                content = getattr(config, config_type)
                archive.writestr(f"{config_type}.cfg", content)
            archive.writestr("readme.txt", config_to_readme(config))

    elif format == "tar":
        with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
            for config_type in CONFIG_TYPES:
                content = getattr(config, config_type)
                content_buffer = io.BytesIO(content)
                info = tarfile.TarInfo(f"{config_type}.cfg")
                info.size = len(content)

                archive.addfile(info, content_buffer)
            readme_content = config_to_readme(config).encode("utf-8")
            info = tarfile.TarInfo("readme.txt")
            info.size = len(readme_content)
            archive.addfile(info, io.BytesIO(readme_content))
    else:
        raise ValueError(f"Unsupported format: {format}")
    return buffer.getvalue()