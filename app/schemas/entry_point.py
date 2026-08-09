"""M1 Entry Point — shapes for /entry-point.

FarmerRequest is the exact contract from CLAUDE.md's "Farmer request
(M1 output)" section. Do not change its fields without agreeing the change
with the whole team first — every downstream module reads this shape.
"""
from typing import Optional

from pydantic import BaseModel


class LocationSchema(BaseModel):
    district: str
    state: str


class FarmerRequest(BaseModel):
    crop: str
    location: LocationSchema
    symptom_description: str
    language: str
    photo_present: bool
    photo_url: Optional[str] = None


class EntryPointInput(BaseModel):
    """Raw capture from the chat/voice/photo UI, before M1 structures it.

    Audio and photo travel as base64 inside this same JSON body (not
    multipart) so the existing text-only callers/tests keep working
    unchanged — every media field is optional and additive.

    crop is an advisory hint only: the real (Gemini) extraction path
    determines crop itself from the text/photo rather than trusting a
    client claim, the same "don't trust an unverifiable client
    assertion" call M7 made for batch_verified. It's still used as a
    best-effort default in the deterministic fallback path, which has no
    real extraction capability of its own.
    """

    raw_text: Optional[str] = None
    crop: Optional[str] = None
    district: str = "Ludhiana"
    state: str = "Punjab"
    language: str = "pa"
    audio_base64: Optional[str] = None
    audio_mime_type: Optional[str] = "audio/webm"
    photo_base64: Optional[str] = None
    photo_mime_type: Optional[str] = "image/jpeg"
