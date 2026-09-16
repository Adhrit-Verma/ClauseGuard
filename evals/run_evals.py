"""Run the pipeline over labeled sample documents and report accuracy, speed and cost.

Unlike the pytest suite (which mocks every model call), this calls the real model -- it measures the
model's judgment, not the code's wiring. Use it to compare prompts, models or retrieval settings:
change one thing, run it again, compare the numbers.

    python evals/run_evals.py                      # all cases
    python evals/run_evals.py --case offer         # cases whose name contains "offer"
    python evals/run_evals.py --json report.json   # also write the raw numbers
    python evals/run_evals.py --min-recall 0.7     # exit 1 if mean recall falls below

Scores are rule-level: did the rule that should have fired, fire at all. Misses (recall) matter more
than extra flags (precision) for a first-pass review tool, but both are reported.
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clauseguard import llm  # noqa: E402
from clauseguard.agents.graph import run_review  # noqa: E402


def run_case(case: dict) -> dict:
    text = (ROOT / case["path"]).read_text(encoding="utf-8")
    started = time.perf_counter()
    with llm.collect_calls() as calls:
        try:
            state = run_review(text)
        except Exception as exc:
            return {"name": case["name"], "error": f"{type(exc).__name__}: {exc}"[:200],
                    "seconds": round(time.perf_counter() - started, 1), **llm.summarize_calls(calls)}

    expected = set(case["expected_findings"])
    found = {finding.rule_id for finding in state["findings"]}
    hits = expected & found
    return {
        "name": case["name"],
        "clauses": len(state["clauses"]),
        "expected_clauses": case["expected_clauses"],
        "recall": round(len(hits) / len(expected), 2) if expected else 1.0,
        "precision": round(len(hits) / len(found), 2) if found else 0.0,
        "missed": sorted(expected - found),
        "unexpected": sorted(found - expected),
        "verdict": state["summary"].verdict.value,
        "seconds": round(time.perf_counter() - started, 1),
        **llm.summarize_calls(calls),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", help="only cases whose name contains this")
    parser.add_argument("--json", type=Path, help="write raw results here")
    parser.add_argument("--min-recall", type=float, help="exit 1 if mean recall is below this")
    args = parser.parse_args()

    cases = json.loads((Path(__file__).parent / "cases.json").read_text(encoding="utf-8"))
    if args.case:
        cases = [c for c in cases if args.case.lower() in c["name"].lower()]
    if not cases:
        print("no matching cases")
        return 1

    print(f"model={llm.MODEL} provider={llm.PROVIDER} retrieval={'hybrid' if llm.embeddings_ready() else 'keywords only'}\n")
    results = [run_case(case) for case in cases]

    for r in results:
        if "error" in r:
            print(f"{r['name']}: ERROR {r['error']}")
            continue
        print(f"{r['name']}")
        print(f"  clauses     {r['clauses']} (expected {r['expected_clauses']})")
        print(f"  recall      {r['recall']:.0%}   missed: {', '.join(r['missed']) or 'none'}")
        print(f"  precision   {r['precision']:.0%}   unexpected: {', '.join(r['unexpected']) or 'none'}")
        print(f"  verdict     {r['verdict']}")
        print(f"  cost        {r['seconds']}s wall, {r['model_seconds']}s in model, {r['calls']} calls, "
              f"{r['prompt_tokens'] + r['output_tokens']} tokens, ${r['cost_usd']}")

    scored = [r for r in results if "recall" in r]
    mean_recall = sum(r["recall"] for r in scored) / len(scored) if scored else 0.0
    mean_precision = sum(r["precision"] for r in scored) / len(scored) if scored else 0.0
    print(f"\nmean recall {mean_recall:.0%}, mean precision {mean_precision:.0%}, {len(results) - len(scored)} errored")

    if args.json:
        args.json.write_text(json.dumps({"results": results, "mean_recall": mean_recall,
                                         "mean_precision": mean_precision}, indent=2), encoding="utf-8")
        print(f"wrote {args.json}")

    if args.min_recall is not None and mean_recall < args.min_recall:
        print(f"FAIL: mean recall {mean_recall:.0%} below --min-recall {args.min_recall:.0%}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
