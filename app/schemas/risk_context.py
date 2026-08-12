"""M3 environmental assessment shapes.

FormulaScores holds the deterministic Syngenta-algorithm outputs.
EnvironmentalAssessment holds the CE Hub / weather / suitability signals.
RiskContext combines both, plus the derived dominant_risk_category which
flows downstream into category-gated retrieval.
"""
from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel

from app.schemas.entry_point import FarmerRequest


class FormulaScores(BaseModel):
    """Outputs of the deterministic Syngenta formula engine (formula_engine.py).

    All values are Optional so that a partial run (e.g. missing weather data)
    still produces a valid object rather than a hard error.
    """
    day_heat_stress: Optional[float] = None       # 0–9
    night_heat_stress: Optional[float] = None     # 0–9
    frost_stress: Optional[float] = None          # 0–9
    drought_index: Optional[float] = None         # negative = drier
    drought_risk_band: Optional[str] = None       # "No risk" | "Medium risk"
    yield_risk: Optional[float] = None            # 0–9
    nue_value: Optional[float] = None
    nue_band: Optional[str] = None                # "Low" | "Moderate" | "High"
    pue_value: Optional[float] = None
    pue_band: Optional[str] = None                # "Low" | "Moderate" | "Good" | "Excellent"


class EnvironmentalAssessment(BaseModel):
    """CE Hub + weather window data.  Authoritative for suitability/alerts."""
    data_status: Literal["current_forecast", "historical_reference", "unavailable"]
    source: str
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    precipitation_total_mm: Optional[float] = None
    evapotranspiration_total_mm: Optional[float] = None
    temperature_min_c: Optional[float] = None
    temperature_max_c: Optional[float] = None
    soil_moisture_vwc: Optional[float] = None
    soil_ph: Optional[float] = None
    soil_texture: Optional[str] = None
    heat_signal: Optional[str] = None             # "green" | "orange" | "red" from Quantis
    hydric_stress_active: Optional[bool] = None   # from Agro Recommendation dataset
    disease_risk_class: Optional[int] = None      # from CE Hub Disease Risk
    alerts: List[str] = []
    application_suitability: Literal["suitable", "caution", "unavailable"]
    suitability_reasons: List[str] = []


class RiskRequest(FarmerRequest):
    """A reference date enables historical CE Hub / Meteoblue mode.
    Without it, /risk-context uses a live Open-Meteo forecast.
    The frontend can omit it — it is never required.
    """
    reference_date: Optional[date] = None


class RiskContext(BaseModel):
    """Complete risk context returned by /risk-context.

    formula_scores  — deterministic Syngenta formula outputs (always present
                      when weather data is available; None fields when not).
    environmental_assessment — weather window + CE Hub signals + suitability.
    dominant_risk_category  — the category label that drives category-gated
                              retrieval in /recommend. One of the exact strings
                              present in efficacy_dataset.json:
                              "Stress Buster" | "Nutrient Booster" | "Yield Booster"
                              or None when risk cannot be determined.
    """
    readiness_score: int
    should_proceed: bool
    weather_summary: str
    active_pests: List[str]
    early_warning: Optional[str] = None
    formula_scores: Optional[FormulaScores] = None
    environmental_assessment: EnvironmentalAssessment
    dominant_risk_category: Optional[str] = None
