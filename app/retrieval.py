"""
Runtime retrieval: load the precomputed embedding matrix once, embed a query
with whichever provider build_embeddings.py actually used (recorded in
embeddings_meta.json), and rank by cosine similarity via a plain numpy
matrix-vector multiply -- this is the swap-out lab/section_2_agentic_ai_basic
/06d_rag.py's own docstring points at ("swap this one function and the rest
still works"): real vectors + a vectorized dot product instead of a
bag-of-words dict and a per-chunk Python loop, needed once the corpus is
NUSMods-scale (hundreds to low thousands of records) rather than the lab's
~20-chunk toy demo.
"""

import json
import pickle

import numpy as np

from app.config import EMBEDDINGS_FILE, EMBEDDINGS_META_FILE, PROCESSED_DIR

_index_cache: tuple[np.ndarray, list[dict], str] | None = None
_tfidf_vectorizer = None


def load_index() -> tuple[np.ndarray, list[dict]]:
    """Load embeddings.npy + embeddings_meta.json once; module-level cache."""
    global _index_cache
    if _index_cache is None:
        if not EMBEDDINGS_FILE.exists() or not EMBEDDINGS_META_FILE.exists():
            raise FileNotFoundError(
                "No embeddings found. Run data_pipeline/build_embeddings.py first."
            )
        matrix = np.load(EMBEDDINGS_FILE)
        meta = json.loads(EMBEDDINGS_META_FILE.read_text())
        _index_cache = (matrix, meta["records"], meta["provider"])
    matrix, records, _provider = _index_cache
    return matrix, records


def _provider() -> str:
    if _index_cache is None:
        load_index()
    return _index_cache[2]


def embed_query(text: str) -> np.ndarray:
    """The only live embedding call at runtime -- everything else was
    precomputed by build_embeddings.py at data-prep time."""
    provider = _provider()
    if provider == "bedrock":
        from app.common import EMBED_MODEL_ID, bedrock_runtime

        client = bedrock_runtime()
        body = json.dumps({"inputText": text[:8000], "dimensions": 1024, "normalize": True})
        resp = client.invoke_model(modelId=EMBED_MODEL_ID, body=body)
        payload = json.loads(resp["body"].read())
        return np.array(payload["embedding"], dtype="float32")

    global _tfidf_vectorizer
    if _tfidf_vectorizer is None:
        vectorizer_path = PROCESSED_DIR / "tfidf_vectorizer.pkl"
        _tfidf_vectorizer = pickle.loads(vectorizer_path.read_bytes())
    vec = _tfidf_vectorizer.transform([text]).toarray().astype("float32")[0]
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec


def cosine_topk(
    query_vec: np.ndarray,
    matrix: np.ndarray,
    meta: list[dict],
    k: int = 5,
    record_type: str | None = None,
    min_score: float = 0.05,
) -> list[dict]:
    """scores = matrix @ query_vec (both L2-normalized -> cosine == dot product).
    Optional record_type mask applied post-matmul -- cheap enough at the
    NUSMods-scoped scale (a few thousand rows at most) with no need to
    pre-partition the matrix by type."""
    scores = matrix @ query_vec
    order = np.argsort(-scores)
    results = []
    for i in order:
        if len(results) >= k:
            break
        score = float(scores[i])
        if score < min_score:
            break
        record = meta[i]
        if record_type and record["record_type"] != record_type:
            continue
        results.append({**record, "score": score})
    return results
