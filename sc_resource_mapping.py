"""
Build resource GUID → name mapping by scanning game data entities and databases.
This identifies what each crafting resource GUID represents in human-readable form.
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from collections import defaultdict

from sc_config import DATA_ROOT, EXTRACTED_INI, step


def _load_localization() -> dict[str, str]:
    """Load localization strings from extracted INI."""
    loc: dict[str, str] = {}
    try:
        with open(EXTRACTED_INI, encoding="utf-8", errors="replace") as f:
            for line in f:
                eq = line.find("=")
                if eq > 0:
                    loc[line[:eq].strip().lower()] = line[eq + 1 :].rstrip("\n")
    except (FileNotFoundError, IOError):
        pass
    return loc


def _scan_entity_files() -> dict[str, tuple]:
    """
    Scan entity files to find SCItem definitions with GUIDs and their names.
    Returns mapping of GUID → (item_id, display_name, entity_class)
    """
    guid_to_entity = {}
    entity_dir = DATA_ROOT / "entities" / "scitem"

    if not entity_dir.exists():
        return guid_to_entity

    loc = _load_localization()
    entity_files = list(entity_dir.glob("*.xml"))

    for entity_file in entity_files:
        try:
            tree = ET.parse(entity_file)
            root = tree.getroot()
        except ET.ParseError:
            continue

        # Get the entity GUID and class
        entity_guid = root.get("__ref", "").lower()
        entity_class = root.get("__type", "")

        if not entity_guid:
            continue

        # Extract item ID (usually from filename or from the entity definition)
        item_id = entity_file.stem

        # Try to find display name from localization
        display_name = ""
        for key_pattern in [f"item_name_{item_id}", f"item_name{item_id}"]:
            if key_pattern.lower() in loc:
                display_name = loc[key_pattern.lower()]
                break

        guid_to_entity[entity_guid] = (item_id, display_name, entity_class)

    return guid_to_entity


def _scan_crafting_records() -> dict[str, tuple]:
    """
    Scan crafting records to find resource definitions with names.
    Looks for commodity/resource configuration files.
    Returns mapping of GUID → (resource_type, name)
    """
    guid_to_resource = {}

    # Try commodity configuration
    commodity_dir = DATA_ROOT / "commodityconfiguration"
    if commodity_dir.exists():
        for xml_file in commodity_dir.glob("*.xml"):
            try:
                tree = ET.parse(xml_file)
                root = tree.getroot()

                for elem in root.iter():
                    guid = elem.get("__ref", "").lower()
                    if guid:
                        # Try to extract meaningful name from element or filename
                        name = elem.get("__type", xml_file.stem)
                        guid_to_resource[guid] = ("commodity", name)
            except ET.ParseError:
                continue

    # Try item resource network
    resource_net_dir = DATA_ROOT / "itemresourcenetwork"
    if resource_net_dir.exists():
        for xml_file in resource_net_dir.glob("*.xml"):
            try:
                tree = ET.parse(xml_file)
                root = tree.getroot()

                for elem in root.iter():
                    guid = elem.get("__ref", "").lower()
                    if guid:
                        name = elem.get("__type", xml_file.stem)
                        guid_to_resource[guid] = ("resource", name)
            except ET.ParseError:
                continue

    return guid_to_resource


def _scan_blueprint_references() -> dict[str, str]:
    """
    Scan all blueprint files to collect all unique resource GUIDs used.
    This helps us understand what resources are actually needed.
    """
    resource_guids = set()
    blueprint_dir = DATA_ROOT / "crafting" / "blueprints"

    if not blueprint_dir.exists():
        return {}

    for blueprint_file in blueprint_dir.rglob("*.xml"):
        try:
            tree = ET.parse(blueprint_file)
            root = tree.getroot()

            for elem in root.iter("CraftingCost_Resource"):
                resource_guid = elem.get("resource", "").lower()
                if resource_guid:
                    resource_guids.add(resource_guid)
        except ET.ParseError:
            continue

    return {guid: "" for guid in resource_guids}


def build_resource_mapping() -> dict[str, str]:
    """
    Build comprehensive resource GUID → name mapping.
    Returns dict of {guid: resource_name}
    """
    step("Building resource GUID → name mapping")

    # Start with all GUIDs referenced in blueprints
    guid_map = _scan_blueprint_references()
    print(f"  Found {len(guid_map)} unique resource GUIDs in blueprints")

    # Try to resolve from entities
    print("  Scanning entity files for resource definitions...")
    entity_map = _scan_entity_files()

    for guid, name in entity_map.items():
        if guid in guid_map:
            guid_map[guid] = (
                name[1] or name[0]
            )  # Prefer display_name, fall back to item_id

    print(f"  Resolved {sum(1 for v in guid_map.values() if v)} GUIDs from entities")

    # Try to resolve from crafting records
    print("  Scanning crafting records for resource definitions...")
    resource_map = _scan_crafting_records()

    for guid, name in resource_map.items():
        if guid in guid_map and not guid_map[guid]:
            guid_map[guid] = name[1]

    print(f"  Resolved {sum(1 for v in guid_map.values() if v)} total GUIDs")

    return guid_map


def get_resource_mapping() -> dict[str, str]:
    """
    Get or build the resource mapping.
    Returns dict of {guid_lower: resource_name}
    """
    return build_resource_mapping()
