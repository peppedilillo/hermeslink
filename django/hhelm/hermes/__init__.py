from .configs import CONFIG_SIZE
from .configs import CONFIG_TYPES
from .configs import STANDARD_FILENAMES
from .configs import STANDARD_SUFFIXES
from .payloads import _maps
from .payloads import UNBOND

SPACECRAFTS_NAMES = ("H1", "H2", "H3", "H4", "H5", "H6")
DETECTOR_MAPS = dict(zip(SPACECRAFTS_NAMES, _maps))
