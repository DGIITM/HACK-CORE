"""Test-suite-wide safety net: the automated suite must always exercise
the deterministic fallback paths, never a real external API — same
principle every module's fallback was built around from the start.

Without this, a developer's local GEMINI_API_KEY (set for manual live
verification — see llm_service.py's docstring) would silently make
`pytest` hit the real Gemini Developer API on every LLM-touching test.
This isn't hypothetical: it's exactly what happened once, caught while
switching Gemini auth. The Developer API's free tier caps at 20 requests
per day per model — a single full test run burns through that in one
pass, and every failure after the quota's gone reads as
`google.genai.errors.ClientError: 429 RESOURCE_EXHAUSTED`, not a real
regression. Live-testing real Gemini calls stays available (and was
verified working end to end for M1/M3/M4/M8) via ad-hoc scripts that
import the services directly — just never through the checked-in
automated suite.
"""
import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def force_deterministic_fallback_paths(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(settings, "GOOGLE_CLOUD_PROJECT", "")
