"""M1 Entry Point route — thin HTTP layer, no logic here."""
from fastapi import APIRouter

from app.schemas.entry_point import EntryPointInput, FarmerRequest
from app.services import entry_point as entry_point_service

router = APIRouter()


@router.post("/entry-point", response_model=FarmerRequest)
def entry_point(payload: EntryPointInput) -> FarmerRequest:
    return entry_point_service.process_entry(payload)
