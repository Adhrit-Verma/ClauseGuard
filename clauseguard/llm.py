"""Thin wrapper around whichever LLM backend is configured. Every agent
calls call_llm() and then validates the JSON it gets back against a
Pydantic schema -- this is the module tests monkeypatch to avoid live API
calls.

Two providers supported via CLAUSEGUARD_LLM_PROVIDER:
- "anthropic" (default when ANTHROPIC_API_KEY is set) -- paid, needs a key.
- "ollama" (default otherwise) -- free, local, needs `ollama serve` running
  and the model pulled (`ollama pull qwen2.5:14b`).
"""

import json
import os
import re
import urllib.request

_DEFAULT_MODELS = {"anthropic": "claude-sonnet-5", "ollama": "qwen2.5:14b"}

PROVIDER = os.environ.get(
    "CLAUSEGUARD_LLM_PROVIDER", "anthropic" if os.environ.get("ANTHROPIC_API_KEY") else "ollama"
)
MODEL = os.environ.get("CLAUSEGUARD_MODEL", _DEFAULT_MODELS[PROVIDER])
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
# Per-call read timeout. A cold qwen2.5:14b load on a mostly-CPU machine exceeded 180s; tune per machine.
OLLAMA_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "600"))

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


def _call_ollama(system: str, user: str) -> str:
    payload = json.dumps(
        {"model": MODEL, "system": system, "prompt": user, "stream": False, "format": "json"}
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{OLLAMA_HOST}/api/generate", data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=OLLAMA_TIMEOUT) as response:
        data = json.loads(response.read())
    return data["response"]


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
