"""Central configuration: paths, .env loading and models.json access.

Secrets (API keys, APP_PASSWORD) are read ONLY from environment variables
(loaded from .env). They are never written to models.json, the database,
logs, error messages or the UI.
"""
import json
import os
import re
import tempfile
import threading
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
APP_PASSWORD = os.getenv("APP_PASSWORD", "")
ALLOW_INSECURE_PUBLIC = os.getenv("ALLOW_INSECURE_PUBLIC", "0") == "1"
ENABLE_TUNNEL = os.getenv("ENABLE_TUNNEL", "1") != "0"
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "4096"))
REAL_HOME = os.getenv("WORKFLOW_REAL_HOME", "0") == "1"

DATA_DIR = BASE_DIR / "data"
WORKSPACE_DIR = BASE_DIR / "workspace"
OUTPUTS_DIR = BASE_DIR / "outputs"
MODELS_FILE = BASE_DIR / "models.json"
for _d in (DATA_DIR, WORKSPACE_DIR, OUTPUTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

ROLES = ("backend_reviewer", "syntax_reviewer", "workflow_runner", "chat")
PROVIDERS = ("openai-compatible", "anthropic", "gemini")
NAME_RE = re.compile(r"^[\w .:+()\-]{1,60}$")
ENV_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_lock = threading.RLock()


# ---------------------------------------------------------------- models.json
def load_models() -> dict:
    with _lock:
        try:
            cfg = json.loads(MODELS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cfg = {}
    cfg.setdefault("models", [])
    cfg.setdefault("roles", {})
    return cfg


def save_models(cfg: dict) -> None:
    """Atomic write so a crash can never leave a half-written file."""
    with _lock:
        fd, tmp = tempfile.mkstemp(dir=str(BASE_DIR), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        os.replace(tmp, MODELS_FILE)


def validate_model(d: dict) -> dict:
    """Validate and normalise a model entry. Raises ValueError with a clear message."""
    m = {
        "name": str(d.get("name", "")).strip(),
        "provider": str(d.get("provider", "")).strip(),
        "base_url": str(d.get("base_url", "")).strip().rstrip("/"),
        "model_id": str(d.get("model_id", "")).strip(),
        "api_key_env": str(d.get("api_key_env", "")).strip(),
        "enabled": bool(d.get("enabled", True)),
    }
    if not NAME_RE.match(m["name"]):
        raise ValueError("Invalid name (1-60 chars: letters, digits, space . : + ( ) -).")
    if m["provider"] not in PROVIDERS:
        raise ValueError("Provider must be one of: " + ", ".join(PROVIDERS))
    if not re.match(r"^https?://[^\s]+$", m["base_url"]):
        raise ValueError("base_url must start with http:// or https://")
    if not m["model_id"] or len(m["model_id"]) > 200:
        raise ValueError("model_id is required.")
    if not ENV_RE.match(m["api_key_env"]) or m["api_key_env"] in ("APP_PASSWORD", "PATH", "HOME"):
        raise ValueError("api_key_env must be an env variable NAME such as MY_API_KEY (not the key itself).")
    return m


def key_for(model: dict) -> str:
    return os.getenv(model.get("api_key_env", ""), "")


def is_usable(model: dict) -> bool:
    return bool(model.get("enabled")) and bool(key_for(model))


def secret_values() -> list:
    """All secret strings that must be scrubbed from any text shown to the user."""
    vals = {key_for(m) for m in load_models()["models"]}
    vals.add(APP_PASSWORD)
    return [v for v in vals if v and len(v) >= 6]
