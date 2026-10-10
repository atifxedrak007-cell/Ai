"""Backend + Syntax reviewers (run in parallel) and the combined summary."""
import threading

import config
import db
import llm
import outputs
from streams import new_stream
from workflow import fsutil

from . import prompts

REVIEW_ROLES = ("backend_reviewer", "syntax_reviewer")


def format_run(run: dict, tail=4000) -> str:
    lines = [f"Workflow run status: {run['status']}"]
    for i, s in enumerate(run["steps"], 1):
        log = (s.get("log") or "")[-tail:]
        lines.append(f"\n### Step {i}: {s['name']} [{s.get('status')}, exit {s.get('exit_code')}]\n"
                     f"command: {s['cmd']}\n{log}")
    return "\n".join(lines)


def build_context(project: dict, run_id=None, max_total=60000) -> str:
    ws = config.WORKSPACE_DIR / project["id"]
    files = "\n".join(f"{f['path']} ({f['size']} bytes)" for f in fsutil.list_files(ws, 200))
    parts = [f"Project: {project['name']}\nDetected language: {project['language']}\n\nFiles:\n{files}",
             "Source code:\n" + fsutil.collect_sources(ws, max_total=max_total)]
    if run_id:
        run = db.get_run(run_id)
        if run:
            parts.append("Workflow execution results:\n" + format_run(run))
    return "\n\n".join(parts)


def start_review_job(project_id, lang="en", run_id=None, include_logs=True) -> str:
    sid, stream = new_stream("job")
    threading.Thread(target=_job, args=(stream, project_id, lang, run_id, include_logs), daemon=True).start()
    return sid


def _job(stream, project_id, lang, run_id, include_logs):
    results = {}
    try:
        project = db.get_project(project_id)
        if not project:
            stream.emit(type="review_error", role="all", message="Project not found.")
            return
        if include_logs and not run_id:
            last = db.latest_run(project_id)
            run_id = last["id"] if last and last["status"] in ("success", "failed", "stopped") else None
        ctx = build_context(project, run_id if include_logs else None)
        stream.emit(type="start", run_id=run_id)

        def work(role):
            stream.emit(type="review_start", role=role)
            try:
                res = llm.complete(role, prompts.system_for(role, lang), [{"role": "user", "content": ctx}])
                blocks = outputs.build_blocks(res["text"], project_id, role.split("_")[0])
                db.add_review(project_id, run_id, role, res["model"], blocks)
                results[role] = res["text"]
                stream.emit(type="review_done", role=role, model=res["model"], notes=res["notes"], blocks=blocks)
            except llm.LLMError as e:
                stream.emit(type="review_error", role=role, message=str(e))
            except Exception as e:
                stream.emit(type="review_error", role=role, message=llm.scrub(f"Unexpected error: {e}"))

        threads = [threading.Thread(target=work, args=(r,)) for r in REVIEW_ROLES]
        [t.start() for t in threads]
        [t.join() for t in threads]

        if results:
            stream.emit(type="summary_start")
            body = "\n\n".join(f"## {r}\n{results[r][:12000]}" for r in REVIEW_ROLES if r in results)
            try:
                res = llm.complete("chat", prompts.system_for("summary", lang), [{"role": "user", "content": body}],
                                   max_tokens=1200)
                blocks = outputs.build_blocks(res["text"], project_id, "summary")
                db.add_review(project_id, run_id, "summary", res["model"], blocks)
                stream.emit(type="summary", model=res["model"], blocks=blocks)
            except llm.LLMError as e:
                stream.emit(type="summary_error", message=str(e))
    except Exception as e:
        stream.emit(type="review_error", role="all", message=llm.scrub(f"Unexpected error: {e}"))
    finally:
        stream.emit(type="done")
        stream.close()
