"""M1 Entry Point — turns voice/text/photo input into a FarmerRequest."""
from app.schemas.entry_point import EntryPointInput, FarmerRequest, LocationSchema


def process_entry(payload: EntryPointInput) -> FarmerRequest:
    # STUB: real logic runs Google Cloud STT on voice audio (language codes
    # hi-IN / pa-guru-IN / en-IN — pa-guru-IN specifically, pa-IN fails
    # silently), sends any attached photo to Gemini for a symptom
    # description, and merges everything into this exact contract shape.
    symptom_description = payload.raw_text or "leaves turning yellow at the tips"

    return FarmerRequest(
        crop=payload.crop or "wheat",
        location=LocationSchema(district=payload.district, state=payload.state),
        symptom_description=symptom_description,
        language=payload.language,
        photo_present=payload.has_photo,
        photo_url="gs://krishisathi-stub/fake-photo.jpg" if payload.has_photo else None,
    )
