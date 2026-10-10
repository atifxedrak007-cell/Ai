"""Authentication, rate limiting and exposure guards."""
import hmac
import os
import secrets
import threading
import time
from collections import defaultdict, deque

from flask import request, session

import config


def load_secret_key() -> str:
    """Session-signing key, generated once and stored (chmod 600) in data/secret.key."""
    path = config.DATA_DIR / "secret.key"
    if not path.exists():
        path.write_text(secrets.token_hex(32))
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return path.read_text().strip()


# -------------------------------------------------------------------- client
def client_ip() -> str:
    # Cloudflare sets CF-Connecting-IP to the real visitor address.
    return request.headers.get("CF-Connecting-IP") or request.remote_addr or "?"


def is_remote() -> bool:
    """True when the request came through the public tunnel (not from the device itself)."""
    h = request.headers
    host = (request.host or "").split(":")[0]
    return bool(h.get("CF-Connecting-IP") or h.get("X-Forwarded-For") or host.endswith("trycloudflare.com"))


def insecure_remote() -> bool:
    """Public access without a password is locked down (see README)."""
    return (not config.APP_PASSWORD) and (not config.ALLOW_INSECURE_PUBLIC) and is_remote()


# ---------------------------------------------------------------------- auth
def auth_required() -> bool:
    return bool(config.APP_PASSWORD)


def authed() -> bool:
    return (not config.APP_PASSWORD) or session.get("ok") is True


def password_ok(candidate: str) -> bool:
    return hmac.compare_digest(candidate.encode(), config.APP_PASSWORD.encode())


# ------------------------------------------------------------- rate limiting
class RateLimiter:
    """Sliding-window limiter kept in memory (enough for a single-user tool)."""

    def __init__(self):
        self.hits = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str, limit: int, window: int):
        """Returns (allowed, retry_after_seconds)."""
        now = time.time()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                return False, int(window - (now - q[0])) + 1
            q.append(now)
            if len(self.hits) > 5000:  # keep memory bounded
                for k in [k for k, v in self.hits.items() if not v][:1000]:
                    self.hits.pop(k, None)
            return True, 0


limiter = RateLimiter()
