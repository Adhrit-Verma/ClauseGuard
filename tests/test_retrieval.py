import pytest

from clauseguard import llm, retrieval
from clauseguard.models.schemas import Clause, ClauseType, Rule, Severity

NON_COMPETE = Rule(
    id="overbroad_non_compete",
    name="Overbroad non-compete",
    applies_to=ClauseType.NON_COMPETE,
    description="Flag non-competes longer than 12 months.",
    severity=Severity.HIGH,
    keywords=["compete", "competitor"],
)
PROBATION = Rule(
    id="open_ended_probation",
    name="Open-ended probation",
    applies_to=ClauseType.PROBATION,
    description="Flag probation that can be extended without limit.",
    severity=Severity.LOW,
    keywords=["probation"],
)


@pytest.fixture(autouse=True)
def clear_vector_cache():
    retrieval._vector_cache.clear()


def test_tokenize_lowercases_and_strips_plural_s():
    assert retrieval.tokenize("Auto-Renews, Fees & Business") == ["auto", "renew", "fee", "business"]


def test_bm25_scores_only_clauses_sharing_query_terms():
    documents = [
        retrieval.tokenize("The employee shall not join a competitor."),
        retrieval.tokenize("Salary is paid monthly."),
    ]
    scores = retrieval.bm25_scores(retrieval.tokenize("competitor compete"), documents)
    assert scores[0] > 0 and scores[1] == 0


def test_bm25_rarer_shared_term_scores_higher():
    documents = [retrieval.tokenize("notice period notice"), retrieval.tokenize("employee notice"),
                 retrieval.tokenize("employee bond repay")]
    scores = retrieval.bm25_scores(retrieval.tokenize("bond employee"), documents)
    assert scores[2] > scores[1] > scores[0] == 0


def test_cosine_scores_rank_by_direction_not_length():
    scores = retrieval.cosine_scores([1.0, 0.0], [[5.0, 0.0], [0.0, 3.0], [1.0, 1.0]])
    assert scores[0] == pytest.approx(1.0)
    assert scores[1] == pytest.approx(0.0)
    assert 0 < scores[2] < 1


def test_rrf_fuse_prefers_what_both_rankings_rate_highly():
    assert retrieval.rrf_fuse([[2, 0, 1], [2, 1, 0]])[0] == 2  # top of both
    assert retrieval.rrf_fuse([[0, 1], [1]])[0] == 1  # in both rankings beats first in only one
    assert sorted(retrieval.rrf_fuse([[0], [1]])) == [0, 1]  # nothing dropped


def test_candidate_pairs_without_embeddings_uses_type_and_keywords(monkeypatch):
    monkeypatch.setattr(llm, "embed", lambda texts: None)
    clauses = [
        Clause(id="c1", type=ClauseType.PROBATION, text="Probation lasts six months."),
        Clause(id="c2", type=ClauseType.OTHER, text="You shall not join a competitor for two years."),
    ]

    pairs = retrieval.candidate_pairs(clauses, [NON_COMPETE, PROBATION])

    # No padding: a clause sharing no words with a rule is not pulled in just to fill its top-k.
    assert {(c.id, r.id, how) for c, r, how in pairs} == {
        ("c1", PROBATION.id, "type"),
        ("c2", NON_COMPETE.id, "keyword"),
    }


def test_embeddings_find_a_clause_that_shares_no_keywords(monkeypatch):
    # Paraphrased clause: no shared words with the rule's keywords, but semantically the same.
    paraphrase = "Staff may not join a rival firm for two years."
    def fake_embed(texts):
        return [[1.0, 0.0] if ("rival" in t.lower() or "compete" in t.lower()) else [0.0, 1.0] for t in texts]

    monkeypatch.setattr(llm, "embed", fake_embed)
    clauses = [
        Clause(id="c1", type=ClauseType.OTHER, text="Salary is paid monthly."),
        Clause(id="c2", type=ClauseType.OTHER, text=paraphrase),
    ]

    pairs = retrieval.candidate_pairs(clauses, [NON_COMPETE])
    matched = {c.id: how for c, r, how in pairs}

    assert retrieval.bm25_scores(retrieval.tokenize(paraphrase), [retrieval.tokenize(" ".join(NON_COMPETE.keywords))]) == [0.0]
    assert matched["c2"] == "hybrid"


def test_vectors_are_cached_so_repeat_text_is_embedded_once(monkeypatch):
    calls = []

    def counting_embed(texts):
        calls.append(list(texts))
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(llm, "embed", counting_embed)
    retrieval._vectors(["a", "b", "a"])
    retrieval._vectors(["b", "c"])

    assert calls == [["a", "b"], ["c"]]
