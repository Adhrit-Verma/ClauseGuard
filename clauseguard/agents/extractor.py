"""Extractor agent: turns raw contract text into a list of labeled clauses."""

from clauseguard.llm import call_llm, parse_json_response
from clauseguard.models.schemas import ExtractionResult

SYSTEM_PROMPT = """You are a contract clause extraction engine. Given the raw \
text of a contract or policy document, identify each distinct clause and \
classify it into one of these types: termination, liability, payment_terms, \
confidentiality, indemnity, auto_renewal, governing_law, other.

Respond with ONLY a JSON object of this exact shape, no prose:
{"clauses": [{"id": "c1", "type": "<type>", "text": "<verbatim clause text>", "confidence": 0.0-1.0}]}

Use confidence below 0.7 when a clause is ambiguous or doesn't cleanly match a type. \
If the document has no identifiable clauses, return {"clauses": []}."""


def extract_clauses(document_text: str) -> ExtractionResult:
    user_prompt = f"Document text:\n\n{document_text}"
    raw = call_llm(SYSTEM_PROMPT, user_prompt)
    data = parse_json_response(raw)
    return ExtractionResult.model_validate(data)
