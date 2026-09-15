# clauseguard/ (package root)

- `main.py` -- FastAPI app. `GET /` serves `static/index.html`;
  `GET /api/info` reports the active provider/model. `POST /review` accepts
  a PDF upload, extracts text with pdfplumber, runs the LangGraph pipeline
  (`agents/graph.py`), persists the report (`storage/db.py`), returns it.
  Failures map to status codes the UI shows verbatim: 400 not a readable
  PDF, 422 no text (scanned), 503 LLM unreachable, 504 model timed out
  (`OLLAMA_TIMEOUT`, default 600s), 502 malformed model output.
  The pipeline runs via `asyncio.to_thread` -- calling it directly inside
  the async endpoint blocks the event loop for the whole review (minutes)
  and freezes every other request. `GET /reviews` and `GET /reviews/{id}`
  read audit history back out.
- `static/index.html` -- the whole web UI: upload, loading state, report
  (verdict, findings by severity, clauses), and a past-reviews sidebar.
  Vanilla JS, no build step. Renders all model output via `textContent`
  since it derives from an untrusted PDF -- keep it that way (no `innerHTML`).
- `llm.py` -- the only file that talks to an LLM backend. Two providers,
  switched by `CLAUSEGUARD_LLM_PROVIDER` (`anthropic` or `ollama`, see the
  module docstring for defaults). Exposes `call_llm(system, user) -> str`
  and `parse_json_response(text) -> dict` (strips markdown code fences
  before `json.loads`). Every agent imports `call_llm` from here and every
  agent test monkeypatches it there -- agent code never knows which
  provider is active.

Subpackages: [models/](models/CLAUDE.md), [agents/](agents/CLAUDE.md),
[rules/](rules/CLAUDE.md), [storage/](storage/CLAUDE.md).
