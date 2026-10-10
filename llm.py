"""Provider-agnostic LLM client with retry, fallback and secret scrubbing.

Providers: openai-compatible, anthropic, gemini. API keys come from the
environment only and are never included in errors or logs.
"""
import time

import requests

import config


class LLMError(Exception):
    """Raised with a user-safe (already scrubbed) message."""


class _Fail(Exception):
    def __init__(self, msg, retryable):
        super().__init__(msg)
        self.retryable = retryable


def scrub(text) -> str:
    text = str(text)
    for secret in config.secret_values():
        text = text.replace(secret, "***")
    return text


def _post(url, headers, payload, timeout):
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.Timeout:
        raise _Fail("request timed out", True)
    except requests.ConnectionError:
        raise _Fail("network connection failed", True)
    except requests.RequestException as e:
        raise _Fail(f"request error ({type(e).__name__})", True)
    if r.status_code >= 400:
        detail = ""
        try:
            j = r.json()
            err = j.get("error", j) if isinstance(j, dict) else j
            detail = err.get("message", "") if isinstance(err, dict) else str(err)
        except ValueError:
            detail = r.text
        detail = scrub(detail)[:200]
        retryable = r.status_code in (408, 409, 425, 429) or r.status_code >= 500
        hint = {401: "invalid API key", 403: "access denied", 404: "model or URL not found",
                429: "rate limited / quota exceeded"}.get(r.status_code, "")
        raise _Fail(f"HTTP {r.status_code}{' - ' + hint if hint else ''}: {detail}".strip(), retryable)
    try:
        return r.json()
    except ValueError:
        raise _Fail("provider returned invalid JSON", True)


def _openai(m, key, system, messages, max_tokens, temperature, timeout):
    data = _post(
        m["base_url"] + "/chat/completions",
        {"Authorization": f"Bearer {key}"},
        {"model": m["model_id"], "max_tokens": max_tokens, "temperature": temperature,
         "messages": [{"role": "system", "content": system}] + messages},
        timeout)
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        raise _Fail("unexpected response format", False)


def _anthropic(m, key, system, messages, max_tokens, temperature, timeout):
    data = _post(
        m["base_url"] + "/messages",
        {"x-api-key": key, "anthropic-version": "2023-06-01"},
        {"model": m["model_id"], "max_tokens": max_tokens, "temperature": temperature,
         "system": system, "messages": messages},
        timeout)
    try:
        return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
    except (KeyError, TypeError):
        raise _Fail("unexpected response format", False)


def _gemini(m, key, system, messages, max_tokens, temperature, timeout):
    contents = [{"role": "model" if x["role"] == "assistant" else "user",
                 "parts": [{"text": x["content"]}]} for x in messages]
    data = _post(
        f"{m['base_url']}/models/{m['model_id']}:generateContent",
        {"x-goog-api-key": key},  # header, so the key never appears in a URL
        {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents,
         "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature}},
        timeout)
    try:
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError, TypeError):
        reason = (data.get("promptFeedback") or {}).get("blockReason") if isinstance(data, dict) else None
        raise _Fail("response blocked" + (f" ({reason})" if reason else "") if reason else "empty/unexpected response", False)


_CALLERS = {"openai-compatible": _openai, "anthropic": _anthropic, "gemini": _gemini}


def candidates(role: str) -> list:
    """Assigned model first, then every other enabled model that has an API key."""
    cfg = config.load_models()
    assigned = cfg["roles"].get(role)
    usable = [m for m in cfg["models"] if config.is_usable(m)]
    if not usable:
        raise LLMError("No usable model: add an API key to .env and enable a model in Settings.")
    return sorted(usable, key=lambda m: m["name"] != assigned)  # stable sort


def complete(role, system, messages, max_tokens=None, temperature=0.2, attempts=2, timeout=120) -> dict:
    """Call the model assigned to `role`; retry, then fall back to other enabled models.

    Returns {"text", "model", "notes"} where notes lists problems that were skipped over.
    """
    max_tokens = max_tokens or config.MAX_TOKENS
    notes, failures = [], []
    for m in candidates(role):
        key = config.key_for(m)
        for attempt in range(1, attempts + 1):
            try:
                text = _CALLERS[m["provider"]](m, key, system, messages, max_tokens, temperature, timeout)
                if not text.strip():
                    raise _Fail("empty answer", True)
                return {"text": text, "model": m["name"], "notes": notes}
            except _Fail as e:
                msg = scrub(str(e))
                if e.retryable and attempt < attempts:
                    time.sleep(1.5 * attempt)
                    continue
                failures.append(f"{m['name']}: {msg}")
                notes.append(f"{m['name']} failed ({msg}); switched to another model.")
                break
    raise LLMError("All models failed. " + " | ".join(failures))
