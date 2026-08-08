"""M2 Data Foundation.

Nearly every other module reads from here, which is why CLAUDE.md says to
build it first. It has no HTTP route of its own.

# STUB: real version loads:
#   - the product/efficacy catalog from Qdrant (for M4 retrieval)
#   - regional pest history + weather from BigQuery (for M3)
#   - the counterfeit batch registry (for M6/M7)
#   - the synthetic season dataset with known ground-truth effect (for M8)
# For now this is a small in-memory fixture so the other stub services have
# something realistic to read from.
"""
from typing import Dict, List

PRODUCT_CATALOG: List[Dict] = [
    {
        "name": "Trichoderma viride bio-fungicide",
        "mode_of_action": "colonizes root zone and out-competes fungal pathogens",
        "targets": ["yellow rust", "root rot"],
    },
    {
        "name": "Pseudomonas fluorescens bio-inoculant",
        "mode_of_action": "triggers the plant's own induced systemic resistance",
        "targets": ["leaf blight", "yellow rust"],
    },
    {
        "name": "Bacillus subtilis seed treatment",
        "mode_of_action": "forms a protective biofilm around the root that blocks soil pathogens",
        "targets": ["root rot", "damping off"],
    },
    {
        "name": "Neem-based bio-pesticide",
        "mode_of_action": "disrupts feeding and growth of soft-bodied pests",
        "targets": ["aphids", "leaf blight"],
    },
]

PEST_HISTORY_BY_DISTRICT: Dict[str, List[str]] = {
    "Ludhiana": ["yellow rust", "aphids"],
    "Patiala": ["leaf blight"],
    "Amritsar": ["root rot", "yellow rust"],
}


def get_product_catalog() -> List[Dict]:
    # STUB: replace with a Qdrant similarity search against the efficacy
    # dataset, filtered by crop + symptom + active pests.
    return PRODUCT_CATALOG


def get_pest_history(district: str) -> List[str]:
    # STUB: replace with a BigQuery lookup against the pest history table.
    return PEST_HISTORY_BY_DISTRICT.get(district, [])
