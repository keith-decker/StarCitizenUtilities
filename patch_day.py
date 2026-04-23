#!/usr/bin/env python3
"""
SC Patch Day — Star Citizen patch-day extraction and merge orchestrator.

Modes:
  (default)  Localization only — extract global.ini, apply overrides, write merged.ini
  --full     Full extract — localization + blueprint rewards CSV + ship components CSV

Flags:
  --deploy   Copy merged.ini to the live game folder after merging (any mode)

Usage:
    python patch_day.py                   # localization merge only
    python patch_day.py --deploy          # localization merge + deploy to game
    python patch_day.py --full            # localization + blueprints + ship components
    python patch_day.py --full --deploy   # everything + deploy to game

All paths are configured in sc_config.py.
"""

import argparse

import sc_blueprints as blueprints
import sc_localization as localization
import sc_ship_components as ship_components
from sc_config import (
    BLUEPRINT_CSV,
    GAME_INI,
    GAME_PAK,
    OUTPUT_MERGED,
    SHIP_COMPONENTS_CSV,
    TARGET_STRINGS,
    UNFORGE_EXE,
    UNP4K_EXE,
    abort,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Star Citizen patch-day extraction and merge tool.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python patch_day.py                 localization merge only\n"
            "  python patch_day.py --deploy        localization merge + deploy to game\n"
            "  python patch_day.py --full          localization + blueprints + ship components\n"
            "  python patch_day.py --full --deploy everything + deploy to game\n"
        ),
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Also extract blueprint_rewards.csv and ship_components.csv from DataForge records.",
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
    if not GAME_PAK.exists():
        abort(f"Data.p4k not found: {GAME_PAK}")
    if not TARGET_STRINGS.exists():
        abort(f"target_strings.ini not found: {TARGET_STRINGS}")
    if args.full and not UNFORGE_EXE.exists():
        abort(f"unforge.exe not found: {UNFORGE_EXE}")

    # --- localization pipeline (always runs) ---
    localization.extract_pak()
    localization.copy_to_src()
    sub_count, line_count = localization.merge()

    # --- full extract pipeline (--full only) ---
    bp_count = comp_count = None
    if args.full:
        blueprints.extract_dcb()  # unforge Game2.dcb — shared prerequisite for both CSVs
        bp_count = blueprints.extract_blueprints()
        comp_count = ship_components.extract_ship_components()

    # --- deploy (--deploy only) ---
    if args.deploy:
        localization.deploy()

    # --- summary ---
    print()
    print("--- Summary ---")
    print(f"    Lines processed : {line_count:,}")
    print(f"    Substitutions   : {sub_count}")
    print(f"    Merged output   : {OUTPUT_MERGED}")
    if bp_count is not None:
        print(f"    Blueprints      : {bp_count} rows → {BLUEPRINT_CSV}")
    if comp_count is not None:
        print(f"    Ship components : {comp_count} rows → {SHIP_COMPONENTS_CSV}")
    if args.deploy:
        print(f"    Deployed to     : {GAME_INI}")
    print("\nDone.")


if __name__ == "__main__":
    main()
