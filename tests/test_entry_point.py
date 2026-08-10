"""M1 text-extraction path — doesn't need real GCP credentials to verify,
per the task: this dev sandbox has none, so process_entry() exercises the
real deterministic fallback end to end, and _validate_extraction is
tested directly with fabricated LLM outputs to prove the extraction
logic itself is correct for when Gemini is available too (same pattern
used for M4's _validate_llm_choice and M8's _validate_narration).
"""
import base64

import pytest

from app.schemas.entry_point import EntryPointInput, LocationSchema
from app.services import entry_point


def _payload(**overrides) -> EntryPointInput:
    defaults = dict(raw_text="leaves turning yellow at the tips", district="Ludhiana", state="Punjab", language="en")
    defaults.update(overrides)
    return EntryPointInput(**defaults)


# --- process_entry() via the real fallback pipeline (no GCP creds here) ----

def test_clear_symptom_extracts_correctly():
    result = entry_point.process_entry(
        _payload(raw_text="my wheat leaves are turning yellow at the tips with small orange spots")
    )
    assert result.crop == "wheat"
    assert "yellow" in result.symptom_description
    assert result.location == LocationSchema(district="Ludhiana", state="Punjab")
    assert result.photo_present is False
    assert result.photo_url is None


def test_vague_symptom_is_not_fabricated_into_something_specific():
    result = entry_point.process_entry(_payload(raw_text="something is wrong with my crop"))
    # The vague text is preserved as-is — never sharpened into a specific
    # diagnosis that wasn't actually said.
    assert result.symptom_description == "something is wrong with my crop"


def test_no_crop_mentioned_defaults_to_wheat_not_invented():
    result = entry_point.process_entry(
        _payload(raw_text="the stems near the base look hollow and the young plants are dying", district="Muktsar")
    )
    assert result.crop == "wheat"
    assert result.location.district == "Muktsar"


def test_no_text_and_no_photo_raises_rather_than_fabricating():
    with pytest.raises(entry_point.NoUsableInputError):
        entry_point.process_entry(_payload(raw_text=""))


def test_whitespace_only_text_and_no_photo_raises():
    with pytest.raises(entry_point.NoUsableInputError):
        entry_point.process_entry(_payload(raw_text="   "))


def test_photo_only_with_no_text_is_usable_input():
    """A photo alone is enough to proceed — but with no LLM available in
    this fallback path, the symptom description honestly says nothing
    was analyzed, it isn't invented from the (unseen-by-the-fallback)
    photo."""
    tiny_png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 100).decode()
    result = entry_point.process_entry(_payload(raw_text="", photo_base64=tiny_png))
    assert result.photo_present is True
    assert result.symptom_description == "no clear symptom described"


def test_oversized_media_is_rejected_not_silently_truncated():
    huge = base64.b64encode(b"0" * (entry_point.MAX_INLINE_MEDIA_BYTES + 1)).decode()
    with pytest.raises(entry_point.NoUsableInputError):
        entry_point.process_entry(_payload(photo_base64=huge))


def test_malformed_base64_is_rejected_cleanly():
    with pytest.raises(entry_point.NoUsableInputError):
        entry_point.process_entry(_payload(photo_base64="not valid base64!!!"))


def test_crop_hint_used_only_in_fallback_mode():
    """crop is advisory in the fallback path specifically (no real
    extraction capability exists there) — a client hint is reasonable to
    use here, unlike trusting an unverifiable claim in the real path."""
    result = entry_point.process_entry(_payload(raw_text="leaves look pale", crop="mustard"))
    assert result.crop == "mustard"


def test_blank_crop_hint_falls_back_to_wheat():
    result = entry_point.process_entry(_payload(raw_text="leaves look pale", crop="   "))
    assert result.crop == "wheat"


# --- _validate_extraction() direct tests: what happens once Gemini IS ------
# --- available (simulated via fabricated LLM outputs) ----------------------

_KNOWN = {
    "location": LocationSchema(district="Ludhiana", state="Punjab"),
    "language": "en",
    "photo_present": False,
    "photo_url": None,
}


def test_validator_accepts_well_formed_extraction():
    llm_output = {
        "crop": "wheat",
        "location": {"district": "Ludhiana", "state": "Punjab"},
        "symptom_description": "yellow rust spots on leaves",
        "language": "en",
        "photo_present": False,
        "photo_url": None,
    }
    result = entry_point._validate_extraction(llm_output, _KNOWN)
    assert result["crop"] == "wheat"
    assert result["symptom_description"] == "yellow rust spots on leaves"


def test_validator_never_trusts_llm_for_location_even_if_it_disagrees():
    """The core safety property: location always comes from `known`,
    never from what the LLM returned, even if the LLM tries to change it."""
    llm_output = {
        "crop": "wheat",
        "location": {"district": "Amritsar", "state": "Punjab"},
        "symptom_description": "yellow leaves",
        "language": "en",
        "photo_present": True,
        "photo_url": "gs://not-real/hallucinated.jpg",
    }
    result = entry_point._validate_extraction(llm_output, _KNOWN)
    assert result["location"] == _KNOWN["location"]
    assert result["photo_present"] is False
    assert result["photo_url"] is None


def test_validator_defaults_missing_crop_to_wheat():
    llm_output = {"symptom_description": "leaves look sick", "language": "en"}
    result = entry_point._validate_extraction(llm_output, _KNOWN)
    assert result["crop"] == "wheat"


def test_validator_reports_missing_symptom_honestly_not_fabricated():
    llm_output = {"crop": "wheat", "symptom_description": "", "language": "en"}
    result = entry_point._validate_extraction(llm_output, _KNOWN)
    assert result["symptom_description"] == "no clear symptom described"


def test_validator_falls_back_to_known_language_on_invalid_code():
    llm_output = {"crop": "wheat", "symptom_description": "leaves yellow", "language": "fr"}
    result = entry_point._validate_extraction(llm_output, _KNOWN)
    assert result["language"] == _KNOWN["language"]


def test_validator_handles_completely_malformed_output():
    result = entry_point._validate_extraction("not a dict at all", _KNOWN)
    assert result["crop"] == "wheat"
    assert result["symptom_description"] == "no clear symptom described"
    assert result["location"] == _KNOWN["location"]


def test_validator_extracts_a_non_wheat_crop_when_genuinely_stated():
    """Extraction should reflect what was actually said, not force
    everything to wheat — the default is only for when it's unclear."""
    llm_output = {"crop": "mustard", "symptom_description": "pods not filling out", "language": "en"}
    result = entry_point._validate_extraction(llm_output, _KNOWN)
    assert result["crop"] == "mustard"


def test_a_live_api_failure_falls_back_gracefully_instead_of_crashing(monkeypatch):
    """Regression: a real Gemini call that fails after credentials were
    valid (rate limit, network error, etc.) used to propagate as an
    unhandled exception all the way to a raw 500 — process_entry() only
    caught 'not configured', not 'configured but the call failed'."""
    from app.services import llm_service

    def _boom(*args, **kwargs):
        raise llm_service.LLMCallFailedError("simulated 429 RESOURCE_EXHAUSTED")

    monkeypatch.setattr(llm_service, "generate_response", _boom)
    result = entry_point.process_entry(_payload(raw_text="my wheat leaves are turning yellow"))
    assert result.symptom_description == "my wheat leaves are turning yellow"
    assert result.crop == "wheat"
