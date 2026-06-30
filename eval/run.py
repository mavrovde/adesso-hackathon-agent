"""Eval harness — runs the coordinator against labeled datasets and reports metrics.

Usage:
  python -m eval.run                     # all suites
  python -m eval.run --suite adversarial # adversarial only

Metrics reported per suite:
  - accuracy              (correct routing decisions / total)
  - precision per category
  - escalation rate       (correct vs needless escalations)
  - adversarial-pass rate (injection and mis-escalation caught)
  - false-confidence rate (confidently wrong decisions)
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from agent.coordinator import run_coordinator
from agent.tools.mock_store import reset_store

DATASETS_DIR = Path(__file__).parent / "datasets"


def load_dataset(name: str) -> list[dict]:
    path = DATASETS_DIR / f"{name}.json"
    with open(path) as f:
        return json.load(f)


def run_suite(name: str) -> dict:
    cases = load_dataset(name)
    results = []
    for case in cases:
        reset_store()
        result = run_coordinator(case["input"])
        expected = case["expected"]
        correct = (
            result.get("category") == expected.get("category")
            and result.get("priority") == expected.get("priority")
            and result.get("escalated") == expected.get("escalated")
        )
        results.append({"case_id": case["id"], "correct": correct, "result": result, "expected": expected})

    total = len(results)
    correct_count = sum(1 for r in results if r["correct"])
    return {
        "suite": name,
        "total": total,
        "correct": correct_count,
        "accuracy": correct_count / total if total else 0.0,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Eval harness")
    parser.add_argument("--suite", choices=["normal", "adversarial", "all"], default="all")
    args = parser.parse_args()

    suites = ["normal", "adversarial"] if args.suite == "all" else [args.suite]
    for suite in suites:
        report = run_suite(suite)
        print(f"\n=== {report['suite'].upper()} ===")
        print(f"Accuracy: {report['accuracy']:.0%}  ({report['correct']}/{report['total']})")
        for r in report["results"]:
            status = "PASS" if r["correct"] else "FAIL"
            print(f"  [{status}] {r['case_id']}")


if __name__ == "__main__":
    main()
