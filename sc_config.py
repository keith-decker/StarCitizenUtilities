"""
Shared configuration — all paths, constants, and utility helpers used across
the sc_* submodules and patch_day.py.

Edit the CONFIG section if any of your install locations change.
"""

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# CONFIG — edit these paths if your install locations change
# ---------------------------------------------------------------------------

# unp4k / unforge tool directory
UNP4K_DIR = Path(r"G:\un4pk")
UNP4K_EXE = UNP4K_DIR / "unp4k.exe"
UNFORGE_EXE = UNP4K_DIR / "unforge.cli.exe"

# Star Citizen installation — branch selected by SC_BRANCH env var ("LIVE" or "PTU")
import os as _os

_BRANCH = _os.environ.get("SC_BRANCH", "LIVE").upper()

# Root directories per branch — all derived paths flow from here
_SC_ROOT_LIVE = Path(r"G:\RSI\StarCitizen\LIVE")
_SC_ROOT_PTU = Path(r"G:\RSI\StarCitizen\PTU")

_SC_ROOT = _SC_ROOT_PTU if _BRANCH == "PTU" else _SC_ROOT_LIVE

GAME_PAK = _SC_ROOT / "Data.p4k"
GAME_INI = _SC_ROOT / "Data" / "Localization" / "english" / "global.ini"
GAME_LOG = _SC_ROOT / "Game.log"
GAME_LOG_BACKUPS = _SC_ROOT / "logbackups"

# Project output directory (this repo)
PROJECT_DIR = Path(r"G:\StarCitizenUtilities")
SRC_GLOBAL_INI = PROJECT_DIR / "src" / "global.ini"
TARGET_STRINGS = PROJECT_DIR / "target_strings.ini"

# Local extraction workspace — branch-scoped so PTU/LIVE records don't overwrite each other
EXTRACT_DIR = PROJECT_DIR / "extract" / _BRANCH.lower()
EXTRACT_REL_PATH = "Data/Localization/english/global.ini"
EXTRACTED_INI = EXTRACT_DIR / "Data" / "Localization" / "english" / "global.ini"
GAME_DCB_REL = (
    Path("Data") / "Game2.dcb"
)  # relative path used as arg; cwd=EXTRACT_DIR at runtime
DATA_ROOT = EXTRACT_DIR / "Data" / "Libs" / "Foundry" / "Records"

# Output directory — branch-scoped so PTU/LIVE outputs don't overwrite each other
OUTPUT_DIR = PROJECT_DIR / "output" / _BRANCH.lower()
OUTPUT_MERGED = OUTPUT_DIR / "merged.ini"
BLUEPRINT_CSV = OUTPUT_DIR / "blueprint_rewards.csv"
SHIP_COMPONENTS_CSV = OUTPUT_DIR / "ship_components.csv"
FPS_WEAPONS_CSV = OUTPUT_DIR / "fps_weapons.csv"
SHIP_ARMOR_CSV = OUTPUT_DIR / "ship_armor.csv"
SHIP_COMPONENTS_INI = (
    OUTPUT_DIR / "ship_components.ini"
)  # generated; fed into the localization merge
MISSION_BLUEPRINTS_INI = (
    OUTPUT_DIR / "mission_blueprints.ini"
)  # generated; fed into the localization merge
MISSILES_INI = OUTPUT_DIR / "missiles.ini"  # generated; fed into the localization merge
UNRESOLVED_ITEMS_MD = (
    OUTPUT_DIR / "unresolved_blueprint_items.md"
)  # report of items with no display name
BLUEPRINTS_JSON = (
    OUTPUT_DIR / "blueprints.json"
)  # comprehensive blueprint data (fps weapons, armor, ship components)
QUALITY_QUANTIZATION_JSON = (
    OUTPUT_DIR / "quality_quantization.json"
)  # per-material 8-band quantization data
QUALITY_DISTRIBUTIONS_CSV = OUTPUT_DIR / "quality_distributions.csv"
QUALITY_QUANTIZATION_CSV = OUTPUT_DIR / "quality_quantization.csv"
BLUEPRINTS_RECEIVED_CSV = OUTPUT_DIR / "blueprints_received.csv"

# Ship component types to include in the extraction
COMPONENT_TYPES = {"QuantumDrive", "Shield", "PowerPlant", "Cooler", "Radar"}

# ---------------------------------------------------------------------------
# END CONFIG
# ---------------------------------------------------------------------------


def step(msg: str) -> None:
    print(f"\n>>> {msg}")


def abort(msg: str) -> None:
    print(f"\nERROR: {msg}", file=sys.stderr)
    sys.exit(1)
