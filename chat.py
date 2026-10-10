"""Free-form chat with the assistant, optionally with the current project as context."""
import threading

import config
import db
import llm
import outputs
from streams import new_stream

from . import prompts
from .reviewers import build_context


def start_chat_job(message: str, project_id=None, lang="en") -> str:
    sid, stream = new_stream("chat")
    threading.Thread(target=_job, args=(stream, message, project_id, lang), daemon=True).start()
    return sid


def _normalize(msgs):
    """Providers need alternating roles starting with 'user': merge repeats, drop a leading assistant turn."""
    out = []
    for m in msgs:
        if out and out[-1]["role"] == m["role"]:
            out[-1] = {"role": m["role"], "content": out[-1]["content"] + "\n\n" + m["content"]}
        elif out or m["role"] == "user":
            out.append(dict(m))
    return out


def _job(stream, message, project_id, lang):
    try:
        history = [{"role": r["role"], "content": r["content"]} for r in db.list_chat(10)]
        db.add_chat("user", project_id, message)
        system = prompts.system_for("chat", lang)
        project = db.get_project(project_id) if project_id else None
        if project:
            system += "\n\nCurrent project context:\n" + build_context(project, None, max_total=30000)
        msgs = _normalize(history + [{"role": "user", "content": message}])
        res = llm.complete("chat", system, msgs, max_tokens=config.MAX_TOKENS, temperature=0.4)
        blocks = outputs.build_blocks(res["text"], project_id or "chat", "chat")
        db.add_chat("assistant", project_id, res["text"], blocks)
        stream.emit(type="chat_done", model=res["model"], notes=res["notes"], blocks=blocks)
    except llm.LLMError as e:
        stream.emit(type="chat_error", message=str(e))
    except Exception as e:
        stream.emit(type="chat_error", message=llm.scrub(f"Unexpected error: {e}"))
    finally:
        stream.emit(type="done")
        stream.close()
