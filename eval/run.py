"""Eval harness — runs the coordinator against labeled datasets and reports metrics.

Usage:
  python -m eval.run                     # all suites
  python -m eval.run --suite adversarial # adversarial only
  python -m eval.run --suite overrides   # overrides only

Metrics reported per suite:
  - accuracy              (correct routing decisions / total)
  - precision per category
  - recall per category
  - escalation rate       (correct vs needless escalations)
  - adversarial-pass rate (injection and mis-escalation caught)
  - false-confidence rate (confidently wrong decisions)
"""
from __future__ import annotations
import argparse
import json
from collections import defaultdict
from pathlib import Path

from agent.coordinator import run_coordinator
from agent.tools.mock_store import reset_store

DATASETS_DIR = Path(__file__).parent / "datasets"


def load_dataset(name: str) -> list[dict]:
    path = DATASETS_DIR / f"{name}.json"
    if not path.exists() or path.stat().st_size == 0:
        return []
    with open(path) as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


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
        results.append({"case_id": case["id"], "correct": correct, "result": result, "expected": expected, "input": case.get("input", "")})

    total = len(results)
    correct_count = sum(1 for r in results if r["correct"])
    accuracy = correct_count / total if total else 0.0

    # precision and recall per category
    # precision: correct in cat / total predicted as cat
    # recall: correct in cat / total actual cat
    cat_tp: dict[str, int] = defaultdict(int)
    cat_predicted: dict[str, int] = defaultdict(int)
    cat_actual: dict[str, int] = defaultdict(int)

    for r in results:
        predicted_cat = r["result"].get("category")
        actual_cat = r["expected"].get("category")
        if predicted_cat:
            cat_predicted[predicted_cat] += 1
        if actual_cat:
            cat_actual[actual_cat] += 1
        if predicted_cat and actual_cat and predicted_cat == actual_cat:
            cat_tp[predicted_cat] += 1

    all_categories = set(cat_predicted.keys()) | set(cat_actual.keys())
    precision_per_category: dict[str, float] = {}
    recall_per_category: dict[str, float] = {}
    for cat in all_categories:
        precision_per_category[cat] = cat_tp[cat] / cat_predicted[cat] if cat_predicted[cat] else 0.0
        recall_per_category[cat] = cat_tp[cat] / cat_actual[cat] if cat_actual[cat] else 0.0

    # escalation rate metrics
    total_escalated = 0
    should_have_escalated = 0
    needless_escalations = 0
    missed_escalations = 0
    for r in results:
        result_escalated = bool(r["result"].get("escalated", False))
        expected_escalated = bool(r["expected"].get("escalated", False))
        if result_escalated:
            total_escalated += 1
        if expected_escalated:
            should_have_escalated += 1
        if result_escalated and not expected_escalated:
            needless_escalations += 1
        if not result_escalated and expected_escalated:
            missed_escalations += 1

    escalation_rate = {
        "total_escalated": total_escalated,
        "should_have_escalated": should_have_escalated,
        "needless_escalations": needless_escalations,
        "missed_escalations": missed_escalations,
    }

    # false confidence rate: fraction of wrong decisions where confidence > 0.75
    wrong_results = [r for r in results if not r["correct"]]
    wrong_with_confidence = [r for r in wrong_results if r["result"].get("confidence") is not None]
    high_conf_wrong = [r for r in wrong_with_confidence if float(r["result"]["confidence"]) > 0.75]
    false_confidence_rate = len(high_conf_wrong) / len(wrong_with_confidence) if wrong_with_confidence else 0.0

    # adversarial pass rate: fraction where injection_blocked=True if expected injection_blocked=True
    adversarial_cases = [r for r in results if r["expected"].get("injection_blocked") is True]
    if adversarial_cases:
        passed_adversarial = sum(1 for r in adversarial_cases if r["result"].get("injection_blocked") is True)
        adversarial_pass_rate: float | None = passed_adversarial / len(adversarial_cases)
    else:
        adversarial_pass_rate = None

    return {
        "suite": name,
        "total": total,
        "correct": correct_count,
        "accuracy": accuracy,
        "precision_per_category": precision_per_category,
        "recall_per_category": recall_per_category,
        "escalation_rate": escalation_rate,
        "false_confidence_rate": false_confidence_rate,
        "adversarial_pass_rate": adversarial_pass_rate,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Eval harness")
    parser.add_argument("--suite", choices=["normal", "adversarial", "overrides", "all"], default="all")
    args = parser.parse_args()

    suites = ["normal", "adversarial", "overrides"] if args.suite == "all" else [args.suite]
    for suite in suites:
        report = run_suite(suite)
        print(f"\n=== {report['suite'].upper()} ===")
        if report["total"] == 0:
            print("  No cases found in this suite. (Run human overrides to populate 'overrides')")
            continue

        esc = report["escalation_rate"]
        print(f"Accuracy: {report['accuracy']:.0%}  ({report['correct']}/{report['total']})")
        print(f"Escalation: {esc['total_escalated']} escalated | {esc['needless_escalations']} needless | {esc['missed_escalations']} missed")
        print(f"False-confidence rate: {report['false_confidence_rate']:.1%}")

        prec = report["precision_per_category"]
        if prec:
            parts = "  ".join(f"{cat}={v:.0%}" for cat, v in sorted(prec.items()))
            print(f"Precision per category: {parts}")

        rec = report["recall_per_category"]
        if rec:
            parts = "  ".join(f"{cat}={v:.0%}" for cat, v in sorted(rec.items()))
            print(f"Recall per category: {parts}")

        if report["adversarial_pass_rate"] is not None:
            print(f"Adversarial pass rate: {report['adversarial_pass_rate']:.0%}")

        for r in report["results"]:
            status = "PASS" if r["correct"] else "FAIL"
            description = str(r.get("input", ""))[:60]
            print(f"  [{status}] {r['case_id']}: {description}")


if __name__ == "__main__":
    main()
