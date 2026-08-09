"""M5's templating and language-routing logic — doesn't need real GCP
creds to verify: this dev sandbox has none, so deliver() exercises the
real translation/TTS fallbacks end to end, and the message-building
helpers are tested directly for the templating logic itself.
"""
from app.schemas.delivery import DeliveryRequest
from app.schemas.recommend import NeighbourProof, Recommendation
from app.services import delivery, translation_service


def _confident_rec(**overrides) -> Recommendation:
    defaults = dict(
        recommended_product="Trichoderma viride bio-fungicide",
        confidence_score=0.81,
        plain_language_reason="Farmers nearby with similar yellowing saw improvement.",
        mode_of_action="It grows around the roots and crowds out the fungus that causes root rot.",
        neighbour_proof=NeighbourProof(farmers_nearby=12, avg_outcome="9% yield improvement", available=True),
        no_confident_match=False,
    )
    defaults.update(overrides)
    return Recommendation(**defaults)


def _no_match_rec() -> Recommendation:
    return Recommendation(
        recommended_product="",
        confidence_score=0.0,
        plain_language_reason="",
        mode_of_action="",
        neighbour_proof=NeighbourProof(farmers_nearby=0, avg_outcome="", available=False),
        no_confident_match=True,
    )


# --- expectation-message templating: product/crop-specific, not generic ----

def test_expectation_message_names_the_specific_product_and_crop():
    msg = delivery._build_expectation_message(_confident_rec(recommended_product="Neem-based bio-pesticide"), "mustard")
    assert "Neem-based bio-pesticide" in msg
    assert "mustard" in msg
    assert "3 weeks" in msg


def test_expectation_message_changes_with_different_product_and_crop():
    """Proves it's genuinely templated, not a hardcoded string with the
    same output regardless of input."""
    msg_a = delivery._build_expectation_message(_confident_rec(recommended_product="Product A"), "wheat")
    msg_b = delivery._build_expectation_message(_confident_rec(recommended_product="Product B"), "rice")
    assert msg_a != msg_b
    assert "Product A" in msg_a and "wheat" in msg_a
    assert "Product B" in msg_b and "rice" in msg_b


def test_expectation_message_for_no_match_does_not_name_a_fake_product():
    msg = delivery._build_expectation_message(_no_match_rec(), "wheat")
    assert "wheat" not in msg  # no specific crop claim without a real recommendation
    for product_word in ["Trichoderma", "Bacillus", "Pseudomonas", "Neem"]:
        assert product_word not in msg


# --- chat message ------------------------------------------------------------

def test_chat_message_for_confident_recommendation_includes_product_and_confidence():
    msg = delivery._build_chat_message(_confident_rec(confidence_score=0.81))
    assert "Trichoderma viride bio-fungicide" in msg
    assert "81%" in msg


def test_chat_message_for_no_match_is_honest_not_a_forced_pick():
    msg = delivery._build_chat_message(_no_match_rec())
    assert "couldn't find" in msg.lower() or "honest" in msg.lower()
    for product_word in ["Trichoderma", "Bacillus", "Pseudomonas", "Neem"]:
        assert product_word not in msg


# --- language routing / translation fallback --------------------------------

def test_translate_helper_skips_translation_for_english():
    text, lang = delivery._translate("hello", "en")
    assert text == "hello"
    assert lang == "en"


def test_translate_helper_falls_back_honestly_when_not_configured():
    """This dev sandbox has no GOOGLE_CLOUD_PROJECT configured, so this
    exercises the real fallback path: never claim a translation happened
    when it didn't."""
    text, lang = delivery._translate("hello there", "pa")
    assert text == "hello there"  # untranslated, unchanged
    assert lang == "en"  # honest about what language this actually is


def test_translate_helper_handles_empty_text():
    text, lang = delivery._translate("", "pa")
    assert text == ""
    assert lang == "en"


def test_translation_not_configured_error_is_real_and_catchable():
    """Confirms the fallback error type actually exists and is raised
    for a non-English target when Cloud Translation isn't configured —
    not just that _translate happens to swallow something."""
    import pytest

    with pytest.raises(translation_service.TranslationNotConfiguredError):
        translation_service.translate_text("hello", "pa")


# --- full deliver() pipeline: real fallback, honest labeling ----------------

def test_deliver_reports_english_when_translation_unavailable():
    req = DeliveryRequest(recommendation=_confident_rec(), language="pa", crop="wheat")
    result = delivery.deliver(req)
    assert result.translated_language == "en"
    assert result.audio_url is None


def test_deliver_output_shape_matches_contract():
    req = DeliveryRequest(recommendation=_confident_rec(), language="pa", crop="wheat")
    result = delivery.deliver(req)
    assert isinstance(result.chat_message, str) and result.chat_message
    assert isinstance(result.translated_language, str)
    assert isinstance(result.expectation_setting, str) and result.expectation_setting
    assert isinstance(result.trust_features_shown, list)


def test_deliver_trust_features_reflect_what_is_actually_present():
    confident = delivery.deliver(
        DeliveryRequest(recommendation=_confident_rec(), language="en", crop="wheat")
    )
    assert set(confident.trust_features_shown) == {"mode_of_action", "neighbour_proof", "expectation_setting"}

    no_match = delivery.deliver(
        DeliveryRequest(recommendation=_no_match_rec(), language="en", crop="wheat")
    )
    assert no_match.trust_features_shown == []


def test_deliver_omits_neighbour_proof_flag_when_not_available():
    rec = _confident_rec(neighbour_proof=NeighbourProof(farmers_nearby=0, avg_outcome="", available=False))
    result = delivery.deliver(DeliveryRequest(recommendation=rec, language="en", crop="wheat"))
    assert "neighbour_proof" not in result.trust_features_shown
    assert "mode_of_action" in result.trust_features_shown


def test_deliver_defaults_crop_when_not_supplied():
    req = DeliveryRequest(recommendation=_confident_rec(), language="en")
    result = delivery.deliver(req)
    assert "wheat" in result.expectation_setting


def test_deliver_handles_explicit_empty_crop_without_doubled_your():
    """Regression: an explicitly empty crop string (as opposed to an
    omitted field, which would use the schema default) used to render
    'in your your crop' — the caller's 'your crop' fallback collided
    with the template's own hardcoded 'your'."""
    req = DeliveryRequest(recommendation=_confident_rec(), language="en", crop="")
    result = delivery.deliver(req)
    assert "your your" not in result.expectation_setting
    assert "in your crop" in result.expectation_setting


def test_build_expectation_message_handles_whitespace_only_crop():
    msg = delivery._build_expectation_message(_confident_rec(), "   ")
    assert "your your" not in msg
    assert "in your crop" in msg
