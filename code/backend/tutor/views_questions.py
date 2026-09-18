"""
Question CRUD and LLM-generation API.

Endpoints:
  GET  /api/questions/              list (accepts ?topic= ?quiz_type= filters)
  POST /api/questions/              create one
  PUT  /api/questions/<id>/         update one
  DELETE /api/questions/<id>/       delete one
  POST /api/questions/generate/     LLM-generate questions for a topic+type
"""

from __future__ import annotations

import json
import logging
import re

from django.db import transaction
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from tutor.models import Question
from tutor.serializers import QuestionSerializer
from tutor.ingestion.embed import get_collection, warm_collection_async
from tutor.services.ollama_service import generate_text
from tutor.services.types import build_citations

logger = logging.getLogger(__name__)

# ─── Number of RAG chunks to retrieve for question generation ────────────────

# ─── Number of questions to request from the LLM per generation call ─────────
_N_PRE_POST = 7
_N_INTERPOLATED = 3


# ─────────────────────────────────────────────────────────────────────────────
# List / Create
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["GET", "POST", "DELETE"])
def question_list_create(request):
    if request.method == "GET":
        warm_collection_async()
        qs = Question.objects.all()
        topic = request.query_params.get("topic")
        quiz_type = request.query_params.get("quiz_type")
        if topic:
            qs = qs.filter(topic=topic)
        if quiz_type:
            qs = qs.filter(quiz_type=quiz_type)
        serializer = QuestionSerializer(qs, many=True)
        return Response(serializer.data)

    if request.method == "POST":
        serializer = QuestionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # DELETE — delete all questions
    deleted_count, _ = Question.objects.all().delete()
    return Response({"deleted": deleted_count}, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# Retrieve / Update / Delete
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["GET", "PUT", "DELETE"])
def question_detail(request, pk):
    try:
        question = Question.objects.get(pk=pk)
    except Question.DoesNotExist:
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return Response(QuestionSerializer(question).data)

    if request.method == "PUT":
        serializer = QuestionSerializer(question, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # DELETE
    question.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


# ─────────────────────────────────────────────────────────────────────────────
# LLM generation
# ─────────────────────────────────────────────────────────────────────────────

def _select_interpolated_chunks(topic, len_all=False):
    """Return all transcript chunks for the topic sorted chronologically.

    Each element is (metadata_dict, document_text). The caller handles
    evenly-spaced selection and fallback logic.
    """
    collection = get_collection(wipe=False)
    raw = collection.get(
        where={"$and": [{"source_type": {"$eq": "transcript"}}, {"topic": {"$eq": topic}}]},
        include=["documents", "metadatas"],
    )
    docs = raw.get("documents") or []
    metas = raw.get("metadatas") or []
    return sorted(zip(metas, docs), key=lambda x: x[0].get("start_time", 0))


def _build_available_chunk_indices(all_chunks, existing_excerpt_keys):
    available_indices = []
    for idx, item in enumerate(all_chunks):
        _, chunk_text = item
        excerpt_key = chunk_text.strip()
        if excerpt_key and excerpt_key in existing_excerpt_keys:
            continue
        available_indices.append(idx)
    return available_indices


def _build_single_excerpt_prompt(chunk_text, covered_concepts, task_instruction, prior_tail=None):
    prior_block = ""
    if prior_tail:
        prior_block = f"""PRIOR CONTEXT (for pronoun/subject resolution only — do NOT generate questions about this):
{prior_tail}

"""

    avoid_block = ""
    if covered_concepts:
        avoid_items = covered_concepts[:20]
        avoid_lines = []
        for item in avoid_items:
            avoid_lines.append(f"- {item}")
        avoid_list = "\n".join(avoid_lines)
        avoid_block = f"""
CONCEPTS ALREADY COVERED (do NOT generate a question on any of these):
{avoid_list}

"""

    return f"""You are an educational assessment designer.

{prior_block}TRANSCRIPT EXCERPT:
{chunk_text}
{avoid_block}
TASK:
{task_instruction}

Rules:
- Write a natural, well-formed question — the stem must be a genuine question, not a statement.
- The question MUST be answerable using ONLY what is stated in the excerpt above.
- Do NOT introduce concepts, people, or ideas not explicitly mentioned in the excerpt.
- Every question must include a short `support_quote` copied verbatim from the excerpt.
- Exactly ONE option must be correct. Do not write distractors that are also explicitly supported by the excerpt.
- Verify that exactly one option is supported by the excerpt. If two or more options seem correct, rewrite the distractors.
- Distractors must be plausibly wrong — not paraphrases of other true claims from the excerpt.
- All four options must be similar in length and style.
- Do not use verbatim quotes from the transcript as answer options.
- Paraphrase the correct answer concisely so it matches the format and style of the distractors.
- Do not test a concept already listed in CONCEPTS ALREADY COVERED above.
- Do NOT generate a question based on a rhetorical or open question in the excerpt — only test declarative facts.
- Do NOT write meta-answers (e.g. "He gives two reasons") as options — all options must be substantive.
- Keep each answer option concise — no option should exceed 15 words.
- The correct answer must grammatically complete or directly answer the question stem. Check for inversion: if the stem asks for a benefit, the answer must be a benefit; if the stem asks for a limitation, the answer must be a limitation — not its opposite.
- Do not end the question stem with a dangling preposition.
- Only attribute a claim to a named person if that person is the explicit subject of the sentence in the excerpt containing that claim — not merely mentioned nearby.
- Every word in every answer option must be supported by the excerpt — do not add qualifiers or phrases not present in the source text.

OUTPUT FORMAT — respond with ONLY a valid JSON array containing one object:
[
  {{
    "question_text": "<question>",
    "option_a": "<option A>",
    "option_b": "<option B>",
    "option_c": "<option C>",
    "option_d": "<option D>",
    "correct_index": <0=A, 1=B, 2=C, 3=D>,
    "support_quote": "<short verbatim quote copied from the excerpt>"
  }}
]

Output ONLY the JSON array."""


def _build_single_interpolated_prompt(chunk_text, topic_label, covered_concepts, prior_tail=None):
    """Build a prompt to generate exactly one interpolated question from a single transcript chunk."""
    task_instruction = "Generate exactly 1 multiple-choice question that tests understanding of this specific excerpt."
    return _build_single_excerpt_prompt(
        chunk_text,
        covered_concepts,
        task_instruction,
        prior_tail=prior_tail,
    )


def _build_single_pre_post_prompt(chunk_text, topic_label, covered_concepts, prior_tail=None):
    task_instruction = (
        f"Generate exactly 1 multiple-choice question for a pre/post quiz on {topic_label}. "
        "Test a foundational concept, argument, or key term stated in this specific excerpt."
    )
    return _build_single_excerpt_prompt(
        chunk_text,
        covered_concepts,
        task_instruction,
        prior_tail=prior_tail,
    )


def _build_option_block(question_dict):
    option_lines = []
    option_lines.append(f"A: {question_dict['option_a']}")
    option_lines.append(f"B: {question_dict['option_b']}")
    option_lines.append(f"C: {question_dict['option_c']}")
    option_lines.append(f"D: {question_dict['option_d']}")
    return "\n".join(option_lines)


def _run_grounding_reviewer(system_prompt, prompt, model_name):
    result = generate_text(
        system_prompt=system_prompt,
        prompt=prompt,
        model_name=model_name,
    )
    return result.text.strip()


def _check_question_grounding(chunk_text, question_dict, model_name):
    """Verify the question is grounded in the chunk.

    Returns a (status, reason) tuple where status is one of:
      "ok"   — question is fully valid
      "fail" — question must be discarded and regenerated
    """
    options = _build_option_block(question_dict)
    prompt = f"""TRANSCRIPT EXCERPT:
{chunk_text}

QUESTION: {question_dict['question_text']}
OPTIONS:
{options}
CORRECT ANSWER INDEX: {question_dict['correct_index']} (0=A, 1=B, 2=C, 3=D)

Can a student answer this question correctly using ONLY the information in the excerpt?
Answer YES or NO followed by one sentence explaining why.

Rules for YES:
- The question stem is a genuine question, not a statement.
- The correct answer is explicitly stated or directly implied by the excerpt.
- No other option is also explicitly supported by the excerpt.
- All four options are similar in length and style.
- No option is written as a verbatim quote copied from the excerpt.
- The correct answer is a concise paraphrase that matches the style of the distractors.
- The question stem does not end with a dangling preposition.
- All options are substantive (no "He gives two reasons"-style meta-answers).
- The correct answer grammatically completes the question stem.
- If the question attributes a claim to a named person, that person must be the explicit grammatical subject of the sentence in the excerpt that contains that claim.

Rules for NO:
- The question stem is a statement rather than a question.
- The correct answer requires knowledge not in the excerpt.
- The excerpt only poses the question as rhetorical or open — no declarative answer is given.
- More than one option could be defended as correct from the excerpt.
- One option is a verbatim quote from the excerpt rather than a matched paraphrase.
- The options differ markedly in length or style.
- The question stem ends with a dangling preposition.
- Any option is a meta-answer about structure (e.g. "He gives two reasons").
- Any answer option exceeds 15 words.
- The correct answer does not grammatically complete the question stem, or is the logical inverse of what the stem asks for (e.g. stem asks for a benefit but the answer is a negative outcome).
- The question attributes a claim to a person who is only mentioned nearby in the excerpt, not the explicit subject of that claim.
- Any answer option contains words or qualifiers not present in the excerpt.

Respond with YES or NO followed by one sentence explaining why."""
    try:
        text = _run_grounding_reviewer(
            system_prompt=(
                "You are a strict educational quality reviewer. "
                "Answer only YES or NO followed by one sentence."
            ),
            prompt=prompt,
            model_name=model_name,
        )
        if text.upper().startswith("YES"):
            return "ok", text
        logger.warning("Grounding check failed: %s", text[:120])
        return "fail", text
    except Exception:
        logger.warning("Grounding check LLM call failed; accepting question by default")
        return "ok", "grounding check exception — accepted by default"


def _build_prompt(topic, quiz_type, context_chunks, n, covered_questions=None):
    topic_label = {
        "liberalism": "Liberalism",
        "rep-democracy": "Representative Democracy",
    }.get(topic, topic)

    type_instruction = {
        "pre": (
            f"Generate {n} multiple-choice quiz questions to assess a student's "
            f"knowledge of {topic_label}. "
            "Questions should probe foundational concepts and key terms."
        ),
    }[quiz_type]

    context_block = "\n\n".join(context_chunks)
    avoid_block = ""
    if covered_questions:
        avoid_items = covered_questions[:20]
        avoid_lines = []
        for item in avoid_items:
            avoid_lines.append(f"- {item}")
        avoid_list = "\n".join(avoid_lines)
        avoid_block = f"""

QUESTIONS ALREADY USED (do NOT generate duplicates or trivial rephrasings of these):
{avoid_list}
"""

    extra_fields = ""

    return f"""You are an educational assessment designer. Use the following transcript excerpts to write quiz questions.

TRANSCRIPT EXCERPTS:
{context_block}

TASK:
{type_instruction}

Grounding rules:
- Every question must be answerable from the transcript excerpts alone.
- Do NOT rely on SEP articles, outside knowledge, or the broader course corpus.
- Prefer a question that can be justified by one clearly identifiable excerpt.
- Every question must include a short `support_quote` copied verbatim from the single transcript excerpt that supports it.
- Each question must target a different portion of the transcript — do not generate two questions from the same grounding excerpt.
- Verify that exactly one option is supported by the cited passage. If two or more options seem correct, rewrite the distractors.
- Distractors must be plausibly wrong — not paraphrases of other true claims from the same passage.
{avoid_block}

OUTPUT FORMAT — respond with ONLY a valid JSON array, no explanation, no markdown fences:
[
  {{
    "question_text": "<question>",
    "option_a": "<option A>",
    "option_b": "<option B>",
    "option_c": "<option C>",
    "option_d": "<option D>",
    "correct_index": <0=A, 1=B, 2=C, 3=D>,
    "support_quote": "<short verbatim quote copied from the supporting excerpt>",{extra_fields}
  }},
  ...
]

Generate exactly {n} questions. Output ONLY the JSON array."""


def _serialize_citations(metadata_items):
    citation_dicts = []
    citations = build_citations(metadata_items)
    for citation in citations:
        citation_dicts.append(citation.to_dict())
    return json.dumps(citation_dicts)


def _format_seconds(seconds):
    total = int(seconds)
    minutes = total // 60
    remainder = total % 60
    return f"{minutes}:{remainder:02d}"


def _parse_llm_json(raw_text):
    """Extract and parse the JSON array from the LLM response."""
    # Strip markdown fences if present
    text = re.sub(r"```(?:json)?", "", raw_text).strip()
    # Find the outermost array
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON array found in LLM response: {raw_text[:200]}")
    return json.loads(text[start : end + 1])


def _validate_question_dict(d, quiz_type):
    required = {"question_text", "option_a", "option_b", "option_c", "option_d", "correct_index", "support_quote"}
    missing = required - set(d.keys())
    if missing:
        raise ValueError(f"Question missing fields: {missing}")
    if d["correct_index"] not in (0, 1, 2, 3):
        raise ValueError(f"correct_index must be 0-3, got {d['correct_index']}")
    if not isinstance(d["support_quote"], str) or not d["support_quote"].strip():
        raise ValueError("support_quote must be a non-empty string")


def _normalise_question_text(text):
    return " ".join((text or "").strip().lower().split())


def _normalise_support_quote(text):
    cleaned = (text or "").strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
        cleaned = cleaned[1:-1].strip()
    return " ".join(cleaned.split())


def _quote_supported_by_excerpt(chunk_text, support_quote):
    normalised_chunk = " ".join((chunk_text or "").split())
    normalised_quote = _normalise_support_quote(support_quote)
    if not normalised_quote:
        return False
    return normalised_quote in normalised_chunk


def _load_existing_questions(topic, quiz_type):
    return list(
        Question.objects
        .filter(topic=topic, quiz_type=quiz_type)
        .order_by("order_index", "id")
    )


def _collect_existing_question_state(existing_questions):
    question_keys = set()
    covered_questions = []
    excerpt_keys = set()
    for question in existing_questions:
        question_key = _normalise_question_text(question.question_text)
        if question_key:
            question_keys.add(question_key)

        if question.question_text:
            covered_questions.append(question.question_text)

        excerpt_key = (question.transcript_excerpt or "").strip()
        if excerpt_key:
            excerpt_keys.add(excerpt_key)

    return question_keys, covered_questions, excerpt_keys


def _pick_evenly_spaced_indices(available_indices, n):
    total = len(available_indices)
    if total <= n:
        return list(available_indices)

    step = (total - 1) / (n - 1) if n > 1 else 0
    selected_positions = []
    for i in range(n):
        position = round(i * step)
        if position not in selected_positions:
            selected_positions.append(position)

    selected_indices = []
    for position in selected_positions:
        selected_indices.append(available_indices[position])

    if len(selected_indices) < n:
        for idx in available_indices:
            if idx in selected_indices:
                continue
            selected_indices.append(idx)
            if len(selected_indices) == n:
                break

    return selected_indices


def _build_fallback_pool(available_indices, used_indices):
    fallback_pool = []
    for idx in available_indices:
        if idx not in used_indices:
            fallback_pool.append(idx)
    return fallback_pool


def _extract_prior_tail(all_chunks, chunk_pool_idx):
    if chunk_pool_idx <= 0:
        return None

    prev_text = all_chunks[chunk_pool_idx - 1][1]
    sentences = []
    for sentence in re.split(r'(?<=[.?!])\s+', prev_text):
        cleaned = sentence.strip()
        if cleaned:
            sentences.append(cleaned)

    if not sentences:
        return None

    return " ".join(sentences[-3:])


def _generate_question_batch(system_prompt, prompt, model, total_latency_ms):
    question_dicts = None
    last_parse_exc = None
    raw_result = None

    for attempt in range(2):
        raw_result = generate_text(system_prompt=system_prompt, prompt=prompt, model_name=model)
        total_latency_ms += raw_result.latency_ms
        try:
            question_dicts = _parse_llm_json(raw_result.text)
            break
        except Exception as exc:
            last_parse_exc = exc
            logger.warning("Failed to parse LLM JSON output (attempt %d/2): %s", attempt + 1, exc)

    return question_dicts, last_parse_exc, raw_result, total_latency_ms


def _summarize_errors(errors):
    counts = {}
    for item in errors:
        error_text = item.get("error")
        if not error_text:
            continue
        if error_text not in counts:
            counts[error_text] = 0
        counts[error_text] += 1
    return counts


def _build_pending_question_data(question_dict, transcript_excerpt, citation_metadatas, timestamp=None, rewatch_start=None):
    return {
        "question_text": question_dict["question_text"],
        "option_a": question_dict["option_a"],
        "option_b": question_dict["option_b"],
        "option_c": question_dict["option_c"],
        "option_d": question_dict["option_d"],
        "correct_index": int(question_dict["correct_index"]),
        "timestamp": timestamp,
        "rewatch_start": rewatch_start,
        "transcript_excerpt": transcript_excerpt,
        "citations_json": _serialize_citations(citation_metadatas),
    }


def _persist_pending_questions(topic, quiz_type, existing_count, pending_creates):
    created = []
    with transaction.atomic():
        for order_offset, question_data in enumerate(pending_creates):
            question = Question.objects.create(
                topic=topic,
                quiz_type=quiz_type,
                order_index=existing_count + order_offset,
                question_text=question_data["question_text"],
                option_a=question_data["option_a"],
                option_b=question_data["option_b"],
                option_c=question_data["option_c"],
                option_d=question_data["option_d"],
                correct_index=question_data["correct_index"],
                timestamp=question_data["timestamp"],
                rewatch_start=question_data["rewatch_start"],
                transcript_excerpt=question_data["transcript_excerpt"],
                citations_json=question_data["citations_json"],
            )
            created.append(question)

    return created


def _generate_questions_from_chunk_queue(
    all_chunks,
    question_queue,
    fallback_pool,
    n,
    prompt_builder,
    topic_label,
    model,
    system_prompt,
    covered_questions,
    seen_question_keys,
    total_latency_ms,
    include_prior_tail=False,
):
    _MAX_GROUNDING_RETRIES = 3
    pending_creates = []
    errors = []

    while len(pending_creates) < n and question_queue:
        chunk_pool_idx = question_queue.pop(0)
        meta, chunk_text = all_chunks[chunk_pool_idx]

        prior_tail = None
        if include_prior_tail:
            # Feed a little leading context only for pronoun resolution.
            prior_tail = _extract_prior_tail(all_chunks, chunk_pool_idx)

        accepted = False
        accepted_question_text = None
        accepted_question = None
        for chunk_attempt in range(_MAX_GROUNDING_RETRIES + 1):
            prompt = prompt_builder(chunk_text, topic_label, covered_questions, prior_tail)
            try:
                question_dicts, last_parse_exc, result, total_latency_ms = _generate_question_batch(
                    system_prompt,
                    prompt,
                    model,
                    total_latency_ms,
                )
            except Exception as exc:
                logger.exception("LLM generation failed for chunk %d attempt %d", chunk_pool_idx, chunk_attempt)
                errors.append({"chunk_index": chunk_pool_idx, "error": f"LLM generation failed: {exc}"})
                break

            if not question_dicts:
                errors.append(
                    {
                        "chunk_index": chunk_pool_idx,
                        "attempt": chunk_attempt,
                        "error": f"Could not parse LLM output: {last_parse_exc}",
                    }
                )
                continue

            d = question_dicts[0]
            try:
                _validate_question_dict(d, "interpolated")
            except ValueError as exc:
                errors.append({"chunk_index": chunk_pool_idx, "attempt": chunk_attempt, "error": str(exc), "data": d})
                continue

            if not _quote_supported_by_excerpt(chunk_text, d["support_quote"]):
                errors.append(
                    {
                        "chunk_index": chunk_pool_idx,
                        "attempt": chunk_attempt,
                        "error": "support_quote does not appear in the transcript excerpt",
                        "data": d,
                    }
                )
                continue

            question_key = _normalise_question_text(d["question_text"])
            if question_key in seen_question_keys:
                errors.append(
                    {
                        "chunk_index": chunk_pool_idx,
                        "attempt": chunk_attempt,
                        "error": "Duplicate question detected",
                        "data": d,
                    }
                )
                continue

            grounding_status, grounding_reason = _check_question_grounding(chunk_text, d, model)
            if grounding_status == "ok":
                accepted = True
                accepted_question_text = d["question_text"]
                accepted_question = d
                break

            errors.append(
                {
                    "chunk_index": chunk_pool_idx,
                    "attempt": chunk_attempt,
                    "error": f"Grounding check failed: {grounding_reason}",
                    "data": d,
                }
            )

        if not accepted:
            logger.warning(
                "Chunk %d failed after %d attempts; trying fallback chunk",
                chunk_pool_idx,
                _MAX_GROUNDING_RETRIES + 1,
            )
            if fallback_pool:
                question_queue.append(fallback_pool.pop(0))
            continue

        timestamp = None
        rewatch_start = None
        end_time = meta.get("end_time")
        start_time = meta.get("start_time")
        if isinstance(end_time, (int, float)):
            timestamp = float(round(end_time))
        if isinstance(start_time, (int, float)):
            rewatch_start = float(round(start_time))

        pending_creates.append(
            _build_pending_question_data(
                accepted_question,
                chunk_text,
                [meta],
                timestamp=timestamp,
                rewatch_start=rewatch_start,
            )
        )
        seen_question_keys.add(_normalise_question_text(accepted_question_text))
        covered_questions.append(accepted_question_text)

    return pending_creates, errors, total_latency_ms


@api_view(["POST"])
def question_generate(request):
    """
    POST /api/questions/generate/
    Body: { "topic": "liberalism", "quiz_type": "pre", "model": "llama3.2" }

    Retrieves RAG context, prompts the LLM, parses the JSON, saves to DB,
    returns the created questions.
    """
    topic = request.data.get("topic", "").strip()
    quiz_type = request.data.get("quiz_type", "").strip()
    model = request.data.get("model") or None

    valid_topics = {"liberalism", "rep-democracy"}
    valid_types = {"pre", "interpolated"}

    if topic not in valid_topics:
        return Response(
            {"error": f"topic must be one of {sorted(valid_topics)}"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if quiz_type not in valid_types:
        return Response(
            {"error": f"quiz_type must be one of {sorted(valid_types)}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    default_n = _N_INTERPOLATED if quiz_type == "interpolated" else _N_PRE_POST
    n = int(request.data.get("count", default_n))

    system_prompt = (
        "You are an expert educational assessment designer. "
        "You only output valid JSON as instructed. No explanations, no markdown."
    )
    topic_label = {
        "liberalism": "Liberalism",
        "rep-democracy": "Representative Democracy",
    }.get(topic, topic)

    created = []
    errors = []
    total_latency_ms = 0

    # Assign order_index after existing questions for this topic+type
    existing_questions = _load_existing_questions(topic, quiz_type)
    existing_count = len(existing_questions)

    if quiz_type == "interpolated":
        try:
            all_chunks = _select_interpolated_chunks(topic, len_all=True)
        except Exception as exc:
            logger.exception("Transcript chunk selection failed")
            return Response(
                {"error": f"Transcript retrieval failed: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if not all_chunks:
            return Response(
                {"error": "No transcript chunks found for this topic. Ingest the transcript first."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        existing_question_keys, covered_concepts, existing_excerpt_keys = _collect_existing_question_state(existing_questions)
        available_indices = _build_available_chunk_indices(all_chunks, existing_excerpt_keys)

        if len(available_indices) < n:
            return Response(
                {
                    "error": (
                        f"Cannot generate {n} unique interpolated questions for {topic}. "
                        f"Only {len(available_indices)} unused transcript excerpts remain."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Pick the initial n evenly-spaced indices.
        selected_indices = _pick_evenly_spaced_indices(available_indices, n)
        used_indices = set(selected_indices)
        # Fallback pool: remaining chunks in chronological order, not already selected.
        fallback_pool = _build_fallback_pool(available_indices, used_indices)
        question_queue = list(selected_indices)
        pending_creates, errors, total_latency_ms = _generate_questions_from_chunk_queue(
            all_chunks,
            question_queue,
            fallback_pool,
            n,
            _build_single_interpolated_prompt,
            topic_label,
            model,
            system_prompt,
            covered_concepts,
            set(existing_question_keys),
            total_latency_ms,
            include_prior_tail=True,
        )

        if len(pending_creates) != n:
            return Response(
                {
                    "error": f"Could not generate {n} unique interpolated questions.",
                    "errors": errors,
                    "accepted_count": len(pending_creates),
                    "rejection_summary": _summarize_errors(errors),
                    "created": [],
                    "latency_ms": total_latency_ms,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        created = _persist_pending_questions(topic, quiz_type, existing_count, pending_creates)

    else:
        try:
            all_chunks = _select_interpolated_chunks(topic, len_all=True)
        except Exception as exc:
            logger.exception("Transcript chunk selection failed during question generation")
            return Response(
                {"error": f"Transcript retrieval failed: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if not all_chunks:
            return Response(
                {"error": "No transcript chunks found for this topic. Ingest the transcript first."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        existing_question_keys, covered_questions, existing_excerpt_keys = _collect_existing_question_state(existing_questions)
        available_indices = _build_available_chunk_indices(all_chunks, existing_excerpt_keys)

        if len(available_indices) < n:
            return Response(
                {
                    "error": (
                        f"Cannot generate {n} unique pre/post questions for {topic}. "
                        f"Only {len(available_indices)} unused transcript excerpts remain."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        selected_indices = _pick_evenly_spaced_indices(available_indices, n)
        used_indices = set(selected_indices)
        fallback_pool = _build_fallback_pool(available_indices, used_indices)
        question_queue = list(selected_indices)
        pending_creates, errors, total_latency_ms = _generate_questions_from_chunk_queue(
            all_chunks,
            question_queue,
            fallback_pool,
            n,
            _build_single_pre_post_prompt,
            topic_label,
            model,
            system_prompt,
            covered_questions,
            set(existing_question_keys),
            total_latency_ms,
        )

        if len(pending_creates) != n:
            return Response(
                {
                    "error": f"Could not generate {n} unique pre/post questions.",
                    "errors": errors,
                    "accepted_count": len(pending_creates),
                    "rejection_summary": _summarize_errors(errors),
                    "created": [],
                    "latency_ms": total_latency_ms,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        created = _persist_pending_questions(topic, quiz_type, existing_count, pending_creates)

    serializer = QuestionSerializer(created, many=True)
    return Response(
        {
            "created": serializer.data,
            "errors": errors,
            "latency_ms": total_latency_ms,
        },
        status=status.HTTP_201_CREATED,
    )
