"""Retrieval: which (clause, rule) pairs are worth asking the model about.

Three signals, in order of cost: the Extractor's clause-type label, BM25 keyword scoring, and -- when
an embedding model is installed -- cosine similarity over embeddings. The last two are merged with
reciprocal rank fusion (hybrid search), so a clause is found either by the words it shares with a
rule or by meaning.

Why retrieval at all: the type label is unreliable on unfamiliar documents (an offer letter got 13 of
18 clauses labeled "termination"), which left rules checking nothing. Clauses are the chunks -- the
Extractor already split the document on clause boundaries, so nothing is re-chunked here.

Embeddings are optional. With no embedding model, `llm.embed()` returns None and this degrades to
keyword-only retrieval instead of failing the review."""

import math
import re
from collections import Counter

from clauseguard import llm

_WORD = re.compile(r"[a-z0-9]+")

TOP_K_PER_RULE = 3
# Retrieval runs both ways: without this, a clause no rule ranked highly and whose type matches
# nothing is checked against nothing at all, and silently comes back clean.
RULES_PER_UNMATCHED_CLAUSE = 2
_RRF_K = 60  # standard reciprocal-rank-fusion constant

# ponytail: process-local embedding cache. Rules are re-embedded once per process; clause text is new
# each review anyway, so a persisted vector store would buy little here.
_vector_cache: dict[tuple[str, str], list[float]] = {}


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


def cosine_scores(query: list[float], documents: list[list[float]]) -> list[float]:
    """Cosine similarity of each document vector to the query vector, clamped at 0."""
    query_norm = math.sqrt(sum(q * q for q in query))
    scores = []
    for doc in documents:
        doc_norm = math.sqrt(sum(d * d for d in doc))
        if not query_norm or not doc_norm:
            scores.append(0.0)
            continue
        scores.append(max(0.0, sum(q * d for q, d in zip(query, doc)) / (query_norm * doc_norm)))
    return scores


def rrf_fuse(rankings: list[list[int]]) -> list[int]:
    """Reciprocal rank fusion: merges rankings from different scorers whose scores aren't comparable
    (BM25 is unbounded, cosine is 0-1) by using positions instead of values."""
    points: dict[int, float] = {}
    for ranking in rankings:
        for position, item in enumerate(ranking):
            points[item] = points.get(item, 0.0) + 1.0 / (_RRF_K + position + 1)
    return sorted(points, key=lambda item: -points[item])


def _ranked(scores: list[float]) -> list[int]:
    return [i for i in sorted(range(len(scores)), key=lambda j: -scores[j]) if scores[i] > 0]


def _vectors(texts: list[str]) -> list[list[float]] | None:
    unseen = [t for t in dict.fromkeys(texts) if (llm.EMBED_MODEL, t) not in _vector_cache]
    if unseen:
        fresh = llm.embed(unseen)
        if fresh is None or len(fresh) != len(unseen):
            return None
        _vector_cache.update({(llm.EMBED_MODEL, text): vector for text, vector in zip(unseen, fresh)})
    return [_vector_cache[(llm.EMBED_MODEL, text)] for text in texts]


def candidate_pairs(clauses: list, rules: list) -> list[tuple]:
    """(clause, rule, matched_by) triples worth checking, where matched_by is "type", "keyword" or
    "hybrid" -- kept so a finding can say how its clause was found."""
    clause_tokens = [tokenize(clause.text) for clause in clauses]
    rule_tokens = [tokenize(" ".join(rule.keywords)) if rule.keywords else tokenize(rule.name) for rule in rules]

    vectors = _vectors([c.text for c in clauses] + [f"{r.name}. {r.description}" for r in rules])
    clause_vectors = vectors[: len(clauses)] if vectors else None
    rule_vectors = vectors[len(clauses) :] if vectors else None
    how = "hybrid" if vectors else "keyword"

    found: dict[tuple[int, int], str] = {}
    for r, rule in enumerate(rules):
        for c, clause in enumerate(clauses):
            if clause.type == rule.applies_to:
                found.setdefault((c, r), "type")
        rankings = [_ranked(bm25_scores(rule_tokens[r], clause_tokens))]
        if rule_vectors and clause_vectors:
            rankings.append(_ranked(cosine_scores(rule_vectors[r], clause_vectors)))
        for c in rrf_fuse(rankings)[:TOP_K_PER_RULE]:
            found.setdefault((c, r), how)

    matched = {c for c, _ in found}
    for c in range(len(clauses)):
        if c in matched:
            continue
        rankings = [_ranked(bm25_scores(clause_tokens[c], rule_tokens))]
        if rule_vectors and clause_vectors:
            rankings.append(_ranked(cosine_scores(clause_vectors[c], rule_vectors)))
        for r in rrf_fuse(rankings)[:RULES_PER_UNMATCHED_CLAUSE]:
            found.setdefault((c, r), how)

    return [(clauses[c], rules[r], matched_by) for (c, r), matched_by in sorted(found.items())]
