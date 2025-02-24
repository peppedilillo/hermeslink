import io
import tarfile
from typing import Literal
import zipfile

from configs.models import Configuration
from configs.reports import write_config_readme_txt
from hermes import STANDARD_FILENAMES


def write_archive(
        config: Configuration,
        format: Literal["zip", "tar"] = "zip",
        dirname: str = None
) -> bytes:
    """
    Creates an archive containing configuration files from a Configuration instance.
    The archive is structured as follows:

    archive.format:
        {dirname}/
            - file1.cfg
            - ...
            - fileN.cfg
            - readme.txt

    Note:
        - dirname is not the name of the archive itself, but of the directory inside it!
    """
    buffer = io.BytesIO()
    dirname = config.filestring() if dirname is None else dirname

    if format == "zip":
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for ftype in config.non_null_configs_keys():
                content = getattr(config, ftype)
                archive.writestr(f"{dirname}/{STANDARD_FILENAMES[ftype]}", content)
            archive.writestr(f"{dirname}/readme.txt", write_config_readme_txt(config))

    elif format == "tar":
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            for ftype in config.non_null_configs_keys():
                content = getattr(config, ftype)
                content_buffer = io.BytesIO(content)
                info = tarfile.TarInfo(f"{dirname}/{STANDARD_FILENAMES[ftype]}")
                info.size = len(content)

                archive.addfile(info, content_buffer)
            readme_content = write_config_readme_txt(config).encode("utf-8")
            info = tarfile.TarInfo(f"{dirname}/readme.txt")
            info.size = len(readme_content)
            archive.addfile(info, io.BytesIO(readme_content))
    else:
        raise ValueError(f"Unsupported format: {format}")
    return buffer.getvalue()
