"""Google Cloud Text-to-Speech for M5 Response Delivery.

Chirp 3 HD voices per CLAUDE.md. Punjabi's HD voice is explicitly called
out there as Preview ("test early") — this module treats *any* HD voice
failure the same way, not just Punjabi's: if the HD voice call errors or
misbehaves, it retries the same text with a standard voice for the same
locale rather than failing delivery entirely, and logs clearly which
voice mode actually spoke.

Falls back to returning None (no audio) when Cloud TTS isn't configured
at all — this dev sandbox has no GCP credentials, the same situation
every other module's real API integration has hit. Never a fake
audio_url pointing at nothing playable.
"""
import base64
import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# "Aoede" is a real Chirp 3 HD voice name Google has enabled across the
# locales below. Locale codes here are TTS's own (pa-IN, not STT's
# special pa-guru-IN — that Gurmukhi-specific code is a Speech-to-Text
# quirk documented in CLAUDE.md, unrelated to TTS voice naming).
_HD_VOICE = {
    "en": ("en-IN", "en-IN-Chirp3-HD-Aoede"),
    "hi": ("hi-IN", "hi-IN-Chirp3-HD-Aoede"),
    "pa": ("pa-IN", "pa-IN-Chirp3-HD-Aoede"),
}
_STANDARD_FALLBACK_VOICE = {
    "en": ("en-IN", "en-IN-Standard-A"),
    "hi": ("hi-IN", "hi-IN-Standard-A"),
    "pa": ("pa-IN", "pa-IN-Standard-A"),
}


class TextToSpeechNotConfiguredError(RuntimeError):
    """Raised when Cloud TTS isn't reachable/configured. Callers fall
    back to no audio — never a fake audio_url."""


def synthesize_speech(text: str, app_language: str) -> Optional[str]:
    """Returns a data: URI of the synthesized MP3. No Firebase Storage
    upload is wired up in this pass (out of scope, same call M1 made for
    photo_url), so the audio travels inline — genuinely playable by a
    browser <audio> tag without needing a storage bucket.
    """
    if not settings.GOOGLE_CLOUD_PROJECT:
        raise TextToSpeechNotConfiguredError(
            "GOOGLE_CLOUD_PROJECT is not set — Cloud Text-to-Speech isn't configured in this environment."
        )

    from google.cloud import texttospeech

    client = texttospeech.TextToSpeechClient()
    synthesis_input = texttospeech.SynthesisInput(text=text)
    audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)

    locale, hd_voice_name = _HD_VOICE.get(app_language, _HD_VOICE["en"])
    try:
        voice = texttospeech.VoiceSelectionParams(language_code=locale, name=hd_voice_name)
        response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
        logger.info("Synthesized speech with Chirp 3 HD voice %s.", hd_voice_name)
    except Exception as exc:
        fallback_locale, fallback_voice_name = _STANDARD_FALLBACK_VOICE.get(
            app_language, _STANDARD_FALLBACK_VOICE["en"]
        )
        logger.warning(
            "Chirp 3 HD voice %s errored (%s) — falling back to standard voice %s.",
            hd_voice_name, exc, fallback_voice_name,
        )
        voice = texttospeech.VoiceSelectionParams(language_code=fallback_locale, name=fallback_voice_name)
        response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)

    audio_base64 = base64.b64encode(response.audio_content).decode()
    return f"data:audio/mp3;base64,{audio_base64}"
