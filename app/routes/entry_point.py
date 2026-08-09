"""M1 Entry Point route — thin HTTP layer, no logic here."""
from fastapi import APIRouter, HTTPException

from app.schemas.entry_point import EntryPointInput, FarmerRequest
from app.services import entry_point as entry_point_service

router = APIRouter()


@router.post("/entry-point", response_model=FarmerRequest)
def entry_point(payload: EntryPointInput) -> FarmerRequest:
    try:
        return entry_point_service.process_entry(payload)
    except entry_point_service.NoUsableInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
