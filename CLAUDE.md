# ClauseGuard

Multi-agent contract & policy review pipeline. Upload a PDF, get back a
structured risk report: extracted clauses, rule violations, and a
plain-English executive summary with a verdict.

See also: [ARCHITECTURE.md](ARCHITECTURE.md) (why three agents / why
LangGraph) and [FLOW.md](FLOW.md) (the exact data flow, state shape, and
routing).

## Layout

```
clauseguard/          the package -- see clauseguard/CLAUDE.md
  models/              Pydantic schemas shared by every agent hand-off
  agents/               Extractor, Risk Analyzer, Summarizer + LangGraph wiring
  rules/                 the configurable rule set the Risk Analyzer checks against
  storage/                SQLite audit history
  llm.py                   LLM wrapper, Ollama or Anthropic (the one place tests mock)
  main.py                   FastAPI app (GET / web UI, POST /review, GET /reviews)
  static/index.html          the web UI -- one file, vanilla JS, no build step
tests/                 pytest, all LLM calls mocked -- no API key needed to run these
sample_docs/           one synthetic NDA for local testing
scripts/demo.py        runs the pipeline standalone, no server, real LLM calls
```

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
```

Two LLM providers, picked via `CLAUSEGUARD_LLM_PROVIDER` (see
[clauseguard/llm.py](clauseguard/llm.py)):

- **ollama** (default if `ANTHROPIC_API_KEY` is unset) -- free, local, no
  key. Needs `ollama serve` running and a model pulled
  (`ollama pull qwen2.5:14b`).
- **anthropic** (default if `ANTHROPIC_API_KEY` is set) -- paid, needs a
  key from console.anthropic.com in `.env`. Higher-quality extraction and
  risk analysis than a small local model.

## Running

```bash
uvicorn clauseguard.main:app --reload
# web UI: http://127.0.0.1:8000   API docs: http://127.0.0.1:8000/docs
```

Or run the pipeline directly against the sample contract (no server, real
LLM calls):

```bash
python scripts/demo.py
```

## Tests

```bash
pytest
```

Every agent test monkeypatches `call_llm` in that agent's module, so the
whole suite runs offline with no API key.

## Conventions

- Every hand-off between agents is a Pydantic model (`clauseguard/models/schemas.py`).
  An agent that returns malformed JSON fails validation immediately at that
  agent's boundary, not somewhere downstream.
- Agents never call an LLM backend directly -- they call `clauseguard.llm.call_llm`,
  which is the one seam tests replace.
- `.env` is loaded once in `clauseguard/__init__.py`; real environment variables override it.
- The rule set is data (`clauseguard/rules/default_rules.json`), not code --
  point `CLAUSEGUARD_RULES_FILE` at a different file to review a different
  document type without touching the Risk Analyzer.
