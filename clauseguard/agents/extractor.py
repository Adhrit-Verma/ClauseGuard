"""Extractor agent: turns raw contract text into a list of labeled clauses.

The model returns only where each clause begins (a line number) plus its type, never clause text:
echoing text back was most of this agent's run time, and asking for end lines added tokens without
adding accuracy. Each clause runs until the next one begins; code slices the text."""

import re

from clauseguard.llm import call_llm, parse_json_response
from clauseguard.models.schemas import Clause, ClauseSpan, ClauseSpans, ExtractionResult

SYSTEM_PROMPT = """You are a contract clause extraction engine. The document is given as numbered \
lines. Identify each distinct clause and classify it as one of: termination, liability, \
payment_terms, confidentiality, indemnity, auto_renewal, governing_law, other.

Respond with ONLY JSON, no prose. One row per clause, giving the line where the clause BEGINS \
(it runs until the next clause begins): [type, first line, confidence 0-1]:
{"clauses": [["<type>", <first line>, <confidence>]]}

Skip titles and headings that are not clauses. Use confidence below 0.7 when a clause is \
ambiguous. If there are no clauses, return {"clauses": []}."""

_HEADING = re.compile(r"^(\d+(\.\d+)*[.)]|section\s+\d+|article\s+\w+)\s", re.IGNORECASE)


def extract_clauses(document_text: str) -> ExtractionResult:
    lines = [line.strip() for line in document_text.splitlines() if line.strip()]
    numbered = "\n".join(f"{i}: {line}" for i, line in enumerate(lines, start=1))
    spans = ClauseSpans.model_validate(parse_json_response(call_llm(SYSTEM_PROMPT, numbered)))

    starts: dict[int, ClauseSpan] = {}
    for span in spans.clauses:
        if span.start <= len(lines):
            starts.setdefault(span.start, span)

    # ponytail: the model reliably points one line past a numbered heading ("12: 4. Indemnification..." -> 13).
    # Snap back when the line above is an unclaimed heading. Unnumbered contracts get no such correction.
    for start in sorted(starts):
        above = start - 1
        if above >= 1 and above not in starts and not _HEADING.match(lines[start - 1]) and _HEADING.match(lines[above - 1]):
            starts[above] = starts.pop(start)

    # ponytail: trailing non-clause text (e.g. a signature block) is absorbed into the last clause.
    ordered = sorted(starts.items())
    clauses = []
    for k, (start, span) in enumerate(ordered):
        end = ordered[k + 1][0] - 1 if k + 1 < len(ordered) else len(lines)
        text = " ".join(lines[start - 1 : end])
        clauses.append(Clause(id=f"c{k + 1}", type=span.type, text=text, confidence=span.confidence))
    return ExtractionResult(clauses=clauses)
