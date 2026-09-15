"""Thin wrapper around whichever LLM backend is configured. Every agent
calls call_llm() and then validates the JSON it gets back against a
Pydantic schema -- this is the module tests monkeypatch to avoid live API
calls.

Two providers supported via CLAUSEGUARD_LLM_PROVIDER:
- "anthropic" (default when ANTHROPIC_API_KEY is set) -- paid, needs a key.
- "ollama" (default otherwise) -- free, local, needs `ollama serve` running
  and the model pulled (`ollama pull qwen2.5:7b`).
"""

import json
import os
import re
import urllib.request

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

_anthropic_client = None


def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        from anthropic import Anthropic

        _anthropic_client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _anthropic_client


def _call_anthropic(system: str, user: str) -> str:
    response = _get_anthropic_client().messages.create(
        model=MODEL,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return response.content[0].text


def _ollama_generate(payload: dict) -> dict:
    body = {
        "model": MODEL,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {"num_ctx": OLLAMA_NUM_CTX, "temperature": 0},
        **payload,
    }
    request = urllib.request.Request(
        f"{OLLAMA_HOST}/api/generate",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=OLLAMA_TIMEOUT) as response:
        return json.loads(response.read())


def _call_ollama(system: str, user: str) -> str:
    # ponytail: ~3.5 chars/token estimate, not a real tokenizer. Ollama silently truncates prompts that
    # overflow num_ctx (dropping clauses), so refuse loudly instead, keeping 1024 tokens for the reply.
    if (len(system) + len(user)) / 3.5 + 1024 > OLLAMA_NUM_CTX:
        raise RuntimeError(
            f"This document is too long for the model's context window (OLLAMA_NUM_CTX={OLLAMA_NUM_CTX}). "
            "Raise OLLAMA_NUM_CTX in .env -- it uses more VRAM and can be slower."
        )
    return _ollama_generate({"system": system, "prompt": user, "stream": False, "format": "json"})["response"]


def preload() -> None:
    """Loads the model into memory ahead of the first review (an empty prompt only loads it).
    Uses the same options as real calls, or the first review would trigger a reload anyway."""
    if PROVIDER == "ollama":
        _ollama_generate({"stream": False})


def call_llm(system: str, user: str) -> str:
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
