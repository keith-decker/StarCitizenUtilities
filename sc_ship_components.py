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
    UNP4K_DIR,
    step,
)

SCITEM_ROOT = DATA_ROOT / "entities" / "scitem" / "ships"
MFGR_ROOT   = DATA_ROOT / "scitemmanufacturer"

GRADE_MAP = {"1": "A", "2": "B", "3": "C", "4": "D"}

_RE_ATTACH = re.compile(r"<AttachDef\s[^>]+>")
_RE_ATTR   = re.compile(r'\b(\w+)="([^"]*)"')
_RE_ENTITY = re.compile(r"<EntityClassDefinition\.(\S+)\s")
_RE_REF    = re.compile(r'__ref="([0-9a-f-]{36})"')
_RE_CODE   = re.compile(r'\bCode="([^"]+)"')
_RE_CLASS  = re.compile(r"\\nClass:\s*([^\\]+)")


def _load_localization() -> dict[str, str]:
    loc: dict[str, str] = {}
    with open(EXTRACTED_INI, encoding="utf-8", errors="replace") as f:
        for line in f:
            eq = line.find("=")
            if eq > 0:
                loc[line[:eq].strip().lower()] = line[eq + 1:].rstrip("\n")
    return loc


def _resolve_name(loc: dict[str, str], entity_class: str) -> str:
    base = re.sub(r"_SCItem$", "", entity_class, flags=re.IGNORECASE)
    for key in (
        f"item_name{entity_class}",
        f"item_name_{entity_class}",
        f"item_name{base}",
        f"item_name_{base}",
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
        ref_m  = _RE_REF.search(content)
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

        sub_type  = attrs.get("SubType", "")
        size      = attrs.get("Size", "")
        grade     = GRADE_MAP.get(attrs.get("Grade", ""), attrs.get("Grade", ""))
        mfgr      = mfgr_index.get(attrs.get("Manufacturer", ""), "")

        entity_m = _RE_ENTITY.search(content)
        entity_class = entity_m.group(1) if entity_m else ""

        rows.append({
            "EntityClass":  entity_class,
            "Name":         _resolve_name(loc, entity_class) if entity_class else "",
            "Type":         item_type,
            "SubType":      "" if sub_type == "UNDEFINED" else sub_type,
            "Size":         size,
            "Grade":        grade,
            "Class":        _resolve_class(loc, entity_class) if entity_class else "",
            "Manufacturer": mfgr,
        })

    print(f"      {len(rows)} components extracted.")

    step(f"[4/4] Writing {SHIP_COMPONENTS_CSV}")
    fieldnames = ["EntityClass", "Name", "Type", "SubType", "Size", "Grade", "Class", "Manufacturer"]
    with open(SHIP_COMPONENTS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)
