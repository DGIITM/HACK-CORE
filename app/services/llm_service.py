"""Single choke point for all LLM calls — per house convention, no route
or other service may import a Gemini SDK directly. M1 (extraction), M3
(early-warning text), M4 (reasoning), and M8 (narration) all route
through generate_response() below.

Two Gemini auth tiers, both via the unified `google-genai` SDK:
  1. Gemini Developer API (GEMINI_API_KEY — a free Google AI Studio key).
     Primary tier: this is what actually works from a dev machine with
     no GCP project, which is the situation every earlier module hit.
  2. Vertex AI (GOOGLE_CLOUD_PROJECT + service-account credentials).
     Fallback tier — CLAUDE.md's stated production path once real GCP
     access comes through, kept working but no longer the thing that
     runs on every call.
If neither is configured, LLMNotConfiguredError propagates and callers
fall back to their own deterministic logic — same as before.

Model: gemini-3.5-flash, not gemini-2.0-flash-001. CLAUDE.md's original
locked choice (gemini-2.0-flash-001) is confirmed fully retired as of
June 1, 2026 — API calls return errors on both Vertex AI and the
Developer API, it's not just a naming difference between the two
surfaces. gemini-2.5-flash was considered as the direct replacement but
itself has a stated shutdown of October 16, 2026 — barely more runway
than what just broke. gemini-3.5-flash is GA (not preview, per CLAUDE.md's
own "avoid preview models" principle), multimodal, and callable under
the identical name on both the Developer API and Vertex AI.
"""
import json
import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

MODEL_NAME = "gemini-3.5-flash"


class LLMNotConfiguredError(RuntimeError):
    """Raised when the configured provider has no usable credentials.
    Callers must catch this and fall back to deterministic logic — a
    missing API key should never surface as a raw 500, and it must never
    be treated as license to invent an answer."""


def generate_response(
    prompt: str,
    system_prompt: str = "",
    json_mode: bool = False,
    image_bytes: Optional[bytes] = None,
    image_mime_type: Optional[str] = None,
) -> str:
    """image_bytes, if given, goes into the SAME call as the text prompt
    (Gemini handles text + image together per CLAUDE.md) — this is the
    only path that should ever be used for a photo, never a separate
    vision-model call."""
    if settings.LLM_PROVIDER == "gemini":
        return _call_gemini(prompt, system_prompt, json_mode, image_bytes, image_mime_type)
    raise LLMNotConfiguredError(f"Unsupported LLM_PROVIDER: {settings.LLM_PROVIDER!r}")


def _get_client_and_tier():
    """Returns (client, tier_name). Tries the Developer API first, then
    Vertex AI, then gives up — see module docstring for why this order."""
    from google import genai

    if settings.GEMINI_API_KEY:
        return genai.Client(api_key=settings.GEMINI_API_KEY), "gemini-developer-api"

    if settings.GOOGLE_CLOUD_PROJECT:
        return (
            genai.Client(vertexai=True, project=settings.GOOGLE_CLOUD_PROJECT, location=settings.VERTEX_AI_LOCATION),
            "vertex-ai",
        )

    raise LLMNotConfiguredError(
        "Neither GEMINI_API_KEY nor GOOGLE_CLOUD_PROJECT is set — Gemini isn't configured in this environment."
    )


def _call_gemini(
    prompt: str,
    system_prompt: str,
    json_mode: bool,
    image_bytes: Optional[bytes],
    image_mime_type: Optional[str],
) -> str:
    from google.genai import types

    client, tier = _get_client_and_tier()
    logger.info("Calling Gemini (%s) via model %s.", tier, MODEL_NAME)

    contents = [prompt]
    if image_bytes:
        contents.append(types.Part.from_bytes(data=image_bytes, mime_type=image_mime_type or "image/jpeg"))

    config = types.GenerateContentConfig(
        system_instruction=system_prompt or None,
        response_mime_type="application/json" if json_mode else None,
    )

    response = client.models.generate_content(model=MODEL_NAME, contents=contents, config=config)
    return response.text


def extract_json_object(text: str) -> str:
    """Gemini sometimes wraps JSON in markdown fences, adds stray text,
    or — observed live with gemini-3.5-flash's JSON mode, not just a
    theoretical concern — appends redundant extra closing braces after a
    complete, valid object, even when told not to. A naive "first { to
    last }" match would swallow that trailing garbage as part of the
    "extracted" JSON and break json.loads. Decoding exactly one JSON
    value from the first '{' (and ignoring whatever comes after it) is
    robust to both problems.
    """
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in LLM response")
    try:
        obj, _ = json.JSONDecoder().raw_decode(text, start)
    except json.JSONDecodeError as exc:
        raise ValueError(f"No valid JSON object found in LLM response: {exc}") from exc
    return json.dumps(obj)
