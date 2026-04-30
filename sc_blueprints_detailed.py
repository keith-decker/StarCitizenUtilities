"""
Detailed Blueprints submodule — extract all game blueprints (FPS weapons, armor, ship components)
and output as structured JSON for tool consumption.

Categories:
  - fps_weapons: FPS weapon blueprints (guns, rifles, etc.)
  - fps_armor: FPS armor blueprints (suits, helmets, backpacks)
  - ship_components: Ship component blueprints (power plants, shields, etc.)

Output structure organized by category for easy filtering and querying.
"""

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime

from sc_config import (
    DATA_ROOT,
    BLUEPRINTS_JSON,
    EXTRACTED_INI,
    step,
)
from sc_resource_mapping import get_resource_mapping


# Material GUID → specific ore name mapping
# Discovered by scanning commodity filenames (e.g., commodity_metal_iron, commodity_mineral_hephaestanite)
MATERIAL_NAME_MAP = {
    "06cafea0-49fe-4dce-b0f0-dc583316c66d": "Taranite",
    "07570c9f-fdf6-4bca-a56b-c42809ec0e01": "Titanium",
    "1b4c4042-5fdc-4b52-bec4-07085cb3520a": "Tin",
    "21825507-7923-4683-9bf3-9cfe316940e3": "Gold",
    "33bff393-42f1-4f70-85a1-71e695ed2a5a": "Borase",
    "35121003-f1af-481a-b16f-7f48d8af0efb": "Quartz",
    "392b4dca-449a-4d4d-8fef-beab024d9ee7": "Lindinium",
    "4236c16b-c47f-4083-9e26-4313733f2326": "Corundum",
    "48c7080a-bbef-43d2-901a-698321ed4340": "Aluminium",
    "4a47cad8-0271-4048-b19b-d9b52521fc20": "Savrilium",
    "60f116f4-c02a-45b2-9ded-333747795124": "Tungsten",
    "61189578-ed7a-4491-9774-37ae2f82b8b0": "Hephaestanite",
    "75b37a54-45c9-4f27-ac09-9830f092dd86": "Torite",
    "7bbd3197-a6e1-49b3-a495-0b7ef4f8ce40": "Silicon",
    "7f4599b0-a2b2-4178-8c7e-13292054ab20": "Laranite",
    "86d00bd8-08f7-4231-b375-a609803fc46d": "Riccite",
    "8cd317a3-df9b-4315-8ac3-0f1fca42dfd4": "Stileron",
    "93c8b7df-d6ac-4b4f-a115-b0e3afc238b8": "Beryl",
    "989f9b73-f636-4f35-a81d-579dcbe3f0ab": "Ouratite",
    "999e3149-fd10-49ac-914f-8911e61c6122": "Bexalite",
    "a789f57a-e12b-4bcd-8132-e0c03d84fc89": "Copper",
    "bde5a2c8-2ef4-46ac-9403-2fcb79e4016c": "Quantanium",
    "dc6fbcbb-5990-4ed5-82ee-93152dab7845": "Agricium",
    "f386a33c-ac9a-400a-a7b8-fe1fc7c8d270": "Iron",
    "f9f3251a-8e48-408a-b957-f1e3d5d3e213": "Pressurized Ice",
    "fde0cd65-8827-4b23-804d-cc8845dfa7ac": "Aslarite",
}


def _categorize_blueprint(item_id: str) -> str:
    """Determine blueprint category from item ID."""
    item_lower = item_id.lower()

    # Ship components
    if item_lower.startswith(("powr_", "shld_")):
        return "ship_components"

    # FPS weapons - various manufacturers
    if any(
        item_lower.startswith(mfr)
        for mfr in [
            "behr_",
            "gmni_",
            "ksar_",
            "lbco_",
            "volt_",
            "klwe_",
            "grin_",
            "none_",
            "krig_",
            "orig_",
            "rsi_",
            "misc_",
        ]
    ):
        if any(
            wtype in item_lower
            for wtype in [
                "pistol",
                "rifle",
                "smg",
                "sniper",
                "lmg",
                "shotgun",
                "cannon",
            ]
        ):
            # Check if it's a magazine variant
            if "mag" in item_lower:
                return "fps_weapons_ammo"
            return "fps_weapons"

    # FPS armor - various manufacturers
    if any(
        item_lower.startswith(mfr)
        for mfr in ["cds_", "qrt_", "kap_", "omc_", "clda_", "grin_"]
    ):
        if any(
            armor_part in item_lower
            for armor_part in [
                "armor",
                "combat",
                "utility",
                "bodysuit",
                "suit",
                "helmet",
                "arms",
                "core",
                "legs",
                "backpack",
            ]
        ):
            return "fps_armor"

    return "other"


def _extract_craft_time(recipe_elem) -> dict:
    """Extract craft time from CraftingRecipe element."""
    time_elem = recipe_elem.find(".//TimeValue_Partitioned")
    if time_elem is None:
        return {"total_seconds": 0}

    days = int(time_elem.get("days", 0))
    hours = int(time_elem.get("hours", 0))
    minutes = int(time_elem.get("minutes", 0))
    seconds = int(time_elem.get("seconds", 0))

    total_seconds = days * 86400 + hours * 3600 + minutes * 60 + seconds

    return {
        "days": days,
        "hours": hours,
        "minutes": minutes,
        "seconds": seconds,
        "total_seconds": total_seconds,
    }


def _extract_materials(
    recipe_elem, resource_map: dict[str, str], loc_map: dict[str, str] = None
) -> list:
    """Extract material requirements from CraftingRecipe element."""
    materials = []

    # Find ALL CraftingCost_Select elements recursively
    all_selects = recipe_elem.findall(".//CraftingCost_Select")

    for cost_select in all_selects:
        # Check if this select has a direct CraftingCost_Resource child (not nested in options)
        resource_elem = cost_select.find("options/CraftingCost_Resource")
        if resource_elem is None:
            continue

        # Get the display name from nameInfo
        name_info = cost_select.find("nameInfo")
        slot_name = ""
        slot_display_key = ""

        if name_info is not None:
            slot_name = name_info.get("debugName", "")
            slot_display_key = name_info.get("displayName", "")

        resource_guid = resource_elem.get("resource", "")
        min_quality = resource_elem.get("minQuality", "0")

        # Get quantity
        qty_elem = resource_elem.find("quantity/SStandardCargoUnit")
        if qty_elem is not None:
            quantity = float(qty_elem.get("standardCargoUnits", 0))
        else:
            quantity = 0

        # Look up resource name from mapping or use slot name
        resource_name = resource_map.get(resource_guid.lower(), "")
        if not resource_name:
            resource_name = slot_name

        # Try to resolve display name from localization
        if slot_display_key and loc_map:
            display_name = loc_map.get(slot_display_key.lower(), "")
            if display_name:
                resource_name = display_name

        # Look up material name (ore type) from GUID mapping
        material_name = MATERIAL_NAME_MAP.get(resource_guid.lower(), "")

        materials.append(
            {
                "resource_guid": resource_guid,
                "resource_name": resource_name,
                "material_name": material_name,
                "quantity_scu": quantity,
                "min_quality": int(min_quality),
            }
        )

    return materials


def _extract_blueprint_data(
    blueprint_file: Path, resource_map: dict[str, str], loc_map: dict[str, str]
) -> dict:
    """Extract all relevant data from a blueprint XML file."""
    try:
        tree = ET.parse(blueprint_file)
        root = tree.getroot()
    except ET.ParseError:
        return None

    # Get the item ID from the filename
    item_id = blueprint_file.stem
    if item_id.lower().startswith("bp_craft_"):
        item_id = item_id[len("bp_craft_") :]

    category = _categorize_blueprint(item_id)

    # Extract blueprint GUID
    blueprint_guid = root.get("__ref", "")

    # Extract tiers and recipes
    tiers = []
    for tier_idx, tier_elem in enumerate(root.findall(".//CraftingBlueprintTier")):
        recipe_elem = tier_elem.find("recipe/CraftingRecipe")
        if recipe_elem is None:
            continue

        # Extract craft time
        craft_time = _extract_craft_time(recipe_elem)

        # Extract materials
        materials = _extract_materials(recipe_elem, resource_map, loc_map)

        tiers.append(
            {
                "tier": tier_idx,
                "craft_time": craft_time,
                "material_slots": materials,
            }
        )

    return {
        "item_id": item_id,
        "blueprint_guid": blueprint_guid,
        "blueprint_file": blueprint_file.name,
        "category": category,
        "tiers": tiers,
    }


def extract_all_blueprints() -> int:
    """
    Walk all blueprint files and extract comprehensive data.
    Returns the number of blueprints extracted.
    """
    blueprint_dir = DATA_ROOT / "crafting" / "blueprints"
    if not blueprint_dir.exists():
        return 0

    step("[1/5] Building resource GUID → name mapping")
    resource_map = get_resource_mapping()

    step("[2/5] Loading localization strings")
    loc_map: dict[str, str] = {}
    try:
        with open(EXTRACTED_INI, encoding="utf-8", errors="replace") as f:
            for line in f:
                eq = line.find("=")
                if eq > 0:
                    loc_map[line[:eq].strip().lower()] = line[eq + 1 :].rstrip("\n")
    except (FileNotFoundError, IOError):
        pass
    print(f"      {len(loc_map)} localization strings loaded.")

    step("[3/5] Scanning blueprint files")
    blueprint_files = list(blueprint_dir.rglob("*.xml"))
    print(f"      {len(blueprint_files)} blueprint files found.")

    step("[4/5] Extracting blueprint data")
    blueprints_by_category = {
        "fps_weapons": [],
        "fps_weapons_ammo": [],
        "fps_armor": [],
        "ship_components": [],
        "other": [],
    }

    for bp_file in blueprint_files:
        data = _extract_blueprint_data(bp_file, resource_map, loc_map)
        if data:
            category = data["category"]
            blueprints_by_category[category].append(data)

    print(f"      FPS Weapons: {len(blueprints_by_category['fps_weapons'])}")
    print(f"      FPS Ammo: {len(blueprints_by_category['fps_weapons_ammo'])}")
    print(f"      FPS Armor: {len(blueprints_by_category['fps_armor'])}")
    print(f"      Ship Components: {len(blueprints_by_category['ship_components'])}")
    print(f"      Other: {len(blueprints_by_category['other'])}")

    # Sort each category by item_id for consistency
    for category in blueprints_by_category:
        blueprints_by_category[category].sort(key=lambda x: x["item_id"])

    step(f"[5/5] Writing {BLUEPRINTS_JSON}")

    output = {
        "metadata": {
            "extract_date": datetime.utcnow().isoformat(),
            "total_blueprints": sum(len(v) for v in blueprints_by_category.values()),
            "categories": {k: len(v) for k, v in blueprints_by_category.items()},
        },
        "blueprints": blueprints_by_category,
    }

    with open(BLUEPRINTS_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    return output["metadata"]["total_blueprints"]
