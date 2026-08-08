"""M10 Platform & Infra — the FastAPI app, wired to every module's router.

Every module below is still a stub (grep "STUB" to see what's left). This
file's only job is correct wiring: one router per module, plus serving the
single-file frontend.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.routes import (
    delivery,
    entry_point,
    impact,
    outcome_log,
    recommend,
    retailer,
    risk_context,
)

app = FastAPI(title=settings.APP_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(entry_point.router, tags=["M1 Entry Point"])
app.include_router(risk_context.router, tags=["M3 Risk Intelligence"])
app.include_router(recommend.router, tags=["M4 Recommendation Engine"])
app.include_router(delivery.router, tags=["M5 Response Delivery"])
app.include_router(retailer.router, tags=["M6 Retailer Console"])
app.include_router(outcome_log.router, tags=["M7 Application & Logging"])
app.include_router(impact.router, tags=["M8 Impact Measurement"])

# Must be mounted last: it's a catch-all for "/" and everything under it.
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
