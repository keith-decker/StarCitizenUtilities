"""
Ship components submodule — extract component metadata (Type, Size, Grade,
Manufacturer, Name, Class) from DataForge records and write ship_components.csv.

Prerequisite: unforge.exe must have already been run to unpack Game2.dcb.
"""

import csv
import re

from sc_config import (
    COMPONENT_TYPES,
    DATA_ROOT,
    EXTRACTED_INI,
    SHIP_COMPONENTS_CSV,
    SHIP_COMPONENTS_INI,
    SRC_GLOBAL_INI,
    step,
)

SCITEM_ROOT = DATA_ROOT / "entities" / "scitem" / "ships"
MFGR_ROOT = DATA_ROOT / "scitemmanufacturer"

GRADE_MAP = {"1": "A", "2": "B", "3": "C", "4": "D"}

_RE_ATTACH = re.compile(r"<AttachDef\s[^>]+>")
_RE_ATTR = re.compile(r'\b(\w+)="([^"]*)"')
_RE_ENTITY = re.compile(r"<EntityClassDefinition\.(\S+)\s")
_RE_REF = re.compile(r'__ref="([0-9a-f-]{36})"')
_RE_CODE = re.compile(r'\bCode="([^"]+)"')
_RE_CLASS = re.compile(r"\\nClass:\s*([^\\]+)")

# Maps full class name (from DataForge desc field) → 2-letter abbreviation used in override values
CLASS_ABBREV: dict[str, str] = {
    "Civilian": "Ci",
    "Industrial": "In",
    "Military": "Mi",
    "Competition": "Co",
    "Stealth": "St",
}


def _load_key_map(path) -> dict[str, str]:
    """Return lowercase_key → original_case_key for every key=value line in path."""
    key_map: dict[str, str] = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            eq = line.find("=")
            if eq > 0:
                orig_key = line[:eq].strip()
                if orig_key:
                    key_map[orig_key.lower()] = orig_key
    return key_map


def _find_loc_key(key_map: dict[str, str], entity_class: str) -> str:
    """Return the original-case localization key for entity_class, or '' if not found."""
    base = re.sub(r"_SCItem$", "", entity_class, flags=re.IGNORECASE)
    for template, ec in (
        ("item_Name_{}", entity_class),
        ("item_Name{}", entity_class),
        ("item_Name_{}", base),
        ("item_Name{}", base),
    ):
        lower = template.format(ec).lower()
        if lower in key_map:
            return key_map[lower]
    return ""


def build_components_ini(rows: list[dict]) -> int:
    """
    Generate ship_components.ini from the extracted component rows.
    Each line: <loc_key>=<Name> (<ClassAbbrev>/<Grade>)
    Only components with a resolved name and localization key are included.
    Returns the number of unique entries written.
    """
    step(f"Building {SHIP_COMPONENTS_INI.name} from {len(rows)} components")
    key_map = _load_key_map(SRC_GLOBAL_INI)

    seen: set[str] = set()
    entries: list[tuple[str, str]] = []
    for row in rows:
        if not row["Name"] or not row["EntityClass"]:
            continue
        loc_key = _find_loc_key(key_map, row["EntityClass"])
        if not loc_key or loc_key in seen:
            continue
        class_abbrev = CLASS_ABBREV.get(row["Class"], row["Class"])
        entries.append((loc_key, f"{row['Name']} ({class_abbrev}/{row['Grade']})"))
        seen.add(loc_key)

    with open(SHIP_COMPONENTS_INI, "w", encoding="utf-8") as f:
        for key, value in entries:
            f.write(f"{key}={value}\n")

    print(f"      {len(entries)} entries written.")
    return len(entries)


def _load_localization() -> dict[str, str]:
    loc: dict[str, str] = {}
    with open(EXTRACTED_INI, encoding="utf-8", errors="replace") as f:
        for line in f:
            eq = line.find("=")
            if eq > 0:
                loc[line[:eq].strip().lower()] = line[eq + 1 :].rstrip("\n")
    return loc


def _resolve_name(loc: dict[str, str], entity_class: str) -> str:
    base = re.sub(r"_SCItem$", "", entity_class, flags=re.IGNORECASE)
    for key in (
        f"item_name_{entity_class}",
        f"item_name{entity_class}",
        f"item_name_{base}",
        f"item_name{base}",
    ):
        if key.lower() in loc:
            return loc[key.lower()]
    return ""


def _resolve_class(loc: dict[str, str], entity_class: str) -> str:
    base = re.sub(r"_SCItem$", "", entity_class, flags=re.IGNORECASE)
    for key in (
        f"item_Desc{entity_class}",
        f"item_Desc_{entity_class}",
        f"item_Desc{base}",
        f"item_Desc_{base}",
    ):
        if key.lower() in loc:
            m = _RE_CLASS.search(loc[key.lower()])
            if m:
                return m.group(1).strip()
    return ""


def _load_manufacturers(loc: dict[str, str]) -> dict[str, str]:
    index: dict[str, str] = {}
    for f in MFGR_ROOT.rglob("*.xml"):
        content = f.read_text(encoding="utf-8", errors="replace")
        ref_m = _RE_REF.search(content)
        code_m = _RE_CODE.search(content)
        if not ref_m or not code_m:
            continue
        code = code_m.group(1)
        index[ref_m.group(1)] = loc.get(f"manufacturer_name{code}".lower(), code)
    return index


def extract_ship_components() -> int:
    """
    Scan DataForge ship entity XML files and write ship_components.csv.
    Only component types listed in COMPONENT_TYPES (sc_config.py) are included.
    Returns the number of rows written.
    """
    step("[1/4] Loading localization strings for ship component name resolution")
    loc = _load_localization()
    print(f"      {len(loc):,} strings loaded.")

    step("[2/4] Indexing manufacturer GUIDs")
    mfgr_index = _load_manufacturers(loc)
    print(f"      {len(mfgr_index)} manufacturers indexed.")

    step("[3/4] Scanning ship component entity files")
    xml_files = list(SCITEM_ROOT.rglob("*.xml"))
    print(f"      {len(xml_files)} XML files found.")

    rows: list[dict] = []
    for f in xml_files:
        content = f.read_text(encoding="utf-8", errors="replace")

        attach_m = _RE_ATTACH.search(content)
        if not attach_m:
            continue
        attrs = dict(_RE_ATTR.findall(attach_m.group(0)))

        item_type = attrs.get("Type", "")
        if item_type not in COMPONENT_TYPES:
            continue

        sub_type = attrs.get("SubType", "")
        size = attrs.get("Size", "")
        grade = GRADE_MAP.get(attrs.get("Grade", ""), attrs.get("Grade", ""))
        mfgr = mfgr_index.get(attrs.get("Manufacturer", ""), "")

        entity_m = _RE_ENTITY.search(content)
        entity_class = entity_m.group(1) if entity_m else ""

        rows.append(
            {
                "EntityClass": entity_class,
                "Name": _resolve_name(loc, entity_class) if entity_class else "",
                "Type": item_type,
                "SubType": "" if sub_type == "UNDEFINED" else sub_type,
                "Size": size,
                "Grade": grade,
                "Class": _resolve_class(loc, entity_class) if entity_class else "",
                "Manufacturer": mfgr,
            }
        )

    print(f"      {len(rows)} components extracted.")

    step(f"[4/5] Writing {SHIP_COMPONENTS_CSV}")
    fieldnames = [
        "EntityClass",
        "Name",
        "Type",
        "SubType",
        "Size",
        "Grade",
        "Class",
        "Manufacturer",
    ]
    with open(SHIP_COMPONENTS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    step(f"[5/5] Generating localization overrides")
    ini_count = build_components_ini(rows)
    return len(rows), ini_count
