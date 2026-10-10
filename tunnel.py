"""Cloudflare Quick Tunnel launcher (cloudflared). Runs in a background thread."""
import os
import re
import shutil
import signal
import socket
import subprocess
import threading
import time

URL_RE = re.compile(r"https://([a-z0-9-]+)\.trycloudflare\.com")

state = {"status": "off", "url": "", "hint": ""}
_proc = None


def _is_termux() -> bool:
    return "com.termux" in os.environ.get("PREFIX", "")


def _wait_port(port, timeout=40) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.4)
    return False


def _worker(port):
    global _proc
    exe = shutil.which("cloudflared")
    if not exe:
        hint = ("pkg install cloudflared" if _is_termux() else
                "Install cloudflared: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/")
        state.update(status="missing", hint=hint)
        print(f"\n[tunnel] cloudflared not found - running locally only.\n[tunnel] Install: {hint}\n")
        return
    if not _wait_port(port):
        state.update(status="error", hint="server did not start in time")
        return
    state.update(status="starting", hint="")
    try:
        _proc = subprocess.Popen(
            [exe, "tunnel", "--no-autoupdate", "--url", f"http://localhost:{port}"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
            errors="replace", start_new_session=True)
    except OSError as e:
        state.update(status="error", hint=f"could not start cloudflared: {e.__class__.__name__}")
        return
    for line in _proc.stdout:  # keep draining so the pipe never fills up
        if state["url"]:
            continue
        for m in URL_RE.finditer(line):
            if m.group(1) != "api":  # api.trycloudflare.com shows up in error lines
                state.update(status="ready", url=m.group(0))
                print(f"\n[tunnel] Public URL: {m.group(0)}\n")
                break
    if not state["url"]:
        state.update(status="error", hint="cloudflared exited before giving a URL (run it manually to see why)")
        print("[tunnel] cloudflared exited without a public URL.")


def start(port):
    threading.Thread(target=_worker, args=(port,), daemon=True).start()


def stop():
    global _proc
    p, _proc = _proc, None
    if p and p.poll() is None:
        try:
            os.killpg(p.pid, signal.SIGTERM)
            p.wait(timeout=5)
        except (ProcessLookupError, subprocess.TimeoutExpired, OSError):
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                pass
    state.update(status="off", url="")
