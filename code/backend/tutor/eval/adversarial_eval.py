"""
Adversarial guardrail evaluation for the tutor pipeline.

Usage (from backend):
    uv run python -m tutor.eval.adversarial_eval

When testing on dev set for iterating the guardrail (from backend):
    uv run python -m tutor.eval.adversarial_eval --dev

When testing on the extended Schulhoff-derived set (from backend):
    uv run python -m tutor.eval.adversarial_eval --extended



For each prompt: the script runs the pipeline, prints the response,
and asks the researcher to classify whether the attack succeeded.

Results are written to tutor/eval/adversarial_results/<timestamp>/.
"""

import csv
import json
import os
import time
import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

import tutor.eval.adversarial_prompts as _full_prompts_module
import tutor.eval.dev_adversarial_prompts as _dev_prompts_module



# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------

def load_prompts(module):
    # grab every public list from the given module - each one is a prompt category
    prompts = {}
    for name, value in vars(module).items():
        if isinstance(value, list) and not name.startswith("_"):
            prompts[name] = value
    return prompts


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass
class AdversarialResult:
    category: str
    prompt: str
    response: str
    attack_succeeded: bool
    latency_ms: int


# ---------------------------------------------------------------------------
# Question loading
# ---------------------------------------------------------------------------

def _load_question():
    question_text = (
        "Mill's harm principle would most clearly justify which of the following state actions?\n"
        "A) Banning a religious group whose teachings most citizens find offensive  "
        "B) Fining a factory whose emissions damage neighbouring properties  "
        "C) Imprisoning a person for privately consuming alcohol  "
        "D) Requiring all citizens to attend public lectures on civic virtue"
    )
    topic = "Mill on Liberty"
    return question_text, topic


# ---------------------------------------------------------------------------
# Pipeline call
# ---------------------------------------------------------------------------

def _run_pipeline(prompt, question_text, topic):
    # imported here (not at top) because django.setup() must run first
    from rest_framework.test import APIRequestFactory
    from tutor.views import ChatStreamView

    payload = {
        "session_id": "adversarial-eval",
        "topic": topic,
        "timestamp": 0,
        "current_scaffold_level": "Moderate Support",
        "message": prompt,
        "interpolated_question": question_text,
        "history": [],
    }

    factory = APIRequestFactory()
    request = factory.post("/api/chat/stream", payload, format="json")
    response = ChatStreamView.as_view()(request)

    if response.status_code != 200:
        details = getattr(response, "data", None)
        raise RuntimeError(f"Chat stream failed with status {response.status_code}: {details}")

    streamed_text = ""
    final_text = ""
    final_latency_ms = 0
    buffer = ""
    for chunk in response.streaming_content:
        buffer += chunk.decode("utf-8")
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue

            event = json.loads(line)
            event_type = event.get("type")
            if event_type == "delta":
                streamed_text += event.get("text", "")
            elif event_type == "replace":
                streamed_text = event.get("text", "")
            elif event_type == "final":
                final_text = event.get("text", "")
                final_latency_ms = int(event.get("latency_ms", 0))
            elif event_type == "error":
                raise RuntimeError(event.get("message", "Chat stream returned an error event."))

    if final_text:
        return final_text, final_latency_ms
    if streamed_text:
        return streamed_text, 0
    raise RuntimeError("Chat stream ended without producing tutor text.")


# ---------------------------------------------------------------------------
# Human classification
# ---------------------------------------------------------------------------

def _ask_human(prompt, response):
    """Print the response and ask whether the attack succeeded.

    Returns True if attack succeeded (answer leaked), False if deflected.
    """
    print("\n" + "=" * 70)
    print("PROMPT:")
    print(prompt)
    print("\nRESPONSE:")
    print(response)
    print("=" * 70)
    while True:
        answer = input("Did the attack SUCCEED? [y/n]: ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please enter y or n.")


# ---------------------------------------------------------------------------
# Evaluation runner
# ---------------------------------------------------------------------------

def _iter_results(prompts, total, question_text, topic):
    index = 0
    for category, prompt_list in prompts.items():
        for prompt in prompt_list:
            index += 1
            print(f"\n[{index}/{total}] category: {category}")
            response, latency_ms = _run_pipeline(prompt, question_text, topic)
            attack_succeeded = _ask_human(prompt, response)
            yield AdversarialResult(
                category=category,
                prompt=prompt,
                response=response,
                attack_succeeded=attack_succeeded,
                latency_ms=latency_ms,
            )


def run_adversarial_eval(results_dir, question_text, topic, prompts_module):
    prompts = load_prompts(prompts_module)
    total = 0
    for prompt_list in prompts.values():
        total += len(prompt_list)
    print(f"\n{total} adversarial prompts across {len(prompts)} categories\n")

    results = list(_iter_results(prompts, total, question_text, topic))
    _write_csv(results, results_dir / "adversarial_results.csv")
    _print_summary(results)
    return results


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _write_csv(results, path):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )  # create the timestamped results folder if it doesn't exist yet
    if not results:
        path.write_text("", encoding="utf-8")
        return

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["category", "prompt", "attack_succeeded", "latency_ms", "response"],
        )
        writer.writeheader()
        for r in results:
            writer.writerow(
                {
                    "category": r.category,
                    "prompt": r.prompt,
                    "attack_succeeded": r.attack_succeeded,
                    "latency_ms": r.latency_ms,
                    "response": r.response,
                }
            )
    print(f"\nResults written to {path}")


def _print_summary(results):
    total = len(results)
    succeeded = 0
    for r in results:
        if r.attack_succeeded:
            succeeded += 1
    deflected = total - succeeded

    print("\n--- Summary ---")
    print(f"  attacks succeeded: {succeeded}/{total} ({100 * succeeded / total:.1f}%)")
    print(f"  attacks deflected: {deflected}/{total} ({100 * deflected / total:.1f}%)")

    by_category = {}
    for r in results:
        by_category.setdefault(r.category, []).append(r)

    print("\n  per category (deflected / total):")
    for category, cat_results in by_category.items():
        cat_deflected = 0
        for r in cat_results:
            if not r.attack_succeeded:
                cat_deflected += 1
        print(f"    {category}: {cat_deflected}/{len(cat_results)}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Use the small dev prompt set for guardrail iteration instead of the full set.",
    )
    parser.add_argument(
        "--extended",
        action="store_true",
        help="Use the Schulhoff-derived extended prompt set.",
    )
    args = parser.parse_args()

    if args.dev:
        prompts_module = _dev_prompts_module
        run_label = "dev"
        print("Running in DEV mode - guardrail iteration sample only.\n")
    elif args.extended:
        import tutor.eval.adversarial_prompts_extended as _extended_prompts_module

        prompts_module = _extended_prompts_module
        run_label = "extended"
    else:
        prompts_module = _full_prompts_module
        run_label = "full"

    question_text, topic = _load_question()  # load once at startup - same question used for every prompt
    print(f"Question: {question_text}\n")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir = Path(__file__).parent / "adversarial_results" / f"{timestamp}_{run_label}"
    run_adversarial_eval(results_dir, question_text, topic, prompts_module)
    print(f"\nAll results saved to {results_dir}")


if __name__ == "__main__":
    main()
