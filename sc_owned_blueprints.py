"""
Owned Blueprints submodule — scan LIVE game logs to build/update the cumulative
list of blueprints this player has earned.

Log format (one canonical line per receipt):
  <ISO8601Z> [Notice] <SHUDEvent_OnNotification> Added notification
      "Received Blueprint: <name>: " [N] to queue. ...

Scans:
  1. All backup logs in GAME_LOG_BACKUPS (sorted oldest-first)
  2. The current session GAME_LOG

Only runs on LIVE — PTU blueprints are not persistent.  Callers should check
_BRANCH before calling these functions (patch_day.py enforces this via --hide-owned).

Output: BLUEPRINTS_RECEIVED_CSV  (Timestamp, Blueprint, LogFile)
        Rows are appended / de-duplicated; existing rows are preserved.
"""

import csv
import re
from datetime import datetime
from pathlib import Path

from sc_config import (
    BLUEPRINTS_RECEIVED_CSV,
    GAME_LOG,
    GAME_LOG_BACKUPS,
    step,
)

# Matches the single canonical "Added notification" line per blueprint receipt.
# Group 1 = ISO8601 timestamp, Group 2 = blueprint display name.
_PATTERN = re.compile(
    r"<(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)>"
    r'.*?Added notification.*?"Received Blueprint: (.+?): "',
    re.IGNORECASE,
)


def _scan_log(path: Path) -> list[tuple[str, str]]:
    """Return [(timestamp, blueprint_name)] from a single log file."""
    results: list[tuple[str, str]] = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = _PATTERN.search(line)
                if m:
                    results.append((m.group(1), m.group(2)))
    except OSError:
        pass
    return results


def _get_newest_timestamp() -> str | None:
    """Return the newest (latest) timestamp from BLUEPRINTS_RECEIVED_CSV, or None if empty."""
    if not BLUEPRINTS_RECEIVED_CSV.exists():
        return None
    newest = None
    with open(BLUEPRINTS_RECEIVED_CSV, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            ts = row["Timestamp"]
            if newest is None or ts > newest:
                newest = ts
    return newest


def scan_and_update_owned() -> tuple[int, int]:
    """
    Scan LIVE game logs newer than the most recent owned blueprint, merge new entries
    into BLUEPRINTS_RECEIVED_CSV. Existing rows are kept; new rows are appended
    (de-duplicated by timestamp+name).

    Returns (new_entries_added, total_owned_blueprints).
    """
    step("Scanning LIVE game logs for owned blueprints")

    # Load existing records keyed by (timestamp, name) to avoid duplicates
    existing: dict[tuple[str, str], str] = {}  # (ts, name) → log_file
    if BLUEPRINTS_RECEIVED_CSV.exists():
        with open(BLUEPRINTS_RECEIVED_CSV, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                existing[(row["Timestamp"], row["Blueprint"])] = row["LogFile"]

    prior_count = len(existing)
    newest_timestamp = _get_newest_timestamp()

    # Gather all log files to scan, oldest first
    log_files: list[Path] = []
    if GAME_LOG_BACKUPS.exists():
        log_files.extend(sorted(GAME_LOG_BACKUPS.glob("*.log")))
    if GAME_LOG.exists():
        log_files.append(GAME_LOG)

    # Filter log files: only scan those modified after the newest known blueprint
    if newest_timestamp:
        cutoff_dt = datetime.fromisoformat(newest_timestamp.replace("Z", "+00:00"))
        filtered_files = [
            f
            for f in log_files
            if datetime.fromtimestamp(f.stat().st_mtime, tz=cutoff_dt.tzinfo)
            > cutoff_dt
        ]
        skipped = len(log_files) - len(filtered_files)
        print(
            f"      {len(log_files)} log files found, {skipped} skipped (before {newest_timestamp})."
        )
        log_files = filtered_files
    else:
        print(f"      {len(log_files)} log files found.")

    for log_path in log_files:
        for ts, name in _scan_log(log_path):
            key = (ts, name)
            if key not in existing:
                existing[key] = log_path.name

    new_count = len(existing) - prior_count
    print(f"      {new_count} new blueprint entries found.")

    # Write sorted by timestamp
    BLUEPRINTS_RECEIVED_CSV.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(
        [
            {"Timestamp": ts, "Blueprint": name, "LogFile": log_file}
            for (ts, name), log_file in existing.items()
        ],
        key=lambda r: r["Timestamp"],
    )
    with open(BLUEPRINTS_RECEIVED_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["Timestamp", "Blueprint", "LogFile"], quoting=csv.QUOTE_ALL
        )
        writer.writeheader()
        writer.writerows(rows)

    total = len(rows)
    print(f"      {total} total owned blueprints -> {BLUEPRINTS_RECEIVED_CSV}")
    return new_count, total


def load_owned_names() -> frozenset[str]:
    """
    Return a frozenset of all blueprint display names the player owns.
    Names are lowercased for case-insensitive matching.
    """
    if not BLUEPRINTS_RECEIVED_CSV.exists():
        return frozenset()
    with open(BLUEPRINTS_RECEIVED_CSV, encoding="utf-8", newline="") as f:
        return frozenset(row["Blueprint"].lower() for row in csv.DictReader(f))


if __name__ == "__main__":
    new, total = scan_and_update_owned()
    print(f"\nDone. {new} new entries, {total} total owned blueprints.")
