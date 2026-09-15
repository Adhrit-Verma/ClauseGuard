"""Run the pipeline directly against a sample contract, no server or PDF
needed. Requires ANTHROPIC_API_KEY to be set (it makes real LLM calls).

Usage: python scripts/demo.py [path/to/document.txt]
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clauseguard.agents.graph import run_review  # noqa: E402


def main() -> None:
    doc_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "sample_docs" / "sample_nda.txt"
    text = doc_path.read_text(encoding="utf-8")

    state = run_review(text)

    print(f"\n=== ClauseGuard review: {doc_path.name} ===\n")
    print(f"Clauses extracted: {len(state['clauses'])}")
    for clause in state["clauses"]:
        print(f"  [{clause.type.value}] {clause.text[:80]}...")

    print(f"\nRisk findings: {len(state['findings'])}")
    for finding in state["findings"]:
        print(f"  [{finding.severity.value}] {finding.rule_name}: {finding.explanation}")

    print("\nExecutive summary:")
    print(json.dumps(state["summary"].model_dump(), indent=2))


if __name__ == "__main__":
    main()
