from pathlib import Path

from dotenv import load_dotenv

# Explicit path: load_dotenv()'s auto-discovery uses cwd under REPL/-c and misses the project .env.
# Runs before any submodule reads os.environ at import time; real env vars still win.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
