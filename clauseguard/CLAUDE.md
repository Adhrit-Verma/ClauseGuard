# clauseguard/ (package root)

- `main.py` -- FastAPI app. `POST /review` accepts a PDF upload, extracts
  text with pdfplumber, runs the LangGraph pipeline (`agents/graph.py`),
  persists the report (`storage/db.py`), returns it. `GET /reviews` and
  `GET /reviews/{id}` read audit history back out.
- `llm.py` -- the only file that talks to an LLM backend. Two providers,
  switched by `CLAUSEGUARD_LLM_PROVIDER` (`anthropic` or `ollama`, see the
  module docstring for defaults). Exposes `call_llm(system, user) -> str`
  and `parse_json_response(text) -> dict` (strips markdown code fences
  before `json.loads`). Every agent imports `call_llm` from here and every
  agent test monkeypatches it there -- agent code never knows which
  provider is active.

Subpackages: [models/](models/CLAUDE.md), [agents/](agents/CLAUDE.md),
[rules/](rules/CLAUDE.md), [storage/](storage/CLAUDE.md).
