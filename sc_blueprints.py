"""
Blueprints submodule — extract Game2.dcb DataForge records with unforge.exe,
then build blueprint_rewards.csv mapping missions to craftable item rewards.
"""

import csv
import re
import subprocess
import xml.etree.ElementTree as ET

from sc_config import (
    BLUEPRINT_CSV,
    DATA_ROOT,
    EXTRACTED_INI,
    GAME_DCB_REL,
    UNP4K_DIR,
    UNFORGE_EXE,
    abort,
    step,
)


def extract_dcb() -> None:
    """Run unforge.exe to unpack Game2.dcb records into Data\\Libs\\Foundry\\Records\\."""
    step("Extracting Game2.dcb records with unforge (this may take a few minutes)")
    result = subprocess.run(
        [str(UNFORGE_EXE), str(GAME_DCB_REL)],
        cwd=str(UNP4K_DIR),
    )
    if result.returncode != 0:
        abort(f"unforge.exe exited with code {result.returncode}")


def extract_blueprints() -> int:
    """
    Walk DataForge records to build blueprint_rewards.csv.
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
                localization[line[:eq].strip()] = line[eq + 1:].rstrip("\n")
    print(f"      {len(localization):,} strings loaded.")

    step("[2/5] Indexing BlueprintPoolRecord files by GUID")
    pool_index: dict[str, object] = {}
    for f in (DATA_ROOT / "crafting" / "blueprintrewards" / "blueprintmissionpools").rglob("*.xml"):
        m = guid_re.search(f.read_text(encoding="utf-8", errors="replace"))
        if m:
            pool_index[m.group(1).lower()] = f
    print(f"      {len(pool_index)} blueprint pools indexed.")

    step("[3/5] Indexing CraftingBlueprintRecord files by GUID")
    bp_index: dict[str, object] = {}
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
                        item_id = item_id[len("bp_craft_"):]
                    item_name = (
                        localization.get(f"item_Name{item_id}")
                        or localization.get(f"item_Name_{item_id}")
                        or item_id
                    )
                    rows.append({
                        "MissionName":   mission_name,
                        "ItemId":        item_id,
                        "ItemName":      item_name,
                        "Weight":        weight,
                        "Chance":        chance,
                        "PoolGuid":      pool_guid,
                        "BlueprintFile": bp_file.name,
                    })

    print(f"      {len(rows)} mission→blueprint mappings found.")

    step(f"[5/5] Writing {BLUEPRINT_CSV}")
    fieldnames = ["MissionName", "ItemId", "ItemName", "Weight", "Chance", "PoolGuid", "BlueprintFile"]
    with open(BLUEPRINT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)
