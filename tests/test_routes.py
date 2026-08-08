"""Contract-shape smoke tests — confirms every stub route returns the exact
shapes defined in CLAUDE.md's data contract, not that the logic is real."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _entry_point_payload():
    return {
        "raw_text": "leaves turning yellow at the tips",
        "district": "Ludhiana",
        "state": "Punjab",
        "language": "pa",
        "has_photo": False,
    }


def test_entry_point_shape():
    res = client.post("/entry-point", json=_entry_point_payload())
    assert res.status_code == 200
    body = res.json()
    for key in ["crop", "location", "symptom_description", "language", "photo_present"]:
        assert key in body
    assert "district" in body["location"] and "state" in body["location"]


def test_risk_context_shape():
    farmer_request = client.post("/entry-point", json=_entry_point_payload()).json()
    res = client.post("/risk-context", json=farmer_request)
    assert res.status_code == 200
    body = res.json()
    for key in ["readiness_score", "should_proceed", "weather_summary", "active_pests", "early_warning"]:
        assert key in body


def test_recommend_shape():
    farmer_request = client.post("/entry-point", json=_entry_point_payload()).json()
    res = client.post("/recommend", json={"farmer_request": farmer_request})
    assert res.status_code == 200
    body = res.json()
    for key in [
        "recommended_product",
        "confidence_score",
        "plain_language_reason",
        "mode_of_action",
        "neighbour_proof",
        "no_confident_match",
    ]:
        assert key in body
    for key in ["farmers_nearby", "avg_outcome", "available"]:
        assert key in body["neighbour_proof"]


def test_deliver_shape():
    farmer_request = client.post("/entry-point", json=_entry_point_payload()).json()
    recommendation = client.post("/recommend", json={"farmer_request": farmer_request}).json()
    res = client.post("/deliver", json={"recommendation": recommendation, "language": "pa"})
    assert res.status_code == 200
    body = res.json()
    for key in ["chat_message", "translated_language", "expectation_setting", "trust_features_shown"]:
        assert key in body


def test_retailer_shape():
    res = client.get("/retailer", params={"district": "Ludhiana"})
    assert res.status_code == 200
    body = res.json()
    assert body["district"] == "Ludhiana"
    assert "rows" in body and "counterfeit_alerts" in body


def test_log_outcome_shape():
    res = client.post(
        "/log-outcome",
        json={
            "farmer_id": "farmer-001",
            "product_used": "Trichoderma viride bio-fungicide",
            "batch_verified": True,
            "application_date": "2026-03-14",
            "observed_outcome": "greener leaves after 3 weeks",
            "yield_result": 42.5,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["synced"] is True


def test_measure_impact_shape():
    res = client.post("/measure-impact", json={"farmer_id": "farmer-001"})
    assert res.status_code == 200
    body = res.json()
    for key in ["estimated_effect_pct", "confidence_range", "roi_per_acre_inr", "nitrogen_saved_kg", "data_basis"]:
        assert key in body
    assert len(body["confidence_range"]) == 2
    assert body["data_basis"] == "simulated"
