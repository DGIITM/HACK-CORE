"""M3 Risk Intelligence — integrates formula engine + CE Hub signals.

Pipeline:
  weather_service   → raw TMAX/TMIN/precip/ET0/soil-moisture
  formula_engine    → heat/frost/drought/NUE/PUE/yield risk scores (0–9)
  data_foundation   → Quantis heat signal, Agro hydric, CE Hub disease risk,
                      soil pH, nutrient defaults, crop thresholds
  risk synthesis    → dominant_risk_category (drives PS-3 retrieval gating)
  EnvironmentalAssessment + FormulaScores → RiskContext

The CE Hub signals and formula scores are combined rather than competing:
  - Formula engine is authoritative for numeric stress magnitudes.
  - CE Hub Quantis / Agro Hydric supplement / validate the formula result
    and fire early warnings even when weather data is unavailable.
  - dominant_risk_category is derived from the formula engine first, then
    elevated by CE Hub signals if the formula engine had no data.
"""
import logging
from datetime import date
from typing import List, Optional, Tuple

from app.schemas.entry_point import FarmerRequest
from app.schemas.risk_context import (
    EnvironmentalAssessment,
    FormulaScores,
    RiskContext,
)
from app.services import (
    data_foundation,
    formula_engine,
    llm_service,
    weather_service,
)

logger = logging.getLogger(__name__)

EARLY_WARNING_SYSTEM_PROMPT = (
    "You are KrishiSathi's risk advisor. Write exactly one short, plain-language "
    "sentence telling a farmer whether to take extra care before using a product. "
    "No jargon, chemical names, markdown, or quotation marks."
)

# Categories that exist in efficacy_dataset.json — MUST match exactly.
CAT_STRESS = "Stress Buster"
CAT_NUTRIENT = "Nutrient Booster"
CAT_YIELD = "Yield Booster"


# ── helpers ──────────────────────────────────────────────────────────────────

def _warning(reasons: List[str], request: FarmerRequest) -> Optional[str]:
    if not reasons:
        return None
    fallback = "Application needs care: " + "; ".join(reasons) + "."
    try:
        text = llm_service.generate_response(
            prompt=f"Crop: {request.crop}. District: {request.location.district}. Conditions: {'; '.join(reasons)}.",
            system_prompt=EARLY_WARNING_SYSTEM_PROMPT,
        ).strip().strip('"')
        return text or fallback
    except llm_service.LLMUnavailableError as exc:
        logger.warning("Early-warning generation unavailable: %s", exc)
        return fallback


def _seasonal_pests(district: str, crop: str, reference_date: Optional[date]) -> List[str]:
    return data_foundation.get_pest_history(
        district, crop.lower(), reference_date.isoformat() if reference_date else None
    )


def _run_formula_scores(
    weather: weather_service.WeatherWindow,
    thresholds: dict,
    soil: dict,
    nutrients: dict,
) -> Optional[FormulaScores]:
    """Run the Syngenta formula engine and return a FormulaScores object.

    Returns None only when the weather window is fully unavailable (no data
    to feed into any formula). Partial results (e.g. one formula's inputs are
    missing) fill those fields with None rather than raising.
    """
    if weather.is_unavailable:
        return None

    t = thresholds  # alias for brevity

    # 1. Heat stress (day)
    if weather.tmax_c is not None and t.get("TMaxOptimum") and t.get("TmaxLimit"):
        day_heat = formula_engine.compute_day_heat_stress(
            weather.tmax_c, t["TMaxOptimum"], t["TmaxLimit"]
        )
    else:
        day_heat = None

    # 2. Night heat stress
    if weather.tmin_c is not None and t.get("TMinOptimum") and t.get("TMinLimit"):
        night_heat = formula_engine.compute_night_heat_stress(
            weather.tmin_c, t["TMinOptimum"], t["TMinLimit"]
        )
    else:
        night_heat = None

    # 3. Frost stress
    if weather.tmin_c is not None:
        frost = formula_engine.compute_frost_stress(
            weather.tmin_c, t.get("TMinNoFrost"), t.get("TminFrost")
        )
    else:
        frost = None

    # 4. Drought index — needs precip, ET0, soil moisture, avg temperature
    di = None
    di_band = None
    if (
        weather.precipitation_total_mm is not None
        and weather.et0_total_mm is not None
        and weather.soil_moisture_vwc is not None
        and weather.tmax_c is not None
        and weather.tmin_c is not None
    ):
        avg_temp = (weather.tmax_c + weather.tmin_c) / 2.0
        # soil_moisture_vwc is in m³/m³; formula expects mm-equivalent; multiply
        # by 1000 to convert to a dimensionally consistent scale.
        sm_mm = weather.soil_moisture_vwc * 1000.0
        di = formula_engine.compute_drought_index(
            weather.precipitation_total_mm,
            weather.et0_total_mm,
            sm_mm,
            avg_temp,
        )
        di_band = formula_engine.get_drought_risk_category(di)

    # 5. Yield risk
    yr = None
    if (
        t.get("GDD_optimal_min") and t.get("GDD_optimal_max")
        and weather.tmax_c is not None and weather.tmin_c is not None
    ):
        # Rough GDD estimate over window: sum((Tmax+Tmin)/2 - base) with base=0
        gdd_est = weather_service.FORECAST_DAYS * max(0.0, (weather.tmax_c + weather.tmin_c) / 2.0)
        ph = soil.get("ph", 7.0)
        n_applied = nutrients.get("N_applied_kg_ha", 120.0)
        yr = formula_engine.compute_yield_risk(
            gdd_est,
            t["GDD_optimal_min"], t["GDD_optimal_max"],
            weather.precipitation_total_mm or 0.0,
            t.get("Precipitation_Optimal_min", 1000.0),
            t.get("Precipitation_Optimal_max", 1500.0),
            ph,
            t.get("pH_optimal_min", 6.0), t.get("pH_optimal_max", 7.5),
            n_applied,
            t.get("N_Optimal_min", 100.0), t.get("N_Optimal_max", 140.0),
        )

    # 6. NUE
    nue = None
    nue_band = None
    n_applied = nutrients.get("N_applied_kg_ha", 0.0)
    if n_applied > 0 and weather.soil_moisture_vwc is not None:
        # Projected yield placeholder: 3 tonnes/ha typical Punjab wheat
        nue = formula_engine.compute_nue(
            3000.0,
            n_applied,
            weather.precipitation_total_mm or 0.0,
            t.get("Precipitation_Optimal_min", 1000.0),
            t.get("Precipitation_Optimal_max", 1500.0),
            (weather.soil_moisture_vwc or 0.0) * 100,
            t.get("SM_optimal_min", 50.0),
            t.get("SM_optimal_max", 70.0),
        )
        nue_band = formula_engine.get_nue_category(nue)

    # 7. PUE
    pue = None
    pue_band = None
    p_applied = nutrients.get("P_applied_kg_ha", 0.0)
    if p_applied > 0 and weather.soil_moisture_vwc is not None:
        sf = formula_engine.compute_pue_soil_factor(
            soil.get("ph", 7.0),
            t.get("pH_optimal_min", 6.0), t.get("pH_optimal_max", 7.5),
            (weather.soil_moisture_vwc or 0.0) * 100,
            t.get("SM_optimal_min", 50.0), t.get("SM_optimal_max", 70.0),
            weather.precipitation_total_mm or 0.0,
            t.get("Precipitation_Optimal_min", 1000.0),
            t.get("Precipitation_Optimal_max", 1500.0),
        )
        pue = formula_engine.compute_pue(3.0, p_applied, sf)
        pue_band = formula_engine.get_pue_category(pue)

    return FormulaScores(
        day_heat_stress=round(day_heat, 3) if day_heat is not None else None,
        night_heat_stress=round(night_heat, 3) if night_heat is not None else None,
        frost_stress=round(frost, 3) if frost is not None else None,
        drought_index=round(di, 6) if di is not None else None,
        drought_risk_band=di_band,
        yield_risk=round(yr, 3) if yr is not None else None,
        nue_value=round(nue, 4) if nue is not None else None,
        nue_band=nue_band,
        pue_value=round(pue, 6) if pue is not None else None,
        pue_band=pue_band,
    )


def _derive_dominant_category(
    fs: Optional[FormulaScores],
    ce_hub_heat: Optional[str],
    ce_hub_hydric: Optional[bool],
    ce_hub_disease_class: Optional[int],
) -> Optional[str]:
    """Single authoritative function that maps risk signals → product category.

    Hierarchy (first matching rule wins):
      1. Any abiotic stress signal (heat, frost, drought) → Stress Buster
      2. Disease risk from CE Hub ≥ 3                    → Stress Buster
      3. Low NUE or low PUE                              → Nutrient Booster
      4. Otherwise                                       → Yield Booster

    CE Hub signals supplement the formula engine:
      - If formula has data, formula scores are authoritative for magnitude.
      - If formula has no data (no weather), CE Hub signals alone can still
        trigger a category (Stress Buster for heat/hydric, etc.).
    """
    # --- formula-engine signals ---
    heat_stress_high = False
    frost_high = False
    drought_risk = False
    nue_low = False
    pue_low = False

    if fs is not None:
        heat_stress_high = (
            (fs.day_heat_stress is not None and fs.day_heat_stress >= 3.0)
            or (fs.night_heat_stress is not None and fs.night_heat_stress >= 3.0)
        )
        frost_high = fs.frost_stress is not None and fs.frost_stress >= 1.0
        drought_risk = fs.drought_risk_band == "Medium risk"
        nue_low = fs.nue_band in ("Low", "Moderate")
        pue_low = fs.pue_band in ("Low", "Moderate")

    # --- CE Hub supplement / override when formula engine lacks data ---
    ce_heat_high = ce_hub_heat in ("orange", "red")
    ce_hydric = bool(ce_hub_hydric)
    ce_disease = (ce_hub_disease_class is not None and ce_hub_disease_class >= 3)

    # Rule 1: abiotic stress
    if heat_stress_high or frost_high or drought_risk or ce_heat_high or ce_hydric:
        return CAT_STRESS

    # Rule 2: CE Hub disease
    if ce_disease:
        return CAT_STRESS

    # Rule 3: nutrient efficiency
    if nue_low or pue_low:
        return CAT_NUTRIENT

    # Rule 4: default when signals are available (no signals → None)
    signals_present = (
        fs is not None
        or ce_hub_heat is not None
        or ce_hub_hydric is not None
        or ce_hub_disease_class is not None
    )
    return CAT_YIELD if signals_present else None


# ── main entry point ──────────────────────────────────────────────────────────

def assess_risk(farmer_request: FarmerRequest) -> RiskContext:
    """Assess application conditions without changing symptom-first product choice."""
    district = farmer_request.location.district
    reference_date = getattr(farmer_request, "reference_date", None)
    crop_key = farmer_request.crop.capitalize()

    # --- weather window ---
    weather = weather_service.get_weather_window(district, reference_date)

    # --- static data ---
    soil = data_foundation.get_soil_properties(district)
    thresholds = data_foundation.get_crop_thresholds(crop_key)
    nutrients = data_foundation.get_nutrient_defaults(crop_key)
    active_pests = _seasonal_pests(district, farmer_request.crop, reference_date)

    # --- run formula engine ---
    fs = _run_formula_scores(weather, thresholds, soil, nutrients)

    # --- CE Hub environmental signals ---
    ce_signals = {"disease_risk_class": None, "heat_signal": None, "hydric_stress_active": None}
    if reference_date:
        # Historical mode: use dated CE Hub data aligned to the weather window.
        ce_signals = data_foundation.get_historical_environmental_signals(
            district, reference_date, weather_service.FORECAST_DAYS
        )
        if ce_signals["disease_risk_class"] is not None and ce_signals["disease_risk_class"] >= 3:
            if "yellow rust" not in active_pests:
                active_pests.append("yellow rust")
    # For live forecast mode, CE Hub dated signals are not usable (no reference date),
    # so they remain None — formula engine + weather thresholds are the only signals.

    # --- build alerts and suitability reasons ---
    alerts: List[str] = []
    reasons: List[str] = []

    # CE Hub alerts (only when reference_date mode)
    if reference_date:
        if ce_signals["heat_signal"] in {"orange", "red"}:
            alerts.append(f"Quantis heat-stress signal: {ce_signals['heat_signal']}")
            reasons.append("a heat-stress alert is active (Syngenta Quantis model)")
        if ce_signals["hydric_stress_active"]:
            alerts.append("CE Hub Agro: low soil moisture constraint active")
            reasons.append("low soil moisture reported by CE Hub hydric model")
        if ce_signals["disease_risk_class"] is not None and ce_signals["disease_risk_class"] >= 3:
            alerts.append(f"CE Hub disease risk class {ce_signals['disease_risk_class']} (≥3 = high)")

    # Formula engine alerts
    if fs is not None:
        if fs.day_heat_stress is not None and fs.day_heat_stress >= 6.0:
            alerts.append(f"Day heat stress score {fs.day_heat_stress:.1f}/9")
            if "a heat-stress alert is active (Syngenta Quantis model)" not in reasons:
                reasons.append("extreme daytime heat stress")
        if fs.frost_stress is not None and fs.frost_stress >= 1.0:
            alerts.append(f"Frost stress score {fs.frost_stress:.1f}/9")
            reasons.append("frost risk")
        if fs.drought_risk_band == "Medium risk":
            alerts.append(f"Drought index {fs.drought_index:.4f} — medium risk")
            if "low soil moisture reported by CE Hub hydric model" not in reasons:
                reasons.append("drought / low soil-water balance")

    # Weather threshold alerts (supplement formula engine)
    if not weather.is_unavailable:
        if weather.precipitation_total_mm is not None and weather.precipitation_total_mm > weather_service.RAIN_CAUTION_MM:
            reasons.append(f"{weather.precipitation_total_mm:.0f}mm precipitation over five days (wash-off risk)")
        if thresholds and weather.tmax_c is not None and weather.tmax_c > thresholds.get("TmaxLimit", float("inf")):
            alerts.append("Temperature exceeds crop heat limit (crop_thresholds.json)")
        if thresholds and weather.tmin_c is not None and weather.tmin_c < thresholds.get("TMinNoFrost", float("-inf")):
            alerts.append("Temperature reaches crop frost threshold (crop_thresholds.json)")
        if thresholds and weather.soil_moisture_vwc is not None:
            lower = thresholds.get("SM_optimal_min")
            upper = thresholds.get("SM_optimal_max")
            moisture_pct = weather.soil_moisture_vwc * 100
            if lower and upper and not (lower <= moisture_pct <= upper):
                alerts.append("Soil moisture outside optimal crop range")
        if weather.et0_total_mm is not None:
            alerts.append(f"Five-day evapotranspiration: {weather.et0_total_mm:.1f}mm")

    if active_pests:
        alerts.append("Seasonal/dated pest or disease context: " + ", ".join(active_pests))

    suitability = "unavailable" if weather.is_unavailable else ("caution" if reasons else "suitable")

    # --- dominant risk category ---
    dominant_category = _derive_dominant_category(
        fs,
        ce_signals["heat_signal"],
        ce_signals["hydric_stress_active"],
        ce_signals["disease_risk_class"],
    )

    # --- assemble return objects ---
    assessment = EnvironmentalAssessment(
        data_status=weather.data_status,
        source=weather.source,
        window_start=weather.window_start,
        window_end=weather.window_end,
        precipitation_total_mm=weather.precipitation_total_mm,
        evapotranspiration_total_mm=weather.et0_total_mm,
        temperature_min_c=weather.tmin_c,
        temperature_max_c=weather.tmax_c,
        soil_moisture_vwc=weather.soil_moisture_vwc,
        soil_ph=soil.get("ph"),
        soil_texture=soil.get("texture") or data_foundation.get_soil_type(district),
        heat_signal=ce_signals["heat_signal"],
        hydric_stress_active=ce_signals["hydric_stress_active"],
        disease_risk_class=ce_signals["disease_risk_class"],
        alerts=alerts,
        application_suitability=suitability,
        suitability_reasons=reasons,
    )

    return RiskContext(
        readiness_score={"suitable": 10, "caution": 5, "unavailable": 0}[suitability],
        should_proceed=suitability == "suitable",
        weather_summary=weather.summary,
        active_pests=active_pests,
        early_warning=_warning(reasons, farmer_request),
        formula_scores=fs,
        environmental_assessment=assessment,
        dominant_risk_category=dominant_category,
    )
