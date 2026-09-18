from __future__ import annotations

import re
from dataclasses import dataclass


_CITATION_PATTERN = re.compile(r"\[(\d+)\]")


@dataclass
class Citation:
    source_type: str       # "sep" or "transcript"
    source_id: str         # e.g. "liberalism"
    title: str             # display name, e.g. "Liberalism"
    url: str               # link for SEP, empty for transcripts
    location: str          # "section › subsection" or "1:20–2:00"
    start_time: float | None = None  # seconds, only for transcripts

    def to_dict(self) -> dict:
        return {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "title": self.title,
            "url": self.url,
            "location": self.location,
            "start_time": self.start_time,
        }


@dataclass
class ChatResponse:
    response: str
    citations: list[Citation]
    latency_ms: int


@dataclass
class ConsolidationQuestion:
    question: str
    options: list[str]
    correct_index: int
    citations: list[Citation]

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "options": self.options,
            "correct_index": self.correct_index,
            "citations": [c.to_dict() for c in self.citations],
        }


@dataclass
class ConsolidationQuestionsResult:
    questions: list[ConsolidationQuestion]
    latency_ms: int


@dataclass
class MasteryQuestionResult:
    question: ConsolidationQuestion | None
    latency_ms: int


@dataclass
class DiscussionCheckResult:
    question: ConsolidationQuestion | None
    explanation: str
    latency_ms: int


@dataclass
class RemediationResult:
    explanation: str
    easy_question: ConsolidationQuestion | None
    hint: str
    latency_ms: int


@dataclass
class RemediationRewordResult:
    question: ConsolidationQuestion | None
    latency_ms: int


@dataclass
class InterpolatedRewordResult:
    question: ConsolidationQuestion | None
    latency_ms: int


def _format_time(seconds: float) -> str:
    total = int(seconds)
    m, s = divmod(total, 60)
    return f"{m}:{s:02d}"


def build_citations(raw_results: list[dict]) -> list[Citation]:
    """Convert raw ChromaDB result metadata dicts into Citation objects."""
    citations: list[Citation] = []
    for meta in raw_results:
        stype = meta.get("source_type", "")
        sid = meta.get("source_id", "")

        if stype == "sep":
            section = meta.get("section", "")
            sub = meta.get("subsection", "")
            location = f"{section} › {sub}" if sub else section
            url = meta.get("url", "")
            title = meta.get("title", sid)
        else:
            start = meta.get("start_time")
            end = meta.get("end_time")
            location = (
                f"{_format_time(start)}–{_format_time(end)}"
                if start is not None and end is not None
                else ""
            )
            url = ""
            title = f"Lecture: {meta.get('topic', sid)}"

        citations.append(Citation(
            source_type=stype,
            source_id=sid,
            title=title,
            url=url,
            location=location,
            start_time=meta.get("start_time") if stype == "transcript" else None,
        ))
    return citations


def build_prompt(payload: dict, retrieval_context: list[str] | None = None) -> str:
    prompt_sections = [
        "Student session metadata:",
        f"- Session ID: {payload['session_id']}",
        f"- Topic: {payload['topic']}",
        f"- Video timestamp (seconds): {payload['timestamp']}",
        f"- Current scaffold level: {payload['current_scaffold_level']}",
    ]

    if payload.get("interpolated_question"):
        prompt_sections += [
            "",
            "The student was just asked this interpolated question:",
            payload["interpolated_question"],
        ]
        if payload.get("interpolated_answer_correct"):
            prompt_sections += [
                "The student's selected answer to that interpolated question was already marked correct.",
                "If you refer to correctness, make clear that the ORIGINAL multiple-choice answer was correct; do not imply that the student's latest explanation was automatically correct unless the evaluation metadata says so.",
            ]
        explanation_outcome = payload.get("explanation_outcome")
        explanation_attempt = payload.get("explanation_attempt")
        if explanation_outcome:
            prompt_sections.append(
                f"The student's follow-up explanation has already been evaluated as: {explanation_outcome}."
            )
        if explanation_attempt:
            prompt_sections.append(
                f"This is the student's explanation attempt number: {explanation_attempt}."
            )
        explanation_gap = payload.get("explanation_gap")
        if explanation_gap:
            prompt_sections.append(
                f"The specific gap or missing idea to address is: {explanation_gap}."
            )

    if retrieval_context:
        prompt_sections += ["", "Retrieved learning context:"]
        for idx, item in enumerate(retrieval_context, start=1):
            prompt_sections.append(f"[{idx}] {item}")

    history = payload.get("history") or []
    if history:
        prompt_sections += ["", "Conversation so far:"]
        for turn in history:
            role = "Student" if turn.get("sender") == "user" else "Tutor"
            prompt_sections.append(f"{role}: {turn.get('text', '')}")

    prompt_sections += ["", "Student message:", payload["message"]]

    return "\n".join(prompt_sections)


def extract_citation_indices(text: str) -> list[int]:
    return [int(match) for match in _CITATION_PATTERN.findall(text or "")]


def response_has_valid_citations(text: str, max_index: int) -> bool:
    indices = extract_citation_indices(text)
    if not indices:
        return False
    return all(1 <= index <= max_index for index in indices)


def response_has_no_citations(text: str) -> bool:
    return not _CITATION_PATTERN.search(text or "")
