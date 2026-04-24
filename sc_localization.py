"""
Localization submodule — extract global.ini from Data.p4k, merge custom
overrides from target_strings.ini, and optionally deploy to the game folder.
"""

import re
import shutil
import subprocess
from pathlib import Path

from sc_config import (
    EXTRACT_DIR,
    EXTRACTED_INI,
    EXTRACT_REL_PATH,
    GAME_INI,
    GAME_PAK,
    MISSION_BLUEPRINTS_INI,
    MISSILES_INI,
    OUTPUT_MERGED,
    SHIP_COMPONENTS_INI,
    SRC_GLOBAL_INI,
    TARGET_STRINGS,
    UNP4K_EXE,
    abort,
    step,
)


def extract_pak() -> None:
    """Delete any previous extraction, run unp4k.exe, verify output exists."""
    if EXTRACTED_INI.exists():
        step(f"Removing previous extracted file: {EXTRACTED_INI}")
        EXTRACTED_INI.unlink()

    step(f"Extracting {EXTRACT_REL_PATH} from {GAME_PAK.name}")
    result = subprocess.run(
        [str(UNP4K_EXE), str(GAME_PAK), EXTRACT_REL_PATH],
        cwd=str(EXTRACT_DIR),
    )
    if result.returncode != 0:
        abort(f"unp4k.exe exited with code {result.returncode}")
    if not EXTRACTED_INI.exists():
        abort(f"unp4k finished but expected output not found: {EXTRACTED_INI}")


def _load_overrides(path: Path) -> dict[str, str]:
    """Load key=value pairs from an ini-style override file into a dict."""
    overrides: dict[str, str] = {}
    key_pattern = re.compile(r"^(.*?)=(.*)$")
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = key_pattern.match(line.rstrip("\n"))
            if m:
                key = m.group(1).strip()
                value = m.group(2)  # do not strip — preserves exact value
                if key:
                    overrides[key] = value
    return overrides


def copy_to_src() -> None:
    """Copy the extracted ini to the project src directory."""
    step(f"Copying extracted ini to: {SRC_GLOBAL_INI}")
    SRC_GLOBAL_INI.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(EXTRACTED_INI, SRC_GLOBAL_INI)


def merge() -> tuple[int, int]:
    """
    Merge TARGET_STRINGS overrides into SRC_GLOBAL_INI, write OUTPUT_MERGED.

      - Keys in target_strings.ini are matched (trimmed) against global.ini keys.
      - The original spacing up to and including '=' is preserved in the output.
      - Lines without '=' (blank lines, comments) pass through unchanged.

    Returns (substitution_count, line_count).
    """
    replacements: dict[str, str] = {}

    if SHIP_COMPONENTS_INI.exists():
        step(f"Loading ship component overrides: {SHIP_COMPONENTS_INI}")
        replacements.update(_load_overrides(SHIP_COMPONENTS_INI))

    if MISSION_BLUEPRINTS_INI.exists():
        step(f"Loading mission blueprint overrides: {MISSION_BLUEPRINTS_INI}")
        replacements.update(_load_overrides(MISSION_BLUEPRINTS_INI))

    if MISSILES_INI.exists():
        step(f"Loading missile overrides: {MISSILES_INI}")
        replacements.update(_load_overrides(MISSILES_INI))

    step(f"Loading overrides: {TARGET_STRINGS}")
    replacements.update(_load_overrides(TARGET_STRINGS))

    step(f"Merging into global.ini ({len(replacements)} override(s) loaded)")
    OUTPUT_MERGED.parent.mkdir(parents=True, exist_ok=True)

    substitutions = 0
    line_count = 0
    split_pattern = re.compile(r"^(.*?)(=)(.*)$")

    with open(SRC_GLOBAL_INI, encoding="utf-8") as fin, open(
        OUTPUT_MERGED, "w", encoding="utf-8"
    ) as fout:
        for raw_line in fin:
            line_count += 1
            line = raw_line.rstrip("\n")
            m = split_pattern.match(line)
            if m:
                key = m.group(1).strip()
                if key in replacements:
                    prefix = line[: line.index("=") + 1]
                    fout.write(prefix + replacements[key] + "\n")
                    substitutions += 1
                    continue
            fout.write(raw_line if raw_line.endswith("\n") else raw_line + "\n")

    return substitutions, line_count


def deploy() -> None:
    """Copy merged.ini to the live game localization folder."""
    step(f"Deploying to game folder: {GAME_INI}")
    GAME_INI.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(OUTPUT_MERGED, GAME_INI)
