"""
Ingestion pipeline orchestrator.

Calls both chunkers, then embeds and stores everything in ChromaDB.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings

from .embed import embed_and_store, get_collection
from .sep import chunk_all_sep
from .transcript import chunk_all_transcripts


def run_ingestion(wipe: bool = True) -> dict:
    """
    Run the full ingestion pipeline.

    Returns:
        {
            "sep_chunks": int,
            "transcript_chunks": int,
            "total_stored": int,
            "sources": {source_id: chunk_count, ...},
        }
    """
    data_dir: Path = settings.BASE_DIR / "data"

    print("Chunking SEP articles...")
    sep_chunks = chunk_all_sep(data_dir)

    print("Chunking transcripts...")
    transcript_chunks = chunk_all_transcripts(data_dir)

    all_chunks = sep_chunks + transcript_chunks

    print(f"\nTotal chunks to embed: {len(all_chunks)}")
    print("Connecting to ChromaDB...")
    collection = get_collection(wipe=wipe)

    print("Embedding and storing chunks...")
    total_stored = embed_and_store(all_chunks, collection)

    # Build per-source counts keyed as "source_type:source_id"
    sources: dict[str, int] = {}
    for chunk in all_chunks:
        sid = chunk["metadata"]["source_id"]
        stype = chunk["metadata"].get("source_type", "unknown")
        key = f"{stype}:{sid}"
        sources[key] = sources.get(key, 0) + 1

    return {
        "sep_chunks": len(sep_chunks),
        "transcript_chunks": len(transcript_chunks),
        "total_stored": total_stored,
        "sources": sources,
    }
