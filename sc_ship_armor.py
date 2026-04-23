"""
Ship armor submodule — extract armor stats (health, damage multipliers, deflection)
from DataForge records and write ship_armor.csv.

Prerequisite: unforge.exe must have already been run to unpack Game2.dcb.
"""

import csv
import xml.etree.ElementTree as ET

from sc_config import (
    DATA_ROOT,
    SHIP_ARMOR_CSV,
    step,
)

ARMOR_ROOT = DATA_ROOT / "entities" / "scitem" / "ships" / "armor"

DAMAGE_TYPES = [
    "DamagePhysical",
    "DamageEnergy",
    "DamageDistortion",
    "DamageThermal",
    "DamageBiochemical",
    "DamageStun",
]

FIELDNAMES = [
    "Ship",
    "Health",
    "Physical Mult",
    "Energy Mult",
    "Distortion Mult",
    "Thermal Mult",
    "Biochemical Mult",
    "Stun Mult",
    "Physical Deflect",
    "Energy Deflect",
    "Distortion Deflect",
    "Thermal Deflect",
    "Biochemical Deflect",
    "Stun Deflect",
]


def _ship_name(filename: str) -> str:
    """Convert armor filename to a readable ship name.

    armr_aegs_avenger_stalker.xml → Aegs Avenger Stalker
    """
    stem = filename.replace("armr_", "").replace(".xml", "")
    return " ".join(p.capitalize() for p in stem.split("_"))


def _parse_armor_file(path) -> dict | None:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return None

    row: dict = {
        "Ship": _ship_name(path.name),
        "Health": 0.0,
    }
    for dt in DAMAGE_TYPES:
        short = dt.replace("Damage", "")
        row[f"{short} Mult"] = 1.0
        row[f"{short} Deflect"] = 0.0

    # Health
    for elem in root.iter("SHealthComponentParams"):
        row["Health"] = float(elem.get("Health", 0))
        break

    # Damage multipliers and deflection
    for elem in root.iter("SCItemVehicleArmorParams"):
        for dmg_info in elem.findall(".//damageMultiplier/DamageInfo"):
            for dt in DAMAGE_TYPES:
                short = dt.replace("Damage", "")
                row[f"{short} Mult"] = float(dmg_info.get(dt, 1))
        for deflect in elem.findall(".//armorDeflection/deflectionValue"):
            for dt in DAMAGE_TYPES:
                short = dt.replace("Damage", "")
                row[f"{short} Deflect"] = float(deflect.get(dt, 0))

    return row


def extract_ship_armor() -> int:
    """Parse all ship armor XML files and write ship_armor.csv.

    Returns the number of rows written.
    """
    step("Extracting ship armor data")

    armor_files = sorted(ARMOR_ROOT.glob("armr_*.xml"))
    if not armor_files:
        print(f"  No armor files found in {ARMOR_ROOT}")
        return 0

    rows = []
    for path in armor_files:
        row = _parse_armor_file(path)
        if row is not None:
            rows.append(row)

    rows.sort(key=lambda r: r["Ship"])

    SHIP_ARMOR_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(SHIP_ARMOR_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f"  Wrote {len(rows)} rows → {SHIP_ARMOR_CSV}")
    return len(rows)
