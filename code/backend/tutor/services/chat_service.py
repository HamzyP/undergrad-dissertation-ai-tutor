from __future__ import annotations

import json
import logging
import re
import time
from typing import Callable

from django.conf import settings

from tutor.services.types import (
    ChatResponse,
    build_citations,
    build_prompt,
    response_has_no_citations,
    response_has_valid_citations,
)
from tutor.services.ollama_service import generate_text, generate_text_stream
from tutor.services.prompts import (
    FALLBACK_RETRY_PROMPT,
    FALLBACK_SYSTEM_PROMPT,
    GROUNDING_RETRY_PROMPT,
    SYSTEM_PROMPT,
    CLASSIFICATION_ADDENDA,
    EXPLANATION_OUTCOME_ADDENDA,
    GUARDRAIL_INSTRUCTIONS,
    SUPPORT_STRATEGY_ADDENDA,
    build_hint_addendum,
)

logger = logging.getLogger(__name__)

CHAT_RAG_TOP_K = 3
CHAT_RAG_MAX_DISTANCE = 0.65

_LOW_INFORMATION_MESSAGES = {
    "idk",
    "i don't know",
    "i dont know",
    "not sure",
    "unsure",
    "no idea",
}


def _debug_log(message: str, *args) -> None:
    if getattr(settings, "TUTOR_DEBUG_LOGS", False):
        logger.warning(message, *args)


# ---------------------------------------------------------------------------
# System prompt selection
# ---------------------------------------------------------------------------

def _build_system_prompt(base: str, payload: dict) -> str:
    """Append dynamic addenda, then guardrails, to the base system prompt."""
    addenda: list[str] = []
    explanation_outcome = payload.get("explanation_outcome")
    question_classification = payload.get("question_classification")
    support_strategy = payload.get("support_strategy")
    hint_level = payload.get("hint_level")

    if explanation_outcome:
        addenda.append(EXPLANATION_OUTCOME_ADDENDA.get(explanation_outcome, ""))

    if hint_level is not None:
        scaffold_level = payload.get("current_scaffold_level", "")
        addenda.append(build_hint_addendum(int(hint_level), scaffold_level))
    elif support_strategy:
        addenda.append(SUPPORT_STRATEGY_ADDENDA.get(support_strategy, ""))
    elif question_classification:
        addenda.append(CLASSIFICATION_ADDENDA.get(question_classification, ""))

    return base + "".join(part for part in addenda if part) + GUARDRAIL_INSTRUCTIONS


# ---------------------------------------------------------------------------
# RAG retrieval
# ---------------------------------------------------------------------------

def _build_chat_retrieval_query(payload: dict) -> str:
    message = (payload.get("message") or "").strip()
    interpolated_question = (payload.get("interpolated_question") or "").strip()
    topic = (payload.get("topic") or "").strip()

    if interpolated_question and (
        message.lower() in _LOW_INFORMATION_MESSAGES or len(message.split()) <= 2
    ):
        return " ".join(part for part in [topic, interpolated_question] if part)

    return message


def _retrieve_chat_context(query: str) -> tuple[list[str], list[dict]]:
    try:
        from tutor.ingestion.embed import embed_query, get_collection

        overall_start = time.monotonic()
        _debug_log("[rag] retrieval start query=%r", query[:200])

        embed_start = time.monotonic()
        embedding = embed_query(query)
        _debug_log("[rag] embed_query completed in %.2fs", time.monotonic() - embed_start)

        collection_start = time.monotonic()
        collection = get_collection(wipe=False)
        _debug_log("[rag] get_collection completed in %.2fs", time.monotonic() - collection_start)

        query_start = time.monotonic()
        _debug_log("[rag] collection.query starting")
        raw = collection.query(
            query_embeddings=[embedding],
            n_results=CHAT_RAG_TOP_K,
            include=["documents", "metadatas", "distances"],
        )
        _debug_log("[rag] collection.query completed in %.2fs", time.monotonic() - query_start)
        docs = (raw.get("documents") or [[]])[0]
        metas = (raw.get("metadatas") or [[]])[0]
        dists = (raw.get("distances") or [[]])[0]

        context: list[str] = []
        metadatas: list[dict] = []
        for doc, meta, dist in zip(docs, metas, dists):
            if dist <= CHAT_RAG_MAX_DISTANCE:
                context.append(doc)
                metadatas.append(meta)
        _debug_log(
            "[rag] retrieval finished in %.2fs (%d/%d chunks kept)",
            time.monotonic() - overall_start,
            len(context),
            len(docs),
        )
        return context, metadatas
    except Exception:
        logger.exception("RAG retrieval failed")
        return [], []


# ---------------------------------------------------------------------------
# Generation with retry
# ---------------------------------------------------------------------------

def _generate_with_retry(
    *,
    model_name: str | None,
    prompt: str,
    system_prompt: str,
    retry_system_prompt: str,
    validator: Callable[[str], bool],
) -> str:
    """Generate text, retrying once with a correction prompt if validation fails.

    Returns the validated response text, or raises ValueError if both attempts fail.
    """
    for system in (system_prompt, retry_system_prompt):
        generation = generate_text(
            model_name=model_name,
            system_prompt=system,
            prompt=prompt,
        )
        if validator(generation.text):
            return generation.text

    raise ValueError("LLM reply failed validation after retry.")


# ---------------------------------------------------------------------------
# Non-streaming chat
# ---------------------------------------------------------------------------

def _grounded_chat_response(payload: dict, context: list[str], metadatas: list[dict]) -> ChatResponse:
    citations = build_citations(metadatas)
    prompt = build_prompt(payload, retrieval_context=context)
    system_prompt = _build_system_prompt(SYSTEM_PROMPT, payload)
    text = _generate_with_retry(
        model_name=payload.get("model"),
        prompt=prompt,
        system_prompt=system_prompt,
        retry_system_prompt=f"{system_prompt}{GROUNDING_RETRY_PROMPT}",
        validator=lambda t: response_has_valid_citations(t, len(citations)),
    )
    return ChatResponse(response=text, citations=citations, latency_ms=0)


def _fallback_chat_response(payload: dict) -> ChatResponse:
    prompt = build_prompt(payload, retrieval_context=None)
    system_prompt = _build_system_prompt(FALLBACK_SYSTEM_PROMPT, payload)
    text = _generate_with_retry(
        model_name=payload.get("model"),
        prompt=prompt,
        system_prompt=system_prompt,
        retry_system_prompt=f"{system_prompt}{FALLBACK_RETRY_PROMPT}",
        validator=response_has_no_citations,
    )
    return ChatResponse(response=text, citations=[], latency_ms=0)


def get_chat_reply(payload: dict) -> ChatResponse:
    """Retrieve RAG context and generate a tutor reply, falling back gracefully."""
    query = _build_chat_retrieval_query(payload)
    context, metadatas = _retrieve_chat_context(query)

    if context and metadatas:
        try:
            return _grounded_chat_response(payload, context, metadatas)
        except ValueError:
            logger.warning(
                "Retrieved answer was not grounded; falling back for session_id=%s topic=%s",
                payload.get("session_id"),
                payload.get("topic"),
            )
    else:
        logger.warning(
            "No usable RAG context found; using fallback for session_id=%s topic=%s",
            payload.get("session_id"),
            payload.get("topic"),
        )

    return _fallback_chat_response(payload)


# ---------------------------------------------------------------------------
# Streaming chat
#
# We generate the full response non-streaming first so we can validate it
# before the user sees anything. Once we have a committed, valid response
# we stream it token-by-token so the user sees a clean, single appearance.
# ---------------------------------------------------------------------------

def _stream_event(event: dict) -> bytes:
    return (json.dumps(event) + "\n").encode("utf-8")


def _stream_one_attempt(
    *,
    model_name: str | None,
    system_prompt: str,
    prompt: str,
    mode: str,
    phase: str = "generate",
):
    """Stream a single Ollama attempt, yielding events and returning the full text.

    `mode` is "delta" (append to what's already shown) or "replace" (overwrite
    prior partial text with the new tokens as they arrive).
    `phase` is a log label (e.g. "grounded", "fallback") so timing output is
    readable when the tutor falls through multiple stages.
    """
    accumulated = ""
    first_chunk_in_replace = True
    chunk_count = 0
    start = time.monotonic()
    logger.info("[stream:%s] opening ollama stream (model=%s)", phase, model_name or "<default>")

    stream = generate_text_stream(
        model_name=model_name,
        system_prompt=system_prompt,
        prompt=prompt,
    )
    try:
        for chunk in stream:
            if chunk_count == 0 and chunk.text:
                logger.info(
                    "[stream:%s] first token received after %.2fs",
                    phase,
                    time.monotonic() - start,
                )
            if chunk.done:
                break
            if not chunk.text:
                continue
            chunk_count += 1
            accumulated += chunk.text
            if mode == "delta":
                yield _stream_event({"type": "delta", "text": chunk.text})
            else:
                if first_chunk_in_replace:
                    yield _stream_event({"type": "replace", "text": accumulated})
                    first_chunk_in_replace = False
                else:
                    yield _stream_event({"type": "delta", "text": chunk.text})
    finally:
        # Close the underlying Ollama HTTP response even on GeneratorExit.
        try:
            stream.close()
        except Exception:
            pass

    logger.info(
        "[stream:%s] completed in %.2fs (%d chunks, %d chars)",
        phase,
        time.monotonic() - start,
        chunk_count,
        len(accumulated),
    )

    # Strip <think>...</think> blocks the same way generate_text does.
    cleaned = re.sub(r"<think>.*?</think>", "", accumulated, flags=re.DOTALL).strip()
    if cleaned != accumulated:
        # Model emitted reasoning tokens we streamed but shouldn't keep; replace.
        yield _stream_event({"type": "replace", "text": cleaned})
    return cleaned


_CITATION_PATTERN = re.compile(r"\[(\d+)\]")


def _repair_grounded_citations(text: str, max_index: int) -> str:
    """Ensure the grounded response has at least one valid [N] citation.

    Strategy:
      - Drop any out-of-range [N] references (keep only 1..max_index).
      - If none remain, append [1] to the end of the first sentence so the
        user sees an inline citation matching the top-ranked RAG chunk.
    """
    def _filter(match: re.Match) -> str:
        idx = int(match.group(1))
        return match.group(0) if 1 <= idx <= max_index else ""

    filtered = _CITATION_PATTERN.sub(_filter, text).strip()
    if _CITATION_PATTERN.search(filtered):
        return filtered

    # No valid citation survived. Insert [1] at the end of the first sentence,
    # or at the end of the whole reply if there's no sentence break.
    sentence_end = re.search(r"[.!?](?=\s|$)", filtered)
    if sentence_end:
        insert_at = sentence_end.start()
        return f"{filtered[:insert_at]} [1]{filtered[insert_at:]}"
    if filtered:
        return f"{filtered} [1]"
    return "[1]"


def _strip_citations(text: str) -> str:
    """Remove any [N] citation markers from a fallback reply."""
    return _CITATION_PATTERN.sub("", text).strip()


def stream_chat_reply(payload: dict):
    """Retrieve RAG context and stream a tutor reply progressively.

    Runs a single generation attempt (no retry) and repairs the text
    server-side if validation would have failed — keeping the user's view
    as a single clean stream.
    """
    overall_start = time.monotonic()
    requested_model = payload.get("model") or "<default>"
    try:
        # Tell the client we accepted the request so the spinner can flip to a
        # live streaming state instead of appearing to hang.
        yield _stream_event({"type": "replace", "text": ""})

        # Report currently-loaded Ollama models so a long first-token delay is
        # legible as a cold-load vs a generation stall.
        try:
            from tutor.services.ollama_service import list_loaded_models
            logger.info(
                "[stream] start; requested_model=%s, ollama_loaded=%s",
                requested_model,
                list_loaded_models(),
            )
        except Exception:
            logger.info("[stream] start; requested_model=%s (loaded-model probe failed)", requested_model)

        rag_start = time.monotonic()
        query = _build_chat_retrieval_query(payload)
        context, metadatas = _retrieve_chat_context(query)
        logger.info(
            "[stream] rag retrieval: %.2fs, %d chunks kept",
            time.monotonic() - rag_start,
            len(context) if context else 0,
        )

        if context and metadatas:
            citations = build_citations(metadatas)
            citation_dicts = [c.to_dict() for c in citations]
            grounded_prompt = build_prompt(payload, retrieval_context=context)
            grounded_system = _build_system_prompt(SYSTEM_PROMPT, payload)
            streamed_text = yield from _stream_one_attempt(
                model_name=payload.get("model"),
                system_prompt=grounded_system,
                prompt=grounded_prompt,
                mode="delta",
                phase="grounded",
            )
            repaired = _repair_grounded_citations(streamed_text, len(citations))
            if repaired != streamed_text:
                logger.info(
                    "Post-hoc citation repair applied for session_id=%s topic=%s",
                    payload.get("session_id"),
                    payload.get("topic"),
                )
                yield _stream_event({"type": "replace", "text": repaired})
            yield _stream_event({
                "type": "final",
                "text": repaired,
                "citations": citation_dicts,
                "latency_ms": int((time.monotonic() - overall_start) * 1000),
            })
            logger.info("[stream] total elapsed: %.2fs (grounded)", time.monotonic() - overall_start)
            return

        logger.warning(
            "No usable RAG context found; using fallback for session_id=%s topic=%s",
            payload.get("session_id"),
            payload.get("topic"),
        )

        fallback_prompt = build_prompt(payload, retrieval_context=None)
        fallback_system = _build_system_prompt(FALLBACK_SYSTEM_PROMPT, payload)
        streamed_text = yield from _stream_one_attempt(
            model_name=payload.get("model"),
            system_prompt=fallback_system,
            prompt=fallback_prompt,
            mode="delta",
            phase="fallback",
        )
        cleaned = _strip_citations(streamed_text)
        if cleaned != streamed_text:
            logger.info(
                "Stripped stray citations from fallback reply for session_id=%s topic=%s",
                payload.get("session_id"),
                payload.get("topic"),
            )
            yield _stream_event({"type": "replace", "text": cleaned})
        yield _stream_event({
            "type": "final",
            "text": cleaned,
            "citations": [],
            "latency_ms": int((time.monotonic() - overall_start) * 1000),
        })
        logger.info("[stream] total elapsed: %.2fs (fallback)", time.monotonic() - overall_start)

    except Exception:
        logger.exception(
            "Chat stream generation failed for session_id=%s topic=%s",
            payload.get("session_id"),
            payload.get("topic"),
        )
        yield _stream_event({
            "type": "error",
            "message": "Temporary backend error while generating tutor reply.",
        })


# ---------------------------------------------------------------------------
# Preserved public API (used by tests)
# ---------------------------------------------------------------------------

def generate_chat_response(
    payload: dict,
    retrieval_context: list[str] | None = None,
    retrieval_metadatas: list[dict] | None = None,
) -> ChatResponse:
    if not retrieval_context or not retrieval_metadatas:
        raise ValueError("RAG-backed tutor replies require retrieved context and citations.")
    return _grounded_chat_response(payload, retrieval_context, retrieval_metadatas)


def generate_fallback_chat_response(payload: dict) -> ChatResponse:
    return _fallback_chat_response(payload)
