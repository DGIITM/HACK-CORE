"""M5 Response Delivery route — thin HTTP layer, no logic here."""
from fastapi import APIRouter

from app.schemas.delivery import DeliveryRequest, DeliveryResponse
from app.services import delivery as delivery_service

router = APIRouter()


@router.post("/deliver", response_model=DeliveryResponse)
def deliver(payload: DeliveryRequest) -> DeliveryResponse:
    return delivery_service.deliver(payload)
