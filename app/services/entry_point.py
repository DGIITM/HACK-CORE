"""M1 Entry Point — turns voice/text/photo input into a FarmerRequest.

Real pipeline: voice audio, if provided, is transcribed via Cloud
Speech-to-Text using CLAUDE.md's exact language codes; the resulting
text (or typed text) plus any photo go into a SINGLE Gemini multimodal
call (gemini-2.0-flash-001, JSON mode) that extracts crop,
symptom_description, and language. location, photo_present, and
photo_url are never left for the LLM to guess — they're always taken
directly from what was actually supplied, the same "don't trust what
can be verified directly instead" pattern used everywhere else in this
codebase (M4 only recommends retrieved candidates, M8 forces
data_basis, M7 verifies batch_number server-side rather than trusting a
client flag).

Falls back to deterministic text-only extraction when Vertex AI isn't
configured (same LLMNotConfiguredError situation M4/M8 hit — this dev
sandbox has no GCP credentials) or when Cloud STT isn't configured for
a voice submission. Both fallbacks are real, working code paths, not
stubs, and both are logged clearly so it's obvious which mode is active.
"""
import base64
import json
import logging
from typing import Dict, Optional

from app.schemas.entry_point import EntryPointInput, FarmerRequest, LocationSchema
from app.services import llm_service, speech_to_text

logger = logging.getLogger(__name__)

# Keeps the total Gemini request comfortably under CLAUDE.md's 20MB cap
# once the prompt text and base64 overhead are accounted for.
MAX_INLINE_MEDIA_BYTES = 15 * 1024 * 1024

SYSTEM_PROMPT = """You are KrishiSathi's entry-point extractor for Punjab wheat farmers.

You're given what a farmer said (possibly transcribed from voice) and,
sometimes, a photo of their crop. Extract this into the JSON shape below.

RULES:
1. "crop" — the crop being described. If not stated or unclear, use "wheat"
   (nearly all our farmers grow wheat) rather than guessing something else.
2. "symptom_description" — a faithful, plain restatement of the problem in
   the farmer's own terms, informed by the photo if one is attached. Never
   invent symptoms that weren't mentioned or shown. If nothing describable
   was said or shown, say so plainly (e.g. "no clear symptom described").
3. "language" — detect it from the input: one of "hi", "pa", "en". If you
   genuinely can't tell, use the hint you're given.
4. "location", "photo_present", and "photo_url" — just echo back exactly
   what you're given for these under "Known context"; you have no way to
   verify them from the text or photo alone, so do not guess or change them.
5. Respond with ONLY a JSON object, no markdown fences, no commentary:
   {"crop": string, "location": {"district": string, "state": string},
   "symptom_description": string, "language": string,
   "photo_present": boolean, "photo_url": string or null}
"""


class NoUsableInputError(ValueError):
    """Raised when there's genuinely nothing to work with: no typed
    text, and either no audio was given or voice transcription wasn't
    available in this environment, and no photo either. A system-
    boundary validation error, not something to paper over with a
    fabricated symptom."""


def _decode_media(b64: Optional[str], label: str) -> Optional[bytes]:
    if not b64:
        return None
    try:
        data = base64.b64decode(b64, validate=True)
    except (ValueError, TypeError) as exc:
        raise NoUsableInputError(f"Could not decode {label} data: {exc}") from exc
    if len(data) > MAX_INLINE_MEDIA_BYTES:
        raise NoUsableInputError(
            f"{label} is {len(data)} bytes, over the {MAX_INLINE_MEDIA_BYTES} byte limit — "
            "compress before sending (CLAUDE.md: keep Gemini requests under 20MB)."
        )
    return data


def _build_user_prompt(text: str, known: Dict) -> str:
    location = known["location"]
    return (
        f"Farmer's message: {text}\n\n"
        "Known context (echo back exactly, do not change):\n"
        f'location: {{"district": "{location.district}", "state": "{location.state}"}}\n'
        f"photo_present: {'true' if known['photo_present'] else 'false'}\n"
        f"photo_url: {json.dumps(known['photo_url'])}\n"
        f"language hint: {known['language']}"
    )


def _fallback_extraction(text: str, known: Dict, crop_hint: Optional[str]) -> Dict:
    """Deterministic fallback used when Vertex AI isn't configured (no
    GOOGLE_CLOUD_PROJECT in this environment) or the call fails: the
    raw/transcribed text becomes the symptom description directly, with
    no photo analysis possible (there's no LLM in this path to look at
    it). crop_hint is a reasonable best-effort signal here specifically
    — unlike the real extraction path, this mode has no way to genuinely
    determine crop at all, so a client-supplied hint is better than
    silently assuming wheat for every submission.
    """
    return {
        "crop": (crop_hint or "").strip() or "wheat",
        "location": known["location"],
        "symptom_description": text.strip() or "no clear symptom described",
        "language": known["language"],
        "photo_present": known["photo_present"],
        "photo_url": known["photo_url"],
    }


def _validate_extraction(llm_output, known: Dict) -> Dict:
    """The safety net for this module: location, photo_present, and
    photo_url always come from `known` (what was actually supplied),
    never from whatever the LLM says — mirrors M4's candidate-only
    constraint and M8's forced data_basis. crop and symptom_description
    are genuinely extracted, but never left blank/fabricated-looking:
    missing information is reported as missing, not invented.
    """
    if not isinstance(llm_output, dict):
        llm_output = {}

    crop = str(llm_output.get("crop") or "").strip() or "wheat"
    symptom_description = str(llm_output.get("symptom_description") or "").strip()
    if not symptom_description:
        symptom_description = "no clear symptom described"

    language = llm_output.get("language")
    if language not in ("hi", "pa", "en"):
        language = known["language"]

    return {
        "crop": crop,
        "location": known["location"],
        "symptom_description": symptom_description,
        "language": language,
        "photo_present": known["photo_present"],
        "photo_url": known["photo_url"],
    }


def process_entry(payload: EntryPointInput) -> FarmerRequest:
    location = LocationSchema(district=payload.district, state=payload.state)

    audio_bytes = _decode_media(payload.audio_base64, "audio")
    photo_bytes = _decode_media(payload.photo_base64, "photo")

    photo_present = photo_bytes is not None
    # STUB: real deployment would upload to Firebase Storage (per
    # CLAUDE.md's tech stack) and use the resulting gs:// URL here. That
    # upload isn't wired up in this pass — only sending the photo bytes
    # into the same Gemini call was in scope — so this is an honestly
    # labeled placeholder, not a real storage location.
    photo_url = "gs://krishisathi-stub/pending-upload.jpg" if photo_present else None

    text = payload.raw_text or ""
    if audio_bytes:
        try:
            text = speech_to_text.transcribe_audio(audio_bytes, payload.language, payload.audio_mime_type)
            logger.info("Voice input transcribed via Cloud Speech-to-Text.")
        except speech_to_text.SpeechToTextNotConfiguredError:
            logger.warning(
                "Voice input received but Cloud Speech-to-Text isn't configured in this "
                "environment — falling back to text-only mode using any typed text."
            )
            # Real, working fallback: proceed with whatever typed text
            # exists (possibly none) rather than fabricating a transcript.

    if not text.strip() and not photo_present:
        raise NoUsableInputError(
            "No usable input: no typed or transcribed text, and no photo, were provided."
        )

    known = {
        "location": location,
        "language": payload.language,
        "photo_present": photo_present,
        "photo_url": photo_url,
    }

    try:
        raw = llm_service.generate_response(
            prompt=_build_user_prompt(text or "(no text provided — see attached photo)", known),
            system_prompt=SYSTEM_PROMPT,
            json_mode=True,
            image_bytes=photo_bytes,
            image_mime_type=payload.photo_mime_type,
        )
        llm_output = json.loads(llm_service.extract_json_object(raw))
        extracted = _validate_extraction(llm_output, known)
    except llm_service.LLMUnavailableError as exc:
        logger.warning("Gemini unavailable for entry-point extraction, falling back: %s", exc)
        extracted = _fallback_extraction(text, known, payload.crop)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Gemini entry-point extraction could not be parsed, falling back: %s", exc)
        extracted = _fallback_extraction(text, known, payload.crop)

    return FarmerRequest(**extracted)
