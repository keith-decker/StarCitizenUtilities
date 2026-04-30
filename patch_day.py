#!/usr/bin/env python3
"""
SC Patch Day — Star Citizen patch-day extraction and merge orchestrator.

Modes:
  (default)  Localization only — extract global.ini, apply overrides, write merged.ini
  --full     Full extract — localization + blueprint rewards CSV + ship components CSV

Flags:
  --ptu        Target the PTU installation instead of LIVE (default: LIVE)
  --deploy     Copy merged.ini to the live game folder after merging (any mode)
  --skip-dcb   Skip the unforge Game2.dcb extraction step (use existing records)

Usage:
    python patch_day.py                          # localization merge only (LIVE)
    python patch_day.py --ptu                    # localization merge only (PTU)
    python patch_day.py --deploy                 # localization merge + deploy to game
    python patch_day.py --full                   # localization + blueprints + ship components
    python patch_day.py --full --ptu             # same, targeting PTU branch
    python patch_day.py --full --deploy          # everything + deploy to game
    python patch_day.py --full --skip-dcb        # full extract, reuse existing DCB records
    python patch_day.py --full --skip-dcb --deploy  # same + deploy to game

All paths are configured in sc_config.py.
"""

# --ptu must be detected before sc_config is imported so the env var is set
# in time for sc_config’s module-level branch selection.
import os
import sys

if "--ptu" in sys.argv:
    os.environ["SC_BRANCH"] = "PTU"
else:
    os.environ.setdefault("SC_BRANCH", "LIVE")

import argparse

import sc_blueprints as blueprints
import sc_blueprints_detailed as blueprints_detailed
import sc_fps_weapons as fps_weapons
import sc_localization as localization
import sc_mining_quality as mining_quality
import sc_missiles as missiles
import sc_missions as missions
import sc_ship_armor as ship_armor
import sc_ship_components as ship_components
from sc_config import (
    BLUEPRINT_CSV,
    BLUEPRINTS_JSON,
    EXTRACT_DIR,
    FPS_WEAPONS_CSV,
    GAME_INI,
    GAME_PAK,
    MISSION_BLUEPRINTS_INI,
    MISSILES_INI,
    OUTPUT_MERGED,
    QUALITY_DISTRIBUTIONS_CSV,
    QUALITY_QUANTIZATION_CSV,
    SHIP_ARMOR_CSV,
    SHIP_COMPONENTS_CSV,
    SHIP_COMPONENTS_INI,
    TARGET_STRINGS,
    UNFORGE_EXE,
    UNRESOLVED_ITEMS_MD,
    UNP4K_EXE,
    _BRANCH,
    abort,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Star Citizen patch-day extraction and merge tool.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python patch_day.py                 localization merge only (LIVE)\n"
            "  python patch_day.py --ptu           localization merge only (PTU)\n"
            "  python patch_day.py --deploy        localization merge + deploy to game\n"
            "  python patch_day.py --full                localization + blueprints + ship components\n"
            "  python patch_day.py --full --ptu          same, targeting PTU branch\n"
            "  python patch_day.py --full --deploy       everything + deploy to game\n"
            "  python patch_day.py --full --skip-dcb     full extract, reuse existing DCB records\n"
        ),
    )
    parser.add_argument(
        "--ptu",
        action="store_true",
        help="Target the PTU installation instead of LIVE (default: LIVE).",
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
    parser.add_argument(
        "--skip-dcb",
        action="store_true",
        dest="skip_dcb",
        help="Skip unforge Game2.dcb extraction and use existing DataForge records (useful during testing).",
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

    # --- prepare extract directory ---
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)

    # --- extract pak (always runs) ---
    localization.extract_pak()
    localization.copy_to_src()

    # --- full extract pipeline (--full only) ---
    # Runs before merge so ship_components.ini is ready for the merge step.
    bp_count = csv_count = ini_count = mission_ini_count = unresolved_count = (
        fps_count
    ) = armor_count = missiles_count = detailed_bp_count = quality_dist_count = (
        quality_quant_count
    ) = None
    if args.full:
        if args.skip_dcb:
            print("\n>>> Skipping Game2.dcb extraction (--skip-dcb)")
        else:
            blueprints.extract_dcb()  # unforge Game2.dcb — shared prerequisite for both CSVs
        bp_count = blueprints.extract_blueprints()
        csv_count, ini_count = ship_components.extract_ship_components()
        mission_ini_count, unresolved_count = missions.extract_mission_blueprints()
        fps_count = fps_weapons.extract_fps_weapons()
        armor_count = ship_armor.extract_ship_armor()
        missiles_count = missiles.extract_missiles()
        detailed_bp_count = blueprints_detailed.extract_all_blueprints()
        quality_dist_count, quality_quant_count = (
            mining_quality.extract_mining_quality()
        )

    # --- merge (always runs; picks up ship_components.ini automatically if present) ---
    sub_count, line_count = localization.merge()

    # --- deploy (--deploy only) ---
    if args.deploy:
        localization.deploy()

    # --- summary ---
    print()
    print("--- Summary ---")
    print(f"    Branch          : {_BRANCH}")
    print(f"    Lines processed : {line_count:,}")
    print(f"    Substitutions   : {sub_count}")
    print(f"    Merged output   : {OUTPUT_MERGED}")
    if bp_count is not None:
        print(f"    Blueprints      : {bp_count} rows → {BLUEPRINT_CSV}")
    if csv_count is not None:
        print(f"    Component CSV   : {csv_count} rows → {SHIP_COMPONENTS_CSV}")
    if ini_count is not None:
        print(f"    Component INI   : {ini_count} entries → {SHIP_COMPONENTS_INI}")
    if mission_ini_count is not None:
        print(
            f"    Mission INI     : {mission_ini_count} entries → {MISSION_BLUEPRINTS_INI}"
        )
    if unresolved_count is not None:
        print(f"    Unresolved      : {unresolved_count} items → {UNRESOLVED_ITEMS_MD}")
    if fps_count is not None:
        print(f"    FPS Weapons     : {fps_count} rows → {FPS_WEAPONS_CSV}")
    if armor_count is not None:
        print(f"    Ship Armor      : {armor_count} rows → {SHIP_ARMOR_CSV}")
    if missiles_count is not None:
        print(f"    Missiles        : {missiles_count} entries → {MISSILES_INI}")
    if detailed_bp_count is not None:
        print(f"    All Blueprints  : {detailed_bp_count} items → {BLUEPRINTS_JSON}")
    if quality_dist_count is not None:
        print(
            f"    Quality Dists   : {quality_dist_count} rows → {QUALITY_DISTRIBUTIONS_CSV}"
        )
    if quality_quant_count is not None:
        print(
            f"    Quality Quant   : {quality_quant_count} materials → {QUALITY_QUANTIZATION_CSV}"
        )
    if args.deploy:
        print(f"    Deployed to     : {GAME_INI}")
    print("\nDone.")


if __name__ == "__main__":
    main()
