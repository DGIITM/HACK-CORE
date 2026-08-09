"""Proves the difference-in-differences model actually works before real
M7 outcome data exists: fit it on synthetic data with a known, documented
ground-truth effect (impact_data.TRUE_EFFECT_PCT) and confirm it recovers
something close to that number, with a 95% CI that actually contains it.
"""
from app.services import impact_data


def test_did_model_recovers_the_known_true_effect():
    panel = impact_data.generate_synthetic_season_panel()
    result = impact_data.fit_did_model(panel)

    # Recovers close to the baked-in ground truth — not exact (it's a
    # statistical estimate from noisy data), but within a couple points.
    assert abs(result.estimated_effect_pct - impact_data.TRUE_EFFECT_PCT) < 2.0


def test_confidence_interval_contains_the_known_true_effect():
    panel = impact_data.generate_synthetic_season_panel()
    result = impact_data.fit_did_model(panel)

    low, high = result.confidence_range_pct
    assert low < impact_data.TRUE_EFFECT_PCT < high


def test_recovery_is_stable_across_different_synthetic_draws():
    """Not just lucky on one seed — the DiD design should recover the
    true effect reasonably well regardless of the random draw."""
    for seed in (1, 7, 99, 123):
        panel = impact_data.generate_synthetic_season_panel(seed=seed)
        result = impact_data.fit_did_model(panel)
        assert abs(result.estimated_effect_pct - impact_data.TRUE_EFFECT_PCT) < 3.0
        low, high = result.confidence_range_pct
        assert low < impact_data.TRUE_EFFECT_PCT < high


def test_confidence_range_is_a_real_range_not_a_point_estimate():
    """Hard constraint from CLAUDE.md: never overclaim precision — report
    a range, not a single confident number."""
    result = impact_data.get_or_fit_did_result()
    assert len(result.confidence_range_pct) == 2
    assert result.confidence_range_pct[0] < result.confidence_range_pct[1]


def test_synthetic_panel_shape():
    panel = impact_data.generate_synthetic_season_panel(n_farmers=50)
    assert len(panel) == 100  # 2 rows (before/after) per farmer
    for col in ["farmer_id", "district", "soil_index", "weather_index", "used_product", "period", "yield_outcome"]:
        assert col in panel.columns
    assert set(panel["period"].unique()) == {0, 1}
    assert set(panel["used_product"].unique()) <= {0, 1}
    # each farmer appears exactly twice (once per period)
    assert (panel.groupby("farmer_id").size() == 2).all()


def test_get_or_fit_did_result_is_cached_and_deterministic():
    first = impact_data.get_or_fit_did_result()
    second = impact_data.get_or_fit_did_result()
    assert first is second
