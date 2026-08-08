"""M8 Impact Measurement — causal attribution -> ROI in rupees/acre.

Depth piece #2. Hard constraint from CLAUDE.md: never overclaim precision
— always report a range, never a single confident number. This stub
already returns a range shape so nothing downstream can round it away.
"""
import random

from app.schemas.impact import ImpactEstimate, ImpactRequest


def measure_impact(req: ImpactRequest) -> ImpactEstimate:
    # STUB: real logic runs a difference-in-differences model (statsmodels,
    # not DoWhy/EconML — too much setup for the timeline) comparing this
    # farmer's season outcome against matched non-adopters, using the
    # synthetic season dataset (known ground-truth effect) until enough
    # real outcome logs accumulate.
    effect = round(random.uniform(8.0, 15.0), 1)
    spread = round(random.uniform(2.0, 4.0), 1)

    return ImpactEstimate(
        estimated_effect_pct=effect,
        confidence_range=[round(effect - spread, 1), round(effect + spread, 1)],
        roi_per_acre_inr=random.randint(2500, 5500),
        nitrogen_saved_kg=random.randint(10, 25),
        data_basis="simulated",
    )
