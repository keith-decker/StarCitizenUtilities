"""
FPS Weapons submodule — extract combat stats for FPS weapons from DataForge.

Produces fps_weapons.csv with one row per fire mode per weapon (base variants only).

Columns:
    WeaponId        internal entity class name
    WeaponName      localized display name
    Manufacturer    manufacturer code (extracted from WeaponId prefix)
    Grade           weapon grade/tier (1-5)
    Size            weapon size class (1-5)
    WeaponType      e.g. rifle, pistol, smg, sniper, shotgun, lmg, special, melee
    FireMode        Rapid / Single / Burst / Charge / Beam etc.
    BurstShots      shots per trigger pull (1 for single/rapid, N for burst)
    FireRate        rounds per minute
    AmmoSpeed       projectile speed (m/s)
    AmmoLifetime    projectile lifetime (s)
    AmmoRange       derived max range = speed * lifetime (m), rounded
    PelletCount     pellets per projectile
    AmmoCost        ammo consumed per shot
    DmgPhysical     physical damage per pellet
    DmgEnergy       energy damage per pellet
    DmgDistortion   distortion damage per pellet
    DmgThermal      thermal damage per pellet
    DmgBiochem      biochemical damage per pellet
    DmgStun         stun damage per pellet
    DmgPerShot      total damage per shot (sum of all damage types * pellets)
    DPS             damage per second (DmgPerShot * FireRate / 60)
"""

import csv
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from sc_config import (
    DATA_ROOT,
    EXTRACTED_INI,
    step,
)

FPS_WEAPONS_CSV = Path(__file__).parent / "output" / "fps_weapons.csv"

# Fire action element tag → friendly fire mode name
_FIREMODE_TAG_MAP = {
    "SWeaponActionFireRapidParams": "Rapid",
    "SWeaponActionFireSingleParams": "Single",
    "SWeaponActionFireBurstParams": "Burst",
    "SWeaponActionFireChargedParams": "Charge",
    "SWeaponActionFireBeamParams": "Beam",
    "SWeaponActionFireLaserParams": "Laser",
    "SWeaponActionFireHitscanParams": "Hitscan",
}

# Regex to match any fire action element tag
_FIREMODE_RE = re.compile(
    r"<(" + "|".join(re.escape(t) for t in _FIREMODE_TAG_MAP) + r")\b"
)

# Weapon entity type → weapon type category derived from filename pattern
_TYPE_PATTERNS = [
    (re.compile(r"_rifle_"), "Rifle"),
    (re.compile(r"_smg_"), "SMG"),
    (re.compile(r"_pistol_"), "Pistol"),
    (re.compile(r"_sniper_"), "Sniper"),
    (re.compile(r"_shotgun_"), "Shotgun"),
    (re.compile(r"_lmg_"), "LMG"),
    (re.compile(r"_special_"), "Special"),
    (re.compile(r"_melee_"), "Melee"),
    (re.compile(r"_medgun_"), "Medical"),
    (re.compile(r"_glauncher_"), "Grenade Launcher"),
    (re.compile(r"_binoculars_"), None),  # skip
]


def _classify_weapon(filename: str) -> str | None:
    """Return weapon category string from filename, or None to skip."""
    name = filename.lower()
    for pat, category in _TYPE_PATTERNS:
        if pat.search(name):
            return category
    return "Other"


def _extract_manufacturer(weapon_id: str) -> str:
    """Extract manufacturer code from weapon ID prefix. E.g., 'behr_rifle_01' -> 'behr'."""
    parts = weapon_id.split("_")
    return parts[0].upper() if parts else "UNK"


def extract_fps_weapons() -> int:
    """Extract FPS weapon stats and write fps_weapons.csv. Returns row count."""

    # ---- 1. Load localization -------------------------------------------
    step("[1/5] Loading localization strings for weapon name resolution")
    localization: dict[str, str] = {}
    with open(EXTRACTED_INI, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            localization[key.strip().lower()] = val
    print(f"      {len(localization):,} strings loaded.")

    # ---- 2. Build GUID indexes -----------------------------------------
    step("[2/5] Indexing magazine and ammoparams records by GUID")

    guid_re = re.compile(
        r'__ref="([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"',
        re.IGNORECASE,
    )

    # magazine GUID → magazine file path
    mag_dir = DATA_ROOT / "entities" / "scitem" / "weapons" / "magazines"
    mag_index: dict[str, Path] = {}
    for f in mag_dir.rglob("*.xml"):
        txt = f.read_text(encoding="utf-8", errors="replace")
        m = guid_re.search(txt)
        if m:
            mag_index[m.group(1).lower()] = f

    # ammoparams GUID → ammoparams file path
    ammo_dir = DATA_ROOT / "ammoparams" / "fps"
    ammo_index: dict[str, Path] = {}
    for f in ammo_dir.rglob("*.xml"):
        txt = f.read_text(encoding="utf-8", errors="replace")
        m = guid_re.search(txt)
        if m:
            ammo_index[m.group(1).lower()] = f

    print(f"      {len(mag_index)} magazines, {len(ammo_index)} ammoparams indexed.")

    # ---- 3. Parse ammoparams ------------------------------------------
    def _parse_ammo(ammo_guid: str) -> dict:
        """Return ammo stat dict for a given ammoparams GUID, or empty dict."""
        af = ammo_index.get(ammo_guid.lower())
        if not af:
            return {}
        try:
            root = ET.parse(af).getroot()
        except ET.ParseError:
            return {}
        speed = float(root.get("speed", 0))
        lifetime = float(root.get("lifetime", 0))
        # Damage from projectileParams > BulletProjectileParams > damage > DamageInfo
        dmg: dict[str, float] = {}
        for di in root.iter("DamageInfo"):
            # take the first one (base damage, not drop damage)
            dmg = {
                "DmgPhysical": float(di.get("DamagePhysical", 0)),
                "DmgEnergy": float(di.get("DamageEnergy", 0)),
                "DmgDistortion": float(di.get("DamageDistortion", 0)),
                "DmgThermal": float(di.get("DamageThermal", 0)),
                "DmgBiochem": float(di.get("DamageBiochemical", 0)),
                "DmgStun": float(di.get("DamageStun", 0)),
            }
            break
        return {"speed": speed, "lifetime": lifetime, **dmg}

    # ---- 4. Scan weapon entity files ----------------------------------
    step("[3/5] Scanning FPS weapon entity files")
    weapons_dir = DATA_ROOT / "entities" / "scitem" / "weapons" / "fps_weapons"
    weapon_files = sorted(
        weapons_dir.glob("*.xml")
    )  # root only — dev/ subdir contains NPC-only weapons
    print(f"      {len(weapon_files)} XML files found.")

    rows: list[dict] = []

    # Only process base variants (no skin/tint/collector variants)
    # Heuristic: skip files whose stem contains a second underscore-separated
    # suffix that looks like a variant (tint01, black01, store01, mat01, etc.)
    # We keep files matching the base pattern: <mfr>_<type>_<ammo>_<num>[.xml]
    # Note: 'civilian' is NOT a variant marker (e.g., behr_rifle_ballistic_02_civilian is P8-AR base weapon)
    _variant_re = re.compile(
        r"_(tint|black|white|grey|blue|red|green|gold|tan|purple|orange|"
        r"brown|camo|store|mat|collector|imp|cen|shin|arctic|contestedzone|"
        r"lumi|iae|xenothreat|yellow|prop|test|firerats|msn_rwd|primed|"
        r"urban|fallout|sunset|acid|chromic)\w*$",
        re.IGNORECASE,
    )

    for wf in weapon_files:
        stem = wf.stem
        weapon_type = _classify_weapon(stem)
        if weapon_type is None:
            continue  # explicitly skipped (binoculars, etc.)
        if _variant_re.search(stem):
            continue  # skin/tint variant — skip

        try:
            root = ET.parse(wf).getroot()
        except ET.ParseError:
            continue

        # Display name — lives in <Localization Name="@KEY"> element
        loc_el = root.find(".//Localization")
        if loc_el is not None:
            loc_raw = loc_el.get("Name") or ""
            loc_key = loc_raw.lstrip("@").lower()
        else:
            loc_raw = ""
            loc_key = ""

        # Skip weapons with no real localization (NPC-only / dev weapons)
        if loc_raw.upper() in ("@LOC_PLACEHOLDER", "@LOC_UNINITIALIZED", ""):
            continue

        weapon_name = localization.get(loc_key, stem)
        manufacturer = _extract_manufacturer(stem)

        # Grade and Size — from SAttachableComponentParams > AttachDef
        grade = 1
        size = 1
        for attach_el in root.iter("AttachDef"):
            grade = int(attach_el.get("Grade", 1) or 1)
            size = int(attach_el.get("Size", 1) or 1)
            break

        # Ammo container → magazine → ammoparams
        ammo_stats: dict = {}
        ammo_container_guid = ""
        for wcp in root.iter("SCItemWeaponComponentParams"):
            ammo_container_guid = (wcp.get("ammoContainerRecord") or "").lower()
            break

        if ammo_container_guid:
            mag_file = mag_index.get(ammo_container_guid)
            if mag_file:
                try:
                    mag_root = ET.parse(mag_file).getroot()
                except ET.ParseError:
                    mag_root = None
                if mag_root is not None:
                    for acc in mag_root.iter("SAmmoContainerComponentParams"):
                        ammo_params_guid = (acc.get("ammoParamsRecord") or "").lower()
                        if ammo_params_guid:
                            ammo_stats = _parse_ammo(ammo_params_guid)
                        break

        speed = ammo_stats.get("speed", 0)
        lifetime = ammo_stats.get("lifetime", 0)
        ammo_range = round(speed * lifetime) if speed and lifetime else 0
        dmg_physical = ammo_stats.get("DmgPhysical", 0)
        dmg_energy = ammo_stats.get("DmgEnergy", 0)
        dmg_distortion = ammo_stats.get("DmgDistortion", 0)
        dmg_thermal = ammo_stats.get("DmgThermal", 0)
        dmg_biochem = ammo_stats.get("DmgBiochem", 0)
        dmg_stun = ammo_stats.get("DmgStun", 0)

        # Fire modes — deduplicate identical entries (game data sometimes repeats them)
        seen_modes: set[str] = set()
        for fa in root.iter():
            mode_name = _FIREMODE_TAG_MAP.get(fa.tag)
            if mode_name is None:
                continue

            fire_rate = float(fa.get("fireRate", 0))
            burst_shots = int(fa.get("burstShots", 1) or 1)

            # pelletCount and ammoCost live in child <launchParams>/<SProjectileLauncher>
            pellet_count = 1
            ammo_cost = 1
            for lp in fa.iter("SProjectileLauncher"):
                pellet_count = int(lp.get("pelletCount", 1) or 1)
                ammo_cost = int(lp.get("ammoCost", 1) or 1)
                break

            # Dedup key: mode + fire rate + pellet count (identical entries in game data)
            dedup_key = (mode_name, fire_rate, pellet_count)
            if dedup_key in seen_modes:
                continue
            seen_modes.add(dedup_key)

            total_dmg_per_pellet = (
                dmg_physical
                + dmg_energy
                + dmg_distortion
                + dmg_thermal
                + dmg_biochem
                + dmg_stun
            )
            dmg_per_shot = round(total_dmg_per_pellet * pellet_count, 4)
            dps = round(dmg_per_shot * fire_rate / 60, 3) if fire_rate else 0

            rows.append(
                {
                    "WeaponId": stem,
                    "WeaponName": weapon_name.strip(),
                    "Manufacturer": manufacturer,
                    "Grade": grade,
                    "Size": size,
                    "WeaponType": weapon_type,
                    "FireMode": mode_name,
                    "BurstShots": burst_shots,
                    "FireRate": int(fire_rate),
                    "AmmoSpeed": int(speed),
                    "AmmoLifetime": lifetime,
                    "AmmoRange": ammo_range,
                    "PelletCount": pellet_count,
                    "AmmoCost": ammo_cost,
                    "DmgPhysical": dmg_physical,
                    "DmgEnergy": dmg_energy,
                    "DmgDistortion": dmg_distortion,
                    "DmgThermal": dmg_thermal,
                    "DmgBiochem": dmg_biochem,
                    "DmgStun": dmg_stun,
                    "DmgPerShot": dmg_per_shot,
                    "DPS": dps,
                }
            )

    # ---- 5. Write CSV --------------------------------------------------
    step(f"[4/5] Writing {FPS_WEAPONS_CSV}")
    FPS_WEAPONS_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "WeaponId",
        "WeaponName",
        "Manufacturer",
        "Grade",
        "Size",
        "WeaponType",
        "FireMode",
        "BurstShots",
        "FireRate",
        "AmmoSpeed",
        "AmmoLifetime",
        "AmmoRange",
        "PelletCount",
        "AmmoCost",
        "DmgPhysical",
        "DmgEnergy",
        "DmgDistortion",
        "DmgThermal",
        "DmgBiochem",
        "DmgStun",
        "DmgPerShot",
        "DPS",
    ]
    with open(FPS_WEAPONS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"      {len(rows)} rows written.")
    return len(rows)
