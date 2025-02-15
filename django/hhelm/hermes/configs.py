from functools import reduce
from pathlib import Path
from typing import Dict


CONFIG_TYPES = tuple(sorted(("acq", "acq0", "asic0", "asic1", "bee")))
CONFIG_SIZE = {
    "acq": 20,
    "acq0": 20,
    "asic0": 124,
    "asic1": 124,
    "bee": 64,
}


def filepath_to_bitdict_asic(filepath: Path) -> Dict[str, str]:
    """
    Takes an asic configuration file and transforms it into a dictionary of strings.
    The dictionary has key for different quadrants, and binary (01 format) strings
    for values.
    """
    with open(filepath, "rb") as f:
        return {quad: "".join([format(b, "08b") for b in f.read(31)]) for quad in "ABCD"}


_SLICES_ASIC = {
    "tests": [slice(0, 32), slice(None, None, -1)],
    "trigger_logic": [slice(32, 34)],  # no reversal needed
    "discriminators": [slice(56, 88), slice(None, None, -1)],
    "prestatus": [slice(88, 120), slice(None, None, -1)],
    "fine_thresholds": [slice(120, 248), slice(None, None, -1)],
}


def parse_bitdict_asic(bitdict: Dict[str, str]) -> Dict[str, Dict[str, str]]:
    """
    Transforms a asic configuration dictionary into a nested dictionary representing
    a parsed asic configuration. Inner keys represent different sections of the
    asic configuration.

    Example Output:
        {
            "A": {
                "tests": "..",
                "trigger_logic": "..",
                "discriminators": ".."},
                ..
            },
            "B": ..
        }
    """
    return {q: {k: reduce(lambda x, s: x[s], slices, bitdict[q]) for k, slices in _SLICES_ASIC.items()} for q in "ABCD"}
