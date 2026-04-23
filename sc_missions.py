"""
Missions submodule — append blueprint reward lists to mission description strings
from global.ini and write mission_blueprints.ini for use in the localization merge.

For each description key in global.ini that is referenced by missions with blueprint
rewards:
  - If all missions share the same blueprint pool, one flat list is appended.
  - If missions use different pools, each pool gets a labelled section.  The label
    is derived by stripping the longest common prefix/suffix shared by all missions
    that reference this description key.

Unresolved item names (ItemName == ItemId in the CSV) are included as-is in the
generated INI and catalogued separately in unresolved_blueprint_items.md.

Prerequisite: blueprint_rewards.csv must already exist (run sc_blueprints first).
"""

import csv
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

from sc_config import (
    BLUEPRINT_CSV,
    DATA_ROOT,
    MISSION_BLUEPRINTS_INI,
    SRC_GLOBAL_INI,
    UNRESOLVED_ITEMS_MD,
    step,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _longest_common_prefix(strings: list[str]) -> str:
    if not strings:
        return ""
    prefix = strings[0]
    for s in strings[1:]:
        while not s.startswith(prefix):
            prefix = prefix[:-1]
            if not prefix:
                return ""
    return prefix


def _longest_common_suffix(strings: list[str]) -> str:
    if not strings:
        return ""
    suffix = strings[0]
    for s in strings[1:]:
        while not s.endswith(suffix):
            suffix = suffix[1:]
            if not suffix:
                return ""
    return suffix


def _shorten_labels(all_missions: list[str], pool_missions: list[str]) -> list[str]:
    """
    Strip the longest common prefix and suffix shared by ALL missions for a desc
    key, then return the shortened labels for the given pool_missions subset.
    Falls back to the full name if stripping produces an empty string.
    """
    prefix = _longest_common_prefix(all_missions)
    suffix = _longest_common_suffix(all_missions)
    labels = []
    for m in pool_missions:
        s = m
        if prefix:
            s = s[len(prefix) :]
        if suffix and s.endswith(suffix):
            s = s[: -len(suffix)]
        labels.append(s or m)
    return labels


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------


def extract_mission_blueprints() -> tuple[int, int]:
    """
    Build mission_blueprints.ini and unresolved_blueprint_items.md.
    Returns (ini_entry_count, unique_unresolved_item_count).
    ini_entry_count includes both description and title entries.
    """
    step(
        "[1/4] Building mission → description/title key maps from DataForge contract XMLs"
    )
    mission_desc_key: dict[str, str] = {}
    mission_title_key: dict[str, str] = {}
    for f in (DATA_ROOT / "contracts").rglob("*.xml"):
        try:
            root = ET.parse(f).getroot()
        except ET.ParseError:
            continue
        for cc in root.iter("CareerContract"):
            debug_name = cc.get("debugName", "")
            if not debug_name:
                continue
            for csp in cc.iter("ContractStringParam"):
                param = csp.get("param")
                key = csp.get("value", "").lstrip("@")
                if not key:
                    continue
                if param == "Description":
                    mission_desc_key[debug_name] = key
                elif param == "Title":
                    mission_title_key[debug_name] = key
    print(
        f"      {len(mission_desc_key)} desc / {len(mission_title_key)} title mappings found."
    )

    step("[2/4] Loading blueprint rewards CSV and localization strings")
    bp_rows: list[dict] = []
    with open(BLUEPRINT_CSV, encoding="utf-8") as f:
        bp_rows = list(csv.DictReader(f))

    loc: dict[str, str] = {}
    with open(SRC_GLOBAL_INI, encoding="utf-8", errors="replace") as f:
        for line in f:
            eq = line.find("=")
            if eq > 0:
                loc[line[:eq].strip()] = line[eq + 1 :].rstrip("\n")

    # ------------------------------------------------------------------
    # Build per-mission helpers
    # ------------------------------------------------------------------
    def pools_for_mission(m: str) -> frozenset:
        return frozenset(r["PoolGuid"] for r in bp_rows if r["MissionName"] == m)

    def items_for_mission(m: str) -> list[tuple[str, str]]:
        """Return [(ItemName, ItemId), ...] deduplicated by ItemName."""
        seen: set[str] = set()
        result: list[tuple[str, str]] = []
        for r in bp_rows:
            if r["MissionName"] == m and r["ItemName"] not in seen:
                seen.add(r["ItemName"])
                result.append((r["ItemName"], r["ItemId"]))
        return result

    # Missions that appear in the blueprint CSV
    bp_missions: set[str] = {r["MissionName"] for r in bp_rows}

    # Group desc key → list of missions (only those with blueprint rewards)
    desc_key_missions: dict[str, list[str]] = defaultdict(list)
    for m in bp_missions:
        if m in mission_desc_key:
            desc_key_missions[mission_desc_key[m]].append(m)

    step(f"[3/4] Generating {MISSION_BLUEPRINTS_INI.name}")
    entries: list[tuple[str, str]] = []
    unresolved: list[tuple[str, str, str]] = []  # (desc_key, item_id, display_used)

    for desc_key, missions in sorted(desc_key_missions.items()):
        # Skip if this description key has no entry in global.ini
        orig = loc.get(desc_key)
        if not orig:
            continue

        # Group missions by their blueprint pool set
        pool_groups: dict[frozenset, list[str]] = defaultdict(list)
        for m in missions:
            pool_groups[pools_for_mission(m)].append(m)

        multiple_pools = len(pool_groups) > 1
        all_sorted = sorted(missions)

        bp_section = r"\n\n<EM4>Potential Blueprints</EM4>"

        for pool, pool_missions in pool_groups.items():
            if multiple_pools:
                labels = _shorten_labels(all_sorted, sorted(pool_missions))
                bp_section += r"\n<EM4>[" + ", ".join(labels) + r"]</EM4>"

            for item_name, item_id in items_for_mission(pool_missions[0]):
                is_unresolved = item_name == item_id
                if is_unresolved:
                    unresolved.append((desc_key, item_id, item_name))
                bp_section += r"\n- " + item_name

        bp_section += r"\n"
        entries.append((desc_key, orig + bp_section))

    print(f"      {len(entries)} description entries generated.")

    # ------------------------------------------------------------------
    # Title entries — append " [BP]" to titles of missions with blueprints
    # ------------------------------------------------------------------
    title_keys_with_bp: set[str] = set()
    for m in bp_missions:
        if m in mission_desc_key and mission_desc_key[m] in desc_key_missions:
            tk = mission_title_key.get(m)
            if tk:
                title_keys_with_bp.add(tk)

    title_entries: list[tuple[str, str]] = []
    for tk in sorted(title_keys_with_bp):
        orig_title = loc.get(tk)
        if orig_title:
            title_entries.append((tk, orig_title + " [BP]"))

    print(f"      {len(title_entries)} title entries generated.")

    MISSION_BLUEPRINTS_INI.parent.mkdir(parents=True, exist_ok=True)
    with open(MISSION_BLUEPRINTS_INI, "w", encoding="utf-8") as f:
        for key, value in entries + title_entries:
            f.write(f"{key}={value}\n")

    # ------------------------------------------------------------------
    # Unresolved items report
    # ------------------------------------------------------------------
    unique_ids = sorted({item_id for _, item_id, _ in unresolved})
    step(
        f"[4/4] Writing {UNRESOLVED_ITEMS_MD.name} ({len(unique_ids)} unique unresolved items)"
    )

    with open(UNRESOLVED_ITEMS_MD, "w", encoding="utf-8") as f:
        f.write("# Unresolved Blueprint Item Names\n\n")
        f.write(
            "Items whose display name could not be resolved from `global.ini`. "
            "The raw item ID is used in `mission_blueprints.ini` in place of a display name.\n\n"
        )
        f.write("| Item ID | First seen in mission desc key |\n")
        f.write("|---|---|\n")
        seen: set[str] = set()
        for desc_key, item_id, _ in sorted(unresolved, key=lambda x: x[1]):
            if item_id not in seen:
                seen.add(item_id)
                f.write(f"| `{item_id}` | `{desc_key}` |\n")

    return len(entries) + len(title_entries), len(unique_ids)
