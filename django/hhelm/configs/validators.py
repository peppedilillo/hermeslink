from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Literal

import hermes
from hermes.payloads import UNBOND
from hermes.configs import bytest_to_bitdict_asic
from hermes.configs import parse_bitdict_asic

class Status(Enum):
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


def test_acq_size(
    bstr: bytes,
) -> TestResult:
    # we double check size both to be extra-sure and for displaying purpose
    if len(bstr) != hermes.CONFIG_SIZE["acq"]:
        return TestResult(Status.ERROR, f"File size is {len(bstr)} bytes. Expected 20 bytes.")
    return TestResult(Status.PASSED, "File size is 20 bytes as expected.")


def test_asic_size(
    bstr: bytes,
) -> TestResult:
    # we double check size both to be extra-sure and for displaying purpose
    if len(bstr) != hermes.CONFIG_SIZE["asic0"]:
        assert len(bstr) != hermes.CONFIG_SIZE["asic1"]
        return TestResult(Status.ERROR, f"File size is {len(bstr)} bytes. Expected 124 bytes.")
    return TestResult(Status.PASSED, "File size is 124 bytes as expected.")


def test_bee_size(
    bstr: bytes,
) -> TestResult:
    # we double check size both to be extra-sure and for displaying purpose
    if len(bstr) != hermes.CONFIG_SIZE["bee"]:
        return TestResult(Status.ERROR, f"File size is {len(bstr)} bytes. Expected 64 bytes.")
    return TestResult(Status.PASSED, "File size is 64 bytes as expected.")


def serialize(tr: TestResult):
    # since we are going to display results in a template, we need them to be serializable
    return {"status": tr.status.name, "message": tr.message}


def validate_configurations(
    bytesdict: dict[str, bytes],
    model: Literal[*hermes.SPACECRAFTS_NAMES],
) -> tuple[Dict[str, List[tuple[str, str]]], bool]:
    """
    Validates a configuration and returns test results and a boolean pass.
    """
    asic1_bitdict = parse_bitdict_asic(bytest_to_bitdict_asic(bytesdict["asic1"]))
    asic0_bitdict = parse_bitdict_asic(bytest_to_bitdict_asic(bytesdict["asic0"]))
    test_results = {
        "acq": [
            test_acq_size(bytesdict["acq"]),
        ],
        "acq0": [
            test_acq_size(bytesdict["acq0"]),
        ],
        "asic1": [
            test_asic_size(bytesdict["asic1"]),
            test_asic1_unbounded_discriminators_are_off(asic1_bitdict, model),
            test_asic1_trigger_logic_is_internal_single(asic1_bitdict, model),
        ],
        "asic0": [
            test_asic_size(bytesdict["asic0"]),
            test_asic0_trigger_logic_is_internal_or(asic0_bitdict, model),
        ],
        "bee": [
            test_bee_size(bytesdict["bee"]),
        ],
    }
    can_proceed = not any([r.status == Status.ERROR for k, v in test_results.items() for r in v])
    return {k: [*map(serialize, v)] for k, v in test_results.items()}, can_proceed
