"""M4 retrieval — direct regression coverage for the active_pests
relevance-gating bug found and fixed while switching Gemini auth
(see llm_service.py's history): retrieval.py used to fold active_pests
straight into the TF-IDF query text, which let a district's pest names
alone produce a confident-looking match for *any* symptom text,
including pure gibberish, since active_pests doesn't vary per request
while the symptom does. This affected the candidate pool for both the
real Gemini path and the deterministic fallback identically — both are
handed the same candidates list retrieval.py builds before either path
runs. Fixed to match the treatment soil_type already had: a ranking
bonus applied only after the symptom text clears the relevance gate on
its own, never a way to manufacture a match out of nothing.
"""
import pytest

from app.services import retrieval

REAL_DISTRICT_PESTS = ["brown rust", "aphid", "karnal bunt"]


def test_gibberish_symptom_returns_empty_even_with_a_real_pest_list():
    candidates = retrieval.retrieve_candidates(
        "wheat", "asdkjfh qwoeiur zzz blah blah blah", REAL_DISTRICT_PESTS, "sandy loam"
    )
    assert candidates == []


def test_off_topic_symptom_returns_empty_even_with_a_real_pest_list():
    candidates = retrieval.retrieve_candidates(
        "wheat", "my car wont start and the wifi is down", REAL_DISTRICT_PESTS, "sandy loam"
    )
    assert candidates == []


def test_gibberish_and_off_topic_symptoms_are_not_rescued_into_a_false_match():
    """The core proof: two symptom texts with nothing in common should
    never produce the identical non-empty result — if they do, whatever
    matched came from something other than the symptom (the bug this
    guards against)."""
    a = retrieval.retrieve_candidates("wheat", "asdkjfh qwoeiur zzz", REAL_DISTRICT_PESTS, "sandy loam")
    b = retrieval.retrieve_candidates("wheat", "my car wont start", REAL_DISTRICT_PESTS, "sandy loam")
    assert a == [] and b == []


def test_genuine_symptom_still_matches_regardless_of_pest_list():
    with_pests = retrieval.retrieve_candidates(
        "wheat", "pink stem borer caterpillar feeding on stems, seedlings dying", REAL_DISTRICT_PESTS, ""
    )
    without_pests = retrieval.retrieve_candidates(
        "wheat", "pink stem borer caterpillar feeding on stems, seedlings dying", [], ""
    )
    assert with_pests and without_pests
    assert with_pests[0]["product_name"] == without_pests[0]["product_name"]


def test_matching_pest_still_gives_a_ranking_bonus_not_a_manufactured_match():
    """The bonus mechanism itself should still work — active_pests isn't
    disabled entirely, just demoted from gate to tie-breaker."""
    without_bonus = retrieval.retrieve_candidates("wheat", "leaves turning yellow at the tips", [], "")
    with_bonus = retrieval.retrieve_candidates("wheat", "leaves turning yellow at the tips", ["yellow rust"], "")

    assert without_bonus and with_bonus
    top_without = next(c for c in without_bonus if c["product_name"] == with_bonus[0]["product_name"])
    assert with_bonus[0]["_similarity"] > top_without["_similarity"]
    assert with_bonus[0]["_similarity"] - top_without["_similarity"] == pytest.approx(retrieval.PEST_MATCH_BONUS)


def test_pest_bonus_alone_cannot_clear_the_relevance_gate():
    """A pest name matching a candidate's target_problem is a tie-
    breaker bonus, not an independent path to relevance — it must never
    be enough on its own when the symptom text itself matched nothing."""
    candidates = retrieval.retrieve_candidates("wheat", "zzz qwoeiur nonsense", ["yellow rust"], "")
    assert candidates == []
