"""M2 Data Foundation.

Nearly every other module reads from here, which is why CLAUDE.md says to
build it first. It has no HTTP route of its own.

Backed by JSON files under data/ for now (pest_history.json,
efficacy_dataset.json, batch_registry.json, soil_type_by_district.json).
Every file carries its own "data_basis" field documenting how placeholder
it is (CLAUDE.md hard constraint: label simulated data as simulated).

# STUB: swap the JSON-file loads below for BigQuery (pest history, soil
# type) and Qdrant (efficacy dataset retrieval) once those are wired up.
# The counterfeit batch registry stays simulated per CLAUDE.md ("What's
# real vs. simulated") even in the real build. The functions below are
# the interface — callers (M3, M4, M7) should never need to know the
# storage format changed underneath.
"""
import json
from pathlib import Path
from typing import Dict, List, Optional

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def _load(filename: str) -> dict:
    with open(DATA_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


_PEST_HISTORY: List[Dict] = _load("pest_history.json")["records"]
_EFFICACY_DATASET: List[Dict] = _load("efficacy_dataset.json")["records"]
_BATCH_REGISTRY: Dict[str, Dict] = {
    row["batch_number"]: row for row in _load("batch_registry.json")["records"]
}
_SOIL_TYPE_BY_DISTRICT: Dict[str, str] = _load("soil_type_by_district.json")["records"]


def get_pest_history(district: str, crop: str = "wheat") -> List[str]:
    """Pest names active in a district for a crop — matches RiskContext's
    active_pests: List[str] contract shape.
    """
    return [
        row["pest"]
        for row in _PEST_HISTORY
        if row["district"] == district and row["crop"] == crop
    ]


def get_pest_history_detail(district: str, crop: str = "wheat") -> List[Dict]:
    """Full rows (district, crop, pest, typical_month, severity) for callers
    that need more than just the pest name, e.g. a future M3 that factors
    severity or seasonal timing into the readiness score.
    """
    return [
        row
        for row in _PEST_HISTORY
        if row["district"] == district and row["crop"] == crop
    ]


def get_efficacy_dataset() -> List[Dict]:
    """Full biological-product efficacy dataset: product_name, crop,
    target_problem, mode_of_action, typical_soil_type, reported_efficacy.
    This is what M4's real retrieval step will query once it exists.
    """
    return _EFFICACY_DATASET


def check_batch(batch_number: str) -> Dict:
    """Counterfeit check against the mock batch/QR registry. Returns
    valid=False (with no other fields) for anything not in the registry —
    that's the "counterfeit" signal M7 will act on.
    """
    row = _BATCH_REGISTRY.get(batch_number)
    if row is None:
        return {"batch_number": batch_number, "valid": False}
    return {**row, "valid": True}


def get_soil_type(district: str) -> Optional[str]:
    """Dominant soil texture for a district — stand-in for live
    satellite/soil-sensor data until that's wired up."""
    return _SOIL_TYPE_BY_DISTRICT.get(district)


def get_product_catalog() -> List[Dict]:
    """Backward-compat adapter for the M4/M6 stubs (recommend.py,
    retailer.py) that already expect the old {"name", "mode_of_action",
    "targets"} shape. New code should call get_efficacy_dataset() instead
    — once M4 is built for real against that dataset, this can be deleted.
    """
    return [
        {
            "name": row["product_name"],
            "mode_of_action": row["mode_of_action"],
            "targets": [row["target_problem"]],
        }
        for row in _EFFICACY_DATASET
    ]
