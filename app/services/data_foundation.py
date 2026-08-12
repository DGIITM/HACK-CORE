"""M2 Data Foundation.

Backed by JSON files under data/ and data_generated/.
Every file carries its own "data_basis" field documenting how placeholder it is.

Syngenta CE Hub datasets used:
  - Disease Risk for {district}.json   → yellow rust early warning (risk class >= 3)
  - Agro Recommendation for {district}.json → hydric stress (soil moisture too low)
  - Quantis heat stress at 25.json     → Syngenta's own Quantis heat stress model
    output (green/orange/red per district/date), supplements formula engine scores.
"""
import json
import logging
from pathlib import Path
from datetime import date, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
GENERATED_DIR = Path(__file__).resolve().parent.parent.parent / "data_generated"

# Coordinate → district mapping for Quantis/Agro datasets (which use lat/lon, not names)
_COORD_TO_DISTRICT = {
    (30.9, 75.85): "Ludhiana",
    (30.21, 74.95): "Bathinda",
    (30.97, 76.53): "Ropar",
}


def _load(filename: str) -> dict:
    try:
        with open(DATA_DIR / filename, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load {filename}: {e}")
        return {}

def _load_generated(filename: str) -> list:
    try:
        with open(GENERATED_DIR / filename, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load generated {filename}: {e}")
        return []

_PEST_HISTORY = _load("pest_history.json").get("records", [])
_EFFICACY_DATASET = _load("efficacy_dataset.json").get("records", [])
_BATCH_REGISTRY = {
    row["batch_number"]: row for row in _load("batch_registry.json").get("records", [])
}
_SOIL_TYPE_BY_DISTRICT = _load("soil_type_by_district.json").get("records", {})
_SOIL_PROPS = _load("soil_properties.json")
_NUTRIENT_DEFAULTS = _load("nutrient_defaults.json")
_CROP_THRESHOLDS = _load("crop_thresholds.json")

# ── CE Hub Disease Risk (Yellow Rust / Cereal diseases) ─────────────────────
_CE_HUB_DISEASE = {
    "Bathinda": _load_generated("Disease Risk for bathinda.json"),
    "Ludhiana": _load_generated("Disease Risk for ludhiana.json"),
    "Ropar": _load_generated("Disease Risk for Ropar.json"),
}

# ── CE Hub Agro Recommendation (Hydric / soil moisture stress) ───────────────
# All three files have 'type': 'Hydric stress' and constraintCodes with soil moisture.
# We index by district using the coordinate→district map at load time.
_AGRO_REC_RAW = (
    _load_generated("Agro Recommendation  for ludhiana.json")
    + _load_generated("Agro reccomendation for bathinda.json")
    + _load_generated("Agro reccomendation for ropar.json")
)
_AGRO_REC_BY_DISTRICT: Dict[str, List[dict]] = {}
for _rec in _AGRO_REC_RAW:
    _lat = round(float(_rec.get("requestLatitude", 0)), 2)
    _lon = round(float(_rec.get("requestLongitude", 0)), 2)
    _dist = _COORD_TO_DISTRICT.get((_lat, _lon))
    if _dist:
        _AGRO_REC_BY_DISTRICT.setdefault(_dist, []).append(_rec)

# ── Quantis Heat Stress model output (Syngenta's own CE Hub signal) ──────────
# Values: 'green' = low, 'orange' = moderate, 'red' = high heat stress.
# We index by (district, date_YYYY-MM-DD) for fast lookup.
_QUANTIS_RAW = _load_generated("Quantis heat stress at 25.json")
_QUANTIS_BY_DISTRICT_DATE: Dict[str, Dict[str, str]] = {}
for _q in _QUANTIS_RAW:
    _lat = round(float(_q.get("latitude", 0)), 2)
    _lon = round(float(_q.get("longitude", 0)), 2)
    _dist = _COORD_TO_DISTRICT.get((_lat, _lon))
    _date = str(_q.get("date", ""))
    # skip malformed dates (the dataset has some entries like "2025--1-2-")
    if _dist and _date and len(_date) == 10 and _date[4] == "-":
        _QUANTIS_BY_DISTRICT_DATE.setdefault(_dist, {})[_date] = _q.get("value", "green")

logger.info(
    "Syngenta CE Hub datasets loaded — Disease Risk: %s districts, "
    "Agro Rec (Hydric): %s districts, Quantis Heat Stress: %s districts",
    len(_CE_HUB_DISEASE),
    len(_AGRO_REC_BY_DISTRICT),
    len(_QUANTIS_BY_DISTRICT_DATE),
)


# ── Public accessors ─────────────────────────────────────────────────────────

def get_ce_hub_disease_risk_class(district: str, target_date: str) -> Optional[int]:
    """
    Checks the CE Hub Disease Risk output for the given date.
    target_date format: YYYY-MM-DD
    Returns active diseases if risk class >= 3 (Medium/High).
    """
    date_str = f"{target_date.replace('-', '/')} 00:00:00"
    records = _CE_HUB_DISEASE.get(district, [])

    for r in records:
        if r.get("date") == date_str:
            try:
                return int(r.get("value", "0"))
            except ValueError:
                return None
    return None


def get_ce_hub_disease_risk(district: str, target_date: str) -> List[str]:
    value = get_ce_hub_disease_risk_class(district, target_date)
    return ["yellow rust"] if value is not None and value >= 3 else []


def get_agro_hydric_stress(district: str, target_date: str) -> bool:
    """
    Returns True if the CE Hub Agro Recommendation dataset reports active
    hydric (soil moisture) stress for this district on this date.
    This is Syngenta's own model output — a 'X' value means the constraint
    fired; constraintCode 'ResLegTooLoSoilMoisture' means soil moisture is
    too low for good agronomic conditions.
    target_date format: YYYY-MM-DD
    """
    date_str = f"{target_date.replace('-', '/')} 00:00:00"
    records = _AGRO_REC_BY_DISTRICT.get(district, [])
    for r in records:
        if r.get("date") == date_str:
            # 'X' means constraint is active (stressed condition)
            if r.get("value") == "X" and "SoilMoisture" in r.get("constraintCodes", ""):
                return True
    return False


def get_quantis_heat_stress_level(district: str, target_date: str) -> Optional[str]:
    """
    Returns Syngenta's Quantis Heat Stress model output for this district/date.
    Values: 'green' (low/no risk), 'orange' (moderate), 'red' (high).
    Returns None when no dated signal is available; absence is not green.
    target_date format: YYYY-MM-DD
    """
    return _QUANTIS_BY_DISTRICT_DATE.get(district, {}).get(target_date)


def get_pest_history(district: str, crop: str = "wheat", target_date: Optional[str] = None) -> List[str]:
    """
    Pest names active in a district for a crop.
    Prioritizes live CE Hub Disease Risk data, falling back to old static table.
    """
    target_date = target_date or date.today().isoformat()
    ce_hub_risks = get_ce_hub_disease_risk(district, target_date)
    if ce_hub_risks:
        return ce_hub_risks

    # Fallback to old pest history (monthly)
    month_names = ["January", "February", "March", "April", "May", "June",
                   "July", "August", "September", "October", "November", "December"]
    try:
        month_idx = int(target_date.split('-')[1]) - 1
        target_month = month_names[month_idx]
    except Exception:
        target_month = "January"

    return [
        row["pest"]
        for row in _PEST_HISTORY
        if row["district"] == district and row["crop"] == crop and row.get("typical_month") == target_month
    ]


def get_pest_history_detail(district: str, crop: str = "wheat") -> List[Dict]:
    """Compatibility accessor for callers that need the raw seasonal records."""
    return [row for row in _PEST_HISTORY if row["district"] == district and row["crop"] == crop]


def get_historical_environmental_signals(district: str, start_date: date, days: int) -> Dict[str, object]:
    """Summarize dated CE Hub signals for an explicit historical reference window.

    Missing records remain None; callers must not convert them into benign values.
    """
    dates = [(start_date + timedelta(days=offset)).isoformat() for offset in range(days)]
    disease_values = [get_ce_hub_disease_risk_class(district, day) for day in dates]
    heat_values = [get_quantis_heat_stress_level(district, day) for day in dates]
    hydric_values = [get_agro_hydric_stress(district, day) for day in dates]
    rank = {"green": 0, "orange": 1, "red": 2}
    present_heat = [value for value in heat_values if value is not None]
    present_disease = [value for value in disease_values if value is not None]
    return {
        "disease_risk_class": max(present_disease) if present_disease else None,
        "heat_signal": max(present_heat, key=lambda value: rank[value]) if present_heat else None,
        "hydric_stress_active": any(hydric_values) if hydric_values else None,
    }


def get_soil_properties(district: str) -> dict:
    """Returns detailed soil properties including pH and organic matter."""
    return _SOIL_PROPS.get(district, {"ph": 7.0, "texture": "unknown", "organic_matter_percent": 0.5})


def get_nutrient_defaults(crop: str) -> dict:
    """Returns PAU recommended nutrient applications."""
    return _NUTRIENT_DEFAULTS.get(crop, {"N_applied_kg_ha": 0.0, "P_applied_kg_ha": 0.0, "K_applied_kg_ha": 0.0})


def get_crop_thresholds(crop: str) -> dict:
    """Returns physiological thresholds for risk computations."""
    return _CROP_THRESHOLDS.get(crop, {})


def get_efficacy_dataset() -> List[Dict]:
    return _EFFICACY_DATASET


def check_batch(batch_number: str) -> Dict:
    row = _BATCH_REGISTRY.get(batch_number)
    if row is None:
        return {"batch_number": batch_number, "valid": False}
    return {**row, "valid": True}


def get_soil_type(district: str) -> Optional[str]:
    return _SOIL_TYPE_BY_DISTRICT.get(district)


def get_product_catalog() -> List[Dict]:
    return [
        {
            "name": row["product_name"],
            "mode_of_action": row["mode_of_action"],
            "targets": [row["target_problem"]],
        }
        for row in _EFFICACY_DATASET
    ]
