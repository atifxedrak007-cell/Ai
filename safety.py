"""Command safety for workflow steps.

Defence in depth (best effort - see README for limits):
  * commands are parsed into an argv list and run WITHOUT a shell, so
    pipes, redirects, `;`, `&&`, `$(...)` and backticks cannot work;
  * only allow-listed executables may run;
  * known-dangerous patterns are rejected with a clear reason;
  * every path-like argument must resolve inside the project's workspace.
"""
import os
import re
import shlex
from pathlib import Path


class Unsafe(Exception):
    """Raised with a human-readable reason when a command is blocked."""


ALLOWED = re.compile(
    r"^(python[\d.]*|pip[\d.]*|pytest|ruff|mypy|flake8|black|node|npm|npx|yarn|pnpm|bun|deno|tsc|eslint|"
    r"go|cargo|rustc|gcc|g\+\+|cc|c\+\+|clang|clang\+\+|make|cmake|javac|java|mvn|gradle|php|composer|"
    r"ruby|bundle|gem|bash|sh|dotnet)$")

DANGEROUS = [
    (re.compile(r"\bsudo\b|\bdoas\b|\bsu\s+-?\w*"), "privilege escalation"),
    (re.compile(r"\brm\s+-[^\s]*[rRfF]|\brm\s+(/|~|\*)"), "recursive/forced delete"),
    (re.compile(r":\s*\(\s*\)\s*\{"), "fork bomb"),
    (re.compile(r"\bmkfs\b|\bdd\s+if=|/dev/(sd|nvme|mmcblk|block|mem)"), "raw disk access"),
    (re.compile(r"\b(shutdown|reboot|poweroff|halt)\b"), "power control"),
    (re.compile(r"\bch(mod|own)\b"), "permission change"),
    (re.compile(r"\b(kill|killall|pkill)\b"), "process killing"),
    (re.compile(r"(curl|wget)[^|]*\|\s*(ba)?sh"), "pipe download to shell"),
    (re.compile(r"\bmount\b|\bumount\b"), "mounting"),
]
SYSTEM_BIN = {"/usr/bin", "/usr/local/bin", "/bin", "/usr/sbin"}
OPS = set("();<>|&")


def _real(p) -> str:
    return os.path.realpath(str(p))


def _inside(path, ws: Path) -> bool:
    p, w = _real(path), _real(ws)
    return p == w or p.startswith(w + os.sep)


def _check_exe_path(exe: str, ws: Path):
    p = Path(exe)
    abspath = os.path.abspath(p if p.is_absolute() else ws / p)  # no symlink resolution (venv python is a symlink)
    w = os.path.abspath(ws)
    if abspath.startswith(w + os.sep):
        return
    prefix = os.environ.get("PREFIX", "")
    allowed = set(SYSTEM_BIN) | ({os.path.join(prefix, "bin")} if prefix else set())
    if os.path.dirname(abspath) in allowed:
        return
    raise Unsafe(f"executable path outside workspace: {exe}")


def _check_arg(a: str, ws: Path):
    cand = a
    if a.startswith("-"):
        m = re.search(r"(?:=|^-[A-Za-z]+)(/.*|~.*)$", a)
        if not m:
            return
        cand = m.group(1)
    if not cand:
        return
    if cand.startswith("~"):
        raise Unsafe("home-directory paths (~) are not allowed")
    parts = re.split(r"[\\/]", cand)
    if cand.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", cand):
        if not _inside(cand, ws):
            raise Unsafe(f"path outside the workspace: {cand}")
    elif ".." in parts and not _inside(ws / cand, ws):
        raise Unsafe(f"path escapes the workspace: {cand}")


def check_command(cmd: str, ws) -> list:
    """Validate a command string; returns the argv list or raises Unsafe."""
    ws = Path(ws).resolve()
    if not isinstance(cmd, str) or not cmd.strip():
        raise Unsafe("empty command")
    if len(cmd) > 1000 or "\n" in cmd or "\x00" in cmd:
        raise Unsafe("invalid command text")
    for rx, why in DANGEROUS:
        if rx.search(cmd):
            raise Unsafe(f"dangerous command blocked ({why})")
    lex = shlex.shlex(cmd, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    try:
        argv = list(lex)
    except ValueError as e:
        raise Unsafe(f"cannot parse command: {e}")
    if not argv:
        raise Unsafe("empty command")
    if any(a and all(c in OPS for c in a) for a in argv):
        raise Unsafe("shell operators (; && || | > <) are not allowed - one plain command per step")
    if any("`" in a or "$(" in a for a in argv):
        raise Unsafe("command substitution is not allowed")
    exe = argv[0]
    base = os.path.basename(exe)
    if not ALLOWED.match(base):
        raise Unsafe(f"executable '{base}' is not in the allow-list")
    if "/" in exe:
        _check_exe_path(exe, ws)
    if base in ("bash", "sh") and any(
            a in ("-c", "-s") or (a.startswith("-") and not a.startswith("--") and "c" in a) for a in argv[1:]):
        raise Unsafe("inline shell scripts (-c) are not allowed")
    for a in argv[1:]:
        _check_arg(a, ws)
    return argv


def check_file_arg(rel: str, ws) -> str:
    """Validate a file name used by an 'each' step."""
    ws = Path(ws).resolve()
    if not isinstance(rel, str) or not rel or rel.startswith("-") or not _inside(ws / rel, ws):
        raise Unsafe(f"invalid file in step: {rel!r}")
    return rel
