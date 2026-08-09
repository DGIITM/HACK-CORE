"""M4 retrieval — embeds get_efficacy_dataset() and serves nearest-neighbour
candidate lookups through Qdrant, per CLAUDE.md's vector-DB choice.

Embedding choice: TF-IDF vectors (scikit-learn) over each product's text
(name + target problem + mode of action), not a hosted embedding model.
That's a deliberate call, not a stub: it needs no GCP credentials or model
download, so retrieval genuinely works end-to-end in any dev environment
(including this one, which has no Vertex AI project configured). The
Qdrant interface below is real and unchanged either way — swap in Vertex
AI's text-embedding model later by changing only how vectors are built,
nothing that calls this module.

Candidates are relevance-gated here, not just top-k: retrieve_candidates()
drops anything below MIN_SIMILARITY before Gemini (or the fallback) ever
sees it, so a crop/symptom that genuinely has nothing relevant in the
catalog comes back as an empty candidate list rather than "the least bad
of 16 unrelated products."

Soil type is deliberately NOT part of the similarity gate. An earlier
version mixed it into the query text and that let soil words alone
(e.g. "loam") produce false-positive matches for empty or nonsense
symptom text, since roughly half the catalog's typical_soil_type field
contains "loam". Soil type is now only a small ranking bonus applied
after a candidate has already cleared the symptom-based relevance bar.
"""
from typing import Dict, List

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from sklearn.feature_extraction.text import TfidfVectorizer

from app.core.config import settings
from app.services import data_foundation

COLLECTION_NAME = "efficacy_products"
MIN_SIMILARITY = 0.12  # cosine similarity floor below which a match doesn't count as relevant
SOIL_MATCH_BONUS = 0.05  # ranking nudge only, applied after the relevance gate
TOP_K = 5


def _document_text(row: Dict) -> str:
    """Deliberately excludes typical_soil_type — see module docstring."""
    return " ".join([row["product_name"], row["target_problem"], row["mode_of_action"]])


class _EfficacyIndex:
    """Lazily built once per process: fits the vectorizer on the wheat
    efficacy catalog and loads the vectors into Qdrant."""

    def __init__(self) -> None:
        self._client = QdrantClient(location=settings.QDRANT_URL or ":memory:")
        self._vectorizer = TfidfVectorizer(stop_words="english")
        self._rows: List[Dict] = []
        self._built = False

    def _build(self) -> None:
        self._rows = data_foundation.get_efficacy_dataset()
        documents = [_document_text(row) for row in self._rows]
        vectors = self._vectorizer.fit_transform(documents).toarray()

        if self._client.collection_exists(COLLECTION_NAME):
            self._client.delete_collection(COLLECTION_NAME)
        self._client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=qmodels.VectorParams(
                size=vectors.shape[1], distance=qmodels.Distance.COSINE
            ),
        )
        self._client.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                qmodels.PointStruct(id=i, vector=vectors[i].tolist(), payload=self._rows[i])
                for i in range(len(self._rows))
            ],
        )
        self._built = True

    def search(self, crop: str, query_text: str, soil_type: str, top_k: int) -> List[Dict]:
        if not self._built:
            self._build()

        matching_crop_rows = [row for row in self._rows if row["crop"].lower() == crop.lower().strip()]
        if not matching_crop_rows:
            return []

        query_vector = self._vectorizer.transform([query_text]).toarray()[0]
        if not query_vector.any():
            # No overlap at all with the catalog's vocabulary — nothing to
            # rank. This is the gate that catches empty/gibberish/off-topic
            # symptom text.
            return []

        # Crop mismatch already returned [] above, so every point in the
        # collection is a valid candidate crop-wise — no filter needed here.
        hits = self._client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector.tolist(),
            limit=len(self._rows),
        ).points

        candidates = []
        for hit in hits:
            if hit.score < MIN_SIMILARITY:
                continue
            score = hit.score
            if soil_type and soil_type.lower() in hit.payload["typical_soil_type"].lower():
                score += SOIL_MATCH_BONUS
            candidates.append({**hit.payload, "_similarity": round(score, 4)})

        candidates.sort(key=lambda c: c["_similarity"], reverse=True)
        return candidates[:top_k]


_index = _EfficacyIndex()


def retrieve_candidates(
    crop: str,
    symptom_description: str,
    active_pests: List[str],
    soil_type: str,
    top_k: int = TOP_K,
) -> List[Dict]:
    """Top 3-5 efficacy-dataset rows most relevant to this farmer's crop,
    symptom, and active regional pests (soil type only breaks ties among
    those). Returns [] — not the "closest available" junk — when nothing
    clears MIN_SIMILARITY.
    """
    query_text = " ".join([symptom_description, " ".join(active_pests)])
    return _index.search(crop=crop, query_text=query_text, soil_type=soil_type, top_k=top_k)
