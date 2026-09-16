"""Thin wrapper around whichever LLM backend is configured. Every agent
calls call_llm() and then validates the JSON it gets back against a
Pydantic schema -- this is the module tests monkeypatch to avoid live API
calls.

Two providers supported via CLAUSEGUARD_LLM_PROVIDER:
- "anthropic" (default when ANTHROPIC_API_KEY is set) -- paid, needs a key.
- "ollama" (default otherwise) -- free, local, needs `ollama serve` running
  and the model pulled (`ollama pull qwen2.5:7b`).
"""

import contextlib
import json
import logging
import os
import re
import threading
import time
import urllib.request

from clauseguard import guardrails

# qwen2.5:7b, not 14b: on a 6GB GPU 14b ran 73% on CPU (~4.6 tok/s, ~210s per review); 7b runs mostly
# on GPU (~22-25 tok/s). 3b is faster still but missed clauses and the most obvious risks in testing.
_DEFAULT_MODELS = {"anthropic": "claude-sonnet-5", "ollama": "qwen2.5:7b"}

PROVIDER = os.environ.get(
    "CLAUSEGUARD_LLM_PROVIDER", "anthropic" if os.environ.get("ANTHROPIC_API_KEY") else "ollama"
)
MODEL = os.environ.get("CLAUSEGUARD_MODEL", _DEFAULT_MODELS[PROVIDER])
# 127.0.0.1, not localhost: on Windows urllib tries ::1 first, Ollama listens on IPv4 only, and the
# refused IPv6 attempt costs ~2s per call (measured: 2.1s vs 0.003s).
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
# Per-call read timeout. A cold qwen2.5:14b load on a mostly-CPU machine exceeded 180s; tune per machine.
OLLAMA_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "600"))
# How long Ollama keeps the model in memory after a call. Reloading costs seconds to minutes;
# "-1" keeps it forever but pins the VRAM, so the default trades that for a long idle window.
OLLAMA_KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "30m")
# Fixed per process on purpose: a request with a different num_ctx makes Ollama reload the model.
# Bigger contexts reserve more VRAM and can push layers onto the CPU (several times slower).
# ponytail: documents longer than this many tokens get truncated by Ollama; raise it for long contracts.
OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "8192"))
# Embedding model for semantic retrieval (`ollama pull nomic-embed-text`). Optional: without it,
# retrieval falls back to keywords alone rather than failing reviews.
EMBED_MODEL = os.environ.get("CLAUSEGUARD_EMBED_MODEL", "nomic-embed-text")
# PII redaction before a prompt leaves this machine. "auto" redacts only for a remote provider --
# a local Ollama model never sends the document anywhere, so redacting it would just lose detail.
REDACT_PII = os.environ.get("CLAUSEGUARD_REDACT_PII", "auto")

_embeddings_available: bool | None = None  # None until the first attempt tells us

# Cost tracing. A local model is free, so these default to 0; set them (USD per million tokens) when
# pointing at a paid provider and summarize_calls() reports cost alongside tokens.
INPUT_COST_PER_MTOK = float(os.environ.get("CLAUSEGUARD_INPUT_COST_PER_MTOK", "0"))
OUTPUT_COST_PER_MTOK = float(os.environ.get("CLAUSEGUARD_OUTPUT_COST_PER_MTOK", "0"))

_call_log = threading.local()  # a review runs in one worker thread, so concurrent reviews stay separate


@contextlib.contextmanager
def collect_calls():
    """Collects model/token/latency stats for every LLM call made inside it (one review, one eval
    case). Nothing is recorded outside a collector, so agents never have to know about metrics."""
    previous = getattr(_call_log, "entries", None)
    _call_log.entries = []
    try:
        yield _call_log.entries
    finally:
        _call_log.entries = previous


def _record_call(model: str, prompt_tokens: int, output_tokens: int, seconds: float) -> None:
    entries = getattr(_call_log, "entries", None)
    if entries is not None:
        entries.append(
            {
                "model": model,
                "prompt_tokens": prompt_tokens or 0,
                "output_tokens": output_tokens or 0,
                "seconds": round(seconds, 2),
            }
        )


def summarize_calls(entries: list[dict]) -> dict:
    """Totals for one run: calls made, tokens in/out, seconds spent inside the model, and cost
    (0 on a local model unless per-token rates are configured)."""
    prompt_tokens = sum(entry["prompt_tokens"] for entry in entries)
    output_tokens = sum(entry["output_tokens"] for entry in entries)
    return {
        "calls": len(entries),
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "model_seconds": round(sum(entry["seconds"] for entry in entries), 1),
        "cost_usd": round(
            prompt_tokens / 1e6 * INPUT_COST_PER_MTOK + output_tokens / 1e6 * OUTPUT_COST_PER_MTOK, 4
        ),
    }

_anthropic_client = None


def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        from anthropic import Anthropic

        _anthropic_client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _anthropic_client


def _call_anthropic(system: str, user: str) -> str:
    started = time.perf_counter()
    response = _get_anthropic_client().messages.create(
        model=MODEL,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    _record_call(MODEL, response.usage.input_tokens, response.usage.output_tokens, time.perf_counter() - started)
    return response.content[0].text


def _ollama_generate(payload: dict) -> dict:
    body = {
        "model": MODEL,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        # num_predict caps a reply at the room prompt_budget() reserves for it: real replies stay well under,
        # and a model stuck repeating itself fails fast as malformed JSON instead of running to the timeout.
        "options": {"num_ctx": OLLAMA_NUM_CTX, "temperature": 0, "num_predict": _REPLY_TOKENS},
        **payload,
    }
    request = urllib.request.Request(
        f"{OLLAMA_HOST}/api/generate",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=OLLAMA_TIMEOUT) as response:
        data = json.loads(response.read())
    _record_call(body["model"], data.get("prompt_eval_count", 0), data.get("eval_count", 0), time.perf_counter() - started)
    return data


_REPLY_TOKENS = 1024


def prompt_budget(system: str) -> int:
    """Characters of user prompt that fit in one call next to `system`, leaving room for the reply.
    Agents split long documents to stay under it."""
    # ponytail: ~3.5 chars/token estimate, not a real tokenizer.
    context_tokens = OLLAMA_NUM_CTX if PROVIDER == "ollama" else 150_000
    return int((context_tokens - _REPLY_TOKENS) * 3.5) - len(system)


def _call_ollama(system: str, user: str) -> str:
    # Safety net: agents split input to prompt_budget, but Ollama would silently truncate (and drop
    # clauses from) anything that still overflows num_ctx, so refuse loudly instead.
    if len(user) > prompt_budget(system):
        raise RuntimeError(
            f"Part of this document is too long for one model call (OLLAMA_NUM_CTX={OLLAMA_NUM_CTX}). "
            "Raise OLLAMA_NUM_CTX in .env -- it uses more VRAM and can be slower."
        )
    return _ollama_generate({"system": system, "prompt": user, "stream": False, "format": "json"})["response"]


def embed(texts: list[str]) -> list[list[float]] | None:
    """Embedding vectors for `texts`, or None when no embedding model is available -- retrieval then
    uses keywords alone instead of the review failing over a missing optional model."""
    global _embeddings_available
    if PROVIDER != "ollama" or _embeddings_available is False or not texts:
        return None

    request = urllib.request.Request(
        f"{OLLAMA_HOST}/api/embed",
        data=json.dumps({"model": EMBED_MODEL, "input": texts}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=OLLAMA_TIMEOUT) as response:
            vectors = json.loads(response.read())["embeddings"]
        _record_call(EMBED_MODEL, 0, 0, time.perf_counter() - started)  # the embed API reports no token counts
    except (OSError, KeyError, ValueError):  # typically: model not pulled
        if _embeddings_available is None:
            logging.getLogger(__name__).info(
                "Embedding model %r unavailable (ollama pull %s); retrieval is keyword-only", EMBED_MODEL, EMBED_MODEL
            )
        _embeddings_available = False
        return None

    _embeddings_available = True
    return vectors


def embeddings_ready() -> bool:
    """Whether semantic retrieval is available; probes the model once if it hasn't been used yet."""
    if _embeddings_available is None:
        embed(["ping"])
    return bool(_embeddings_available)


def preload() -> None:
    """Loads the model into memory ahead of the first review (an empty prompt only loads it).
    Uses the same options as real calls, or the first review would trigger a reload anyway."""
    if PROVIDER == "ollama":
        _ollama_generate({"stream": False})


def redaction_on() -> bool:
    return REDACT_PII == "always" or (REDACT_PII == "auto" and PROVIDER != "ollama")


def call_llm(system: str, user: str) -> str:
    if redaction_on():
        user, _ = guardrails.redact_pii(user)
    if PROVIDER == "ollama":
        return _call_ollama(system, user)
    return _call_anthropic(system, user)


_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def parse_json_response(text: str) -> dict:
    """LLMs like to wrap JSON in markdown code fences -- strip that before parsing."""
    text = text.strip()
    match = _JSON_FENCE.search(text)
    if match:
        text = match.group(1).strip()
    return json.loads(text)
