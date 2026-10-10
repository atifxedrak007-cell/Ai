"""Workflow execution: runs plan steps as subprocesses with timeouts and live log streaming."""
import os
import re
import resource
import shlex
import signal
import subprocess
import threading
import time
import uuid
from pathlib import Path

import config
import db
import llm
from streams import Stream
from . import planner, safety

MAX_LOG_CHARS = 200_000
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
SAFE_ENV_KEYS = ("PATH", "LANG", "LC_ALL", "TERM", "TMPDIR", "PREFIX", "ANDROID_ROOT", "ANDROID_DATA",
                 "LD_LIBRARY_PATH", "LD_PRELOAD", "SHELL", "USER")


class Busy(Exception):
    pass


class Run:
    def __init__(self, project_id):
        self.id = uuid.uuid4().hex[:12]
        self.project_id = project_id
        self.status = "planning"
        self.plan = None
        self.steps = []
        self.stream = Stream()
        self.stop_flag = threading.Event()
        self.proc = None
        self.lock = threading.Lock()

    def snapshot(self):
        return {"id": self.id, "project_id": self.project_id, "status": self.status, "steps": self.steps}

    def set_status(self, status, **extra):
        self.status = status
        self.stream.emit(type="run_status", status=status, **extra)

    def stop(self):
        self.stop_flag.set()
        with self.lock:
            if self.proc:
                _terminate(self.proc)


RUNS = {}
_reg_lock = threading.Lock()


def get_run(run_id):
    return RUNS.get(run_id)


def active_run(project_id):
    return next((r for r in RUNS.values() if r.project_id == project_id and r.status in ("planning", "running")), None)


def stop(run_id) -> bool:
    r = RUNS.get(run_id)
    if r:
        r.stop()
    return bool(r)


def stop_all():
    for r in list(RUNS.values()):
        if r.status in ("planning", "running"):
            r.stop()


def _terminate(proc):
    """SIGTERM the whole process group, then SIGKILL after 3 seconds."""
    for sig, delay in ((signal.SIGTERM, 0), (signal.SIGKILL, 3)):
        def _send(s=sig):
            try:
                os.killpg(proc.pid, s)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        if delay:
            threading.Timer(delay, _send).start()
        else:
            _send()


def _safe_env(ws: Path) -> dict:
    """Minimal environment: API keys and other secrets are NOT passed to workflow commands."""
    env = {k: os.environ[k] for k in SAFE_ENV_KEYS if k in os.environ}
    if not config.REAL_HOME:
        home = ws / ".home"
        home.mkdir(exist_ok=True)
        env["HOME"] = str(home)
    elif "HOME" in os.environ:
        env["HOME"] = os.environ["HOME"]
    extra = [str(ws / d) for d in (".venv/bin", "node_modules/.bin") if (ws / d).is_dir()]
    env["PATH"] = os.pathsep.join(extra + [env.get("PATH", "/usr/bin:/bin")])
    env.update(PYTHONUNBUFFERED="1", PIP_DISABLE_PIP_VERSION_CHECK="1", CI="1", NO_COLOR="1")
    return env


def _limits():  # runs in the child before exec
    try:
        resource.setrlimit(resource.RLIMIT_FSIZE, (512 * 1024 * 1024, 512 * 1024 * 1024))
    except (ValueError, OSError):
        pass


def _log(run, idx, text):
    step = run.steps[idx]
    if len(step["log"]) >= MAX_LOG_CHARS:
        return
    text = llm.scrub(ANSI_RE.sub("", text))
    step["log"] += text
    if len(step["log"]) >= MAX_LOG_CHARS:
        step["log"] += "\n... [log truncated]\n"
        text += "\n... [log truncated]\n"
    run.stream.emit(type="log", index=idx, text=text)


def _run_argv(run, idx, argv, ws, timeout, kind):
    """Run one argv; returns (exit_code, timed_out)."""
    try:
        proc = subprocess.Popen(argv, cwd=ws, env=_safe_env(ws), stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                errors="replace", bufsize=1, start_new_session=True, preexec_fn=_limits)
    except FileNotFoundError:
        _log(run, idx, f"command not found: {argv[0]} (install it first, e.g. pkg install {argv[0]})\n")
        return 127, False
    except OSError as e:
        _log(run, idx, f"could not start command: {e.__class__.__name__}\n")
        return 126, False
    with run.lock:
        run.proc = proc
    timed_out = threading.Event()

    def on_timeout():
        timed_out.set()
        _terminate(proc)

    timer = threading.Timer(timeout, on_timeout)
    timer.start()
    try:
        for line in proc.stdout:
            _log(run, idx, line)
        proc.wait()
    finally:
        timer.cancel()
        with run.lock:
            run.proc = None
    return proc.returncode, timed_out.is_set()


def _exec_step(run, idx, ws):
    st = run.steps[idx]
    # Re-validate right before running (plans can come from the DB or the AI).
    try:
        base = safety.check_command(st["cmd"], ws)
        files = [safety.check_file_arg(f, ws) for f in (st.get("each") or [])]
        jobs = [base + [f] for f in files] or [base]
    except safety.Unsafe as e:
        _log(run, idx, f"BLOCKED by safety rules: {e}\n")
        return False, None
    _log(run, idx, "$ " + " ".join(shlex.quote(a) for a in base) + (f"  (x{len(jobs)} files)" if len(jobs) > 1 else "") + "\n")
    worst, timed_out_any = 0, False
    for argv in jobs:
        if run.stop_flag.is_set():
            break
        if len(jobs) > 1:
            _log(run, idx, f"-- {argv[-1]}\n")
        code, to = _run_argv(run, idx, argv, ws, st.get("timeout", 120), st.get("kind"))
        timed_out_any |= to
        if code not in (0, None):
            worst = code
    if timed_out_any:
        if st.get("kind") == "run":  # long-running programs (servers, bots) are expected to hit the timeout
            _log(run, idx, f"\n[stopped after {st.get('timeout')}s - program was still running; treated as OK]\n")
            return True, 0
        _log(run, idx, f"\n[timeout after {st.get('timeout')}s]\n")
        return False, 124
    if run.stop_flag.is_set():
        return False, worst or -15
    return worst == 0, worst


def _persist(run):
    db.save_run(run.id, run.project_id, run.status, run.plan, run.steps)


def _execute(run, ws):
    run.set_status("running")
    _persist(run)
    blocked_failure = False
    for i, st in enumerate(run.steps):
        if run.stop_flag.is_set() or blocked_failure:
            st["status"] = "skipped"
            run.stream.emit(type="step", index=i, status="skipped")
            continue
        st["status"] = "running"
        run.stream.emit(type="step", index=i, status="running")
        t0 = time.time()
        ok, code = _exec_step(run, i, ws)
        st["duration"] = round(time.time() - t0, 1)
        st["exit_code"] = code
        st["status"] = "success" if ok else ("stopped" if run.stop_flag.is_set() else "failed")
        run.stream.emit(type="step", index=i, status=st["status"], exit_code=code, duration=st["duration"])
        if not ok and not st.get("continue_on_fail") and not run.stop_flag.is_set():
            blocked_failure = True
    if run.stop_flag.is_set():
        run.set_status("stopped")
    elif any(s["status"] == "failed" and not s.get("continue_on_fail") for s in run.steps):
        run.set_status("failed")
    else:
        run.set_status("success")


def _main(run, project, lang, replan, auto_review):
    ws = config.WORKSPACE_DIR / run.project_id
    try:
        plan = None if replan else db.latest_plan(run.project_id)
        if plan:
            plan["note"] = (plan.get("note") or "").strip()
        else:
            run.stream.emit(type="run_status", status="planning")
            plan = planner.generate_plan(ws, project, lang)
        run.plan = plan
        run.steps = [{**s, "status": "pending", "exit_code": None, "duration": None, "log": ""} for s in plan["steps"]]
        run.stream.emit(type="plan", steps=[{k: v for k, v in s.items() if k != "log"} for s in run.steps],
                        source=plan.get("source"), model=plan.get("model"),
                        blocked=plan.get("blocked", []), note=plan.get("note", ""))
        if not run.steps:
            run.set_status("failed", message="no_steps")
            return
        _execute(run, ws)
    except Exception as e:  # never let the thread die silently
        run.set_status("failed", message=llm.scrub(f"Internal error: {e.__class__.__name__}: {e}"))
    finally:
        _persist(run)
        if auto_review and run.status in ("success", "failed") and run.steps:
            try:
                from agents import reviewers
                run.stream.emit(type="review_job", job_id=reviewers.start_review_job(
                    run.project_id, lang, run_id=run.id, include_logs=True))
            except Exception:
                pass
        run.stream.emit(type="done")
        run.stream.close()


def start_run(project, lang="en", replan=True, auto_review=True) -> Run:
    with _reg_lock:
        if active_run(project["id"]):
            raise Busy()
        run = Run(project["id"])
        RUNS[run.id] = run
        if len(RUNS) > 50:  # forget the oldest finished runs (they stay in the DB)
            for k in [k for k, r in RUNS.items() if r.status not in ("planning", "running")][:20]:
                RUNS.pop(k, None)
    db.save_run(run.id, run.project_id, "planning", None, [])
    threading.Thread(target=_main, args=(run, project, lang, replan, auto_review), daemon=True).start()
    return run
