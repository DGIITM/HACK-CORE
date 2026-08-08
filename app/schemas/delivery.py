"""M5 Response Delivery — shapes for /deliver.

Not part of CLAUDE.md's formal data contract (only M1/M3/M4/M7/M8 are),
so this shape is designed to match M5's stated job: translate, speak,
set expectations, and surface the trust features in the chat UI.
"""
from typing import List, Optional

from pydantic import BaseModel

from app.schemas.recommend import Recommendation


class DeliveryRequest(BaseModel):
    recommendation: Recommendation
    language: str = "pa"


class DeliveryResponse(BaseModel):
    chat_message: str
    translated_language: str
    audio_url: Optional[str] = None
    expectation_setting: str
    trust_features_shown: List[str]
