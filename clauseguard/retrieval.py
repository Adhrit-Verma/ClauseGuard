"""Keyword index for matching rules to clauses by content (BM25, plain Python).

The Extractor's clause-type label is often wrong on documents it wasn't tuned for (an offer letter got
13 of 18 clauses labeled "termination"), so the Risk Analyzer uses this to find candidate clauses for
each rule by shared words, not only by label. The LLM checklist then verifies -- in effect reranks --
just those candidates. The index is built per document over its clauses; nothing is persisted."""

import math
import re
from collections import Counter

_WORD = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    # ponytail: plural-"s" stripping instead of a stemmer -- "renews" matches "renew", "renewal" doesn't.
    return [w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in _WORD.findall(text.lower())]


def bm25_scores(query: list[str], documents: list[list[str]], k1: float = 1.5, b: float = 0.75) -> list[float]:
    """BM25 relevance of each tokenized document to the tokenized query; 0.0 means no shared terms."""
    if not documents:
        return []
    avg_len = sum(len(doc) for doc in documents) / len(documents) or 1.0
    doc_freq = Counter(term for doc in documents for term in set(doc))
    scores = []
    for doc in documents:
        counts = Counter(doc)
        score = 0.0
        for term in set(query):
            tf = counts.get(term)
            if tf:
                idf = math.log(1 + (len(documents) - doc_freq[term] + 0.5) / (doc_freq[term] + 0.5))
                score += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len(doc) / avg_len))
        scores.append(score)
    return scores
