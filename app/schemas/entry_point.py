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
    """Raw capture from the chat/voice/photo UI, before M1 structures it."""

    raw_text: Optional[str] = None
    crop: Optional[str] = "wheat"
    district: str = "Ludhiana"
    state: str = "Punjab"
    language: str = "pa"
    has_photo: bool = False
