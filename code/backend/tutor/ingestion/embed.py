"""
Ollama embedding client and ChromaDB storage.
"""

from __future__ import annotations

import json
import logging
import math
import threading
from urllib.request import Request, urlopen

import chromadb
from django.conf import settings

COLLECTION_NAME = "tutor_corpus"
BATCH_SIZE = 64
PROGRESS_EVERY = 10

_collection_lock = threading.Lock()
_cached_client = None
_cached_collection = None
_cached_chroma_dir = None
_warmup_started = False

logger = logging.getLogger(__name__)


def _debug_log(message: str, *args) -> None:
    if getattr(settings, "TUTOR_DEBUG_LOGS", False):
        logger.warning(message, *args)


def _get_settings() -> tuple[str, str, str]:
    base_url: str = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
    embed_model: str = getattr(settings, "OLLAMA_EMBED_MODEL", "nomic-embed-text")
    chroma_dir: str = str(getattr(settings, "CHROMA_PERSIST_DIR", settings.BASE_DIR / "data" / "chroma"))
    return base_url, embed_model, chroma_dir


def _l2_normalise(vector: list[float]) -> list[float]:
    """Return the L2-normalised vector. Returns the original on zero-vector."""
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0.0:
        return vector
    return [x / norm for x in vector]


def _embed_raw(text: str, base_url: str, model: str) -> list[float]:
    """Call Ollama's /api/embeddings endpoint and return the L2-normalised vector."""
    payload = json.dumps({"model": model, "prompt": text, "keep_alive": "24h"}).encode("utf-8")
    req = Request(
        f"{base_url}/api/embeddings",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return _l2_normalise(data["embedding"])


def embed_query(text: str) -> list[float]:
    """
    Embed a retrieval query using the nomic-embed-text query prefix.
    Use this at query time in the retrieval endpoint.

    Normalisation applied before embedding (not to documents):
      - strip leading/trailing whitespace
      - strip trailing question marks
      - lowercase
    This aligns query vectors with SEP document vectors, which use
    lowercase conventions for most philosophical terms.
    """
    normalised = text.strip().rstrip("?").lower()
    base_url, embed_model, _ = _get_settings()
    return _embed_raw(f"search_query: {normalised}", base_url, embed_model)


def get_collection(wipe: bool = False):
    """
    Return (and optionally wipe) the ChromaDB collection.
    Creates the persistent directory if it doesn't exist.
    """
    global _cached_client, _cached_collection, _cached_chroma_dir

    _, _, chroma_dir = _get_settings()
    import pathlib
    pathlib.Path(chroma_dir).mkdir(parents=True, exist_ok=True)

    _debug_log("[chroma] get_collection called wipe=%s dir=%s", wipe, chroma_dir)
    with _collection_lock:
        _debug_log("[chroma] collection lock acquired")
        # Reuse a single in-process PersistentClient. On Windows, repeatedly
        # constructing new persistent clients during live HTTP requests can
        # stall around local DB/file initialization even though the same code
        # works fine in one-off scripts.
        if (
            not wipe
            and _cached_client is not None
            and _cached_collection is not None
            and _cached_chroma_dir == chroma_dir
        ):
            _debug_log("[chroma] returning cached collection")
            return _cached_collection

        _debug_log("[chroma] creating PersistentClient")
        client = chromadb.PersistentClient(path=chroma_dir)
        _debug_log("[chroma] PersistentClient created")

        if wipe:
            try:
                client.delete_collection(COLLECTION_NAME)
            except Exception:
                pass

        _debug_log("[chroma] get_or_create_collection starting")
        collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        _debug_log("[chroma] get_or_create_collection completed")

        _cached_client = client
        _cached_collection = collection
        _cached_chroma_dir = chroma_dir
        _debug_log("[chroma] collection cached and returned")
        return collection


def warm_collection_async() -> None:
    """Start a one-time background warm-up of the persistent Chroma collection.

    This avoids making the student's first chat message pay the full Windows
    `PersistentClient(...)` startup cost.
    """
    global _warmup_started

    with _collection_lock:
        if _cached_collection is not None:
            _debug_log("[chroma] warm-up skipped; collection already cached")
            return
        if _warmup_started:
            _debug_log("[chroma] warm-up already in progress")
            return
        _warmup_started = True

    def _warm():
        global _warmup_started
        try:
            _debug_log("[chroma] async warm-up starting")
            get_collection(wipe=False)
            _debug_log("[chroma] async warm-up completed")
        except Exception:
            logger.exception("Asynchronous Chroma warm-up failed")
        finally:
            with _collection_lock:
                _warmup_started = False

    threading.Thread(target=_warm, daemon=True, name="chroma-warmup").start()


def embed_and_store(chunks: list[dict], collection) -> int:
    """
    Embed each chunk via Ollama and add to the Chroma collection in batches.
    Returns the total number of chunks stored.
    """
    base_url, embed_model, _ = _get_settings()
    total = len(chunks)

    ids: list[str] = []
    embeddings: list[list[float]] = []
    documents: list[str] = []
    metadatas: list[dict] = []

    for n, chunk in enumerate(chunks, start=1):
        source_id = chunk["metadata"]["source_id"]
        chunk_index = chunk["metadata"]["chunk_index"]
        source_type = chunk["metadata"].get("source_type", "chunk")
        doc_id = f"{source_type}-{source_id}-{chunk_index}"

        if n % PROGRESS_EVERY == 0 or n == 1 or n == total:
            print(f"  Embedding [{source_id}] chunk {n}/{total}")

        # Prefix for nomic-embed-text asymmetric embedding; store original prose
        embedding = _embed_raw(f"search_document: {chunk['text']}", base_url, embed_model)

        ids.append(doc_id)
        embeddings.append(embedding)
        documents.append(chunk["text"])  # original text, no prefix
        metadatas.append(chunk["metadata"])

        # Flush batch
        if len(ids) >= BATCH_SIZE:
            collection.add(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)
            ids, embeddings, documents, metadatas = [], [], [], []

    # Flush remaining
    if ids:
        collection.add(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)

    return total
