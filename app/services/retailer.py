"""M6 Retailer Console — district view of recommendations + evidence."""
import random

from app.schemas.retailer import RetailerConsoleResponse, RetailerEvidenceRow
from app.services import data_foundation


def get_district_console(district: str) -> RetailerConsoleResponse:
    # STUB: real logic queries Firestore for every recommendation + outcome
    # log in this district, plus counterfeit batch registry lookups, so the
    # retailer can see the evidence a farmer would otherwise never share.
    catalog = data_foundation.get_product_catalog()
    rows = [
        RetailerEvidenceRow(
            farmer_id=f"farmer-{i:03d}",
            crop="wheat",
            recommended_product=random.choice(catalog)["name"],
            confidence_score=round(random.uniform(0.6, 0.95), 2),
            outcome_verified=random.choice([True, False]),
            counterfeit_flagged=random.random() < 0.1,
        )
        for i in range(1, 6)
    ]

    return RetailerConsoleResponse(
        district=district,
        rows=rows,
        counterfeit_alerts=sum(1 for r in rows if r.counterfeit_flagged),
    )
