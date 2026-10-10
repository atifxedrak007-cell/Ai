"""Workflow planning: a deterministic baseline plan per language, refined by the Workflow Runner AI.

A step is a dict:
  name, cmd (one plain command, no shell), kind (install|syntax|test|run|other),
  timeout (seconds), each (optional list of files: the command runs once per file),
  continue_on_fail (optional bool).
"""
import json
import re
import shutil
from pathlib import Path

import llm
from agents import prompts
from . import fsutil, safety

KINDS = {"install", "syntax", "test", "run", "other"}


def S(name, cmd, kind, timeout=120, each=None, cof=False):
    st = {"name": name, "cmd": cmd, "kind": kind, "timeout": timeout}
    if each:
        st["each"] = each
    if cof:
        st["continue_on_fail"] = True
    return st


def _py():
    return "python3" if shutil.which("python3") else "python"


def _files(ws, exts):
    return [p.relative_to(ws).as_posix() for p in fsutil.iter_files(ws) if p.suffix.lower() in exts][:60]


def _first(ws, names):
    for n in names:
        if (ws / n).is_file():
            return n
    return None


def _plan_python(ws):
    py, steps = _py(), []
    req = ws / "requirements.txt"
    if req.exists() or (ws / "pyproject.toml").exists() or (ws / "setup.py").exists():
        steps.append(S("Create virtualenv", f"{py} -m venv --system-site-packages .venv", "install", 180))
        py = ".venv/bin/python"
        if req.exists():
            steps.append(S("Install dependencies", f"{py} -m pip install -r requirements.txt", "install", 900))
        else:
            steps.append(S("Install project", f"{py} -m pip install .", "install", 900))
    pyfiles = _files(ws, {".py"})
    if pyfiles:
        steps.append(S("Syntax check (py_compile)", py + ' -m compileall -q -x "(\\.venv|node_modules)" .', "syntax", 120))
        if shutil.which("ruff"):
            steps.append(S("Lint (ruff)", "ruff check --exclude .venv .", "syntax", 120, cof=True))
    has_tests = (ws / "tests").is_dir() or any(Path(f).name.startswith("test_") or f.endswith("_test.py") for f in pyfiles)
    if has_tests:
        import importlib.util
        req_text = req.read_text(errors="ignore") if req.exists() else ""
        use_pytest = "pytest" in req_text or importlib.util.find_spec("pytest") is not None
        steps.append(S("Run tests", f"{py} -m pytest -q" if use_pytest else f"{py} -m unittest discover -q", "test", 300))
    entry = _first(ws, ["main.py", "app.py", "run.py", "server.py", "bot.py", "__main__.py"]) or \
        next((f for f in pyfiles if "/" not in f and not Path(f).name.startswith("test_")), None)
    if entry:
        steps.append(S(f"Run {entry}", f"{py} {entry}", "run", 30))
    return steps


def _plan_node(ws, typescript=False):
    steps, pkg = [], {}
    if (ws / "package.json").exists():
        try:
            pkg = json.loads((ws / "package.json").read_text(errors="ignore"))
        except ValueError:
            pkg = {}
        steps.append(S("Install dependencies", "npm install", "install", 900))
    jsfiles = _files(ws, {".js", ".mjs", ".cjs"})
    if jsfiles:
        steps.append(S("Syntax check (node --check)", "node --check", "syntax", 120, each=jsfiles))
    if typescript and (ws / "tsconfig.json").exists():
        steps.append(S("Type check (tsc)", "npx --yes -p typescript tsc --noEmit", "syntax", 300, cof=True))
    scripts = pkg.get("scripts", {}) if isinstance(pkg, dict) else {}
    if scripts.get("test") and "no test specified" not in scripts["test"]:
        steps.append(S("Run tests", "npm test", "test", 300))
    if scripts.get("start"):
        steps.append(S("Run (npm start)", "npm start", "run", 30))
    else:
        main = pkg.get("main") if isinstance(pkg, dict) and isinstance(pkg.get("main"), str) else None
        entry = main or _first(ws, ["index.js", "main.js", "app.js", "server.js"]) or (jsfiles[0] if jsfiles else None)
        if entry and (ws / entry).is_file():
            steps.append(S(f"Run {entry}", f"node {entry}", "run", 30))
    return steps


def _plan_go(ws):
    steps = [S("Build", "go build ./...", "syntax", 300), S("Vet", "go vet ./...", "syntax", 300, cof=True)]
    if _files(ws, {".go"}) and any(f.endswith("_test.go") for f in _files(ws, {".go"})):
        steps.append(S("Run tests", "go test ./...", "test", 300))
    steps.append(S("Run", "go run .", "run", 30))
    return steps


def _plan_rust(ws):
    steps = [S("Check", "cargo check", "syntax", 900)]
    steps.append(S("Run tests", "cargo test", "test", 900))
    steps.append(S("Run", "cargo run", "run", 30))
    return steps


def _plan_c(ws, cpp=False):
    cc, exts = ("g++", {".cpp", ".cc"}) if cpp else ("gcc", {".c"})
    srcs = _files(ws, exts)
    if (ws / "Makefile").exists():
        return [S("Build (make)", "make", "install", 600)]
    if not srcs:
        return []
    return [S("Syntax check", f"{cc} -fsyntax-only -Wall", "syntax", 120, each=srcs),
            S("Compile", f"{cc} -Wall -o app " + " ".join(srcs), "install", 300),
            S("Run", "./app", "run", 30)]


def _plan_java(ws):
    srcs = _files(ws, {".java"})
    if not srcs:
        return []
    main = next((Path(f).stem for f in srcs if "static void main" in (ws / f).read_text(errors="ignore")), None)
    steps = [S("Compile", "javac -d build " + " ".join(srcs), "syntax", 300)]
    if main:
        steps.append(S(f"Run {main}", f"java -cp build {main}", "run", 30))
    return steps


def _plan_simple(ws, exts, check_cmd, run_cmd):
    files = _files(ws, exts)
    if not files:
        return []
    steps = [S("Syntax check", check_cmd, "syntax", 60, each=files)]
    entry = next((f for f in files if "/" not in f), files[0])
    steps.append(S(f"Run {entry}", f"{run_cmd} {entry}", "run", 30))
    return steps


def default_plan(ws: Path, language: str) -> list:
    ws = Path(ws)
    if language == "python":
        return _plan_python(ws)
    if language in ("javascript", "typescript"):
        return _plan_node(ws, language == "typescript")
    if language == "go":
        return _plan_go(ws)
    if language == "rust":
        return _plan_rust(ws)
    if language == "c":
        return _plan_c(ws)
    if language == "cpp":
        return _plan_c(ws, cpp=True)
    if language == "java":
        return _plan_java(ws)
    if language == "php":
        return _plan_simple(ws, {".php"}, "php -l", "php")
    if language == "ruby":
        return _plan_simple(ws, {".rb"}, "ruby -c", "ruby")
    if language == "bash":
        return _plan_simple(ws, {".sh"}, "bash -n", "bash")
    return []


def validate_steps(steps, ws):
    """Keep only safe, well-formed steps. Returns (good_steps, blocked[{cmd, reason}])."""
    good, blocked = [], []
    for raw in steps if isinstance(steps, list) else []:
        if not isinstance(raw, dict):
            continue
        cmd = str(raw.get("cmd", ""))
        try:
            safety.check_command(cmd, ws)
            each = raw.get("each")
            if each is not None:
                if not isinstance(each, list) or len(each) > 100:
                    raise safety.Unsafe("'each' must be a list of at most 100 files")
                each = [safety.check_file_arg(str(f), ws) for f in each]
                for f in each:
                    safety.check_command(f"{cmd} {f}", ws)
        except safety.Unsafe as e:
            blocked.append({"cmd": cmd[:200], "reason": str(e)})
            continue
        kind = raw.get("kind") if raw.get("kind") in KINDS else "other"
        try:
            timeout = max(5, min(int(raw.get("timeout", 120)), 1800))
        except (TypeError, ValueError):
            timeout = 120
        good.append(S(str(raw.get("name") or cmd)[:80], cmd, kind, timeout, each=each,
                      cof=bool(raw.get("continue_on_fail"))))
    return good, blocked


def _extract_json(text: str):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON found")
    return json.loads(m.group(0))


def generate_plan(ws: Path, project: dict, lang: str = "en") -> dict:
    """Ask the Workflow Runner model for a plan; fall back to the baseline if anything fails."""
    ws = Path(ws)
    baseline = default_plan(ws, project["language"])
    base_good, _ = validate_steps(baseline, ws)
    result = {"steps": base_good, "source": "default", "model": None, "blocked": [], "note": ""}
    try:
        files = [f["path"] for f in fsutil.list_files(ws, 150)]
        extras = ""
        for name in ("requirements.txt", "package.json"):
            if (ws / name).is_file():
                extras += f"\n--- {name} ---\n{fsutil.read_text(ws / name, 1500)}"
        user = (f"Language: {project['language']}\nFiles:\n" + "\n".join(files) + extras +
                "\n\nBaseline plan (JSON):\n" + json.dumps({"steps": baseline}, indent=1) +
                "\n\nReturn the final plan as JSON.")
        res = llm.complete("workflow_runner", prompts.PLANNER, [{"role": "user", "content": user}],
                           max_tokens=1500, temperature=0.1)
        ai_steps, blocked = validate_steps(_extract_json(res["text"]).get("steps"), ws)
        result["blocked"] = blocked
        result["model"] = res["model"]
        if ai_steps:
            result.update(steps=ai_steps, source="ai")
        else:
            result["note"] = "AI plan had no valid steps; using the default plan."
    except llm.LLMError as e:
        result["note"] = f"AI planning unavailable ({e}); using the default plan."
    except (ValueError, AttributeError) as e:
        result["note"] = f"AI plan could not be parsed ({e}); using the default plan."
    return result
