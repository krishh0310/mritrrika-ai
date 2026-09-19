"""Vector search over approved records, in pgvector (§10).

What is indexed: one row per parcel whose record is APPROVED, built from the
same public fields record search returns -- place, khasra, khata, area, land
class -- plus the kinds of mutation and record the parcel has. Owner names are
NOT embedded: ranking by similarity to a name would answer "which plot does
this person hold" through the order of results alone.

Two vector providers, and a query only ever compares against vectors from the
same one (the `model_version` column):

  * `gemini`  -- text-embedding-004. Semantic: "irrigated land" finds सिंचित.
  * `ngram`   -- the default. Character trigrams hashed into the same 768
                 dimensions, stdlib only. Not semantic: it matches by shared
                 spelling, which is still useful for OCR-mangled and
                 transliterated names, and it works offline and in tests.
"""

from __future__ import annotations

import hashlib
import math
import unicodedata

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.models import Embedding, LandRecord, Location, Mutation, Parcel

ENTITY = "parcel"
NGRAM_VERSION = "ngram-v1"


def _ngram_vector(text: str, dim: int) -> list[float]:
    text = f"  {unicodedata.normalize('NFC', text.lower())}  "
    vector = [0.0] * dim
    for i in range(len(text) - 2):
        bucket = int.from_bytes(hashlib.blake2b(text[i:i + 3].encode(), digest_size=8).digest())
        vector[bucket % dim] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


def _gemini_vectors(texts: list[str], settings) -> list[list[float]]:
    import httpx

    model = settings.gemini_embedding_model
    response = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents",
        headers={"x-goog-api-key": settings.gemini_api_key},
        json={"requests": [
            {"model": f"models/{model}", "content": {"parts": [{"text": t}]}} for t in texts
        ]},
        timeout=60,
    )
    response.raise_for_status()
    return [e["values"] for e in response.json()["embeddings"]]


def embed(texts: list[str]) -> tuple[list[list[float]], str]:
    """Vectors for `texts`, and the model version that made them."""
    settings = get_settings()
    if settings.embedding_provider == "gemini" and settings.gemini_api_key:
        return _gemini_vectors(texts, settings), settings.gemini_embedding_model
    return [_ngram_vector(t, settings.embedding_dim) for t in texts], NGRAM_VERSION


def content_for(session: Session, parcel: Parcel) -> str:
    places, node = [], session.get(Location, parcel.village_id)
    while node is not None:
        places.append(f"{node.name} {node.name_devanagari or ''}".strip())
        node = session.get(Location, node.parent_id) if node.parent_id else None
    mutations = sorted({m for m in session.execute(
        select(Mutation.mutation_type).where(Mutation.parcel_id == parcel.id)
    ).scalars()})
    records = sorted({f"{t} {y}" for t, y in session.execute(
        select(LandRecord.document_type, LandRecord.record_year)
        .where(LandRecord.parcel_id == parcel.id)
    ).all()})
    return " | ".join(filter(None, [
        ", ".join(places),
        f"khasra {parcel.khasra_number}",
        f"khata {parcel.khata_number}" if parcel.khata_number else "",
        f"area {parcel.area_value:g} {parcel.area_unit}",
        f"land class {parcel.land_class}" if parcel.land_class else "",
        f"mutations {', '.join(mutations)}" if mutations else "",
        f"records {', '.join(records)}" if records else "",
    ]))


def index_parcels(session: Session, parcels: list[Parcel]) -> int:
    """(Re)index these parcels. Replaces their rows; does not commit."""
    if not parcels:
        return 0
    contents = [content_for(session, p) for p in parcels]
    vectors, version = embed(contents)
    session.execute(delete(Embedding).where(
        Embedding.entity_type == ENTITY, Embedding.parcel_id.in_([p.id for p in parcels])
    ))
    session.add_all([
        Embedding(entity_type=ENTITY, entity_id=p.external_id, parcel_id=p.id,
                  village_id=p.village_id, content=text, embedding=vector,
                  model_version=version)
        for p, text, vector in zip(parcels, contents, vectors, strict=True)
    ])
    return len(parcels)


def reindex_approved(session: Session) -> int:
    parcels = session.execute(
        select(Parcel).join(LandRecord, LandRecord.parcel_id == Parcel.id)
        .where(LandRecord.status == "APPROVED").distinct()
    ).scalars().all()
    count = index_parcels(session, list(parcels))
    session.commit()
    return count


def search(session: Session, query: str, limit: int = 10) -> list[dict]:
    """Approved parcels nearest to `query`, with the public fields only."""
    [vector], version = embed([query])
    distance = Embedding.embedding.cosine_distance(vector)
    rows = session.execute(
        select(Parcel, Location, distance.label("distance"))
        .join(Embedding, Embedding.parcel_id == Parcel.id)
        .join(Location, Location.id == Parcel.village_id)
        .join(LandRecord, LandRecord.parcel_id == Parcel.id)
        .where(Embedding.entity_type == ENTITY, Embedding.model_version == version,
               LandRecord.status == "APPROVED")
        .distinct()
        .order_by(distance)
        .limit(limit)
    ).all()
    return [
        {
            "parcel_id": parcel.external_id,
            "khasra_number": parcel.khasra_number,
            "khata_number": parcel.khata_number,
            "village": village.name_devanagari or village.name,
            "village_id": village.external_id,
            "area_value": parcel.area_value,
            "area_unit": parcel.area_unit,
            "land_class": parcel.land_class,
            "similarity": round(1 - float(d), 4),
            "is_synthetic": parcel.is_synthetic,
        }
        for parcel, village, d in rows
    ]
