"""
RAG evaluation using Ragas 0.3 + local Ollama models.

Usage (from backend/):
    uv sync --extra eval
    uv run python -m tutor.eval.rag_eval [--metric correctness|faithfulness|all] [--dataset path.json]

Results are written to tutor/eval/rag_results/<timestamp>/.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, TypedDict

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.conf import settings
from langchain_community.llms import Ollama as LangchainOllama
from ragas import evaluate
from ragas.dataset_schema import EvaluationDataset, SingleTurnSample
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import Faithfulness, SimpleCriteriaScore
from ragas.run_config import RunConfig

# Local Ollama can only handle one concurrent request; run Ragas jobs serially.
_RUN_CONFIG = RunConfig(max_workers=1, timeout=300)

_OLLAMA_BASE = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
_OLLAMA_MODEL = getattr(settings, "OLLAMA_MODEL", "llama3.1:8b-instruct-q4_K_M")
_DEFAULT_TOPIC = "philosophy"

_llm = LangchainLLMWrapper(LangchainOllama(model=_OLLAMA_MODEL, base_url=_OLLAMA_BASE))

CORRECTNESS = SimpleCriteriaScore(
    name="correctness",
    definition=(
        "You are evaluating a philosophy tutor's response. "
        "Score 1 if the response addresses the key points in the grading notes, score 0 if it misses them."
    ),
    llm=_llm,
)

FAITHFULNESS = Faithfulness(llm=_llm)


class DatasetSample(TypedDict, total=False):
    query: str
    topic: str
    grading_notes: str
    reference_answer: str


@dataclass(slots=True)
class RagResult:
    answer: str
    retrieved_contexts: list[str]
    latency_ms: int


RagRun = tuple[DatasetSample, RagResult]


def _run_rag(question: str, topic: str) -> RagResult:
    from tutor.services.chat_service import (
        _build_chat_retrieval_query,
        _build_system_prompt,
        _retrieve_chat_context,
    )
    from tutor.services.ollama_service import generate_text
    from tutor.services.prompts import FALLBACK_SYSTEM_PROMPT, SYSTEM_PROMPT
    from tutor.services.types import build_prompt

    payload = {
        "session_id": "eval",
        "topic": topic,
        "timestamp": 0,
        "current_scaffold_level": "",
        "message": question,
        "history": [],
    }
    query = _build_chat_retrieval_query(payload)
    context, _ = _retrieve_chat_context(query)
    prompt = build_prompt(payload, retrieval_context=context)
    system = _build_system_prompt(SYSTEM_PROMPT if context else FALLBACK_SYSTEM_PROMPT, payload)

    t0 = time.monotonic()
    result = generate_text(model_name=None, system_prompt=system, prompt=prompt)
    return RagResult(
        answer=result.text,
        retrieved_contexts=context,
        latency_ms=int((time.monotonic() - t0) * 1000),
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run RAG evaluations against the tutor pipeline.")
    parser.add_argument("--metric", choices=["correctness", "faithfulness", "all"], default="all")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="Path to a JSON dataset. Defaults to tutor.eval.eval_dataset.EVAL_DATASET.",
    )
    return parser.parse_args()


def _load_dataset(dataset_path: Path | None) -> list[DatasetSample]:
    if dataset_path is None:
        from tutor.eval.eval_dataset import EVAL_DATASET

        return EVAL_DATASET

    with dataset_path.open(encoding="utf-8") as f:
        dataset = json.load(f)

    if not isinstance(dataset, list):
        raise ValueError("Dataset JSON must be a list of samples.")

    return dataset


def _get_required_text(sample: DatasetSample, field: str) -> str:
    value = sample.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Each dataset sample must include a non-empty '{field}' field.")
    return value


def _get_topic(sample: DatasetSample) -> str:
    topic = sample.get("topic")
    if isinstance(topic, str) and topic.strip():
        return topic
    return _DEFAULT_TOPIC


def _preview_query(query: str, width: int = 70) -> str:
    return query if len(query) <= width else f"{query[:width]}..."


def _build_base_row(sample: DatasetSample, rag: RagResult) -> dict[str, Any]:
    return {
        **sample,
        "answer": rag.answer,
        "context_count": len(rag.retrieved_contexts),
        "latency_ms": rag.latency_ms,
    }


def _iter_rag_results(dataset: list[DatasetSample]) -> Iterator[tuple[DatasetSample, RagResult]]:
    total = len(dataset)
    for index, sample in enumerate(dataset, start=1):
        query = _get_required_text(sample, "query")
        print(f"[{index}/{total}] {_preview_query(query)}")
        yield sample, _run_rag(query, _get_topic(sample))


def _collect_rag_results(dataset: list[DatasetSample]) -> list[RagRun]:
    return list(_iter_rag_results(dataset))


def _print_pass_fail_summary(rows: list[dict[str, Any]], field: str) -> None:
    total = len(rows)
    for label in ("pass", "fail"):
        count = sum(1 for row in rows if row[field] == label)
        print(f"  {label}: {count}/{total} ({100 * count // total}%)")


def run_correctness_eval(
    dataset: list[DatasetSample],
    results_dir: Path,
    rag_runs: list[RagRun] | None = None,
) -> list[dict[str, Any]]:
    print("\nRunning correctness evaluation\n")
    rows: list[dict[str, Any]] = []
    for sample, rag in rag_runs or _collect_rag_results(dataset):
        query = _get_required_text(sample, "query")
        grading_notes = _get_required_text(sample, "grading_notes")
        score = CORRECTNESS.single_turn_score(
            SingleTurnSample(user_input=query, response=rag.answer, reference=grading_notes)
        )
        score_value = float(score)
        label = "pass" if score_value >= 0.5 else "fail"
        row = _build_base_row(sample, rag)
        row["correctness_score"] = round(score_value, 4)
        row["correctness"] = label
        rows.append(row)
        print(f"  -> {label} ({score_value:.2f})  {rag.latency_ms}ms")

    _write_csv(rows, results_dir / "correctness_results.csv")
    if rows:
        _print_pass_fail_summary(rows, "correctness")
    return rows


def run_faithfulness_eval(
    dataset: list[DatasetSample],
    results_dir: Path,
    rag_runs: list[RagRun] | None = None,
) -> list[dict[str, Any]]:
    print("\nRunning faithfulness evaluation\n")
    rows: list[dict[str, Any]] = []
    samples: list[SingleTurnSample] = []
    for sample, rag in rag_runs or _collect_rag_results(dataset):
        query = _get_required_text(sample, "query")
        contexts = rag.retrieved_contexts or [""]
        samples.append(
            SingleTurnSample(
                user_input=query,
                response=rag.answer,
                retrieved_contexts=contexts,
            )
        )
        rows.append(_build_base_row(sample, rag))
        print(f"  -> {len(contexts)} chunks  {rag.latency_ms}ms")

    if not samples:
        _write_csv(rows, results_dir / "faithfulness_results.csv")
        return rows

    print("\nScoring faithfulness (this may take a few minutes)...")
    results_df = evaluate(dataset=EvaluationDataset(samples=samples), metrics=[FAITHFULNESS], run_config=_RUN_CONFIG).to_pandas()
    for index, row in enumerate(rows):
        row["faithfulness"] = round(float(results_df["faithfulness"].iloc[index]), 4)

    _write_csv(rows, results_dir / "faithfulness_results.csv")
    if rows:
        values = [row["faithfulness"] for row in rows]
        print(
            f"  faithfulness: avg={sum(values) / len(values):.4f}  "
            f"min={min(values):.4f}  max={max(values):.4f}"
        )
    return rows


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        print(f"No rows to write for {path.name}")
        return

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Results written to {path}")


def main() -> None:
    args = _parse_args()
    dataset = _load_dataset(args.dataset)
    print(f"{len(dataset)} samples loaded")

    results_dir = Path(__file__).parent / "rag_results" / datetime.now().strftime("%Y%m%d_%H%M%S")
    rag_runs = None

    if args.metric == "all":
        print("\nGenerating RAG outputs once for all metrics\n")
        rag_runs = _collect_rag_results(dataset)

    if args.metric in ("correctness", "all"):
        run_correctness_eval(dataset, results_dir, rag_runs=rag_runs)
    if args.metric in ("faithfulness", "all"):
        run_faithfulness_eval(dataset, results_dir, rag_runs=rag_runs)

    print(f"\nAll results saved to {results_dir}")


if __name__ == "__main__":
    main()
