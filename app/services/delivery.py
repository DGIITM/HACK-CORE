"""M5 Response Delivery — translate, speak, set expectations, chat UI.

All source copy (chat_message, expectation_setting) is authored in
English here, then run through Cloud Translation into the farmer's
language. translated_language reports the language the returned text is
ACTUALLY in — "en" whenever translation wasn't available, never a false
claim that untranslated English is really Punjabi or Hindi. Audio is
synthesized from the (possibly translated) combined text via Chirp 3 HD,
with a standard-voice fallback per CLAUDE.md's Punjabi-Preview warning.
"""
import logging
from typing import Tuple

from app.schemas.delivery import DeliveryRequest, DeliveryResponse
from app.services import translation_service, tts_service

logger = logging.getLogger(__name__)


def _build_chat_message(rec) -> str:
    if rec.no_confident_match:
        return (
            "I couldn't find a product I'm confident enough about yet — "
            "it's better to be honest than guess."
        )
    return (
        f"Based on what you described, {rec.recommended_product} looks like a good fit "
        f"({int(rec.confidence_score * 100)}% confidence). {rec.plain_language_reason}"
    )


def _build_expectation_message(rec, crop: str) -> str:
    crop = (crop or "").strip() or "crop"
    if rec.no_confident_match or not rec.recommended_product:
        return (
            "Once we do have a confident recommendation for you, keep in mind biological "
            "products usually take a few weeks to show visible results."
        )
    return (
        f"You likely won't see a visible change in your {crop} for about 3 weeks after using "
        f"{rec.recommended_product} — that's normal for biological products, not a sign it isn't working."
    )


def _translate(text: str, language: str) -> Tuple[str, str]:
    """Returns (text, actual_language_of_returned_text)."""
    if not text or language == "en":
        return text, "en"
    try:
        return translation_service.translate_text(text, language), language
    except translation_service.TranslationNotConfiguredError:
        logger.warning(
            "Cloud Translation isn't configured in this environment — returning "
            "untranslated English text instead of a stub."
        )
        return text, "en"


def deliver(req: DeliveryRequest) -> DeliveryResponse:
    rec = req.recommendation

    chat_message_en = _build_chat_message(rec)
    expectation_en = _build_expectation_message(rec, req.crop)

    chat_message, chat_lang = _translate(chat_message_en, req.language)
    expectation_setting, expectation_lang = _translate(expectation_en, req.language)
    # Both should land in the same actual language. If they somehow
    # didn't (one translated, one fell back), report the more
    # conservative claim rather than an inconsistent one.
    translated_language = chat_lang if chat_lang == expectation_lang else "en"

    try:
        audio_url = tts_service.synthesize_speech(f"{chat_message} {expectation_setting}", translated_language)
    except tts_service.TextToSpeechNotConfiguredError:
        logger.warning(
            "Cloud Text-to-Speech isn't configured in this environment — returning no "
            "audio_url instead of a fake one."
        )
        audio_url = None

    trust_features_shown = []
    if rec.mode_of_action:
        trust_features_shown.append("mode_of_action")
    if rec.neighbour_proof.available:
        trust_features_shown.append("neighbour_proof")
    if not rec.no_confident_match and rec.recommended_product:
        trust_features_shown.append("expectation_setting")

    return DeliveryResponse(
        chat_message=chat_message,
        translated_language=translated_language,
        audio_url=audio_url,
        expectation_setting=expectation_setting,
        trust_features_shown=trust_features_shown,
    )
