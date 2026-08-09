"""Google Cloud Translation API for M5 Response Delivery.

Falls back to returning the original English text when Cloud Translation
isn't configured — the same LLMNotConfiguredError-style situation every
other module has hit (this dev sandbox has no GCP credentials). Callers
must catch TranslationNotConfiguredError and report the text as still
being in English rather than falsely claiming it was translated.
"""
from app.core.config import settings

# App language codes -> BCP-47 codes Cloud Translation expects. "en" is
# handled by callers before this is ever called (no translation needed).
TRANSLATE_LANGUAGE_CODES = {
    "hi": "hi",
    "pa": "pa",
}


class TranslationNotConfiguredError(RuntimeError):
    """Raised when Cloud Translation isn't reachable/configured. Callers
    fall back to the original English text — never a garbled or
    fabricated "translation."""


def translate_text(text: str, target_language: str) -> str:
    """All source text in this app is authored in English (see M4's and
    M5's prompts/templates), so source_language is always "en"."""
    if not settings.GOOGLE_CLOUD_PROJECT:
        raise TranslationNotConfiguredError(
            "GOOGLE_CLOUD_PROJECT is not set — Cloud Translation isn't configured in this environment."
        )

    from google.cloud import translate_v2 as translate

    client = translate.Client()
    target = TRANSLATE_LANGUAGE_CODES.get(target_language, target_language)
    result = client.translate(text, target_language=target, source_language="en")
    return result["translatedText"]
