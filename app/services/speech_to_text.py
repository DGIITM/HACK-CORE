"""Google Cloud Speech-to-Text for M1 voice input.

Language codes are locked per CLAUDE.md: hi-IN, pa-guru-IN (Gurmukhi —
NOT pa-IN, which CLAUDE.md warns fails silently), en-IN.

Falls back cleanly when GCP credentials aren't configured — the same
LLMNotConfiguredError situation M4 hit with Vertex AI and M7 hit with
Firestore. Callers must catch SpeechToTextNotConfiguredError and fall
back to text-only mode; never fabricate a transcript.
"""
from typing import Optional

from app.core.config import settings

# NOT pa-IN — CLAUDE.md is explicit that pa-IN fails silently.
STT_LANGUAGE_CODES = {
    "hi": "hi-IN",
    "pa": "pa-guru-IN",
    "en": "en-IN",
}

# Browser MediaRecorder defaults to audio/webm (Opus) in Chrome and
# audio/ogg (Opus) in Firefox — both map to an Opus encoding Cloud STT
# understands directly.
_MIME_TO_ENCODING = {
    "audio/webm": "WEBM_OPUS",
    "audio/ogg": "OGG_OPUS",
    "audio/wav": "LINEAR16",
    "audio/x-wav": "LINEAR16",
    "audio/flac": "FLAC",
}
DEFAULT_ENCODING = "WEBM_OPUS"


class SpeechToTextNotConfiguredError(RuntimeError):
    """Raised when Cloud STT isn't reachable/configured. Callers fall
    back to text-only mode — never fabricate a transcript."""


def stt_language_code(app_language: str) -> str:
    return STT_LANGUAGE_CODES.get(app_language, "en-IN")


def transcribe_audio(audio_bytes: bytes, app_language: str, mime_type: Optional[str] = None) -> str:
    if not settings.GOOGLE_CLOUD_PROJECT:
        raise SpeechToTextNotConfiguredError(
            "GOOGLE_CLOUD_PROJECT is not set — Cloud Speech-to-Text isn't configured in this environment."
        )

    from google.cloud import speech

    encoding_name = _MIME_TO_ENCODING.get((mime_type or "").lower(), DEFAULT_ENCODING)
    encoding = getattr(speech.RecognitionConfig.AudioEncoding, encoding_name)

    client = speech.SpeechClient()
    audio = speech.RecognitionAudio(content=audio_bytes)
    # sample_rate_hertz intentionally omitted: for OPUS-in-WebM/Ogg,
    # Cloud STT reads the rate from the container instead of requiring
    # it up front — hardcoding one here risks silently mismatching
    # whatever the browser's mic actually captured at.
    config = speech.RecognitionConfig(
        encoding=encoding,
        language_code=stt_language_code(app_language),
    )
    response = client.recognize(config=config, audio=audio)
    transcript = " ".join(
        result.alternatives[0].transcript for result in response.results if result.alternatives
    )
    return transcript.strip()
