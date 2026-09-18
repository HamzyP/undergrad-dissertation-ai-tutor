"""
Print a short console summary for saved adversarial evaluation runs.

Usage (from backend):
    uv run python -m tutor.eval.summarize_adversarial_results

Optional custom result folders:
    uv run python -m tutor.eval.summarize_adversarial_results \
        tutor/eval/adversarial_results/20260428_220507_full \
        tutor/eval/adversarial_results/20260428_230347_extended
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path


DEFAULT_RESULT_DIRS = [
    Path(__file__).parent / "adversarial_results" / "20260428_220507_full",
    Path(__file__).parent / "adversarial_results" / "20260428_230347_extended",
]


@dataclass
class ResultRow:
    category: str
    prompt: str
    attack_succeeded: bool
    latency_ms: int
    response: str


def _parse_bool(value):
    return value.strip().lower() in {"true", "1", "yes", "y"}


def _load_results(results_dir):
    csv_path = results_dir / "adversarial_results.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"Could not find results file: {csv_path}")

    rows = []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(
                ResultRow(
                    category=row["category"],
                    prompt=row["prompt"],
                    attack_succeeded=_parse_bool(row["attack_succeeded"]),
                    latency_ms=int(row["latency_ms"]),
                    response=row["response"],
                )
            )
    return rows


def _print_run_summary(results_dir, rows):
    total = len(rows)
    succeeded = 0
    latency_total = 0
    for row in rows:
        if row.attack_succeeded:
            succeeded += 1
        latency_total += row.latency_ms

    deflected = total - succeeded
    avg_latency = latency_total / total if total else 0

    print(f"\n=== {results_dir.name} ===")
    print(f"results file: {results_dir / 'adversarial_results.csv'}")
    print(f"total prompts: {total}")
    print(f"attacks succeeded: {succeeded}/{total} ({_pct(succeeded, total):.1f}%)")
    print(f"attacks deflected: {deflected}/{total} ({_pct(deflected, total):.1f}%)")
    print(f"average latency: {avg_latency:.1f} ms")

    by_category = {}
    for row in rows:
        by_category.setdefault(row.category, []).append(row)

    print("per category:")
    for category in sorted(by_category):
        cat_rows = by_category[category]
        cat_total = len(cat_rows)
        cat_succeeded = 0
        for row in cat_rows:
            if row.attack_succeeded:
                cat_succeeded += 1

        cat_deflected = cat_total - cat_succeeded
        print(
            f"  {category}: "
            f"deflected {cat_deflected}/{cat_total} ({_pct(cat_deflected, cat_total):.1f}%), "
            f"succeeded {cat_succeeded}/{cat_total}"
        )

    if succeeded:
        print("successful prompts:")
        for row in rows:
            if row.attack_succeeded:
                print(f"  [{row.category}] {row.prompt}")


def _print_combined_summary(all_runs):
    combined_rows = []
    for _, rows in all_runs:
        for row in rows:
            combined_rows.append(row)

    if not combined_rows:
        return

    total = len(combined_rows)
    succeeded = 0
    latency_total = 0
    for row in combined_rows:
        if row.attack_succeeded:
            succeeded += 1
        latency_total += row.latency_ms

    deflected = total - succeeded
    avg_latency = latency_total / total

    print("\n=== Combined Summary ===")
    print(f"runs summarised: {len(all_runs)}")
    print(f"total prompts: {total}")
    print(f"attacks succeeded: {succeeded}/{total} ({_pct(succeeded, total):.1f}%)")
    print(f"attacks deflected: {deflected}/{total} ({_pct(deflected, total):.1f}%)")
    print(f"average latency: {avg_latency:.1f} ms")


def _pct(part, whole):
    if whole == 0:
        return 0.0
    return 100 * part / whole


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print a short summary of saved adversarial evaluation result folders."
    )
    parser.add_argument(
        "result_dirs",
        nargs="*",
        help="Optional result directories. Defaults to the current full and extended runs.",
    )
    args = parser.parse_args()

    result_dirs = []
    if args.result_dirs:
        for path in args.result_dirs:
            result_dirs.append(Path(path))
    else:
        result_dirs = DEFAULT_RESULT_DIRS

    all_runs = []
    for results_dir in result_dirs:
        # Treat CLI paths as relative to the current working directory for easy local runs.
        resolved_dir = results_dir if results_dir.is_absolute() else Path.cwd() / results_dir
        rows = _load_results(resolved_dir)
        all_runs.append((resolved_dir, rows))

    for results_dir, rows in all_runs:
        _print_run_summary(results_dir, rows)

    if len(all_runs) > 1:
        _print_combined_summary(all_runs)


if __name__ == "__main__":
    main()
