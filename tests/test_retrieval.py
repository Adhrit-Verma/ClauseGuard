from clauseguard.retrieval import bm25_scores, tokenize


def test_tokenize_lowercases_and_strips_plural_s():
    assert tokenize("Auto-Renews, Fees & Business") == ["auto", "renew", "fee", "business"]


def test_bm25_scores_only_clauses_sharing_query_terms():
    documents = [
        tokenize("The employee shall not join a competitor."),
        tokenize("Salary is paid monthly."),
        tokenize("The employee may resign with notice."),
    ]
    scores = bm25_scores(tokenize("competitor compete"), documents)
    assert scores[0] > 0 and scores[1] == 0 and scores[2] == 0


def test_bm25_rarer_shared_term_scores_higher():
    documents = [tokenize("notice period notice"), tokenize("employee notice"), tokenize("employee bond repay")]
    scores = bm25_scores(tokenize("bond employee"), documents)
    assert scores[2] > scores[1] > scores[0] == 0  # "bond" (1 doc) outweighs "employee" (2 docs)


def test_bm25_empty_documents():
    assert bm25_scores(["x"], []) == []
