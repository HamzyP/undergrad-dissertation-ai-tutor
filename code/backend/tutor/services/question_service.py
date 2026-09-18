"""
Question generation service.

Generates in-chat multiple-choice questions to reinforce student understanding
at two critical moments:

  1. CONSOLIDATION: After a student answers correctly but gives a weak explanation.
     Generates 2 questions testing definition vs. application of the concept.
     Accessed by: views.ConsolidationGenerateView → generate_consolidation_questions()

  2. MASTERY: After a student answers correctly with a strong explanation.
     Generates 1 harder question to probe deeper understanding.
     Accessed by: views.MasteryGenerateView → generate_mastery_question()

Both flows:
  - Retrieve RAG context (top 4 chunks, distance <= 0.65)
  - Generate JSON via LLM (2 attempts, with retry on invalid JSON)
  - Validate each question: structure, options, citations, correctness clarity
  - Strip any hallucinated citation markers (LLM sometimes writes [4] when only [1-3] exist)
  - Return best questions found, or empty list if both attempts fail
"""

from __future__ import annotations

import json
import logging
import re

from tutor.services.types import (
    Citation,
    ConsolidationQuestion,
    ConsolidationQuestionsResult,
    DiscussionCheckResult,
    InterpolatedRewordResult,
    MasteryQuestionResult,
    RemediationResult,
    RemediationRewordResult,
    build_citations,
)
from tutor.services.ollama_service import generate_text
from tutor.services.prompts import (
    CONSOLIDATION_SYSTEM_PROMPT,
    DISCUSSION_CHECK_SYSTEM_PROMPT,
    EXPLANATION_EVALUATION_SYSTEM_PROMPT,
    INTENT_CLASSIFICATION_SYSTEM_PROMPT,
    INTERPOLATED_REWORD_SYSTEM_PROMPT,
    MASTERY_SYSTEM_PROMPT,
    REMEDIATION_GENERATE_SYSTEM_PROMPT,
    REMEDIATION_REWORD_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)

CONSOLIDATION_RAG_TOP_K = 4
CONSOLIDATION_RAG_MAX_DISTANCE = 0.65
_CITATION_MARKER = re.compile(r"\[(\d+)\]")

# Validation helpers for MCQ answer options
_VAGUE_OPTION_PHRASES = (
    "it depends",
    "as long as",
    "maybe",
    "perhaps",
    "possibly",
    "sometimes",
    "in some cases",
    "often",
    "usually",
    "can be",
    "could be",
    "might be",
)
_OPTION_TOKEN_PATTERN = re.compile(r"[a-z0-9']+")
_OPTION_STOPWORDS = {
    "a", "an", "and", "are", "as", "be", "by", "for", "if", "in", "is", "it",
    "its", "of", "on", "or", "that", "the", "their", "there", "they", "this",
    "to", "when", "with",
}


def _normalise_option_text(text: str) -> str:
    """Lowercase, strip, and normalize whitespace for option comparison."""
    return " ".join(" ".join(text.strip().lower().split()).split())


def _content_tokens(text: str) -> set[str]:
    """Extract non-stopword tokens from text for semantic overlap detection."""
    return {
        token
        for token in _OPTION_TOKEN_PATTERN.findall(_normalise_option_text(text))
        if token not in _OPTION_STOPWORDS
    }


def _options_overlap_too_much(correct_option: str, other_option: str) -> bool:
    """Check if incorrect options are too similar to the correct one.

    Rejects if: normalized text is identical, substring match, or >80% token overlap.
    Prevents the LLM from writing trick questions with near-identical distractors.
    """
    correct_normalized = _normalise_option_text(correct_option)
    other_normalized = _normalise_option_text(other_option)

    if correct_normalized == other_normalized:
        return True
    if correct_normalized in other_normalized or other_normalized in correct_normalized:
        return True

    correct_tokens = _content_tokens(correct_option)
    other_tokens = _content_tokens(other_option)
    if not correct_tokens or not other_tokens:
        return False

    overlap = len(correct_tokens & other_tokens)
    return overlap > 0 and overlap == min(len(correct_tokens), len(other_tokens))


def _is_unambiguous_correct_option(option: str) -> bool:
    """Check that the correct answer is clear and definitive, not wishy-washy.

    Rejects if the option is empty, ends with '?', or contains vague language
    like "maybe", "it depends", "sometimes", etc. The correct answer must be
    a crisp, unqualified statement so students can't argue it away.
    """
    normalized = _normalise_option_text(option)
    if not normalized or normalized.endswith("?"):
        return False
    return not any(phrase in normalized for phrase in _VAGUE_OPTION_PHRASES)


def _truncate_for_log(text: str, limit: int = 600) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _validate_consolidation_question(
    item: object,
    citations: list[Citation] | None = None,
) -> tuple[ConsolidationQuestion | None, str | None]:
    question_citations = citations or []

    if not isinstance(item, dict):
        return None, "item is not an object"

    question_text = item.get("question")
    options = item.get("options")
    correct_index = item.get("correct_index")

    if not isinstance(question_text, str) or not question_text.strip():
        return None, "missing question text"
    if not isinstance(options, list) or len(options) != 4:
        return None, "options must contain exactly 4 items"
    if not isinstance(correct_index, int) or not 0 <= correct_index < len(options):
        return None, "correct_index is out of bounds"
    if not all(isinstance(option, str) and option.strip() for option in options):
        return None, "all options must be non-empty strings"

    if question_citations:
        max_index = len(question_citations)
        question_text = _CITATION_MARKER.sub(
            lambda m: m.group(0) if 1 <= int(m.group(1)) <= max_index else "",
            question_text,
        ).strip()
        if not _CITATION_MARKER.search(question_text):
            return None, "missing valid citation marker in question stem"

    correct_option = options[correct_index]
    if not _is_unambiguous_correct_option(correct_option):
        return None, "correct option is ambiguous or vague"
    if any(
        _options_overlap_too_much(correct_option, option)
        for idx, option in enumerate(options)
        if idx != correct_index
    ):
        return None, "one or more distractors overlap too much with the correct option"

    return (
        ConsolidationQuestion(
            question=question_text,
            options=options,
            correct_index=correct_index,
            citations=question_citations,
        ),
        None,
    )


def _retrieve_consolidation_context(
    original_question: str,
    topic: str | None = None,
) -> tuple[list[str], list[dict]]:
    """Retrieve RAG context for question generation.

    Queries the knowledge base with the original interpolated question (+ topic if provided).
    Returns up to 4 chunks with distance <= 0.65, with full metadata for building citations.
    Used by both consolidation and mastery generation.

    Returns: (documents, metadatas) or ([], []) on failure.
    """
    try:
        from tutor.ingestion.embed import embed_query, get_collection

        query_parts = [original_question.strip()]
        if topic:
            query_parts.insert(0, topic.strip())
        query_text = " ".join(part for part in query_parts if part)

        embedding = embed_query(query_text)
        collection = get_collection(wipe=False)
        raw = collection.query(
            query_embeddings=[embedding],
            n_results=CONSOLIDATION_RAG_TOP_K,
            where={"source_type": {"$in": ["sep", "transcript"]}},
            include=["documents", "metadatas", "distances"],
        )
        docs = (raw.get("documents") or [[]])[0]
        metas = (raw.get("metadatas") or [[]])[0]
        dists = (raw.get("distances") or [[]])[0]

        context: list[str] = []
        metadatas: list[dict] = []
        for doc, meta, dist in zip(docs, metas, dists):
            if dist <= CONSOLIDATION_RAG_MAX_DISTANCE:
                context.append(doc)
                metadatas.append(meta)
        return context, metadatas
    except Exception:
        logger.exception("Consolidation RAG retrieval failed")
        return [], []


def _build_consolidation_prompt(
    original_question: str,
    student_explanation: str,
    retrieval_context: list[str],
    gap_focus: str | None = None,
) -> str:
    """Build the LLM prompt for generating consolidation questions.

    Includes the original question, the student's weak explanation, and the
    retrieved context chunks. The LLM will generate 2 MCQs: one testing
    definition, one testing application.
    """
    prompt_sections = [
        f"Original interpolated question: {original_question}",
        f"Student's weak explanation: {student_explanation}",
    ]
    if gap_focus:
        prompt_sections += [
            f"Specific gap to probe: {gap_focus}",
            "At least one question must directly test this missing idea, not just the overall concept.",
        ]
    prompt_sections += [
        "",
        "Retrieved course material:",
    ]
    for idx, item in enumerate(retrieval_context, start=1):
        prompt_sections.append(f"[{idx}] {item}")
    return "\n".join(prompt_sections)


def _build_mastery_prompt(
    original_question: str,
    student_explanation: str,
    retrieval_context: list[str],
) -> str:
    """Build the LLM prompt for generating a mastery check question.

    Includes the original question, the student's strong explanation, and the
    retrieved context chunks. The LLM will generate 1 MCQ at a deeper/applied
    level than the original question.
    """
    prompt_sections = [
        f"Original interpolated question: {original_question}",
        f"Student's strong explanation: {student_explanation}",
        "",
        "Retrieved course material:",
    ]
    for idx, item in enumerate(retrieval_context, start=1):
        prompt_sections.append(f"[{idx}] {item}")
    return "\n".join(prompt_sections)


def _build_discussion_check_prompt(
    original_question: str,
    student_question: str,
    question_classification: str | None,
    retrieval_context: list[str],
) -> str:
    prompt_sections = [
        f"Original interpolated question: {original_question}",
        f"Student question: {student_question}",
    ]
    if question_classification:
        prompt_sections.append(f"Question classification: {question_classification}")
    prompt_sections += [
        "",
        "Retrieved course material:",
    ]
    for idx, item in enumerate(retrieval_context, start=1):
        prompt_sections.append(f"[{idx}] {item}")
    return "\n".join(prompt_sections)


def _build_explanation_evaluation_prompt(
    original_question: str,
    correct_answer: str,
    student_explanation: str,
    retrieval_context: list[str],
) -> str:
    prompt_sections = [
        f"Original interpolated question: {original_question}",
        f"Correct answer: {correct_answer}",
        f"Student explanation: {student_explanation}",
    ]
    if retrieval_context:
        prompt_sections += ["", "Retrieved course material:"]
        for idx, item in enumerate(retrieval_context, start=1):
            prompt_sections.append(f"[{idx}] {item}")
    return "\n".join(prompt_sections)


def _parse_explanation_evaluation(raw_text: str) -> tuple[str, str] | None:
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    outcome = parsed.get("outcome")
    gap_focus = parsed.get("gap_focus", "")
    if outcome in {"correct", "partial", "incorrect"}:
        if not isinstance(gap_focus, str):
            return None
        return outcome, gap_focus.strip()
    return None


def _parse_discussion_check_result(
    parsed: object,
    citations: list[Citation] | None = None,
) -> tuple[ConsolidationQuestion | None, str]:
    if not isinstance(parsed, dict):
        return None, ""

    question = _parse_valid_consolidation_questions([parsed.get("question")], citations=citations)
    explanation = parsed.get("explanation")
    if not isinstance(explanation, str) or not explanation.strip():
        return None, ""

    return (question[0] if question else None, explanation.strip())


def _parse_valid_consolidation_questions(
    parsed: object,
    citations: list[Citation] | None = None,
    rejection_reasons: list[str] | None = None,
) -> list[ConsolidationQuestion]:
    """Validate and parse LLM-generated question JSON.

    Checks:
      - Structure: list of dicts with question, options (exactly 4), correct_index
      - Content: non-empty strings, correct_index in bounds
      - Correctness: correct answer is unambiguous (no vague modifiers)
      - Distractors: no incorrect option is >80% similar to the correct answer
      - Citations: strips hallucinated out-of-range markers, but still requires
        at least one valid in-range citation marker when RAG citations exist

    Returns a list of valid ConsolidationQuestion objects, or [] if parsing fails.
    """
    if not isinstance(parsed, list):
        return []

    questions: list[ConsolidationQuestion] = []
    for idx, item in enumerate(parsed, start=1):
        question, reason = _validate_consolidation_question(item, citations=citations)
        if question:
            questions.append(question)
        elif rejection_reasons is not None and reason:
            rejection_reasons.append(f"item {idx}: {reason}")

    return questions


def _build_question_generation_retry_system_prompt(
    base_system_prompt: str,
    rejection_reasons: list[str],
    expected_count: int,
) -> str:
    instructions = [
        "",
        "## Output correction",
        "- Your previous draft was rejected during MCQ validation.",
        f"- Return ONLY a JSON array of exactly {expected_count} object{'s' if expected_count != 1 else ''}.",
        "- Do not include markdown fences, explanations, labels, or any text outside the JSON array.",
        # Always remind the model about citations — if attempt 1 failed for a structural
        # reason (e.g. returned an object instead of an array), the model tends to fix the
        # structure but silently drop citation markers on the retry.
        "- Each question stem MUST include at least one inline citation marker like [1] or [2] from the retrieved chunks.",
        "- Put citation markers in the question stem only, never inside any answer option.",
        "- Do not invent citation indices beyond those provided.",
    ]

    if any("missing valid citation marker" in reason for reason in rejection_reasons):
        instructions += [
            "- IMPORTANT: your previous attempt had no valid citation marker — add one to the question stem.",
        ]

    if any("correct option is ambiguous or vague" in reason for reason in rejection_reasons):
        instructions += [
            "- Rewrite the correct answer so it is direct, definite, and free of vague qualifiers like 'as long as', 'maybe', or 'sometimes'.",
        ]

    if any("overlap too much" in reason for reason in rejection_reasons):
        instructions += [
            "- Make every incorrect option clearly distinct from the correct answer in wording and meaning.",
            "- Do not use distractors that are paraphrases, substrings, or near-restatements of the correct answer.",
        ]

    if any("options must contain exactly 4 items" in reason for reason in rejection_reasons):
        instructions += [
            "- Each question must have exactly 4 answer options.",
        ]

    if any("correct_index is out of bounds" in reason for reason in rejection_reasons):
        instructions += [
            "- Each correct_index must be a 0-based integer that points to one of the 4 options.",
        ]

    if any("JSON object" in reason for reason in rejection_reasons):
        instructions += [
            "- Your response must start with '[' and end with ']' — a JSON array, not a JSON object.",
            f"- Wrap the {expected_count} question object{'s' if expected_count != 1 else ''} inside a top-level array: [{{...}}]",
        ]

    correction_block = "\n".join(instructions)
    return f"{base_system_prompt}{correction_block}"


def _generate_grounded_question_set(
    *,
    system_prompt: str,
    prompt: str,
    citations: list[Citation],
    model_name: str | None,
    expected_count: int,
    log_label: str,
) -> tuple[list[ConsolidationQuestion], int]:
    """Generate and validate a set of MCQs with up to 2 retry attempts.

    Calls the LLM, parses JSON, validates questions, and keeps track of the best
    result across attempts (in case attempt 1 partially fails but attempt 2 succeeds).
    Stops early if expected_count is reached.

    Args:
      system_prompt: Base LLM system prompt (consolidation or mastery)
      prompt: The full prompt including original question, explanation, and context
      citations: The RAG chunks, used to validate citation markers in questions
      model_name: Ollama model name (e.g. "llama2")
      expected_count: 2 for consolidation, 1 for mastery
      log_label: Log prefix for debugging (e.g. "Consolidation question generation")

    Returns: (questions, total_latency_ms across all attempts)
    """
    total_latency_ms = 0
    best_questions: list[ConsolidationQuestion] = []
    active_system_prompt = system_prompt

    for attempt in range(2):
        generation = generate_text(
            model_name=model_name,
            system_prompt=active_system_prompt,
            prompt=prompt,
        )
        total_latency_ms += generation.latency_ms

        try:
            parsed = json.loads(generation.text)
        except json.JSONDecodeError:
            logger.warning("%s returned invalid JSON on attempt %s", log_label, attempt + 1)
            logger.warning(
                "%s raw output on attempt %s: %r",
                log_label,
                attempt + 1,
                _truncate_for_log(generation.text),
            )
            if attempt == 0:
                active_system_prompt = _build_question_generation_retry_system_prompt(
                    system_prompt,
                    ["response was not valid JSON"],
                    expected_count,
                )
            continue

        rejection_reasons: list[str] = []
        if not isinstance(parsed, list):
            rejection_reasons.append("response was a JSON object, not a JSON array")
            questions = []
        else:
            questions = _parse_valid_consolidation_questions(
                parsed,
                citations=citations,
                rejection_reasons=rejection_reasons,
            )[:expected_count]
        if len(questions) > len(best_questions):
            best_questions = questions
        if len(questions) == expected_count:
            break

        logger.warning(
            "%s produced %s valid item(s) on attempt %s",
            log_label,
            len(questions),
            attempt + 1,
        )
        if rejection_reasons:
            logger.warning(
                "%s rejection details on attempt %s: %s",
                log_label,
                attempt + 1,
                "; ".join(rejection_reasons),
            )
        logger.warning(
            "%s raw output on attempt %s: %r",
            log_label,
            attempt + 1,
            _truncate_for_log(generation.text),
        )
        if attempt == 0:
            retry_reasons = rejection_reasons or ["response had the wrong JSON structure"]
            active_system_prompt = _build_question_generation_retry_system_prompt(
                system_prompt,
                retry_reasons,
                expected_count,
            )

    return best_questions, total_latency_ms


def generate_explanation_outcome(
    original_question: str,
    correct_answer: str,
    student_explanation: str,
    topic: str | None = None,
    model_name: str | None = None,
) -> dict[str, str]:
    """Classify a student's post-answer explanation as correct, partial, or incorrect."""
    retrieval_context, _ = _retrieve_consolidation_context(
        original_question,
        topic=topic,
    )
    prompt = _build_explanation_evaluation_prompt(
        original_question,
        correct_answer,
        student_explanation,
        retrieval_context,
    )

    for attempt in range(2):
        generation = generate_text(
            model_name=model_name,
            system_prompt=EXPLANATION_EVALUATION_SYSTEM_PROMPT,
            prompt=prompt,
        )
        parsed = _parse_explanation_evaluation(generation.text)
        if parsed:
            outcome, gap_focus = parsed
            return {"outcome": outcome, "gap_focus": gap_focus}
        logger.warning(
            "Explanation evaluation returned invalid JSON/outcome on attempt %s",
            attempt + 1,
        )

    logger.warning("Falling back to 'partial' after explanation evaluation retries failed")
    return {"outcome": "partial", "gap_focus": ""}


_VALID_INTENTS = frozenset({"evaluate_response", "asks_question", "confused_or_stuck"})


def classify_student_intent(
    message: str,
    interpolated_question: str | None = None,
    topic: str | None = None,
    model_name: str | None = None,
) -> str:
    """Ask the LLM to classify an ambiguous student message into one of three intents.

    Called only when the frontend's regex classifier is uncertain (message has no
    reasoning cues and is not clearly a question or uncertainty expression).

    Returns one of: "evaluate_response", "asks_question", "confused_or_stuck".
    Falls back to "evaluate_response" on any failure.
    """
    context_parts = []
    if topic:
        context_parts.append(f"Topic: {topic}")
    if interpolated_question:
        context_parts.append(f"Current concept question: {interpolated_question}")
    context_parts.append(f"Student message: {message}")
    prompt = "\n".join(context_parts)

    for attempt in range(2):
        generation = generate_text(
            model_name=model_name,
            system_prompt=INTENT_CLASSIFICATION_SYSTEM_PROMPT,
            prompt=prompt,
        )
        try:
            parsed = json.loads(generation.text)
            intent = parsed.get("intent", "")
            if intent in _VALID_INTENTS:
                return intent
            logger.warning(
                "Intent classification returned unknown intent %r on attempt %s",
                intent,
                attempt + 1,
            )
        except json.JSONDecodeError:
            logger.warning(
                "Intent classification returned invalid JSON on attempt %s",
                attempt + 1,
            )

    logger.warning("Intent classification failed after retries; falling back to evaluate_response")
    return "evaluate_response"


def generate_consolidation_questions(
    original_question: str,
    student_explanation: str,
    gap_focus: str | None = None,
    topic: str | None = None,
    model_name: str | None = None,
) -> ConsolidationQuestionsResult:
    """Generate 2 consolidation MCQs for a student who gave a weak explanation.

    Called by: views.ConsolidationGenerateView (POST /api/consolidation/generate)

    Flow:
      1. Retrieve RAG context on the original question
      2. Build a prompt with the weak explanation
      3. Generate 2 MCQs (up to 2 LLM attempts)
      4. Validate and return

    Returns: ConsolidationQuestionsResult with questions=[] if both attempts fail or no RAG context.
    """
    retrieval_context, retrieval_metadatas = _retrieve_consolidation_context(
        original_question,
        topic=topic,
    )
    if not retrieval_context or not retrieval_metadatas:
        logger.warning("No usable RAG context found for consolidation question generation")
        return ConsolidationQuestionsResult(questions=[], latency_ms=0)

    citations = build_citations(retrieval_metadatas)
    prompt = _build_consolidation_prompt(
        original_question,
        student_explanation,
        retrieval_context,
        gap_focus=gap_focus,
    )
    questions, total_latency_ms = _generate_grounded_question_set(
        system_prompt=CONSOLIDATION_SYSTEM_PROMPT,
        prompt=prompt,
        citations=citations,
        model_name=model_name,
        expected_count=2,
        log_label="Consolidation question generation",
    )
    return ConsolidationQuestionsResult(questions=questions, latency_ms=total_latency_ms)


def generate_mastery_question(
    original_question: str,
    student_explanation: str,
    topic: str | None = None,
    model_name: str | None = None,
) -> MasteryQuestionResult:
    """Generate 1 mastery check MCQ for a student who gave a strong explanation.

    Called by: views.MasteryGenerateView (POST /api/mastery/generate)

    Flow:
      1. Retrieve RAG context on the original question
      2. Build a prompt with the strong explanation
      3. Generate 1 MCQ at a deeper/applied level (up to 2 LLM attempts)
      4. Validate and return

    Returns: MasteryQuestionResult with question=None if both attempts fail or no RAG context.
             This is not an error — the frontend auto-continues if mastery fails.
    """
    retrieval_context, retrieval_metadatas = _retrieve_consolidation_context(
        original_question,
        topic=topic,
    )
    if not retrieval_context or not retrieval_metadatas:
        logger.warning("No usable RAG context found for mastery question generation")
        return MasteryQuestionResult(question=None, latency_ms=0)

    citations = build_citations(retrieval_metadatas)
    prompt = _build_mastery_prompt(original_question, student_explanation, retrieval_context)
    questions, total_latency_ms = _generate_grounded_question_set(
        system_prompt=MASTERY_SYSTEM_PROMPT,
        prompt=prompt,
        citations=citations,
        model_name=model_name,
        expected_count=1,
        log_label="Mastery question generation",
    )
    return MasteryQuestionResult(
        question=questions[0] if questions else None,
        latency_ms=total_latency_ms,
    )


def generate_discussion_check(
    original_question: str,
    student_question: str,
    question_classification: str | None = None,
    topic: str | None = None,
    model_name: str | None = None,
) -> DiscussionCheckResult:
    """Generate one closing MCQ plus explanation after a help-seeking question."""
    retrieval_context, retrieval_metadatas = _retrieve_consolidation_context(
        original_question,
        topic=topic,
    )
    if not retrieval_context or not retrieval_metadatas:
        logger.warning("No usable RAG context found for discussion-check generation")
        return DiscussionCheckResult(
            question=None,
            explanation="",
            latency_ms=0,
        )

    citations = build_citations(retrieval_metadatas)
    prompt = _build_discussion_check_prompt(
        original_question,
        student_question,
        question_classification,
        retrieval_context,
    )

    total_latency_ms = 0
    for attempt in range(2):
        generation = generate_text(
            model_name=model_name,
            system_prompt=DISCUSSION_CHECK_SYSTEM_PROMPT,
            prompt=prompt,
        )
        total_latency_ms += generation.latency_ms

        try:
            parsed = json.loads(generation.text)
        except json.JSONDecodeError:
            logger.warning("Discussion-check generation returned invalid JSON on attempt %s", attempt + 1)
            continue

        question, explanation = _parse_discussion_check_result(parsed, citations=citations)
        if question and explanation:
            return DiscussionCheckResult(
                question=question,
                explanation=explanation,
                latency_ms=total_latency_ms,
            )

        logger.warning("Discussion-check generation produced invalid content on attempt %s", attempt + 1)

    return DiscussionCheckResult(question=None, explanation="", latency_ms=total_latency_ms)


def generate_remediation(
    original_question: str,
    correct_answer: str,
    topic: str | None = None,
    model_name: str | None = None,
) -> RemediationResult:
    """Generate an explanation, an easy MCQ, and a hint for a failed interpolated question.

    Called by: views.RemediationGenerateView (POST /api/remediation/generate)

    Flow:
      1. Retrieve RAG context on the original question
      2. Build a prompt with the correct answer
      3. Generate explanation + easy_question + hint via LLM (up to 2 attempts)
      4. Validate and return

    Returns: RemediationResult with easy_question=None if both attempts fail.
    """
    retrieval_context, retrieval_metadatas = _retrieve_consolidation_context(
        original_question,
        topic=topic,
    )
    if not retrieval_context or not retrieval_metadatas:
        logger.warning("No usable RAG context found for remediation generation")
        return RemediationResult(
            explanation=f"The correct answer is: {correct_answer}.",
            easy_question=None,
            hint="",
            latency_ms=0,
        )

    citations = build_citations(retrieval_metadatas)
    prompt_sections = [
        f"Original question: {original_question}",
        f"Correct answer: {correct_answer}",
        "",
        "Retrieved course material:",
    ]
    for idx, item in enumerate(retrieval_context, start=1):
        prompt_sections.append(f"[{idx}] {item}")
    prompt = "\n".join(prompt_sections)

    total_latency_ms = 0
    for attempt in range(2):
        generation = generate_text(
            model_name=model_name,
            system_prompt=REMEDIATION_GENERATE_SYSTEM_PROMPT,
            prompt=prompt,
        )
        total_latency_ms += generation.latency_ms

        try:
            parsed = json.loads(generation.text)
        except json.JSONDecodeError:
            logger.warning("Remediation generation returned invalid JSON on attempt %s", attempt + 1)
            continue

        if not isinstance(parsed, dict):
            continue

        explanation = parsed.get("explanation") or f"The correct answer is: {correct_answer}."
        hint = parsed.get("hint") or ""
        easy_raw = parsed.get("easy_question")
        rejection_reasons: list[str] = []
        easy_questions = _parse_valid_consolidation_questions(
            [easy_raw] if isinstance(easy_raw, dict) else [],
            citations=None,
            rejection_reasons=rejection_reasons,
        )
        if easy_questions:
            return RemediationResult(
                explanation=explanation,
                easy_question=easy_questions[0],
                hint=hint,
                latency_ms=total_latency_ms,
            )

        logger.warning(
            "Remediation generation produced no valid easy question on attempt %s — reasons=%s, easy_raw=%r",
            attempt + 1, rejection_reasons or ["easy_question missing or not a dict"], easy_raw,
        )

    return RemediationResult(
        explanation=f"The correct answer is: {correct_answer}.",
        easy_question=None,
        hint="",
        latency_ms=total_latency_ms,
    )


def generate_remediation_reword(
    original_question: str,
    hint: str,
    topic: str | None = None,
    model_name: str | None = None,
) -> RemediationRewordResult:
    """Reword an easy remediation question using the provided hint for accessibility.

    Called by: views.RemediationRewordView (POST /api/remediation/reword)

    Returns: RemediationRewordResult with question=None if generation fails.
    """
    retrieval_context, retrieval_metadatas = _retrieve_consolidation_context(
        original_question,
        topic=topic,
    )
    if not retrieval_context or not retrieval_metadatas:
        logger.warning("No usable RAG context found for remediation reword")
        return RemediationRewordResult(question=None, latency_ms=0)

    citations = build_citations(retrieval_metadatas)
    prompt_sections = [
        f"Original question: {original_question}",
        f"Hint: {hint}",
        "",
        "Retrieved course material:",
    ]
    for idx, item in enumerate(retrieval_context, start=1):
        prompt_sections.append(f"[{idx}] {item}")
    prompt = "\n".join(prompt_sections)

    questions, total_latency_ms = _generate_grounded_question_set(
        system_prompt=REMEDIATION_REWORD_SYSTEM_PROMPT,
        prompt=prompt,
        citations=citations,
        model_name=model_name,
        expected_count=1,
        log_label="Remediation reword",
    )
    return RemediationRewordResult(
        question=questions[0] if questions else None,
        latency_ms=total_latency_ms,
    )


def generate_interpolated_reword(
    original_question: str,
    original_options: list[str],
    correct_index: int,
    scaffold_level: str,
    topic: str | None = None,
    model_name: str | None = None,
) -> InterpolatedRewordResult:
    """Reword an interpolated video question for a student who clicked 'Reword'.

    Skips RAG entirely — rewording is a paraphrase task over existing content,
    not a knowledge retrieval task. No citation markers are required or expected.

    Called by: views.InterpolatedRewordView (POST /api/interpolated/reword)

    Returns: InterpolatedRewordResult with question=None if generation fails.
    """
    options_formatted = "\n".join(f"  {i}. {opt}" for i, opt in enumerate(original_options))
    prompt = "\n".join([
        f"Scaffold level: {scaffold_level}",
        f"Original question: {original_question}",
        f"Original options (0-based):\n{options_formatted}",
        f"Correct index: {correct_index}",
    ])

    total_latency_ms = 0
    for attempt in range(2):
        generation = generate_text(
            model_name=model_name,
            system_prompt=INTERPOLATED_REWORD_SYSTEM_PROMPT,
            prompt=prompt,
        )
        total_latency_ms += generation.latency_ms

        try:
            parsed = json.loads(generation.text)
        except json.JSONDecodeError:
            logger.warning("Interpolated reword returned invalid JSON on attempt %s", attempt + 1)
            logger.warning("Interpolated reword raw output on attempt %s: %r", attempt + 1, _truncate_for_log(generation.text))
            continue

        if not isinstance(parsed, dict):
            logger.warning("Interpolated reword returned non-object JSON on attempt %s", attempt + 1)
            logger.warning("Interpolated reword raw output on attempt %s: %r", attempt + 1, _truncate_for_log(generation.text))
            continue

        question_text = parsed.get("question", "").strip()
        options = parsed.get("options")
        returned_index = parsed.get("correct_index")

        if (
            not question_text
            or not isinstance(options, list)
            or len(options) != 4
            or not all(isinstance(o, str) and o.strip() for o in options)
            or not isinstance(returned_index, int)
            or not (0 <= returned_index < 4)
        ):
            logger.warning("Interpolated reword returned malformed question on attempt %s", attempt + 1)
            logger.warning("Interpolated reword raw output on attempt %s: %r", attempt + 1, _truncate_for_log(generation.text))
            continue

        return InterpolatedRewordResult(
            question=ConsolidationQuestion(
                question=question_text,
                options=original_options,
                correct_index=correct_index,
                citations=[],
            ),
            latency_ms=total_latency_ms,
        )

    return InterpolatedRewordResult(question=None, latency_ms=total_latency_ms)
