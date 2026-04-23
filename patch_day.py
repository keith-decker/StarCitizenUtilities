#!/usr/bin/env python3
"""
SC Patch Day — Star Citizen localization extractor and merger.

Replaces the manual PowerShell extraction commands and merge-translations.ps1.

Workflow:
  1. Delete any previously extracted global.ini from the unp4k working dir
  2. Run unp4k.exe to extract global.ini from Data.p4k
  3. Copy extracted file to src/global.ini
  4. Merge target_strings.ini overrides into global.ini → output/merged.ini
  5. Run unforge.exe to extract Game2.dcb DataForge records
  6. Build blueprint_rewards.csv from DataForge XML records
  7. (Optional, --deploy) Copy merged.ini to the live game folder

Usage:
    python patch_day.py           # extract + merge only
    python patch_day.py --deploy  # extract + merge + deploy to game folder
"""

import argparse
import csv
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


# ---------------------------------------------------------------------------
# CONFIG — edit these paths if your install locations change
# ---------------------------------------------------------------------------

# unp4k extraction tool
UNP4K_DIR = Path(r"G:\un4pk")
UNP4K_EXE = UNP4K_DIR / "unp4k.exe"

# Star Citizen game pak to extract from
GAME_PAK = Path(r"G:\RSI\StarCitizen\LIVE\Data.p4k")

# Where unp4k drops the extracted file (relative path inside Data.p4k)
EXTRACT_REL_PATH = "Data/Localization/english/global.ini"
EXTRACTED_INI = UNP4K_DIR / "Data" / "Localization" / "english" / "global.ini"

# Project directory (this script's folder)
PROJECT_DIR = Path(r"G:\StarCitizenUtilities")
SRC_GLOBAL_INI = PROJECT_DIR / "src" / "global.ini"
TARGET_STRINGS = PROJECT_DIR / "target_strings.ini"
OUTPUT_MERGED = PROJECT_DIR / "output" / "merged.ini"

# unforge DataForge extractor
UNFORGE_EXE = UNP4K_DIR / "unforge.exe"
GAME_DCB_REL = (
    Path("Data") / "Game2.dcb"
)  # relative path passed to unforge (cwd = UNP4K_DIR)
DATA_ROOT = UNP4K_DIR / "Data" / "Libs" / "Foundry" / "Records"
BLUEPRINT_CSV = PROJECT_DIR / "blueprint_rewards.csv"

# Live game localization file (only written when --deploy is passed)
GAME_INI = Path(r"G:\RSI\StarCitizen\LIVE\Data\Localization\english\global.ini")

# ---------------------------------------------------------------------------
# END CONFIG
# ---------------------------------------------------------------------------


def step(msg: str) -> None:
    print(f"\n>>> {msg}")


def abort(msg: str) -> None:
    print(f"\nERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def extract_dcb() -> None:
    """Run unforge.exe to extract Game2.dcb records into Data\\Libs\\Foundry\\Records\\."""
    step("Extracting Game2.dcb records with unforge (this may take a few minutes)")
    result = subprocess.run(
        [str(UNFORGE_EXE), str(GAME_DCB_REL)],
        cwd=str(UNP4K_DIR),
    )
    if result.returncode != 0:
        abort(f"unforge.exe exited with code {result.returncode}")


def extract() -> None:
    """Delete any previous extraction, run unp4k, verify output exists."""
    if EXTRACTED_INI.exists():
        step(f"Removing previous extracted file: {EXTRACTED_INI}")
        EXTRACTED_INI.unlink()

    step(f"Extracting {EXTRACT_REL_PATH} from {GAME_PAK.name}")
    result = subprocess.run(
        [str(UNP4K_EXE), str(GAME_PAK), EXTRACT_REL_PATH],
        cwd=str(UNP4K_DIR),
    )
    if result.returncode != 0:
        abort(f"unp4k.exe exited with code {result.returncode}")
    if not EXTRACTED_INI.exists():
        abort(f"unp4k finished but expected output not found: {EXTRACTED_INI}")


def copy_to_src() -> None:
    """Copy the extracted ini to the project src directory."""
    step(f"Copying to merge tool src: {SRC_GLOBAL_INI}")
    SRC_GLOBAL_INI.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(EXTRACTED_INI, SRC_GLOBAL_INI)


def merge() -> tuple[int, int]:
    """
    Merge TARGET_STRINGS overrides into SRC_GLOBAL_INI, write OUTPUT_MERGED.

    Replicates the logic from merge-translations.ps1:
      - Keys in target_strings.ini are matched (trimmed) against global.ini keys
      - The original spacing up to and including '=' is preserved in the output
      - Lines without '=' (blank lines, comments) pass through unchanged

    Returns (substitution_count, line_count).
    """
    step(f"Loading target_strings.ini: {TARGET_STRINGS}")

    replacements: dict[str, str] = {}
    key_pattern = re.compile(r"^(.*?)=(.*)$")

    with open(TARGET_STRINGS, encoding="utf-8") as f:
        for line in f:
            m = key_pattern.match(line.rstrip("\n"))
            if m:
                key = m.group(1).strip()
                value = m.group(2)  # do not strip — preserves exact value, matching PS1
                if key:
                    replacements[key] = value

    step(f"Processing global.ini ({len(replacements)} substitution(s) loaded)")
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
                    # Preserve original spacing up to and including '=' (mirrors PS1 behaviour)
                    prefix = line[: line.index("=") + 1]
                    fout.write(prefix + replacements[key] + "\n")
                    substitutions += 1
                    continue
            # Unmodified line — write as-is (handles blank lines, comments, non-matched keys)
            fout.write(raw_line if raw_line.endswith("\n") else raw_line + "\n")

    return substitutions, line_count


def deploy() -> None:
    """Copy merged.ini to the live game localization folder."""
    step(f"Deploying to game folder: {GAME_INI}")
    GAME_INI.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(OUTPUT_MERGED, GAME_INI)


def extract_blueprints() -> int:
    """
    Walk DataForge records to build blueprint_rewards.csv.
    Replicates extract_blueprint_rewards.ps1.
    Returns the number of rows written.
    """
    guid_re = re.compile(
        r'__ref="([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"',
        re.IGNORECASE,
    )

    step("[1/5] Loading localization strings for blueprint name resolution")
    localization: dict[str, str] = {}
    with open(EXTRACTED_INI, encoding="utf-8") as f:
        for line in f:
            eq = line.find("=")
            if eq > 0:
                localization[line[:eq].strip()] = line[eq + 1 :].rstrip("\n")
    print(f"      {len(localization):,} strings loaded.")

    step("[2/5] Indexing BlueprintPoolRecord files by GUID")
    pool_index: dict[str, Path] = {}
    for f in (
        DATA_ROOT / "crafting" / "blueprintrewards" / "blueprintmissionpools"
    ).rglob("*.xml"):
        m = guid_re.search(f.read_text(encoding="utf-8", errors="replace"))
        if m:
            pool_index[m.group(1).lower()] = f
    print(f"      {len(pool_index)} blueprint pools indexed.")

    step("[3/5] Indexing CraftingBlueprintRecord files by GUID")
    bp_index: dict[str, Path] = {}
    for f in (DATA_ROOT / "crafting" / "blueprints").rglob("*.xml"):
        m = guid_re.search(f.read_text(encoding="utf-8", errors="replace"))
        if m:
            bp_index[m.group(1).lower()] = f
    print(f"      {len(bp_index)} blueprints indexed.")

    step("[4/5] Scanning ContractGenerator files for BlueprintRewards")
    contract_files = list((DATA_ROOT / "contracts").rglob("*.xml"))
    print(f"      {len(contract_files)} contract files found.")

    rows: list[dict] = []
    for cf in contract_files:
        try:
            root = ET.parse(cf).getroot()
        except ET.ParseError:
            continue
        for cc in root.iter():
            if cc.get("__polymorphicType") != "CareerContract":
                continue
            mission_name = cc.get("debugName", "")
            if not mission_name:
                continue
            for bpr in cc.iter("BlueprintRewards"):
                pool_guid = (bpr.get("blueprintPool") or "").lower()
                chance = bpr.get("chance", "")
                if not pool_guid or pool_guid == "00000000-0000-0000-0000-000000000000":
                    continue
                if pool_guid not in pool_index:
                    continue
                try:
                    pool_root = ET.parse(pool_index[pool_guid]).getroot()
                except ET.ParseError:
                    continue
                for rn in pool_root.iter("BlueprintReward"):
                    bp_guid = (rn.get("blueprintRecord") or "").lower()
                    weight = rn.get("weight", "")
                    if not bp_guid or bp_guid not in bp_index:
                        continue
                    bp_file = bp_index[bp_guid]
                    item_id = bp_file.stem
                    if item_id.lower().startswith("bp_craft_"):
                        item_id = item_id[len("bp_craft_") :]
                    item_name = (
                        localization.get(f"item_Name{item_id}")
                        or localization.get(f"item_Name_{item_id}")
                        or item_id
                    )
                    rows.append(
                        {
                            "MissionName": mission_name,
                            "ItemId": item_id,
                            "ItemName": item_name,
                            "Weight": weight,
                            "Chance": chance,
                            "PoolGuid": pool_guid,
                            "BlueprintFile": bp_file.name,
                        }
                    )

    print(f"      {len(rows)} mission\u2192blueprint mappings found.")

    step(f"[5/5] Writing {BLUEPRINT_CSV}")
    fieldnames = [
        "MissionName",
        "ItemId",
        "ItemName",
        "Weight",
        "Chance",
        "PoolGuid",
        "BlueprintFile",
    ]
    with open(BLUEPRINT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Star Citizen patch-day localization extractor and merger.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python patch_day.py             extract, merge — stop here\n"
            "  python patch_day.py --deploy    extract, merge, then copy to game folder\n"
        ),
    )
    parser.add_argument(
        "--deploy",
        action="store_true",
        help="Copy merged.ini to the live game folder after merging.",
    )
    args = parser.parse_args()

    # --- prerequisite checks ---
    if not UNP4K_EXE.exists():
        abort(f"unp4k.exe not found: {UNP4K_EXE}")
    if not UNFORGE_EXE.exists():
        abort(f"unforge.exe not found: {UNFORGE_EXE}")
    if not GAME_PAK.exists():
        abort(f"Data.p4k not found: {GAME_PAK}")
    if not TARGET_STRINGS.exists():
        abort(f"target_strings.ini not found: {TARGET_STRINGS}")

    # --- run pipeline ---
    extract()
    copy_to_src()
    sub_count, line_count = merge()
    extract_dcb()
    bp_count = extract_blueprints()

    print()
    print("--- Summary ---")
    print(f"    Lines processed : {line_count:,}")
    print(f"    Substitutions   : {sub_count}")
    print(f"    Merged output   : {OUTPUT_MERGED}")
    print(f"    Blueprints      : {bp_count} rows \u2192 {BLUEPRINT_CSV}")

    if args.deploy:
        deploy()
        print(f"    Deployed to     : {GAME_INI}")

    print("\nDone.")


if __name__ == "__main__":
    main()
