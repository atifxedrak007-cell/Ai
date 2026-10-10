"""Multi-AI code review & workflow tool - web server.   Start with:  python app.py"""
import atexit
import logging
import re
import shutil
import signal
import sys
import time
import uuid
import zipfile
from pathlib import Path

from flask import Flask, Response, jsonify, redirect, request, send_file, send_from_directory, session

import config
import db
import llm
import outputs
import security
import tunnel
from agents import chat as chat_agent
from agents import reviewers
from streams import get_stream, one_shot
from workflow import detect, fsutil, runner

STATIC = config.BASE_DIR / "static"
PID_RE = re.compile(r"^[a-f0-9]{12}$")

app = Flask(__name__, static_folder=None)
app.config.update(
    SECRET_KEY=security.load_secret_key(),
    MAX_CONTENT_LENGTH=config.MAX_UPLOAD_MB * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=7 * 86400,
)


def err(msg, code=400, **extra):
    return jsonify(error=msg, **extra), code


def lang_of(data):
    return data.get("lang") if data.get("lang") in ("bn", "en") else "en"


def need_project(pid):
    return db.get_project(pid) if PID_RE.match(pid or "") else None


# ------------------------------------------------------------------ gatekeeper
@app.before_request
def gate():
    path, ip = request.path, security.client_ip()
    if path == "/api/login" and request.method == "POST":
        ok, wait = security.limiter.allow(f"login:{ip}", 8, 300)
    elif path.startswith("/api/"):
        heavy = request.method == "POST" and path.endswith(("/review", "/runs")) or path == "/api/chat" and request.method == "POST"
        ok, wait = security.limiter.allow(f"{'llm' if heavy else 'api'}:{ip}", 12 if heavy else 400, 60)
    else:
        ok, wait = security.limiter.allow(f"page:{ip}", 300, 60)
    if not ok:
        r = jsonify(error="rate_limited", message=f"Too many requests. Try again in {wait}s.")
        r.status_code = 429
        r.headers["Retry-After"] = str(wait)
        return r
    if not security.authed():
        if path in ("/login", "/api/login"):
            return None
        return err("auth_required", 401) if path.startswith("/api/") else redirect("/login")
    if path.startswith("/api/") and path != "/api/info" and security.insecure_remote():
        return err("locked", 403, message="Public access is locked because APP_PASSWORD is not set. "
                                          "Set it in .env (or use the app locally).")
    return None


@app.after_request
def headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["X-Frame-Options"] = "DENY"
    script = "'self' 'unsafe-inline'" if request.path == "/login" else "'self'"
    resp.headers["Content-Security-Policy"] = (f"default-src 'self'; script-src {script}; "
                                               "style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'")
    return resp


# ----------------------------------------------------------------- pages/auth
@app.get("/")
def index():
    return send_file(STATIC / "index.html", max_age=0)


@app.get("/login")
def login_page():
    return send_file(STATIC / "login.html", max_age=0)


@app.get("/static/<path:name>")
def static_files(name):
    return send_from_directory(STATIC, name, max_age=0)


@app.post("/api/login")
def login():
    if not config.APP_PASSWORD:
        return jsonify(ok=True)
    data = request.get_json(silent=True) or {}
    if security.password_ok(str(data.get("password", ""))):
        session.permanent = True
        session["ok"] = True
        return jsonify(ok=True)
    return err("wrong_password", 401)


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/api/info")
def info():
    return jsonify(tunnel_url=tunnel.state["url"], tunnel_status=tunnel.state["status"],
                   tunnel_hint=tunnel.state["hint"], auth_required=security.auth_required(),
                   locked=security.insecure_remote())


# ------------------------------------------------------------ models/settings
def _public_model(m):
    return {**m, "key_set": bool(config.key_for(m))}  # never the key itself


@app.get("/api/models")
def models_get():
    cfg = config.load_models()
    return jsonify(models=[_public_model(m) for m in cfg["models"]], roles=cfg["roles"],
                   role_names=list(config.ROLES), providers=list(config.PROVIDERS))


@app.post("/api/models")
def models_add():
    try:
        m = config.validate_model(request.get_json(silent=True) or {})
    except ValueError as e:
        return err(str(e))
    cfg = config.load_models()
    if any(x["name"] == m["name"] for x in cfg["models"]):
        return err("A model with this name already exists.")
    cfg["models"].append(m)
    config.save_models(cfg)
    return jsonify(ok=True)


@app.patch("/api/models/<name>")
def models_patch(name):
    data = request.get_json(silent=True) or {}
    cfg = config.load_models()
    for m in cfg["models"]:
        if m["name"] == name:
            if "enabled" in data:
                m["enabled"] = bool(data["enabled"])
            config.save_models(cfg)
            return jsonify(ok=True)
    return err("Model not found.", 404)


@app.delete("/api/models/<name>")
def models_delete(name):
    cfg = config.load_models()
    cfg["models"] = [m for m in cfg["models"] if m["name"] != name]
    cfg["roles"] = {r: n for r, n in cfg["roles"].items() if n != name}
    config.save_models(cfg)
    return jsonify(ok=True)


@app.put("/api/roles")
def roles_put():
    data = request.get_json(silent=True) or {}
    cfg = config.load_models()
    names = {m["name"] for m in cfg["models"]}
    for role, name in data.items():
        if role in config.ROLES and (name in names or name == ""):
            cfg["roles"][role] = name
    config.save_models(cfg)
    return jsonify(ok=True)


# ------------------------------------------------------------------- projects
def project_view(p):
    ws = config.WORKSPACE_DIR / p["id"]
    files = fsutil.list_files(ws, 300) if ws.is_dir() else []
    return {**p, "files": files, "last_run": db.latest_run(p["id"]),
            "active_run": getattr(runner.active_run(p["id"]), "id", None)}


@app.post("/api/upload")
def upload():
    files = [f for f in request.files.getlist("files") if f and f.filename]
    if not files:
        return err("No file selected.")
    pid = uuid.uuid4().hex[:12]
    ws = config.WORKSPACE_DIR / pid
    ws.mkdir(parents=True)
    try:
        saved = fsutil.save_uploads(files, ws)
    except (ValueError, zipfile.BadZipFile) as e:
        shutil.rmtree(ws, ignore_errors=True)
        return err(str(e))
    language, _ = detect.detect_language(ws)
    count = len(fsutil.list_files(ws, 5000))
    name = (request.form.get("name") or "").strip()[:60] or Path(saved[0]).stem or pid
    db.add_project(pid, name, language, count)
    return jsonify(project_view(db.get_project(pid)))


@app.get("/api/projects/<pid>")
def project_get(pid):
    p = need_project(pid)
    return jsonify(project_view(p)) if p else err("Project not found.", 404)


@app.delete("/api/projects/<pid>")
def project_delete(pid):
    p = need_project(pid)
    if not p:
        return err("Project not found.", 404)
    if runner.active_run(pid):
        return err("Stop the running workflow first.", 409)
    shutil.rmtree(config.WORKSPACE_DIR / pid, ignore_errors=True)
    shutil.rmtree(config.OUTPUTS_DIR / pid, ignore_errors=True)
    db.delete_project(pid)
    return jsonify(ok=True)


@app.get("/api/history")
def history():
    return jsonify(projects=db.list_projects())


# ------------------------------------------------------------------ workflows
def sse(gen):
    return Response(gen, mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})


def start_index():
    """SSE resume point: browsers send Last-Event-ID on reconnect; ?from=N is for manual replay."""
    last = request.headers.get("Last-Event-ID", "")
    if last.isdigit():
        return int(last) + 1
    f = request.args.get("from", "")
    return int(f) if f.isdigit() else 0


@app.post("/api/projects/<pid>/runs")
def run_start(pid):
    p = need_project(pid)
    if not p:
        return err("Project not found.", 404)
    data = request.get_json(silent=True) or {}
    try:
        run = runner.start_run(p, lang_of(data), replan=bool(data.get("replan", True)),
                               auto_review=bool(data.get("auto_review", True)))
    except runner.Busy:
        return err("A workflow is already running for this project.", 409)
    return jsonify(run_id=run.id)


@app.get("/api/runs/<rid>/stream")
def run_stream(rid):
    run = runner.get_run(rid)
    if run:
        return sse(run.stream.sse(start_index()))
    row = db.get_run(rid) if re.match(r"^[a-f0-9]{12}$", rid) else None
    if not row:
        return err("Run not found.", 404)
    snap = {"id": row["id"], "project_id": row["project_id"], "status": row["status"], "steps": row["steps"]}
    return sse(one_shot([{"type": "snapshot", "run": snap, "plan": row["plan"] and {
        k: v for k, v in row["plan"].items() if k != "steps"}}, {"type": "done"}]))


@app.post("/api/runs/<rid>/stop")
def run_stop(rid):
    return jsonify(ok=True) if runner.stop(rid) else err("Run is not active.", 404)


# ------------------------------------------------------------ reviews and chat
@app.post("/api/projects/<pid>/review")
def review_start(pid):
    if not need_project(pid):
        return err("Project not found.", 404)
    data = request.get_json(silent=True) or {}
    jid = reviewers.start_review_job(pid, lang_of(data), run_id=data.get("run_id"),
                                     include_logs=bool(data.get("include_logs", True)))
    return jsonify(job_id=jid)


@app.get("/api/projects/<pid>/reviews")
def reviews_get(pid):
    return jsonify(reviews=db.list_reviews(pid)) if need_project(pid) else err("Project not found.", 404)


@app.get("/api/jobs/<jid>/stream")
def job_stream(jid):
    s = get_stream(jid)
    return sse(s.sse(start_index())) if s else err("Job not found.", 404)


@app.post("/api/chat")
def chat_post():
    data = request.get_json(silent=True) or {}
    msg = str(data.get("message", "")).strip()
    if not msg or len(msg) > 20000:
        return err("Message is empty or too long.")
    pid = data.get("project_id") if need_project(data.get("project_id")) else None
    return jsonify(job_id=chat_agent.start_chat_job(msg, pid, lang_of(data)))


@app.get("/api/chat")
def chat_get():
    return jsonify(messages=db.list_chat())


@app.delete("/api/chat")
def chat_clear():
    db.clear_chat()
    return jsonify(ok=True)


# -------------------------------------------------------------- output files
@app.get("/api/files/<pid>/<name>")
def file_get(pid, name):
    p = outputs.resolve(pid, name)
    if not p:
        return err("File not found.", 404)
    if request.args.get("raw"):
        return Response(p.read_text(encoding="utf-8", errors="replace"), mimetype="text/plain; charset=utf-8")
    # Single file, original extension, forced download (never rendered in the browser).
    return send_file(p, as_attachment=True, download_name=p.name, mimetype="application/octet-stream")


@app.errorhandler(413)
def too_big(_):
    return err(f"Upload too large (limit {config.MAX_UPLOAD_MB} MB).", 413)


@app.errorhandler(500)
def server_error(e):
    return err(llm.scrub("Internal server error."), 500)


# ------------------------------------------------------------------- lifecycle
_down = False


def shutdown(*_):
    global _down
    if _down:
        return
    _down = True
    print("\nShutting down: stopping workflows and tunnel ...")
    runner.stop_all()
    time.sleep(0.3)
    tunnel.stop()


def main():
    db.init()
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    atexit.register(shutdown)
    signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))
    print(f"AI Review Tool running on http://localhost:{config.PORT}")
    if not config.APP_PASSWORD:
        print("WARNING: APP_PASSWORD is not set. Public (tunnel) access is locked until you set it in .env.")
    if config.ENABLE_TUNNEL:
        tunnel.start(config.PORT)
    try:
        app.run(host=config.HOST, port=config.PORT, threaded=True, debug=False, use_reloader=False)
    finally:
        shutdown()


if __name__ == "__main__":
    main()
