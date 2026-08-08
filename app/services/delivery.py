"""M5 Response Delivery — translate, speak, set expectations, chat UI."""
from app.schemas.delivery import DeliveryRequest, DeliveryResponse


def deliver(req: DeliveryRequest) -> DeliveryResponse:
    # STUB: real logic runs the recommendation through the Google Cloud
    # Translation API into the farmer's language, synthesizes speech with
    # Chirp 3 HD TTS (Punjabi HD voice is Preview — test early), and
    # assembles the trust-feature copy (mode of action, neighbour proof,
    # expectation setting) in plain, jargon-free language.
    rec = req.recommendation

    if rec.no_confident_match:
        chat_message = (
            "I couldn't find a product I'm confident enough about yet — "
            "it's better to be honest than guess."
        )
    else:
        chat_message = (
            f"Based on what you described, {rec.recommended_product} looks like a good fit "
            f"({int(rec.confidence_score * 100)}% confidence). {rec.plain_language_reason}"
        )

    return DeliveryResponse(
        chat_message=chat_message,
        translated_language=req.language,
        audio_url=f"gs://krishisathi-stub/tts/{req.language}-fake.mp3",
        expectation_setting="You likely won't see visible change for about 3 weeks — that's normal for biological products.",
        trust_features_shown=["mode_of_action", "neighbour_proof", "expectation_setting"],
    )
