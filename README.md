# AI Code Review & Workflow Tool

Upload a program, let an AI build a workflow (install → syntax check → tests → run), watch live logs,
and get reviews from a Backend Reviewer and a Syntax Reviewer. Works on Termux (Android, no root) and Linux.
Mobile-first dark UI, Bengali/English toggle (default Bengali).

## ⚠️ Security warning (read this)

The page is reachable from the internet through a Cloudflare Quick Tunnel.
**Without a password, anyone with the link could spend your API tokens and run code on your phone.**

* Set `APP_PASSWORD` in `.env`. Then every page and API route requires login (with rate limiting).
* If `APP_PASSWORD` is empty, the app **locks all `/api/*` routes for requests that arrive through the tunnel**
  (the UI shows a red banner). Using it locally (`http://localhost:8000`) still works.
  Override only if you really want to: `ALLOW_INSECURE_PUBLIC=1`.
* Uploaded programs are **executed on your device with your user's permissions**. The workflow runner is a
  best-effort guard, not a sandbox: no shell (so no pipes/redirects/`&&`), an allow-list of executables,
  blocked dangerous commands, path arguments must stay inside `workspace/<project_id>/`, a minimal environment
  (your API keys are NOT passed to the program), timeouts, and a file-size limit. A malicious program can still
  do things its own code does. Only upload code you trust.
* Settings lets you change where requests are sent (`base_url`). Keep `APP_PASSWORD` set so only you can do that.

## Termux setup

```bash
pkg update && pkg upgrade -y
pkg install -y python git cloudflared nodejs      # nodejs only if you run JS projects
cd ai-review-tool
pip install -r requirements.txt
cp .env.example .env
nano .env                                          # set APP_PASSWORD and at least one API key
termux-wake-lock                                   # optional: keep running with the screen off
python app.py
```

Open the printed `https://*.trycloudflare.com` URL (also shown at the top of the page),
or `http://localhost:8000` on the phone. Stop with `Ctrl+C` (tunnel and running workflows are stopped).

On normal Linux: install Python 3.9+, `pip install -r requirements.txt`, install
[cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/), then `python app.py`.
Without `cloudflared` the app prints the install hint and keeps running locally.

## API keys and models

* Keys live only in `.env` (variable names match `api_key_env` in `models.json`). They are never shown in the UI,
  logs or error messages (all error text is scrubbed).
* `models.json` holds the model list and the role → model assignment. Edit it in **Settings** (add, remove,
  enable/disable, assign models to the 3 agents + chat). Providers: `openai-compatible`, `anthropic`, `gemini`.
* Model IDs (especially free ones such as OpenRouter `:free`) change often. If a model returns "not found",
  fix its `model_id` in Settings. Failed calls are retried, then the next enabled model that has a key is used.
* The chat and the combined summary use the `chat` role.

## Features

* **Workflow**: language detection, AI-generated plan (falls back to a built-in plan), steps with
  pending/running/success/failed status, live logs over SSE, Re-run and Stop. Long-running programs
  (servers/bots) are stopped at the run step's timeout and counted as OK.
* **Reviewers**: Backend + Syntax run in parallel, then a combined summary. After a workflow finishes,
  the logs are reviewed automatically.
* **Copy buttons**: AI answers use `<note>` and `<code lang file>` tags; each tagged block is its own card with its
  own Copy button. Plain text has none.
* **Large code (> 150 lines or 8 KB)**: saved as real files in `outputs/<project_id>/` with the correct extension
  (never a ZIP) and shown as file cards (preview, Copy, per-file Download).
* **History** in SQLite (`data/app.db`).

## Layout

```
app.py            web server, routes, shutdown
config.py db.py security.py llm.py streams.py outputs.py tunnel.py
agents/           prompts.py reviewers.py chat.py
workflow/         fsutil.py detect.py safety.py planner.py runner.py
static/           index.html style.css app.js login.html
models.json  .env.example  requirements.txt
```
