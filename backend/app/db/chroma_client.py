from functools import lru_cache
from pathlib import Path

import chromadb
from chromadb.config import Settings

from app.core.config import settings as app_settings


CHROMA_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "chroma"


@lru_cache(maxsize=1)
def get_chroma_client() -> chromadb.ClientAPI:
    CHROMA_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(CHROMA_DATA_DIR),
        settings=Settings(anonymized_telemetry=False),
    )


class ChromaCollections:
    CHUNKS = "chapter_chunks"
    ANCHORS = "anchor_summaries"
    ENTITIES = "entity_descriptions"


def get_or_create_collection(name: str) -> chromadb.Collection:
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )
