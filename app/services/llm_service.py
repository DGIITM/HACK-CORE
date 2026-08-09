"""Single choke point for all LLM calls — per house convention, no route
or other service may import the Gemini/Vertex AI SDK directly.

Only the "gemini" provider is implemented, matching CLAUDE.md's locked
model choice (gemini-2.0-flash-001 via Vertex AI — not a preview model).
"""
import re
from typing import Optional

from app.core.config import settings

MODEL_NAME = "gemini-2.0-flash-001"


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
    (Gemini 2.0 Flash handles text + image together per CLAUDE.md) — this
    is the only path that should ever be used for a photo, never a
    separate vision-model call."""
    if settings.LLM_PROVIDER == "gemini":
        return _call_gemini(prompt, system_prompt, json_mode, image_bytes, image_mime_type)
    raise LLMNotConfiguredError(f"Unsupported LLM_PROVIDER: {settings.LLM_PROVIDER!r}")


def _call_gemini(
    prompt: str,
    system_prompt: str,
    json_mode: bool,
    image_bytes: Optional[bytes],
    image_mime_type: Optional[str],
) -> str:
    if not settings.GOOGLE_CLOUD_PROJECT:
        raise LLMNotConfiguredError(
            "GOOGLE_CLOUD_PROJECT is not set — Vertex AI Gemini isn't configured in this environment."
        )

    import vertexai
    from vertexai.generative_models import GenerationConfig, GenerativeModel, Part

    vertexai.init(project=settings.GOOGLE_CLOUD_PROJECT, location=settings.VERTEX_AI_LOCATION)
    model = GenerativeModel(MODEL_NAME, system_instruction=system_prompt or None)
    generation_config = GenerationConfig(response_mime_type="application/json") if json_mode else None

    contents = [prompt]
    if image_bytes:
        contents.append(Part.from_data(data=image_bytes, mime_type=image_mime_type or "image/jpeg"))

    response = model.generate_content(contents, generation_config=generation_config)
    return response.text


def extract_json_object(text: str) -> str:
    """Gemini sometimes wraps JSON in markdown fences or adds stray text
    even when asked not to — pull out the first {...} block rather than
    assuming the raw response is clean JSON."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in LLM response")
    return match.group(0)
