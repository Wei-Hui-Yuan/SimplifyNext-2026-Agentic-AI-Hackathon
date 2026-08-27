"""
Build one embedding vector per record (module or synthetic entry), cached to
disk so the only live embedding call at runtime is the query itself.

Tries Bedrock Titan Embed Text v2 first (dimensions=1024, normalize=True --
pre-normalized vectors mean query-time cosine similarity is a plain dot
product). Falls back automatically to a TF-IDF vectorizer (pure CPU, no
AWS/network dependency) if Bedrock creds/access aren't available -- same
"a tool error the pipeline can recover from" ethos as the rest of this repo's
tool-calling code. app/retrieval.py reads which provider was used from
embeddings_meta.json and embeds queries the same way at runtime.

Idempotency is only worth doing on the Bedrock path (real API cost/latency
per call) -- TF-IDF refits the whole corpus every run, which is free and near
instant, so there's no reason to complicate that path.

  uv run python data_pipeline/build_embeddings.py
"""

import hashlib
import json
import pickle
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from app.config import (
    ALUMNI_FILE,
    COMPETITIONS_FILE,
    EMBEDDINGS_FILE,
    EMBEDDINGS_META_FILE,
    MODULES_DIR,
    OPPORTUNITIES_FILE,
    PROCESSED_DIR,
    PROFESSORS_FILE,
    SCHOLARSHIPS_FILE,
)

TFIDF_VECTORIZER_FILE = PROCESSED_DIR / "tfidf_vectorizer.pkl"


def _hash(record_id: str, text: str) -> str:
    return hashlib.sha256(f"{record_id}:{text}".encode()).hexdigest()[:16]


def load_module_records() -> list[dict]:
    records = []
    for f in MODULES_DIR.glob("*.json"):
        m = json.loads(f.read_text())
        code = m["moduleCode"]
        text = f"{code} {m.get('title', '')}\n{m.get('department', '')}\n{m.get('description') or ''}"
        records.append({
            "id": code, "record_type": "module", "text": text,
            "payload": {
                "moduleCode": code, "title": m.get("title"),
                "department": m.get("department"), "moduleCredit": m.get("moduleCredit"),
            },
        })
    return records


_SYNTHETIC_FILES = [
    (PROFESSORS_FILE, "name", "bio", "research_areas"),
    (OPPORTUNITIES_FILE, "title", "description", "required_skills"),
    (COMPETITIONS_FILE, "title", "description", "skills_tested"),
    (SCHOLARSHIPS_FILE, "title", "description", None),
    (ALUMNI_FILE, "name", "story", None),
]


def load_synthetic_records() -> list[dict]:
    records = []
    for path, name_field, text_field, tag_field in _SYNTHETIC_FILES:
        for item in json.loads(path.read_text()):
            text = f"{item.get(name_field, '')}\n{item.get(text_field, '')}"
            if tag_field and item.get(tag_field):
                text += "\n" + ", ".join(item[tag_field])
            records.append({
                "id": item["id"], "record_type": item["record_type"],
                "text": text, "payload": item,
            })
    return records


def embed_bedrock(texts: list[str], prev_by_hash: dict[str, list[float]] | None = None,
                   hashes: list[str] | None = None) -> np.ndarray | None:
    try:
        from app.common import EMBED_MODEL_ID, bedrock_runtime

        client = bedrock_runtime()
    except RuntimeError as exc:
        print(f"  [no Bedrock access: {exc}] falling back to TF-IDF")
        return None

    prev_by_hash = prev_by_hash or {}
    vectors = []
    reused, called = 0, 0
    for i, text in enumerate(texts):
        h = hashes[i] if hashes else None
        if h and h in prev_by_hash:
            vectors.append(prev_by_hash[h])
            reused += 1
            continue
        body = json.dumps({"inputText": text[:8000], "dimensions": 1024, "normalize": True})
        try:
            resp = client.invoke_model(modelId=EMBED_MODEL_ID, body=body)
            payload = json.loads(resp["body"].read())
            vectors.append(payload["embedding"])
            called += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  [Bedrock embed call failed: {exc}] falling back to TF-IDF for the whole run")
            return None
    print(f"  Bedrock: {called} embedded, {reused} reused from cache")
    return np.array(vectors, dtype="float32")


def embed_tfidf(texts: list[str]) -> np.ndarray:
    from sklearn.feature_extraction.text import TfidfVectorizer

    vectorizer = TfidfVectorizer(max_features=2048, stop_words="english")
    matrix = vectorizer.fit_transform(texts).toarray().astype("float32")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    matrix = matrix / norms
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    TFIDF_VECTORIZER_FILE.write_bytes(pickle.dumps(vectorizer))
    return matrix


def main() -> None:
    records = load_module_records() + load_synthetic_records()
    if not records:
        sys.exit("No records to embed. Run fetch_nusmods.py first.")

    texts = [r["text"] for r in records]
    hashes = [_hash(r["id"], r["text"]) for r in records]

    prev_by_hash: dict[str, list[float]] = {}
    if EMBEDDINGS_META_FILE.exists() and EMBEDDINGS_FILE.exists():
        try:
            prev_meta = json.loads(EMBEDDINGS_META_FILE.read_text())
            if prev_meta.get("provider") == "bedrock":
                prev_matrix = np.load(EMBEDDINGS_FILE)
                for i, rec in enumerate(prev_meta["records"]):
                    prev_by_hash[rec["hash"]] = prev_matrix[i].tolist()
        except Exception:  # noqa: BLE001 — stale/corrupt cache is fine to ignore
            pass

    matrix = embed_bedrock(texts, prev_by_hash, hashes)
    provider = "bedrock"
    if matrix is None:
        matrix = embed_tfidf(texts)
        provider = "tfidf"

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    np.save(EMBEDDINGS_FILE, matrix)
    meta = {
        "provider": provider,
        "dimensions": matrix.shape[1],
        "records": [
            {"id": r["id"], "record_type": r["record_type"], "text": r["text"],
             "payload": r["payload"], "hash": h}
            for r, h in zip(records, hashes)
        ],
    }
    EMBEDDINGS_META_FILE.write_text(json.dumps(meta))
    print(f"{len(records)} records embedded via {provider} -> {EMBEDDINGS_FILE}")


if __name__ == "__main__":
    main()
