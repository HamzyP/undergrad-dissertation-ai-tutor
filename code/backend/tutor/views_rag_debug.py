"""
RAG pipeline debug API.

Endpoints:
  GET  /api/rag-debug/corpus/                             corpus stats + source list
  POST /api/rag-debug/query/                              run a query (optionally filtered)
  POST /api/rag-debug/sources/<type>/<id>/deactivate/    delete all chunks for a source
  POST /api/rag-debug/upload/transcript/                  upload & ingest a VTT file
  POST /api/rag-debug/sources/url/add/                   add a URL to the manifest (pending)
  POST /api/rag-debug/sources/url/ingest/                ingest all pending URL sources
"""

from __future__ import annotations

import json
import re
import statistics
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import tiktoken
from django.conf import settings
from django.http import JsonResponse
from rest_framework.decorators import api_view

from tutor.ingestion.embed import embed_and_store, embed_query, get_collection
from tutor.ingestion.transcript import chunk_vtt_file
from tutor.ingestion.url_source import fetch_and_chunk, _url_to_source_id

_enc = tiktoken.get_encoding("cl100k_base")

# Internal ChromaDB source_type for URL-sourced content (kept for DB compat)
_URL_CHROMA_TYPE = "sep"
# Display label shown in the API / frontend
_URL_DISPLAY_TYPE = "url"


def _token_count(text: str) -> int:
    return len(_enc.encode(text))


def _format_time(seconds: float) -> str:
    total = int(seconds)
    m, s = divmod(total, 60)
    return f"{m}:{s:02d}"


def _manifest_path() -> Path:
    return Path(settings.BASE_DIR) / "data" / "sep" / "sources.json"


def _load_manifest() -> list[dict]:
    path = _manifest_path()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_manifest(entries: list[dict]) -> None:
    path = _manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")


def _manifest_as_dict() -> dict[str, dict]:
    return {e["id"]: e for e in _load_manifest()}


@api_view(["GET"])
def rag_corpus(request):
    """
    GET /api/rag-debug/corpus/
    Returns corpus overview stats and per-source breakdown.
    Source type is reported as "url" for SEP/URL sources and "transcript" for transcripts.
    """
    collection = get_collection(wipe=False)
    result = collection.get(include=["documents", "metadatas"])
    all_docs: list[str] = result.get("documents") or []
    all_meta: list[dict] = result.get("metadatas") or []

    token_counts = [_token_count(doc) for doc in all_docs]
    mean_tokens = round(statistics.mean(token_counts), 1) if token_counts else 0
    median_tokens = round(statistics.median(token_counts), 1) if token_counts else 0

    url_count = sum(1 for m in all_meta if m.get("source_type") == _URL_CHROMA_TYPE)
    transcript_count = sum(1 for m in all_meta if m.get("source_type") == "transcript")

    manifest = _manifest_as_dict()

    # chunk counts per (chroma_type, source_id)
    source_chunk_counts: dict[tuple[str, str], int] = {}
    for m in all_meta:
        key = (m.get("source_type", "unknown"), m.get("source_id", "unknown"))
        source_chunk_counts[key] = source_chunk_counts.get(key, 0) + 1

    sources = []
    seen: set[tuple[str, str]] = set()

    # All manifest entries (may be pending with 0 chunks)
    for sid, entry in manifest.items():
        seen.add((_URL_CHROMA_TYPE, sid))
        chunk_count = source_chunk_counts.get((_URL_CHROMA_TYPE, sid), 0)
        sources.append({
            "source_id": sid,
            "source_type": _URL_DISPLAY_TYPE,
            "display_name": entry.get("title", sid),
            "url": entry.get("url", ""),
            "chunk_count": chunk_count,
            "accessed": entry.get("accessed", ""),
            "active": chunk_count > 0,
            "ingested": chunk_count > 0,
        })

    # Transcript sources discovered in ChromaDB
    transcript_dir = Path(settings.BASE_DIR) / "data" / "sep" / "transcripts"
    for m in all_meta:
        if m.get("source_type") != "transcript":
            continue
        sid = m.get("source_id", "unknown")
        if ("transcript", sid) in seen:
            continue
        seen.add(("transcript", sid))
        chunk_count = source_chunk_counts.get(("transcript", sid), 0)
        vtt_exists = (transcript_dir / f"{sid}.vtt").exists()
        sources.append({
            "source_id": sid,
            "source_type": "transcript",
            "display_name": m.get("topic", sid),
            "url": f"/api/rag-debug/transcripts/{sid}.vtt" if vtt_exists else "",
            "chunk_count": chunk_count,
            "accessed": "",
            "active": chunk_count > 0,
            "ingested": chunk_count > 0,
        })

    return JsonResponse({
        "total_chunks": len(all_docs),
        "url_count": url_count,
        "transcript_count": transcript_count,
        "mean_tokens": mean_tokens,
        "median_tokens": median_tokens,
        "sources": sources,
    })


@api_view(["POST"])
def rag_query(request):
    """
    POST /api/rag-debug/query/
    Body: {
        "query": "...",
        "source_type": "url" | "transcript" | null,
        "source_id": "..." | null
    }
    """
    query_text = (request.data.get("query") or "").strip()
    if not query_text:
        return JsonResponse({"error": "query is required."}, status=400)

    display_type_filter = (request.data.get("source_type") or "").strip() or None
    source_id_filter = (request.data.get("source_id") or "").strip() or None

    # Map the display type back to the chroma type
    chroma_type_filter: str | None = None
    if display_type_filter == _URL_DISPLAY_TYPE:
        chroma_type_filter = _URL_CHROMA_TYPE
    elif display_type_filter == "transcript":
        chroma_type_filter = "transcript"

    where: dict | None = None
    if source_id_filter and chroma_type_filter:
        where = {"$and": [
            {"source_type": {"$eq": chroma_type_filter}},
            {"source_id": {"$eq": source_id_filter}},
        ]}
    elif chroma_type_filter:
        where = {"source_type": {"$eq": chroma_type_filter}}

    try:
        embedding = embed_query(query_text)
        collection = get_collection(wipe=False)
        query_kwargs: dict = {
            "query_embeddings": [embedding],
            "n_results": 5,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            query_kwargs["where"] = where
        raw = collection.query(**query_kwargs)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=502)

    docs = (raw.get("documents") or [[]])[0]
    metas = (raw.get("metadatas") or [[]])[0]
    dists = (raw.get("distances") or [[]])[0]

    results = []
    for rank, (doc, meta, dist) in enumerate(zip(docs, metas, dists), start=1):
        chroma_type = meta.get("source_type", "")
        display_type = _URL_DISPLAY_TYPE if chroma_type == _URL_CHROMA_TYPE else chroma_type

        if chroma_type == _URL_CHROMA_TYPE:
            section = meta.get("section", "")
            sub = meta.get("subsection", "")
            location = f"{section} › {sub}" if sub else section
        else:
            start = meta.get("start_time")
            end = meta.get("end_time")
            location = (
                f"{_format_time(start)}–{_format_time(end)}"
                if start is not None and end is not None
                else ""
            )

        results.append({
            "rank": rank,
            "distance": round(dist, 4),
            "source_id": meta.get("source_id", ""),
            "source_type": display_type,
            "location": location,
            "text": doc,
        })

    return JsonResponse({"results": results})


@api_view(["POST"])
def rag_source_deactivate(request, source_type: str, source_id: str):
    """
    POST /api/rag-debug/sources/<source_type>/<source_id>/deactivate/
    Removes all chunks for the given source from ChromaDB.
    Accepts source_type as "url" or "transcript" (display values).
    """
    if source_type not in (_URL_DISPLAY_TYPE, "transcript"):
        return JsonResponse({"error": "source_type must be 'url' or 'transcript'."}, status=400)

    chroma_type = _URL_CHROMA_TYPE if source_type == _URL_DISPLAY_TYPE else "transcript"

    try:
        collection = get_collection(wipe=False)
        existing = collection.get(
            where={"$and": [
                {"source_type": {"$eq": chroma_type}},
                {"source_id": {"$eq": source_id}},
            ]},
            include=[],
        )
        ids_to_delete = existing.get("ids") or []
        if not ids_to_delete:
            return JsonResponse({"deleted": 0, "message": "No chunks found for this source."})
        collection.delete(ids=ids_to_delete)
        return JsonResponse({"deleted": len(ids_to_delete)})
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=502)


@api_view(["DELETE"])
def rag_source_delete(request, source_type: str, source_id: str):
    """
    DELETE /api/rag-debug/sources/<source_type>/<source_id>/
    Removes all chunks from ChromaDB AND deletes the backing file/manifest entry.
    """
    if source_type not in (_URL_DISPLAY_TYPE, "transcript"):
        return JsonResponse({"error": "source_type must be 'url' or 'transcript'."}, status=400)

    chroma_type = _URL_CHROMA_TYPE if source_type == _URL_DISPLAY_TYPE else "transcript"

    # Remove chunks from ChromaDB
    chunks_deleted = 0
    try:
        collection = get_collection(wipe=False)
        existing = collection.get(
            where={"$and": [
                {"source_type": {"$eq": chroma_type}},
                {"source_id": {"$eq": source_id}},
            ]},
            include=[],
        )
        ids_to_delete = existing.get("ids") or []
        if ids_to_delete:
            collection.delete(ids=ids_to_delete)
            chunks_deleted = len(ids_to_delete)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=502)

    # Remove backing file / manifest entry
    if source_type == _URL_DISPLAY_TYPE:
        entries = _load_manifest()
        entries = [e for e in entries if e["id"] != source_id]
        _save_manifest(entries)
        # Also delete cached HTML file if present
        sep_dir = Path(settings.BASE_DIR) / "data" / "sep"
        for ext in (".html", ".htm"):
            candidate = sep_dir / f"{source_id}{ext}"
            candidate.unlink(missing_ok=True)
    else:
        transcript_dir = Path(settings.BASE_DIR) / "data" / "sep" / "transcripts"
        vtt_path = transcript_dir / f"{source_id}.vtt"
        vtt_path.unlink(missing_ok=True)

    return JsonResponse({"deleted_chunks": chunks_deleted})


@api_view(["POST"])
def rag_upload_transcript(request):
    """
    POST /api/rag-debug/upload/transcript/
    Multipart form: file=<.vtt file>
    """
    uploaded = request.FILES.get("file")
    if not uploaded:
        return JsonResponse({"error": "No file provided. Send as multipart field 'file'."}, status=400)

    filename = uploaded.name or "upload.vtt"
    if not filename.lower().endswith(".vtt"):
        return JsonResponse({"error": "Only .vtt files are accepted."}, status=400)

    transcript_dir = Path(settings.BASE_DIR) / "data" / "sep" / "transcripts"
    transcript_dir.mkdir(parents=True, exist_ok=True)
    dest_path = transcript_dir / filename

    with open(dest_path, "wb") as f:
        for chunk in uploaded.chunks():
            f.write(chunk)

    try:
        chunks = chunk_vtt_file(dest_path)
    except Exception as exc:
        dest_path.unlink(missing_ok=True)
        return JsonResponse({"error": f"Failed to parse VTT file: {exc}"}, status=400)

    if not chunks:
        dest_path.unlink(missing_ok=True)
        return JsonResponse({"error": "VTT file produced no chunks. Check that the file has content."}, status=400)

    try:
        collection = get_collection(wipe=False)
        source_id = dest_path.stem
        existing = collection.get(
            where={"$and": [
                {"source_type": {"$eq": "transcript"}},
                {"source_id": {"$eq": source_id}},
            ]},
            include=[],
        )
        old_ids = existing.get("ids") or []
        if old_ids:
            collection.delete(ids=old_ids)
        embed_and_store(chunks, collection)
    except Exception as exc:
        return JsonResponse({"error": f"Embedding failed: {exc}"}, status=502)

    return JsonResponse({"source_id": dest_path.stem, "chunks_stored": len(chunks)})


@api_view(["GET"])
def rag_transcript_download(request, filename: str):
    """
    GET /api/rag-debug/transcripts/<filename>.vtt
    Serves the raw VTT file for download/preview.
    """
    from django.http import FileResponse, Http404

    if not filename.endswith(".vtt") or "/" in filename or "\\" in filename:
        raise Http404

    transcript_dir = Path(settings.BASE_DIR) / "data" / "sep" / "transcripts"
    path = transcript_dir / filename
    if not path.exists():
        raise Http404

    return FileResponse(open(path, "rb"), content_type="text/vtt", filename=filename)


@api_view(["POST"])
def rag_add_url(request):
    """
    POST /api/rag-debug/sources/url/add/
    Body: { "url": "https://...", "title": "optional title" }
    Adds the URL to sources.json as a pending entry (not yet ingested).
    """
    url = (request.data.get("url") or "").strip()
    if not url:
        return JsonResponse({"error": "url is required."}, status=400)

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return JsonResponse({"error": "url must start with http:// or https://"}, status=400)

    title = (request.data.get("title") or "").strip()
    source_id = _url_to_source_id(url)

    entries = _load_manifest()
    existing_ids = {e["id"] for e in entries}
    if source_id in existing_ids:
        return JsonResponse({"error": f"A source with id '{source_id}' already exists."}, status=409)

    entry = {
        "id": source_id,
        "url": url,
        "title": title or source_id,
        "file": "",
        "accessed": "",
    }
    entries.append(entry)
    _save_manifest(entries)

    return JsonResponse({"source_id": source_id, "title": entry["title"]}, status=201)


@api_view(["POST"])
def rag_ingest_pending(request):
    """
    POST /api/rag-debug/sources/url/ingest/
    Fetches and embeds all manifest entries that have no chunks in ChromaDB yet.
    Streams a summary back on completion.
    """
    collection = get_collection(wipe=False)
    manifest = _load_manifest()

    # Find which source_ids already have chunks
    result = collection.get(include=["metadatas"])
    all_meta: list[dict] = result.get("metadatas") or []
    ingested_ids = {m["source_id"] for m in all_meta if m.get("source_type") == _URL_CHROMA_TYPE}

    pending = [e for e in manifest if e["id"] not in ingested_ids and e.get("url")]
    if not pending:
        return JsonResponse({"ingested": [], "errors": [], "message": "Nothing pending."})

    ingested = []
    errors = []
    today = date.today().isoformat()

    for entry in pending:
        sid = entry["id"]
        url = entry["url"]
        title = entry.get("title", sid)
        try:
            chunks = fetch_and_chunk(url, sid, title)
            if not chunks:
                errors.append({"source_id": sid, "error": "No content extracted from page."})
                continue
            # Update title from page if we didn't have one
            if not entry.get("title") or entry["title"] == sid:
                fetched_title = chunks[0]["metadata"].get("title", "") if chunks else ""
                if fetched_title:
                    entry["title"] = fetched_title
            entry["accessed"] = today
            embed_and_store(chunks, collection)
            ingested.append({"source_id": sid, "chunks": len(chunks)})
        except Exception as exc:
            errors.append({"source_id": sid, "error": str(exc)})

    # Persist updated titles / accessed dates back to manifest
    _save_manifest(manifest)

    return JsonResponse({"ingested": ingested, "errors": errors})
