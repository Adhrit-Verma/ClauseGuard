# ClauseGuard

Multi-agent contract & policy review pipeline. Upload a PDF, get back a
structured risk report: extracted clauses, rule violations, and a
plain-English executive summary with a verdict.

Three LangGraph agents do the work — **Extractor** segments the document
into labeled clauses, **Risk Analyzer** checks each clause against a
configurable rule set, **Summarizer** writes the verdict and summary. Every
hand-off between them is validated against a Pydantic schema.

![verdict](https://img.shields.io/badge/verdict-high__risk-b91c1c) ![tests](https://img.shields.io/badge/tests-23%20passing-2f855a)

## Why

Legal/procurement/compliance teams manually read long contracts to spot
risky clauses (auto-renewal traps, low liability caps, one-sided
indemnity). Slow, inconsistent between reviewers, doesn't scale.
ClauseGuard automates the first pass so a human reviewer starts from a
report instead of a blank document. See [ARCHITECTURE.md](ARCHITECTURE.md)
for the full design rationale (including why LangGraph over a plain
script) and [FLOW.md](FLOW.md) for the exact data flow.

## Quickstart

```bash
python -m venv .venv
source .venv/Scripts/activate      # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
```

Pick an LLM backend (see [clauseguard/llm.py](clauseguard/llm.py)):

- **Ollama** (free, local, default when no key is set) — install from
  [ollama.com](https://ollama.com), then:
  ```bash
  ollama pull qwen2.5:7b
  ```
- **Anthropic** (paid, better quality) — put `ANTHROPIC_API_KEY` in `.env`.

Then start everything with one command:

```bash
python scripts/start.py
```

This checks Ollama is running (starting `ollama serve` and pulling the
model if needed — skipped entirely if you're using Anthropic), launches
the FastAPI server, and opens **http://127.0.0.1:8000** in your browser.
Drop in `sample_docs/sample_nda.pdf` and watch the pipeline extract
clauses, flag risks, and write a summary. API docs are at `/docs`.

(`uvicorn clauseguard.main:app --reload` also works if you'd rather run
the server directly — just make sure Ollama is already up first.)

Or skip the server entirely:

```bash
python scripts/demo.py
```

## Tests

```bash
pytest
```

23 tests, every LLM call mocked — no API key or running model needed.

## Project layout

```
clauseguard/
  models/       Pydantic schemas shared by every agent hand-off
  agents/       Extractor, Risk Analyzer, Summarizer + LangGraph wiring
  rules/        the configurable rule set the Risk Analyzer checks against
  storage/      SQLite audit history
  static/       the web UI (one HTML file, vanilla JS, no build step)
  llm.py        LLM wrapper -- Ollama or Anthropic, one seam tests mock
  main.py       FastAPI app (web UI, POST /review, GET /reviews)
tests/          pytest, offline
sample_docs/    a synthetic NDA (.txt and .pdf) for local testing
scripts/start.py   one-command launch: Ollama + server + browser
scripts/demo.py    runs the pipeline standalone, no server
```

Every folder has its own `CLAUDE.md` with more detail. Start at the root
[CLAUDE.md](CLAUDE.md).

## Known gaps

No retry when the model returns malformed JSON, no OCR for scanned PDFs,
no human-review queue for low-confidence extractions. See
[ARCHITECTURE.md](ARCHITECTURE.md#failure-modes-and-what-to-do-about-them)
for the reasoning behind each.

## License

MIT
