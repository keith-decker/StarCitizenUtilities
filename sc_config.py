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

# Star Citizen installation
GAME_PAK = Path(r"G:\RSI\StarCitizen\LIVE\Data.p4k")
GAME_INI = Path(r"G:\RSI\StarCitizen\LIVE\Data\Localization\english\global.ini")

# Project output directory (this repo)
PROJECT_DIR = Path(r"G:\StarCitizenUtilities")
SRC_GLOBAL_INI = PROJECT_DIR / "src" / "global.ini"
TARGET_STRINGS = PROJECT_DIR / "target_strings.ini"

# Local extraction workspace — unp4k/unforge write here; wiped before each --full run
EXTRACT_DIR = PROJECT_DIR / "extract"
EXTRACT_REL_PATH = "Data/Localization/english/global.ini"
EXTRACTED_INI = EXTRACT_DIR / "Data" / "Localization" / "english" / "global.ini"
GAME_DCB_REL = (
    Path("Data") / "Game2.dcb"
)  # relative path used as arg; cwd=EXTRACT_DIR at runtime
DATA_ROOT = EXTRACT_DIR / "Data" / "Libs" / "Foundry" / "Records"
OUTPUT_MERGED = PROJECT_DIR / "output" / "merged.ini"
BLUEPRINT_CSV = PROJECT_DIR / "output" / "blueprint_rewards.csv"
SHIP_COMPONENTS_CSV = PROJECT_DIR / "output" / "ship_components.csv"
FPS_WEAPONS_CSV = PROJECT_DIR / "output" / "fps_weapons.csv"
SHIP_ARMOR_CSV = PROJECT_DIR / "output" / "ship_armor.csv"
SHIP_COMPONENTS_INI = (
    PROJECT_DIR / "output" / "ship_components.ini"
)  # generated; fed into the localization merge
MISSION_BLUEPRINTS_INI = (
    PROJECT_DIR / "output" / "mission_blueprints.ini"
)  # generated; fed into the localization merge
UNRESOLVED_ITEMS_MD = (
    PROJECT_DIR / "output" / "unresolved_blueprint_items.md"
)  # report of items with no display name

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
