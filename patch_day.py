#!/usr/bin/env python3
"""
SC Patch Day — Star Citizen patch-day extraction and merge orchestrator.

Modes:
  (default)  Localization only — extract global.ini, apply overrides, write merged.ini
  --full     Full extract — localization + blueprints + weapons + quality data + localization INIs
  --crafting Crafting data only — blueprints.json, fps_weapons.csv, quality_quantization.json (no localization merge)

Flags:
  --ptu        Target the PTU installation instead of LIVE (default: LIVE)
  --deploy     Copy merged.ini to the live game folder after merging (any mode)
  --skip-dcb   Skip the unforge Game2.dcb extraction step (use existing records)
  --hide-owned Scan LIVE game logs and hide already-owned blueprints from mission
               text (LIVE only; ignored silently when --ptu is set)

Usage:
    python patch_day.py                          # localization merge only (LIVE)
    python patch_day.py --ptu                    # localization merge only (PTU)
    python patch_day.py --deploy                 # localization merge + deploy to game
    python patch_day.py --full                   # localization + all crafting data exports
    python patch_day.py --crafting               # crafting data only (no localization merge)
    python patch_day.py --full --ptu             # same, targeting PTU branch
    python patch_day.py --full --hide-owned      # hide blueprints you already own
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
import sc_owned_blueprints as owned_blueprints
import sc_ship_armor as ship_armor
import sc_ship_components as ship_components
from sc_config import (
    BLUEPRINT_CSV,
    BLUEPRINTS_JSON,
    BLUEPRINTS_RECEIVED_CSV,
    EXTRACT_DIR,
    FPS_WEAPONS_CSV,
    GAME_INI,
    GAME_PAK,
    MISSION_BLUEPRINTS_INI,
    MISSILES_INI,
    OUTPUT_DIR,
    OUTPUT_MERGED,
    QUALITY_QUANTIZATION_JSON,
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
            "  python patch_day.py --full --hide-owned   hide already-owned blueprints (LIVE only)\n"
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
        "--crafting",
        action="store_true",
        help="Extract crafting data only (blueprints.json, fps_weapons.csv, quality_quantization.json) without localization merge.",
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
    parser.add_argument(
        "--hide-owned",
        action="store_true",
        dest="hide_owned",
        help="Scan LIVE game logs and hide already-owned blueprints from mission text. Ignored when --ptu is set.",
    )
    args = parser.parse_args()

    # --- prerequisite checks ---
    if not UNP4K_EXE.exists():
        abort(f"unp4k.exe not found: {UNP4K_EXE}")
    if not GAME_PAK.exists():
        abort(f"Data.p4k not found: {GAME_PAK}")
    if not TARGET_STRINGS.exists():
        abort(f"target_strings.ini not found: {TARGET_STRINGS}")
    if (args.full or args.crafting) and not UNFORGE_EXE.exists():
        abort(f"unforge.exe not found: {UNFORGE_EXE}")

    # --crafting implies no localization merge
    do_localization = not args.crafting
    do_crafting = args.full or args.crafting

    # --- prepare extract and output directories ---
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # --- extract pak (runs for localization or if crafting data needed) ---
    if do_localization:
        localization.extract_pak()
        localization.copy_to_src()

    # --- scan game logs for owned blueprints (LIVE + --hide-owned only) ---
    owned_set: frozenset[str] = frozenset()
    owned_new = owned_total = None
    if args.hide_owned:
        if _BRANCH == "PTU":
            print(
                "\n>>> --hide-owned ignored on PTU (blueprints are not persistent on PTU)"
            )
        else:
            owned_new, owned_total = owned_blueprints.scan_and_update_owned()
            owned_set = owned_blueprints.load_owned_names()

    # --- GROUP A: Localization (default + --full) ---
    sub_count = line_count = ini_count = mission_ini_count = unresolved_count = (
        missiles_count
    ) = None

    if do_localization:
        # Extract DCB and build blueprint/component data (needed for mission descriptions)
        blueprint_rewards = None
        if do_crafting or args.hide_owned:
            if args.skip_dcb:
                print("\n>>> Skipping Game2.dcb extraction (--skip-dcb)")
            else:
                blueprints.extract_dcb()
            blueprint_rewards = blueprints.extract_blueprints()

        # Extract ship components INI
        ini_count = ship_components.extract_ship_components()

        # Extract missiles INI
        missiles_count = missiles.extract_missiles()

        # Generate mission blueprints INI (depends on blueprint data)
        mission_ini_count, unresolved_count = missions.extract_mission_blueprints(
            blueprint_rewards=blueprint_rewards, owned=owned_set
        )

        # Merge localization INIs into merged.ini
        sub_count, line_count = localization.merge()

        # Deploy if requested
        if args.deploy:
            localization.deploy()

    # --- GROUP B: Crafting Tracker Data (--full or --crafting) ---
    bp_count = fps_count = detailed_bp_count = quality_quant_count = None

    if do_crafting:
        # Extract DCB if not already done in GROUP A
        if not do_localization:
            if args.skip_dcb:
                print("\n>>> Skipping Game2.dcb extraction (--skip-dcb)")
            else:
                blueprints.extract_dcb()

        # Extract blueprint reward mappings (in-memory only)
        blueprint_rewards = blueprints.extract_blueprints()
        bp_count = len(blueprint_rewards)

        # Extract FPS weapons data
        fps_count = fps_weapons.extract_fps_weapons()

        # Extract blueprints with embedded mission sources
        detailed_bp_count = blueprints_detailed.extract_all_blueprints(
            blueprint_rewards=blueprint_rewards
        )

        # Export quality quantization as JSON
        quality_quant_count = mining_quality.export_quality_quantization_json()

    # --- summary ---
    print()
    print("--- Summary ---")
    print(f"    Branch          : {_BRANCH}")
    if do_localization:
        print(f"    Lines processed : {line_count:,}")
        print(f"    Substitutions   : {sub_count}")
        print(f"    Merged output   : {OUTPUT_MERGED}")
        if ini_count is not None:
            print(f"    Component INI   : {ini_count} entries → {SHIP_COMPONENTS_INI}")
        if mission_ini_count is not None:
            print(
                f"    Mission INI     : {mission_ini_count} entries → {MISSION_BLUEPRINTS_INI}"
            )
        if unresolved_count is not None:
            print(
                f"    Unresolved      : {unresolved_count} items → {UNRESOLVED_ITEMS_MD}"
            )
        if missiles_count is not None:
            print(f"    Missiles INI    : {missiles_count} entries → {MISSILES_INI}")
    if owned_new is not None:
        print(
            f"    Owned Blueprints: {owned_total} total ({owned_new} new) → {BLUEPRINTS_RECEIVED_CSV}"
        )
    if do_crafting:
        if bp_count is not None:
            print(f"    Blueprints      : {bp_count} mission reward mappings")
        if fps_count is not None:
            print(f"    FPS Weapons     : {fps_count} rows → {FPS_WEAPONS_CSV}")
        if detailed_bp_count is not None:
            print(
                f"    All Blueprints  : {detailed_bp_count} items → {BLUEPRINTS_JSON}"
            )
        if quality_quant_count is not None:
            print(
                f"    Quality Bands   : {quality_quant_count} materials → {QUALITY_QUANTIZATION_JSON}"
            )
    if args.deploy and do_localization:
        print(f"    Deployed to     : {GAME_INI}")
    print("\nDone.")


if __name__ == "__main__":
    main()
