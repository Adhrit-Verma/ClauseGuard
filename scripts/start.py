"""One-command startup: makes sure the configured LLM backend is reachable,
then launches the FastAPI server and opens the web UI.

Usage: python scripts/start.py
"""

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clauseguard import llm  # noqa: E402  (importing clauseguard loads .env as a side effect)

UI_URL = "http://127.0.0.1:8000"
STARTUP_TIMEOUT_S = 30


def _reachable(url: str, timeout: float = 1.5) -> bool:
    try:
        urllib.request.urlopen(url, timeout=timeout)
        return True
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return False


def _wait_until_reachable(url: str, timeout_s: int) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _reachable(url):
            return True
        time.sleep(1)
    return False


def _ensure_ollama_running() -> None:
    tags_url = f"{llm.OLLAMA_HOST}/api/tags"
    if _reachable(tags_url):
        print(f"Ollama already running at {llm.OLLAMA_HOST}")
        return

    if not shutil.which("ollama"):
        sys.exit(
            "Ollama isn't installed or not on PATH. Install it from https://ollama.com, "
            "then re-run this script (or set ANTHROPIC_API_KEY in .env to use Anthropic instead)."
        )

    print("Ollama isn't responding -- starting `ollama serve`...")
    subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )

    if not _wait_until_reachable(tags_url, STARTUP_TIMEOUT_S):
        sys.exit(f"Timed out waiting for Ollama to come up at {llm.OLLAMA_HOST}.")
    print("Ollama is up.")


def _ensure_model_pulled() -> None:
    tags_url = f"{llm.OLLAMA_HOST}/api/tags"
    try:
        data = json.loads(urllib.request.urlopen(tags_url, timeout=5).read())
    except (urllib.error.URLError, TimeoutError):
        sys.exit(f"Could not reach Ollama at {llm.OLLAMA_HOST} to check for {llm.MODEL}.")

    have = {m["name"] for m in data.get("models", [])}
    if llm.MODEL in have or f"{llm.MODEL}:latest" in have:
        print(f"Model {llm.MODEL} is already pulled.")
        return

    print(f"Pulling {llm.MODEL} (first time only -- this can take a while)...")
    subprocess.run(["ollama", "pull", llm.MODEL], check=True)


def _open_browser_once_serving() -> None:
    def watch():
        if _wait_until_reachable(UI_URL, STARTUP_TIMEOUT_S):
            webbrowser.open(UI_URL)

    threading.Thread(target=watch, daemon=True).start()


def main() -> None:
    if llm.PROVIDER == "ollama":
        _ensure_ollama_running()
        _ensure_model_pulled()
    else:
        print(f"Using provider={llm.PROVIDER} model={llm.MODEL} -- skipping Ollama startup.")

    print(f"Starting ClauseGuard at {UI_URL} (Ctrl+C to stop)")
    _open_browser_once_serving()
    subprocess.run([sys.executable, "-m", "uvicorn", "clauseguard.main:app", "--host", "127.0.0.1", "--port", "8000"])


if __name__ == "__main__":
    main()
