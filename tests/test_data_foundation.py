"""M2 Data Foundation — confirms each lookup function returns data in the
expected shape. Not testing real agronomic accuracy (the data is labeled
placeholder in data/*.json), just that the interface other modules rely
on is honored.
"""
from app.services import data_foundation


def test_get_pest_history_returns_list_of_pest_name_strings():
    pests = data_foundation.get_pest_history("Ludhiana")
    assert isinstance(pests, list)
    assert len(pests) > 0
    assert all(isinstance(p, str) for p in pests)
    assert "aphid" in pests


def test_get_pest_history_unknown_district_returns_empty_list():
    assert data_foundation.get_pest_history("Nowhere District") == []


def test_get_pest_history_detail_rows_have_expected_columns():
    rows = data_foundation.get_pest_history_detail("Gurdaspur")
    assert len(rows) > 0
    for row in rows:
        for key in ["district", "crop", "pest", "typical_month", "severity"]:
            assert key in row
        assert row["district"] == "Gurdaspur"
        assert row["severity"] in ("low", "medium", "high")


def test_pest_history_dataset_size_in_expected_range():
    all_rows = data_foundation._PEST_HISTORY
    assert 20 <= len(all_rows) <= 30


def test_get_efficacy_dataset_shape_and_size():
    dataset = data_foundation.get_efficacy_dataset()
    assert 15 <= len(dataset) <= 20
    for row in dataset:
        for key in [
            "product_name",
            "crop",
            "target_problem",
            "mode_of_action",
            "typical_soil_type",
            "reported_efficacy",
        ]:
            assert key in row
            assert isinstance(row[key], str)
            assert row[key]


def test_check_batch_valid_number():
    result = data_foundation.check_batch("TRV-2026-00417")
    assert result["valid"] is True
    assert result["product_name"] == "Trichoderma viride bio-fungicide"
    assert "manufacturer" in result and "expiry_date" in result


def test_check_batch_unknown_number_is_invalid():
    result = data_foundation.check_batch("FAKE-0000-00000")
    assert result == {"batch_number": "FAKE-0000-00000", "valid": False}


def test_get_soil_type_known_district():
    assert data_foundation.get_soil_type("Bathinda") == "sandy"


def test_get_soil_type_unknown_district_returns_none():
    assert data_foundation.get_soil_type("Nowhere District") is None


def test_get_product_catalog_backward_compat_shape():
    """M4/M6 stubs (recommend.py, retailer.py) still call this — must not
    break while this pass only touches data_foundation.py."""
    catalog = data_foundation.get_product_catalog()
    assert len(catalog) == len(data_foundation.get_efficacy_dataset())
    for product in catalog:
        assert "name" in product
        assert "mode_of_action" in product
        assert "targets" in product and isinstance(product["targets"], list)
