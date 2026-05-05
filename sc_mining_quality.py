"""
Mining Quality submodule — extract crafting quality distribution and quantization
data from DataForge records.

Outputs:
  quality_distributions.csv  — per-tier (and per-location override) normal
                                distribution params used to roll raw quality (0-1000)
  quality_quantization.csv   — per-material 8-band quantization mapping (legacy CSV format)
  quality_quantization.json  — per-material 8-band quantization mapping (for API consumption)
"""

import csv
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from sc_config import (
    DATA_ROOT,
    QUALITY_DISTRIBUTIONS_CSV,
    QUALITY_QUANTIZATION_CSV,
    QUALITY_QUANTIZATION_JSON,
    step,
)

# Directories under DATA_ROOT
QUAL_DIST_DIR = DATA_ROOT / "crafting" / "qualitydistribution"
QUAL_QUANT_DIR = DATA_ROOT / "crafting" / "qualityquantization"

# Human-friendly scope labels derived from subdirectory names
_SCOPE_LABELS = {
    "shipmineables": "Ship Mining",
    "fpsmineables": "FPS Mining",
    "groundmineables": "Ground Vehicle Mining",
    "harvestables": "Harvesting",
    "creatures": "Creatures",
}


def _parse_dist_node(elem) -> dict | None:
    """Return {min, max, mean, stddev} from a CraftingQualityDistributionNormal element,
    or None if not present."""
    node = elem.find(".//CraftingQualityDistributionNormal")
    if node is None:
        return None
    return {
        "min": node.get("min"),
        "max": node.get("max"),
        "mean": node.get("mean"),
        "stddev": node.get("stddev"),
    }


def extract_quality_distributions() -> int:
    """
    Parse all CraftingQualityDistributionRecord and CraftingQualityLocationOverrideRecord
    files under crafting/qualitydistribution/ and write quality_distributions.csv.
    Returns the number of rows written.
    """
    step("[1/2] Extracting quality distributions")

    rows: list[dict] = []

    for scope_dir in sorted(QUAL_DIST_DIR.iterdir()):
        if not scope_dir.is_dir():
            continue
        scope = _SCOPE_LABELS.get(scope_dir.name, scope_dir.name)

        for xml_file in sorted(scope_dir.glob("*.xml")):
            root = ET.parse(xml_file).getroot()
            rec_type = root.get("__type", "")
            record_name = (
                xml_file.stem
            )  # e.g. "commonshipmineable_qualitydistribution_default"

            if rec_type == "CraftingQualityDistributionRecord":
                # Default distribution — no location override
                dist = _parse_dist_node(root)
                if dist:
                    rows.append(
                        {
                            "Scope": scope,
                            "Record": record_name,
                            "LocationGUID": "default",
                            "Min": dist["min"],
                            "Max": dist["max"],
                            "Mean": dist["mean"],
                            "StdDev": dist["stddev"],
                        }
                    )

            elif rec_type == "CraftingQualityLocationOverrideRecord":
                # Per-location distribution overrides
                for entry in root.findall(".//CraftingQualityLocationOverrideEntry"):
                    loc_guid = entry.get("location", "")
                    dist = _parse_dist_node(entry)
                    if dist:
                        rows.append(
                            {
                                "Scope": scope,
                                "Record": record_name,
                                "LocationGUID": loc_guid,
                                "Min": dist["min"],
                                "Max": dist["max"],
                                "Mean": dist["mean"],
                                "StdDev": dist["stddev"],
                            }
                        )

    QUALITY_DISTRIBUTIONS_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["Scope", "Record", "LocationGUID", "Min", "Max", "Mean", "StdDev"]
    with open(QUALITY_DISTRIBUTIONS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"      {len(rows)} distribution rows written → {QUALITY_DISTRIBUTIONS_CSV}")
    return len(rows)


# Band boundary labels for the 8 fixed bands (start-end)
_BAND_LABELS = [
    "0-399",
    "400-599",
    "600-699",
    "700-799",
    "800-899",
    "900-949",
    "950-998",
    "999-1000",
]


def extract_quality_quantization() -> int:
    """
    Parse all CraftingQualityQuantizationRecord files under crafting/qualityquantization/
    and write quality_quantization.csv.  Each row is one material with 8 mapped-value
    columns (one per quality band).
    Returns the number of material rows written.
    """
    step("[2/2] Extracting quality quantization bands")

    rows: list[dict] = []

    for xml_file in sorted(QUAL_QUANT_DIR.glob("*.xml")):
        material = xml_file.stem.removeprefix("quantization_")  # e.g. "iron"
        if material == "template":
            continue  # skip the template record

        root = ET.parse(xml_file).getroot()
        bands = root.findall(".//CraftingQualityQuantizationBand")

        if not bands:
            continue

        row: dict = {"Material": material.capitalize()}
        for band in bands:
            start = band.get("start")
            end = band.get("end")
            label = f"{start}-{end}"
            row[label] = band.get("mappedValue")

        rows.append(row)

    # Ensure consistent column order: Material + 8 band columns
    QUALITY_QUANTIZATION_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["Material"] + _BAND_LABELS
    with open(QUALITY_QUANTIZATION_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"      {len(rows)} materials written → {QUALITY_QUANTIZATION_CSV}")
    return len(rows)


def export_quality_quantization_json() -> int:
    """
    Parse all CraftingQualityQuantizationRecord files and export to quality_quantization.json
    in the format: { "materials": { "material_name": { "bands": [...] } } }
    Returns the number of materials exported.
    """
    step("Exporting quality quantization to JSON")

    materials_data: dict = {}

    for xml_file in sorted(QUAL_QUANT_DIR.glob("*.xml")):
        material = xml_file.stem.removeprefix("quantization_")  # e.g. "iron"
        if material == "template":
            continue  # skip the template record

        root = ET.parse(xml_file).getroot()
        bands_data = []

        for band in root.findall(".//CraftingQualityQuantizationBand"):
            input_min = int(band.get("start", 0))
            input_max = int(band.get("end", 0))
            output_value = int(band.get("mappedValue", 0))

            # Determine label based on output value ranges
            if output_value < 400:
                label = "Low"
            elif output_value < 600:
                label = "Below Average"
            elif output_value < 700:
                label = "Average"
            elif output_value < 800:
                label = "Good"
            elif output_value < 900:
                label = "High"
            elif output_value < 950:
                label = "Very High"
            elif output_value < 999:
                label = "Exceptional"
            else:
                label = "Perfect"

            bands_data.append(
                {
                    "input_min": input_min,
                    "input_max": input_max,
                    "output_value": output_value,
                    "label": label,
                }
            )

        if bands_data:
            materials_data[material.lower()] = {"bands": bands_data}

    output = {"materials": materials_data}

    QUALITY_QUANTIZATION_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(QUALITY_QUANTIZATION_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(
        f"      {len(materials_data)} materials written → {QUALITY_QUANTIZATION_JSON}"
    )
    return len(materials_data)


def extract_mining_quality() -> tuple[int, int]:
    """Run both extractions. Returns (dist_rows, quant_rows)."""
    dist_count = extract_quality_distributions()
    quant_count = extract_quality_quantization()
    return dist_count, quant_count


if __name__ == "__main__":
    dist_count, quant_count = extract_mining_quality()
    print(
        f"\nDone. {dist_count} distribution rows, {quant_count} quantization materials."
    )
