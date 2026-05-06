"""
Detailed Blueprints submodule — extract all game blueprints (FPS weapons, armor, ship components)
and output as structured JSON for tool consumption.

Categories:
  - fps_weapons: FPS weapon blueprints (guns, rifles, etc.)
  - fps_armor: FPS armor blueprints (suits, helmets, backpacks)
  - ship_components: Ship component blueprints (power plants, shields, etc.)

Output structure organized by category for easy filtering and querying.
"""

import csv
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

    # Map of known item GUIDs to material names (FPS harvestable minerals)
    ITEM_MATERIAL_MAP = {
        "0b83f4b2-1d15-4843-aa94-29f2b40a5cbe": "Caranite",  # harvestable_mineral_1h_carinite
        "125dd723-95ad-488d-830f-62c954445ca1": "Hadanite",  # harvestable_mineral_1h_hadanite
        "20094ded-ad04-46a3-b734-9e37aa3154b3": "Dolivine",  # harvestable_mineral_1h_dolivine
        "38d7d7e9-819b-4351-a40e-7b764cb304e6": "Beradom",  # harvestable_mineral_1h_beradom
        "3f137385-dd8f-410b-b5f3-7b4d283c09cd": "Aphorite",  # harvestable_mineral_1h_aphorite
        "51b456cd-e73e-42a8-b36e-0bf6fbe29ce6": "Sadaryx",  # harvestable_mineral_1h_sadaryx
        "e954d75e-fb1e-487e-90a8-170f0284b502": "Janalite",  # harvestable_mineral_1h_janalite
    }

    for cost_select in all_selects:
        # Get the display name from nameInfo
        name_info = cost_select.find("nameInfo")
        slot_name = ""
        slot_display_key = ""

        if name_info is not None:
            slot_name = name_info.get("debugName", "")
            slot_display_key = name_info.get("displayName", "")

        # Try CraftingCost_Resource first
        resource_elem = cost_select.find("options/CraftingCost_Resource")
        if resource_elem is not None:
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
        else:
            # Try CraftingCost_Item (for items like Caranite)
            item_elem = cost_select.find("options/CraftingCost_Item")
            if item_elem is not None:
                item_class = item_elem.get("entityClass", "")
                quantity = float(item_elem.get("quantity", 1))
                min_quality = item_elem.get("minQuality", "0")

                # Look up material name from item GUID
                material_name = ITEM_MATERIAL_MAP.get(item_class, "")
                if not material_name:
                    # If not found, use slot name as fallback
                    material_name = slot_name

                materials.append(
                    {
                        "resource_guid": item_class,
                        "resource_name": slot_name,
                        "material_name": material_name,
                        "quantity_scu": quantity,  # quantity for items, not SCU
                        "min_quality": int(min_quality),
                    }
                )

    return materials


def _load_entity_display_names(loc_map: dict[str, str]) -> dict[str, str]:
    """
    Build a comprehensive item_id → display_name mapping by scanning entity XML files.

    Covers:
      - FPS weapons (all variants, all manufacturers, ballistic + energy)
      - FPS weapon magazines / ammo
      - FPS armor (all manufacturers, all weight classes)
      - Ship components (power plants, shields, coolers, quantum drives, etc.)

    Uses <Localization Name="@KEY"> in each entity XML, resolved via loc_map.
    Falls back to empty string if no valid localization found.
    """
    display_names: dict[str, str] = {}

    entity_dirs = [
        # All FPS weapon variants (incl. energy, tints, collector editions)
        DATA_ROOT / "entities" / "scitem" / "weapons" / "fps_weapons",
        # Magazine / ammo entities
        DATA_ROOT / "entities" / "scitem" / "weapons" / "magazines",
        # FPS armor body pieces (CDS, QRT, KAP, etc.) — nested by weight/slot
        DATA_ROOT / "entities" / "scitem" / "characters" / "human" / "armor",
        # FPS helmets — separate subtree
        DATA_ROOT
        / "entities"
        / "scitem"
        / "characters"
        / "human"
        / "starwear"
        / "helmet",
    ]

    # Add all ship component subdirectories (powerplant, shieldgenerator, cooler, etc.)
    ships_dir = DATA_ROOT / "entities" / "scitem" / "ships"
    if ships_dir.exists():
        for subdir in ships_dir.iterdir():
            if subdir.is_dir() and not subdir.name.startswith("_"):
                entity_dirs.append(subdir)

    loc_re = re.compile(r'<Localization\b[^>]*\bName="@([^"]+)"', re.IGNORECASE)

    for base_dir in entity_dirs:
        if not base_dir.exists():
            continue
        for xml_file in base_dir.rglob("*.xml"):
            item_id = xml_file.stem
            if item_id in display_names:
                continue
            try:
                text = xml_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            m = loc_re.search(text)
            if not m:
                continue
            loc_key = m.group(1).lower()
            name = loc_map.get(loc_key, "")
            if name and name not in (
                "@LOC_PLACEHOLDER",
                "@LOC_UNINITIALIZED",
                "@LOC_EMPTY",
            ):
                display_names[item_id] = name

    # Supplemental fallback: scan loc_map for item_name_* keys to fill any gaps
    # left by missing entity XML files. Handles both plain and ",p" suffix variants.
    for key, value in loc_map.items():
        if not key.startswith("item_name_"):
            continue
        item_id = key[len("item_name_") :]
        if item_id.endswith(",p"):
            item_id = item_id[:-2]
        if (
            item_id
            and item_id not in display_names
            and value
            and not value.startswith("@LOC_")
        ):
            display_names[item_id] = value

    return display_names


def _get_display_name(item_id: str, display_names: dict[str, str]) -> str:
    """
    Get display name for any item. Tries exact match first, then strips common
    cosmetic variant suffixes to inherit the base item's display name.
    Returns item_id unchanged if nothing found.
    """
    if item_id in display_names:
        return display_names[item_id]

    # Sorted longest-first so multi-word suffixes match before shorter ones
    variant_suffixes = sorted(
        [
            "_firerats01",
            "_firerats02",
            "_firerats03",
            "_collector01",
            "_collector02",
            "_arctic01",
            "_arctic02",
            "_black01",
            "_black02",
            "_black03",
            "_blue01",
            "_blue02",
            "_blue_gold",
            "_blue_white01",
            "_blue_white02",
            "_gold01",
            "_gold02",
            "_green01",
            "_green02",
            "_green_grey01",
            "_grey_red01",
            "_white01",
            "_white02",
            "_white03",
            "_tan01",
            "_tan02",
            "_imp01",
            "_imp02",
            "_pink_red01",
            "_pink_cian01",
            "_pink_cian02",
            "_red_black01",
            "_red_white01",
            "_tint01",
            "_tint02",
            "_tint03",
            "_tint04",
            "_urban01",
            "_urban02",
            "_engraved01",
            "_engraved02",
            "_digi01",
            "_digi02",
            "_spc",
            "_cc17",
            "_cc17a",
            "_cc17b",
            "_headhunters01",
            "_reward01",
            "_reward02",
            "_300",
            "_default",
            "_ai",
            "_ai_default",
            "_uee01",
            "_uee02",
        ],
        key=len,
        reverse=True,
    )

    item_lower = item_id.lower()
    for suffix in variant_suffixes:
        if item_lower.endswith(suffix):
            base_id = item_id[: -len(suffix)]
            if base_id in display_names:
                return display_names[base_id]
            # Allow one more level of stripping (e.g. tint on top of civilian variant)
            base_lower = base_id.lower()
            for suffix2 in variant_suffixes:
                if base_lower.endswith(suffix2):
                    base2 = base_id[: -len(suffix2)]
                    if base2 in display_names:
                        return display_names[base2]

    return item_id


def _build_mission_standing_index(loc_map: dict[str, str]) -> dict[str, dict]:
    """
    Scan all contract XMLs and reputation standings to build a per-mission index of:
      faction (display name), min_standing (human label), is_rank_locked (bool)

    Returns dict keyed by mission debugName (base name, _V suffix stripped).
    """
    contracts_root = DATA_ROOT / "contracts"
    standings_root = DATA_ROOT / "reputation" / "standings"
    factionrep_root = DATA_ROOT / "factions" / "factionreputation"

    if not contracts_root.exists():
        return {}

    # --- Step 1: Build standing GUID -> human label ---
    standing_label: dict[str, str] = {}  # lower-guid -> label
    if standings_root.exists():
        for xml_file in standings_root.rglob("*.xml"):
            try:
                text = xml_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            ref_m = re.search(r'__ref="([^"]*)"', text)
            if not ref_m:
                continue
            guid = ref_m.group(1).lower()
            for key in re.findall(r"@([A-Za-z0-9_]+)", text):
                if key in ("blank_space", "LOC_PLACEHOLDER"):
                    continue
                label = loc_map.get(key.lower(), "")
                if label:
                    standing_label[guid] = label
                    break

    # --- Step 2: Build faction GUID -> display name (from filename) ---
    faction_name: dict[str, str] = {}  # lower-guid -> name
    if factionrep_root.exists():
        for xml_file in factionrep_root.rglob("*.xml"):
            try:
                text = xml_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            ref_m = re.search(r'__ref="([^"]*)"', text)
            if not ref_m:
                continue
            guid = ref_m.group(1).lower()
            # Try loc keys first
            for key in re.findall(r"@([A-Za-z0-9_]+)", text):
                if key in ("blank_space", "LOC_PLACEHOLDER"):
                    continue
                label = loc_map.get(key.lower(), "")
                if label:
                    faction_name[guid] = label
                    break
            if guid not in faction_name:
                # Derive from filename: factionreputation_lawful_eckhartsecurity -> Eckhartsecurity
                stem = xml_file.stem
                parts = stem.split("_")
                if len(parts) > 2:
                    faction_name[guid] = " ".join(p.capitalize() for p in parts[2:])

    # --- Step 3: Parse contract XMLs with ElementTree ---
    # ContractGeneratorHandler_Career: factionReputation on handler, minStanding on
    #   ContractPrerequisite_Reputation within each CareerContract.
    # ContractGeneratorHandler_List: each Contract in <contracts> has
    #   ContractPrerequisite_Reputation in its <additionalPrerequisites>.
    index: dict[str, dict] = {}
    NULL_GUID = "00000000-0000-0000-0000-000000000000"

    def _add(name: str, fac_guid: str, min_guid: str, max_guid: str) -> None:
        base = name[:-2] if name.endswith("_V") else name
        if base in index:
            return
        index[base] = {
            "faction": faction_name.get(fac_guid.lower(), ""),
            "min_standing": standing_label.get(min_guid.lower(), ""),
            "is_rank_locked": min_guid.lower() == max_guid.lower(),
        }

    for xml_file in contracts_root.rglob("*.xml"):
        try:
            tree = ET.parse(xml_file)
        except ET.ParseError:
            continue
        root_elem = tree.getroot()

        # Career handlers
        for handler in root_elem.iter("ContractGeneratorHandler_Career"):
            fac_guid = handler.get("factionReputation", "")
            for cc in handler.iter("CareerContract"):
                name = cc.get("debugName", "")
                if not name:
                    continue
                # minStanding and maxStanding are direct attributes on CareerContract
                min_guid = cc.get("minStanding", "")
                max_guid = cc.get("maxStanding", "")
                if min_guid and min_guid != NULL_GUID:
                    _add(name, fac_guid, min_guid, max_guid)

        # List handlers
        for handler in root_elem.iter("ContractGeneratorHandler_List"):
            contracts_elem = handler.find("contracts")
            if contracts_elem is None:
                continue
            for contract in contracts_elem:
                name = contract.get("debugName", "")
                if not name:
                    continue
                # additionalPrerequisites is a direct child of the contract element
                add_prereqs = contract.find("additionalPrerequisites")
                if add_prereqs is None:
                    continue
                prereq = add_prereqs.find("ContractPrerequisite_Reputation")
                if prereq is None:
                    continue
                fac_guid = prereq.get("factionReputation", "")
                min_guid = prereq.get("minStanding", "")
                max_guid = prereq.get("maxStanding", "")
                if min_guid and min_guid != NULL_GUID:
                    _add(name, fac_guid, min_guid, max_guid)

    return index


def _extract_blueprint_data(
    blueprint_file: Path,
    resource_map: dict[str, str],
    loc_map: dict[str, str],
    display_names: dict[str, str],
    mission_sources: list[dict],
    mission_standing_index: dict[str, dict] | None = None,
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

    # Filter mission sources for this item
    item_missions = [m for m in mission_sources if m["ItemId"] == item_id]

    # Infer armor weight class from item_id token
    armor_class: str | None = None
    if category == "fps_armor":
        item_lower = item_id.lower()
        if "_light_" in item_lower:
            armor_class = "light"
        elif "_medium_" in item_lower:
            armor_class = "medium"
        elif "_heavy_" in item_lower:
            armor_class = "heavy"

    result = {
        "item_id": item_id,
        "display_name": _get_display_name(item_id, display_names),
        "blueprint_guid": blueprint_guid,
        "blueprint_file": blueprint_file.name,
        "category": category,
        "mission_sources": [
            {
                "mission_name": m["MissionName"],
                "chance": float(m.get("Chance", 0)),
                **(
                    {
                        "faction": (mission_standing_index or {})
                        .get(m["MissionName"], {})
                        .get("faction", ""),
                        "min_standing": (mission_standing_index or {})
                        .get(m["MissionName"], {})
                        .get("min_standing", ""),
                        "is_rank_locked": (mission_standing_index or {})
                        .get(m["MissionName"], {})
                        .get("is_rank_locked", False),
                    }
                    if mission_standing_index is not None
                    else {}
                ),
            }
            for m in item_missions
        ],
        "tiers": tiers,
    }
    if armor_class is not None:
        result["armor_class"] = armor_class
    return result


def extract_all_blueprints(blueprint_rewards: list[dict] = None) -> int:
    """
    Walk all blueprint files and extract comprehensive data.

    Args:
        blueprint_rewards: List of dicts from sc_blueprints.extract_blueprints()
                         with keys: MissionName, ItemId, ItemName, Chance, etc.
                         If None, mission_sources will be empty for all blueprints.

    Returns the number of blueprints extracted.
    """
    if blueprint_rewards is None:
        blueprint_rewards = []

    blueprint_dir = DATA_ROOT / "crafting" / "blueprints"
    if not blueprint_dir.exists():
        return 0

    step("[1/5] Building resource GUID → name mapping")
    resource_map = get_resource_mapping()

    step("[2/5] Loading localization strings and weapon display names")
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

    display_names = _load_entity_display_names(loc_map)
    print(f"      {len(display_names)} entity display names loaded.")

    step("[3/5] Building mission → standing/faction index")
    mission_standing_index = _build_mission_standing_index(loc_map)
    print(f"      {len(mission_standing_index)} missions indexed with standing data.")

    step("[4/5] Scanning blueprint files")
    blueprint_files = list(blueprint_dir.rglob("*.xml"))
    print(f"      {len(blueprint_files)} blueprint files found.")

    step("[5/5] Extracting blueprint data")
    blueprints: list[dict] = []

    for bp_file in blueprint_files:
        data = _extract_blueprint_data(
            bp_file,
            resource_map,
            loc_map,
            display_names,
            blueprint_rewards,
            mission_standing_index,
        )
        if data:
            blueprints.append(data)

    # Sort by item_id for consistency
    blueprints.sort(key=lambda x: x["item_id"])

    step(f"[6/6] Writing {BLUEPRINTS_JSON}")

    with open(BLUEPRINTS_JSON, "w", encoding="utf-8") as f:
        json.dump(blueprints, f, indent=2, ensure_ascii=False)

    return len(blueprints)
