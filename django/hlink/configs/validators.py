from dataclasses import dataclass
from enum import Enum
from typing import Literal

from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator

import hermes
from hermes.configs import bytest_to_bitdict_asic
from hermes.configs import parse_bitdict_asic
from hermes.payloads import UNBOND


def crc16(data: bytes) -> bytes:
    """
    Calculate CRC16-CCITT (0xFFFF initial value, polynomial 0x1021)
    """
    if not isinstance(data, bytes):
        raise ValueError("Input must be bytes")

    crc = 0xFFFF
    poly = 0x1021  # CRC16-CCITT polynomial

    for byte in data:
        byte = byte & 0xFF
        mask = 0x80

        # process each bit
        for _ in range(8):
            xor_flag = bool(crc & 0x8000)
            crc = (crc << 1) & 0xFFFF

            if byte & mask:
                crc = (crc + 1) & 0xFFFF
            if xor_flag:
                crc = (crc ^ poly) & 0xFFFF

            mask = (mask >> 1) & 0xFF

    # final 16 shifts
    for _ in range(16):
        xor_flag = bool(crc & 0x8000)
        crc = (crc << 1) & 0xFFFF
        if xor_flag:
            crc = (crc ^ poly) & 0xFFFF

    return crc.to_bytes(2, byteorder="big")


class Status(int, Enum):
    PASSED = 0
    WARNING = 1
    ERROR = 2


@dataclass
class TestResult:
    status: Status
    message: str


def test_asic1_unbounded_discriminators_are_off(
    asic1_bitdict: dict[str, dict[str, str]],
    model: Literal[hermes.SPACECRAFTS_NAMES],
) -> TestResult:
    # useful for making sure we are not passing asic configurations for a different payload.
    warn_about_channels = []
    for q, qmap in hermes.DETECTOR_MAPS[model].items():
        assert len(asic1_bitdict[q]["discriminators"]) == len(qmap)
        for ch, (bit, channel_mapping) in enumerate(zip(asic1_bitdict[q]["discriminators"], qmap)):
            if channel_mapping == UNBOND and not int(bit):  # 0 is for enabled discriminator
                warn_about_channels.append((q, ch))
    if warn_about_channels:
        return TestResult(
            Status.WARNING,
            f"Discriminator are set on for unbonded channel{'s' if len(warn_about_channels) > 1 else ''} "
            f"{', '.join(map(lambda x: ''.join(map(str, x)), warn_about_channels))}.",
        )
    return TestResult(Status.PASSED, "All unbonded channels discriminators are off.")


def test_asic0_trigger_logic_is_internal_or(
    asic0_bitdict: dict[str, dict[str, str]],
    model: Literal[*hermes.SPACECRAFTS_NAMES],
) -> TestResult:
    # if trigger logic is not set to internal or, the configuration is not asic0
    warn_about_quadrants = []
    for q in hermes.DETECTOR_MAPS[model].keys():
        if asic0_bitdict[q]["trigger_logic"] != "10":
            warn_about_quadrants.append(q)
    if warn_about_quadrants:
        return TestResult(
            Status.WARNING,
            f"Trigger logic not set to `internal or` for quadrant{'s' if len(warn_about_quadrants) > 1 else ''}. "
            f"{', '.join(warn_about_quadrants)}.",
        )
    return TestResult(Status.PASSED, "Trigger logic is set to `internal or`.")


def test_asic1_trigger_logic_is_internal_single(
    asic0_bitdict: dict[str, dict[str, str]],
    model: Literal[*hermes.SPACECRAFTS_NAMES],
) -> TestResult:
    # if trigger logic is not set to internal single, the configuration is not asic1
    warn_about_quadrants = []
    for q in hermes.DETECTOR_MAPS[model].keys():
        if asic0_bitdict[q]["trigger_logic"] != "01":
            warn_about_quadrants.append(q)
    if warn_about_quadrants:
        return TestResult(
            Status.WARNING,
            f"Trigger logic not set to `internal single` for quadrant{'s' if len(warn_about_quadrants) > 1 else ''}. "
            f"{', '.join(warn_about_quadrants)}.",
        )
    return TestResult(Status.PASSED, "Trigger logic is set to `internal single`.")


def _test_size(
    bstr: bytes,
    ftype: Literal[*hermes.CONFIG_SIZE],
):
    # we double check size both to be extra-sure and for displaying purpose
    if len(bstr) != hermes.CONFIG_SIZE[ftype]:
        return TestResult(Status.ERROR, f"File size is {len(bstr)} bytes. Expected {hermes.CONFIG_SIZE[ftype]} bytes.")
    return TestResult(Status.PASSED, f"File size is {hermes.CONFIG_SIZE[ftype]} bytes as expected.")


def test_acq_size(
    bstr: bytes,
) -> TestResult:
    return _test_size(bstr, "acq")


def test_asic_size(
    bstr: bytes,
) -> TestResult:
    return _test_size(bstr, "asic1")


def test_bee_size(
    bstr: bytes,
) -> TestResult:
    return _test_size(bstr, "bee")


def test_obs_size(
    bstr: bytes,
) -> TestResult:
    return _test_size(bstr, "obs")


def test_liktrg_size(
    bstr: bytes,
) -> TestResult:
    return _test_size(bstr, "liktrg")


def serialize(tr: TestResult):
    # since we are going to display results in a template, we need them to be serializable
    return {"status": tr.status.name, "message": tr.message}


def validate_configurations(
    bytesdict: dict[str, bytes],
    model: Literal[*hermes.SPACECRAFTS_NAMES],
) -> dict[str, list[TestResult]]:
    """
    Validates a configuration and returns test results and a boolean pass.
    """
    test_map = {
        "acq": [
            lambda: test_acq_size(bytesdict["acq"]),
        ],
        "acq0": [
            lambda: test_acq_size(bytesdict["acq0"]),
        ],
        "asic1": [
            lambda: test_asic_size(bytesdict["asic1"]),
            lambda: test_asic1_unbounded_discriminators_are_off(
                parse_bitdict_asic(bytest_to_bitdict_asic(bytesdict["asic1"])), model
            ),
            lambda: test_asic1_trigger_logic_is_internal_single(
                parse_bitdict_asic(bytest_to_bitdict_asic(bytesdict["asic1"])), model
            ),
        ],
        "asic0": [
            lambda: test_asic_size(bytesdict["asic0"]),
            lambda: test_asic0_trigger_logic_is_internal_or(
                parse_bitdict_asic(bytest_to_bitdict_asic(bytesdict["asic0"])), model
            ),
        ],
        "bee": [
            lambda: test_bee_size(bytesdict["bee"]),
        ],
        "obs": [
            lambda: test_obs_size(bytesdict["obs"]),
        ],
        "liktrg": [
            lambda: test_liktrg_size(bytesdict["liktrg"]),
        ],
    }

    return {ftype: [f() for f in test_map[ftype]] for ftype in bytesdict.keys()}


def parse_multiple_emails(value: str) -> list[str]:
    """
    Parses a list of email addresses. Supports:
     - `prova@dom.com`
     - `prova@dom.com;`
     - `prova@dom.com; lol@dom1.com; ..`
     - `prova@dom.com; lol@dom1.com; ..;`
    """
    value = value.strip()
    if not value:
        return []
    elif ";" not in value:
        return [value]
    values = [s.strip() for s in value.split(";")]
    # user can terminate value cc list with ";"
    if values[-1] == "":
        values.pop(-1)
    return values


def validate_multiple_emails(emails: list[str]):
    invalid_emails = []
    for email in emails:
        try:
            EmailValidator()(email)
        except ValidationError:
            invalid_emails.append(email)
    if invalid_emails:
        raise ValidationError(f"The emails '{', '.join(invalid_emails)}' are not valid.")
    return
