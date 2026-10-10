"""SQLite history: projects, workflow runs, reviews and chat messages."""
import json
import sqlite3
import threading
import time

from config import DATA_DIR

DB_PATH = DATA_DIR / "app.db"
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects(
  id TEXT PRIMARY KEY, name TEXT, language TEXT, created REAL, file_count INTEGER);
CREATE TABLE IF NOT EXISTS runs(
  id TEXT PRIMARY KEY, project_id TEXT, status TEXT, plan_json TEXT,
  steps_json TEXT, created REAL, finished REAL);
CREATE TABLE IF NOT EXISTS reviews(
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT, run_id TEXT,
  role TEXT, model TEXT, blocks_json TEXT, created REAL);
CREATE TABLE IF NOT EXISTS chats(
  id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, project_id TEXT,
  content TEXT, blocks_json TEXT, created REAL);
CREATE INDEX IF NOT EXISTS idx_runs_p ON runs(project_id, created);
CREATE INDEX IF NOT EXISTS idx_rev_p ON reviews(project_id, created);
"""


def _exec(sql, args=(), fetch=False):
    with _lock:
        conn = sqlite3.connect(DB_PATH, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute(sql, args)
            out = [dict(r) for r in cur.fetchall()] if fetch else cur.lastrowid
            conn.commit()
            return out
        finally:
            conn.close()


def init():
    with _lock:
        conn = sqlite3.connect(DB_PATH)
        conn.executescript(SCHEMA)
        # Runs that were active when the app last stopped can never finish.
        conn.execute("UPDATE runs SET status='failed' WHERE status IN ('planning','running')")
        conn.commit()
        conn.close()


# ------------------------------------------------------------------ projects
def add_project(pid, name, language, file_count):
    _exec("INSERT INTO projects VALUES(?,?,?,?,?)", (pid, name, language, time.time(), file_count))


def get_project(pid):
    rows = _exec("SELECT * FROM projects WHERE id=?", (pid,), True)
    return rows[0] if rows else None


def list_projects():
    return _exec(
        """SELECT p.*, 
           (SELECT COUNT(*) FROM runs r WHERE r.project_id=p.id) AS run_count,
           (SELECT COUNT(*) FROM reviews v WHERE v.project_id=p.id) AS review_count
           FROM projects p ORDER BY created DESC LIMIT 100""", (), True)


def delete_project(pid):
    for table in ("runs", "reviews", "chats"):
        _exec(f"DELETE FROM {table} WHERE project_id=?", (pid,))
    _exec("DELETE FROM projects WHERE id=?", (pid,))


# ---------------------------------------------------------------------- runs
def save_run(run_id, pid, status, plan, steps):
    _exec(
        """INSERT INTO runs(id,project_id,status,plan_json,steps_json,created,finished)
           VALUES(?,?,?,?,?,?,NULL)
           ON CONFLICT(id) DO UPDATE SET status=excluded.status,
             plan_json=COALESCE(excluded.plan_json, runs.plan_json), steps_json=excluded.steps_json,
             finished=CASE WHEN excluded.status IN ('success','failed','stopped') THEN ? ELSE NULL END""",
        (run_id, pid, status, json.dumps(plan) if plan else None, json.dumps(steps), time.time(), time.time()))


def get_run(run_id):
    rows = _exec("SELECT * FROM runs WHERE id=?", (run_id,), True)
    if not rows:
        return None
    r = rows[0]
    r["steps"] = json.loads(r["steps_json"] or "[]")
    r["plan"] = json.loads(r["plan_json"]) if r["plan_json"] else None
    return r


def latest_run(pid):
    rows = _exec("SELECT id,status,created FROM runs WHERE project_id=? ORDER BY created DESC LIMIT 1", (pid,), True)
    return rows[0] if rows else None


def latest_plan(pid):
    rows = _exec("SELECT plan_json FROM runs WHERE project_id=? AND plan_json IS NOT NULL "
                 "ORDER BY created DESC LIMIT 1", (pid,), True)
    return json.loads(rows[0]["plan_json"]) if rows else None


# ------------------------------------------------------------------- reviews
def add_review(pid, run_id, role, model, blocks):
    _exec("INSERT INTO reviews(project_id,run_id,role,model,blocks_json,created) VALUES(?,?,?,?,?,?)",
          (pid, run_id, role, model, json.dumps(blocks), time.time()))


def list_reviews(pid, limit=30):
    rows = _exec("SELECT * FROM reviews WHERE project_id=? ORDER BY id DESC LIMIT ?", (pid, limit), True)
    for r in rows:
        r["blocks"] = json.loads(r.pop("blocks_json"))
    return rows


# ---------------------------------------------------------------------- chat
def add_chat(role, pid, content, blocks=None):
    _exec("INSERT INTO chats(role,project_id,content,blocks_json,created) VALUES(?,?,?,?,?)",
          (role, pid, content, json.dumps(blocks) if blocks else None, time.time()))


def list_chat(limit=40):
    rows = _exec("SELECT * FROM chats ORDER BY id DESC LIMIT ?", (limit,), True)[::-1]
    for r in rows:
        r["blocks"] = json.loads(r.pop("blocks_json")) if r["blocks_json"] else None
    return rows


def clear_chat():
    _exec("DELETE FROM chats")
