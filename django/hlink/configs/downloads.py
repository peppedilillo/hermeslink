import io
import tarfile
from typing import Literal
import zipfile

from configs.models import Configuration
from configs.reports import write_config_readme_txt
from hermes import STANDARD_FILENAMES


def write_archive(config: Configuration, format: Literal["zip", "tar"] = "zip") -> bytes:
    """
    Creates an archive containing configuration files from a Configuration instance.
    """
    buffer = io.BytesIO()

    if format == "zip":
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for ftype in config.non_null_configs_keys():
                content = getattr(config, ftype)
                archive.writestr(str(STANDARD_FILENAMES[ftype]), content)
            archive.writestr("readme.txt", write_config_readme_txt(config))

    elif format == "tar":
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            for ftype in config.non_null_configs_keys():
                content = getattr(config, ftype)
                content_buffer = io.BytesIO(content)
                info = tarfile.TarInfo(STANDARD_FILENAMES[ftype])
                info.size = len(content)

                archive.addfile(info, content_buffer)
            readme_content = write_config_readme_txt(config).encode("utf-8")
            info = tarfile.TarInfo("readme.txt")
            info.size = len(readme_content)
            archive.addfile(info, io.BytesIO(readme_content))
    else:
        raise ValueError(f"Unsupported format: {format}")
    return buffer.getvalue()
