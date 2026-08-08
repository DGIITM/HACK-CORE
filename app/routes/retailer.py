"""M6 Retailer Console route — thin HTTP layer, no logic here."""
from fastapi import APIRouter

from app.schemas.retailer import RetailerConsoleResponse
from app.services import retailer as retailer_service

router = APIRouter()


@router.get("/retailer", response_model=RetailerConsoleResponse)
def retailer(district: str = "Ludhiana") -> RetailerConsoleResponse:
    return retailer_service.get_district_console(district)
