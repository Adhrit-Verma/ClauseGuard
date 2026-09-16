# evals/

Accuracy measurement against the real model. The pytest suite mocks every
LLM call and tests the code; this tests the *model's judgment* -- whether a
prompt, model or retrieval change actually finds more real violations.

```bash
python evals/run_evals.py                      # all cases
python evals/run_evals.py --case offer         # filter by name
python evals/run_evals.py --json report.json   # raw numbers
python evals/run_evals.py --min-recall 0.7     # non-zero exit below the bar
```

- `cases.json` -- labeled documents: the clause count a correct extraction
  finds, and every rule that *should* fire. Scoring is rule-level (did the
  rule fire at all), not per-clause, which keeps labeling cheap enough that
  the set actually gets maintained.
- `run_evals.py` -- runs each case, reports recall, precision, extracted
  clause count, verdict, wall/model seconds, calls, tokens and cost
  (`llm.collect_calls`), then means across cases.

Recall is the number that matters: a missed risky clause is the failure this
tool exists to prevent, while an extra flag costs a human a few seconds.

Adding a case: drop the document in `sample_docs/`, list the rules that
should fire, and keep it synthetic -- these files are committed, so no real
contracts or offer letters.

Expect run-to-run variation even at temperature 0 (measured: the same NDA
scored 4-7 findings across runs), so treat a single run as a sample, not a
verdict. Compare a few runs before concluding a change helped.
