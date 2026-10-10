"use strict";
/* ---------- tiny helpers ---------- */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
function h(tag, props, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (k === "class") e.className = v;
    else if (k === "text") e.textContent = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v === true) e.setAttribute(k, "");
    else if (v !== false && v != null) e.setAttribute(k, v);
  }
  for (const kid of kids.flat()) if (kid != null) e.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return e;
}

/* ---------- i18n (default Bengali) ---------- */
const I18N = {
  bn: {
    public_url: "পাবলিক URL:", copy: "কপি", copied: "কপি হয়েছে", logout: "লগআউট", download: "ডাউনলোড",
    tab_upload: "আপলোড", tab_workflow: "ওয়ার্কফ্লো", tab_reviewers: "রিভিউয়ার", tab_chat: "চ্যাট",
    tab_settings: "সেটিংস", tab_history: "ইতিহাস",
    upload_title: "প্রোগ্রাম আপলোড", upload_hint: "একটি ফাইল, একাধিক ফাইল বা একটি zip আপলোড করুন।",
    choose_files: "ফাইল বেছে নিতে এখানে ট্যাপ করুন", project_name: "প্রজেক্টের নাম (ঐচ্ছিক)",
    upload_btn: "আপলোড করুন", need_project: "প্রথমে একটি প্রোগ্রাম আপলোড করুন বা ইতিহাস থেকে খুলুন।",
    run_new: "ওয়ার্কফ্লো তৈরি ও চালান", rerun: "আবার চালান", stop: "থামান",
    review_now: "রিভিউ করুন", with_logs: "রান লগসহ", backend: "ব্যাকএন্ড", syntax: "সিনট্যাক্স", summary: "সারসংক্ষেপ",
    chat_ctx: "বর্তমান প্রজেক্ট ব্যবহার করুন", chat_ph: "আপনার প্রশ্ন লিখুন…", send: "পাঠান", clear: "চ্যাট মুছুন",
    roles_title: "এজেন্টের মডেল", models_title: "মডেল তালিকা",
    keys_hint: "API কী শুধু .env ফাইলে থাকে; এখানে শুধু আছে/নেই দেখানো হয়।",
    add_model: "নতুন মডেল যোগ করুন", f_name: "নাম", f_base: "base_url (যেমন https://api.groq.com/openai/v1)",
    f_model: "model_id", f_env: "API কী এনভায়রনমেন্ট ভ্যারিয়েবল (যেমন GROQ_API_KEY)", add: "যোগ করুন",
    role_backend_reviewer: "ব্যাকএন্ড রিভিউয়ার", role_syntax_reviewer: "সিনট্যাক্স রিভিউয়ার",
    role_workflow_runner: "ওয়ার্কফ্লো রানার", role_chat: "চ্যাট ও সারসংক্ষেপ",
    key_set: "কী আছে", key_missing: "কী নেই", remove: "মুছুন", open: "খুলুন", delete: "ডিলিট",
    st_pending: "অপেক্ষমাণ", st_running: "চলছে", st_success: "সফল", st_failed: "ব্যর্থ", st_skipped: "বাদ", st_planning: "পরিকল্পনা",
    st_stopped: "থামানো", st_queued: "অপেক্ষমাণ", st_idle: "প্রস্তুত",
    no_steps: "কোনো ধাপ তৈরি করা যায়নি (ভাষা শনাক্ত হয়নি?)", plan_ai: "AI পরিকল্পনা", plan_default: "ডিফল্ট পরিকল্পনা",
    blocked: "নিরাপত্তার কারণে বাদ", exit: "এক্সিট", sec: "সে.", lines: "লাইন",
    review_running: "রিভিউ চলছে…", review_none: "এখনো রিভিউ নেই।", review_started: "রিভিউ শুরু হয়েছে",
    thinking: "ভাবছি…", uploaded: "আপলোড সম্পন্ন", files: "ফাইল", language: "ভাষা", go_workflow: "ওয়ার্কফ্লো চালান",
    go_review: "শুধু রিভিউ", no_history: "এখনো কোনো প্রজেক্ট নেই।", confirm_del: "এই প্রজেক্ট ডিলিট করবেন?",
    locked_msg: "পাসওয়ার্ড সেট করা নেই, তাই পাবলিক লিংকে ব্যবহার বন্ধ। .env-এ APP_PASSWORD দিন, অথবা ফোনেই localhost ব্যবহার করুন।",
    tunnel_starting: "চালু হচ্ছে…", tunnel_missing: "cloudflared নেই — শুধু লোকাল", tunnel_error: "টানেল ত্রুটি",
    fell_back: "ফলব্যাক", runs: "রান", reviews: "রিভিউ", preview: "প্রিভিউ", fail_net: "নেটওয়ার্ক ত্রুটি",
  },
  en: {
    public_url: "Public URL:", copy: "Copy", copied: "Copied", logout: "Log out", download: "Download",
    tab_upload: "Upload", tab_workflow: "Workflow", tab_reviewers: "Reviewers", tab_chat: "Chat",
    tab_settings: "Settings", tab_history: "History",
    upload_title: "Upload a program", upload_hint: "Upload one file, several files or a zip.",
    choose_files: "Tap to choose files", project_name: "Project name (optional)", upload_btn: "Upload",
    need_project: "Upload a program first, or open one from History.",
    run_new: "Generate & run workflow", rerun: "Re-run", stop: "Stop",
    review_now: "Run review", with_logs: "Include run logs", backend: "Backend", syntax: "Syntax", summary: "Summary",
    chat_ctx: "Use the current project", chat_ph: "Type your question…", send: "Send", clear: "Clear chat",
    roles_title: "Model per agent", models_title: "Models",
    keys_hint: "API keys live only in .env; this page only shows whether a key is set.",
    add_model: "Add a model", f_name: "Name", f_base: "base_url (e.g. https://api.groq.com/openai/v1)",
    f_model: "model_id", f_env: "API key env variable name (e.g. GROQ_API_KEY)", add: "Add",
    role_backend_reviewer: "Backend Reviewer", role_syntax_reviewer: "Syntax Reviewer",
    role_workflow_runner: "Workflow Runner", role_chat: "Chat & summary",
    key_set: "key set", key_missing: "no key", remove: "Remove", open: "Open", delete: "Delete",
    st_pending: "pending", st_running: "running", st_success: "success", st_failed: "failed", st_skipped: "skipped", st_planning: "planning",
    st_stopped: "stopped", st_queued: "queued", st_idle: "ready",
    no_steps: "No steps could be created (language not detected?)", plan_ai: "AI plan", plan_default: "default plan",
    blocked: "Blocked by safety rules", exit: "exit", sec: "s", lines: "lines",
    review_running: "Review running…", review_none: "No review yet.", review_started: "Review started",
    thinking: "Thinking…", uploaded: "Upload complete", files: "files", language: "language", go_workflow: "Run workflow",
    go_review: "Review only", no_history: "No projects yet.", confirm_del: "Delete this project?",
    locked_msg: "No password is set, so public-link use is locked. Set APP_PASSWORD in .env, or use localhost on the phone.",
    tunnel_starting: "starting…", tunnel_missing: "cloudflared missing - local only", tunnel_error: "tunnel error",
    fell_back: "fallback", runs: "runs", reviews: "reviews", preview: "preview", fail_net: "Network error",
  },
};
let lang = localStorage.getItem("lang") || "bn";
const t = (k) => (I18N[lang] && I18N[lang][k]) || I18N.en[k] || k;

function applyI18n() {
  document.documentElement.lang = lang;
  $$("[data-i18n]").forEach((e) => (e.textContent = t(e.dataset.i18n)));
  $$("[data-i18n-ph]").forEach((e) => (e.placeholder = t(e.dataset.i18nPh)));
  $("#langBtn").textContent = lang === "bn" ? "EN" : "বাং";
  renderProjBar();
  setRunStatus(S.runStatus);
}

/* ---------- state ---------- */
const S = { project: null, runId: null, runES: null, steps: [], runStatus: "idle", rv: {}, rvTab: "backend_reviewer", chatLoaded: false, info: {} };

/* ---------- toast / api / sse ---------- */
let toastTimer;
function toast(msg, bad) {
  const el = $("#toast");
  el.textContent = msg;
  el.className = "show" + (bad ? " bad" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.className = ""), bad ? 6000 : 2500);
}

async function api(path, opts = {}) {
  const init = { method: opts.method || "GET", headers: {} };
  if (opts.json !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(opts.json); }
  if (opts.form) init.body = opts.form;
  let r;
  try { r = await fetch(path, init); } catch (e) { throw new Error(t("fail_net")); }
  if (r.status === 401) { location.href = "/login"; throw new Error("auth"); }
  let data = {};
  try { data = await r.json(); } catch (_) { /* non-JSON */ }
  if (!r.ok) throw new Error(data.message || data.error || `HTTP ${r.status}`);
  return data;
}
const guard = (fn) => async (...a) => { try { return await fn(...a); } catch (e) { if (e.message !== "auth") toast(e.message, true); } };

function listen(url, onEvent) {
  const es = new EventSource(url);
  es.onmessage = (m) => {
    let ev; try { ev = JSON.parse(m.data); } catch (_) { return; }
    onEvent(ev);
    if (ev.type === "done") es.close();
  };
  return es;
}

/* ---------- copy ---------- */
async function copyText(text, btn) {
  try { await navigator.clipboard.writeText(text); }
  catch (_) {
    const ta = h("textarea", { style: "position:fixed;opacity:0" }); ta.value = text; document.body.append(ta);
    ta.select(); try { document.execCommand("copy"); } catch (_) { /* ignore */ } ta.remove();
  }
  if (btn) { const old = btn.textContent; btn.textContent = t("copied"); setTimeout(() => (btn.textContent = old), 1400); }
}

/* ---------- AI blocks: text (no copy) / note / code / file ---------- */
function inlineText(s) {
  // plain text with light **bold** and `code`; built from DOM nodes (no HTML injection)
  const out = []; const re = /(\*\*[^*]+\*\*|`[^`\n]+`)/g; let last = 0, m;
  while ((m = re.exec(s))) {
    out.push(s.slice(last, m.index));
    out.push(m[0].startsWith("**") ? h("b", { text: m[0].slice(2, -2) }) : h("code", { class: "cmd", text: m[0].slice(1, -1) }));
    last = m.index + m[0].length;
  }
  out.push(s.slice(last));
  return out;
}

function renderBlocks(box, blocks) {
  box.replaceChildren();
  for (const b of blocks || []) {
    if (b.type === "text") box.append(h("div", { class: "text-block" }, inlineText(b.content)));
    else if (b.type === "note") {
      const btn = h("button", { class: "btn sm", text: t("copy") });
      btn.addEventListener("click", () => copyText(b.content, btn));
      box.append(h("div", { class: "bcard note" }, h("div", { class: "bhead" }, h("span", { class: "lbl", text: "Note" }), h("span", { class: "acts" }, btn)),
        h("div", { class: "note-body", text: b.content })));
    } else if (b.type === "code") {
      const btn = h("button", { class: "btn sm", text: t("copy") });
      btn.addEventListener("click", () => copyText(b.content, btn));
      box.append(h("div", { class: "bcard" }, h("div", { class: "bhead" },
        h("span", { class: "lbl", text: [b.file, b.lang].filter(Boolean).join(" · ") }), h("span", { class: "acts" }, btn)),
        h("pre", { text: b.content })));
    } else if (b.type === "file") {
      const url = `/api/files/${encodeURIComponent(b.project_id)}/${encodeURIComponent(b.name)}`;
      const cbtn = h("button", { class: "btn sm", text: t("copy") });
      cbtn.addEventListener("click", guard(async () => {
        const r = await fetch(url + "?raw=1"); if (!r.ok) throw new Error("HTTP " + r.status);
        await copyText(await r.text(), cbtn);
      }));
      const dl = h("a", { class: "btn sm", href: url, download: b.name, text: t("download") });
      box.append(h("div", { class: "bcard" },
        h("div", { class: "bhead" }, h("span", { class: "lbl", text: b.name }), h("span", { class: "acts" }, cbtn, dl)),
        h("div", { class: "fileinfo" }, h("span", { text: b.lang }), h("span", { text: fmtSize(b.size) }), h("span", { text: `${b.lines} ${t("lines")}` })),
        h("pre", { text: b.preview + (b.lines > 15 ? "\n…" : "") })));
    }
  }
}
const fmtSize = (n) => (n < 1024 ? `${n} B` : `${(n / 1024).toFixed(1)} KB`);

/* ---------- tabs ---------- */
function showTab(name) {
  $$("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === name));
  $$(".panel").forEach((p) => p.classList.toggle("on", p.id === "tab-" + name));
  if (name === "settings") loadSettings();
  if (name === "history") loadHistory();
  if (name === "chat") loadChat();
  localStorage.setItem("tab", name);
}
$("#tabs").addEventListener("click", (e) => { const b = e.target.closest("button[data-tab]"); if (b) showTab(b.dataset.tab); });

/* ---------- top bar ---------- */
async function loadInfo() {
  try {
    const i = await api("/api/info"); S.info = i;
    const a = $("#pubUrl");
    if (i.tunnel_url) { a.textContent = i.tunnel_url; a.href = i.tunnel_url; $("#copyUrl").hidden = false; }
    else {
      a.removeAttribute("href");
      a.textContent = i.tunnel_status === "missing" ? `${t("tunnel_missing")}: ${i.tunnel_hint}`
        : i.tunnel_status === "error" ? `${t("tunnel_error")}: ${i.tunnel_hint}` : i.tunnel_status === "off" ? "—" : t("tunnel_starting");
    }
    $("#logoutBtn").hidden = !i.auth_required;
    $("#lockedBanner").hidden = !i.locked;
    if (i.tunnel_status === "starting" || (i.tunnel_status !== "ready" && i.tunnel_status !== "off")) setTimeout(loadInfo, 3000);
  } catch (_) { /* ignore */ }
}
$("#copyUrl").addEventListener("click", () => copyText($("#pubUrl").textContent, $("#copyUrl")));
$("#logoutBtn").addEventListener("click", async () => { await fetch("/api/logout", { method: "POST" }); location.href = "/login"; });
$("#langBtn").addEventListener("click", () => {
  lang = lang === "bn" ? "en" : "bn"; localStorage.setItem("lang", lang); applyI18n(); loadInfo();
  const tab = localStorage.getItem("tab"); if (tab === "settings") loadSettings(); if (tab === "history") loadHistory();
  renderRv(); renderUploadResult();
});

/* ---------- project bar ---------- */
function renderProjBar() {
  const bar = $("#projBar"); const p = S.project;
  bar.hidden = !p; if (!p) return;
  bar.replaceChildren(h("b", { text: p.name }), h("span", { class: "muted", text: `${p.language} · ${p.file_count || (p.files || []).length} ${t("files")}` }));
}
function setProject(p) {
  S.project = p; renderProjBar();
  $("#wfEmpty").hidden = $("#rvEmpty").hidden = true; $("#wfBody").hidden = $("#rvBody").hidden = false;
  S.rv = {}; renderRv();
}

/* ---------- upload ---------- */
$("#fileInput").addEventListener("change", (e) => {
  const n = e.target.files.length;
  $("#dropText").textContent = n ? [...e.target.files].map((f) => f.name).join(", ") : t("choose_files");
});
$("#uploadBtn").addEventListener("click", guard(async () => {
  const files = $("#fileInput").files;
  if (!files.length) { toast(t("choose_files"), true); return; }
  const fd = new FormData();
  for (const f of files) fd.append("files", f, f.webkitRelativePath || f.name);
  fd.append("name", $("#projName").value);
  $("#uploadBtn").disabled = true;
  try {
    const p = await api("/api/upload", { method: "POST", form: fd });
    setProject(p); S.runId = null; resetSteps(); S.uploaded = p; renderUploadResult();
    $("#fileInput").value = ""; $("#dropText").textContent = t("choose_files"); toast(t("uploaded"));
  } finally { $("#uploadBtn").disabled = false; }
}));
function renderUploadResult() {
  const box = $("#uploadResult"); const p = S.uploaded; if (!p) return box.replaceChildren();
  box.replaceChildren(h("div", { class: "card" },
    h("b", { text: p.name }),
    h("div", { class: "muted small", text: `${t("language")}: ${p.language} · ${p.file_count} ${t("files")}` }),
    h("div", { class: "small muted", style: "margin:8px 0;word-break:break-all", text: (p.files || []).slice(0, 12).map((f) => f.path).join("\n") }),
    h("div", { class: "row" },
      h("button", { class: "btn primary", text: t("go_workflow"), onclick: () => { showTab("workflow"); startRun(true); } }),
      h("button", { class: "btn", text: t("go_review"), onclick: () => { showTab("reviewers"); startReview(); } }))));
}

/* ---------- workflow ---------- */
const STATUS_KEY = (s) => "st_" + s;
function setRunStatus(s) {
  S.runStatus = s || "idle";
  const b = $("#runStatus"); b.className = "badge " + S.runStatus; b.textContent = t(STATUS_KEY(S.runStatus));
  const active = S.runStatus === "planning" || S.runStatus === "running";
  $("#runBtn").disabled = active; $("#rerunBtn").disabled = active; $("#stopBtn").disabled = !active;
}
function resetSteps() { S.steps = []; $("#steps").replaceChildren(); $("#planWarn").replaceChildren(); $("#planInfo").textContent = ""; setRunStatus("idle"); }

function buildSteps(steps) {
  const box = $("#steps"); box.replaceChildren(); S.steps = [];
  steps.forEach((st, i) => {
    const badge = h("span", { class: "badge pending", text: t("st_pending") });
    const meta = h("div", { class: "step-meta" });
    const log = h("pre", { class: "log" });
    const card = h("div", { class: "card step" },
      h("div", { class: "step-head", onclick: () => card.classList.toggle("open") },
        h("span", { class: "step-n", text: i + 1 }),
        h("div", { class: "step-title" }, h("b", { text: st.name }), h("span", { class: "cmd", text: st.cmd + (st.each ? ` (${st.each.length} ${t("files")})` : "") })), badge),
      meta, log);
    box.append(card); S.steps.push({ card, badge, meta, log });
  });
}
function updateStep(i, status, code, dur) {
  const s = S.steps[i]; if (!s) return;
  s.badge.className = "badge " + status; s.badge.textContent = t(STATUS_KEY(status));
  if (status === "running") s.card.classList.add("open");
  if (code !== undefined && code !== null || dur) s.meta.textContent = [code != null ? `${t("exit")} ${code}` : "", dur ? `${dur}${t("sec")}` : ""].filter(Boolean).join(" · ");
  if (status === "failed") s.card.classList.add("open");
}
function appendLog(i, text) {
  const s = S.steps[i]; if (!s) return;
  const near = s.log.scrollHeight - s.log.scrollTop - s.log.clientHeight < 60;
  s.log.append(text); if (near) s.log.scrollTop = s.log.scrollHeight;
}
function showPlanMeta(ev) {
  const box = $("#planWarn"); box.replaceChildren();
  $("#planInfo").textContent = ev.source ? `${ev.source.startsWith("ai") ? t("plan_ai") : t("plan_default")}${ev.model ? " · " + ev.model : ""}` : "";
  if (ev.note) box.append(h("div", { class: "warnbox", text: ev.note }));
  (ev.blocked || []).forEach((b) => box.append(h("div", { class: "warnbox", text: `${t("blocked")}: ${b.cmd} — ${b.reason}` })));
}
function onRunEvent(ev) {
  switch (ev.type) {
    case "plan": buildSteps(ev.steps); showPlanMeta(ev); break;
    case "snapshot": {
      buildSteps(ev.run.steps); showPlanMeta(ev.plan || {});
      ev.run.steps.forEach((s, i) => { updateStep(i, s.status, s.exit_code, s.duration); if (s.log) S.steps[i].log.textContent = s.log; });
      setRunStatus(ev.run.status); break;
    }
    case "run_status": setRunStatus(ev.status); if (ev.message === "no_steps") toast(t("no_steps"), true); else if (ev.message) toast(ev.message, true); break;
    case "step": updateStep(ev.index, ev.status, ev.exit_code, ev.duration); break;
    case "log": appendLog(ev.index, ev.text); break;
    case "review_job": toast(t("review_started")); attachReviewJob(ev.job_id); break;
  }
}
function connectRun(runId) {
  if (S.runES) S.runES.close();
  S.runId = runId; resetSteps();
  S.runES = listen(`/api/runs/${runId}/stream`, onRunEvent);
}
const startRun = guard(async (replan) => {
  if (!S.project) return;
  const r = await api(`/api/projects/${S.project.id}/runs`, { method: "POST", json: { replan, lang, auto_review: true } });
  S.rv = {}; renderRv(); connectRun(r.run_id); setRunStatus("planning");
});
$("#runBtn").addEventListener("click", () => startRun(true));
$("#rerunBtn").addEventListener("click", () => startRun(false));
$("#stopBtn").addEventListener("click", guard(async () => { if (S.runId) await api(`/api/runs/${S.runId}/stop`, { method: "POST" }); }));

/* ---------- reviewers ---------- */
function renderRv() {
  $$("#rvTabs button").forEach((b) => b.classList.toggle("on", b.dataset.rv === S.rvTab));
  for (const k of ["backend_reviewer", "syntax_reviewer", "summary"]) {
    const d = $("#dot-" + k); if (d) d.className = "dot " + ((S.rv[k] && S.rv[k].state) || "");
  }
  const pane = $("#rvPane"); if (!pane) return;
  const cur = S.rv[S.rvTab]; pane.replaceChildren();
  if (!cur) { pane.append(h("div", { class: "muted card", text: t("review_none") })); return; }
  if (cur.state === "running") { pane.append(h("div", { class: "card muted", text: t("review_running") })); return; }
  if (cur.state === "error") { pane.append(h("div", { class: "warnbox", text: cur.message })); return; }
  const card = h("div", { class: "card" });
  if (cur.model) card.append(h("div", { class: "modelline", text: cur.model }));
  (cur.notes || []).forEach((n) => card.append(h("div", { class: "warnbox", text: `${t("fell_back")}: ${n}` })));
  const body = h("div"); renderBlocks(body, cur.blocks); card.append(body); pane.append(card);
}
$("#rvTabs").addEventListener("click", (e) => { const b = e.target.closest("button[data-rv]"); if (b) { S.rvTab = b.dataset.rv; renderRv(); } });

function attachReviewJob(jobId) {
  if (S.jobES) S.jobES.close();
  S.rv = { backend_reviewer: { state: "running" }, syntax_reviewer: { state: "running" }, summary: { state: "running" } }; renderRv();
  S.jobES = listen(`/api/jobs/${jobId}/stream`, (ev) => {
    if (ev.type === "review_done") S.rv[ev.role] = { state: "done", model: ev.model, notes: ev.notes, blocks: ev.blocks };
    else if (ev.type === "review_error") {
      if (ev.role === "all") ["backend_reviewer", "syntax_reviewer", "summary"].forEach((r) => (S.rv[r] = { state: "error", message: ev.message }));
      else S.rv[ev.role] = { state: "error", message: ev.message };
    } else if (ev.type === "summary") S.rv.summary = { state: "done", model: ev.model, blocks: ev.blocks };
    else if (ev.type === "summary_error") S.rv.summary = { state: "error", message: ev.message };
    else if (ev.type === "done") for (const k in S.rv) if (S.rv[k].state === "running") S.rv[k] = { state: "error", message: "—" };
    renderRv();
  });
}
const startReview = guard(async () => {
  if (!S.project) return;
  const r = await api(`/api/projects/${S.project.id}/review`, { method: "POST", json: { lang, include_logs: $("#withLogs").checked, run_id: S.runId } });
  attachReviewJob(r.job_id);
});
$("#reviewBtn").addEventListener("click", startReview);

async function loadStoredReviews() {
  if (!S.project) return;
  const { reviews } = await api(`/api/projects/${S.project.id}/reviews`);
  S.rv = {};
  for (const r of reviews) if (!S.rv[r.role]) S.rv[r.role] = { state: "done", model: r.model, blocks: r.blocks };
  renderRv();
}

/* ---------- chat ---------- */
function chatBubble(role, blocks, text) {
  const box = h("div", { class: "msg " + role });
  if (role === "user") box.textContent = text; else renderBlocks(box, blocks && blocks.length ? blocks : [{ type: "text", content: text }]);
  $("#chatLog").append(box); box.scrollIntoView({ block: "end" }); return box;
}
const loadChat = guard(async () => {
  if (S.chatLoaded) return; S.chatLoaded = true;
  const { messages } = await api("/api/chat");
  messages.forEach((m) => chatBubble(m.role, m.blocks, m.content));
});
$("#chatSend").addEventListener("click", guard(async () => {
  const input = $("#chatMsg"); const msg = input.value.trim(); if (!msg) return;
  input.value = ""; chatBubble("user", null, msg);
  const wait = chatBubble("assistant", null, t("thinking")); $("#chatSend").disabled = true;
  try {
    const r = await api("/api/chat", { method: "POST", json: { message: msg, lang, project_id: $("#chatCtx").checked && S.project ? S.project.id : null } });
    listen(`/api/jobs/${r.job_id}/stream`, (ev) => {
      if (ev.type === "chat_done") { renderBlocks(wait, ev.blocks); (ev.notes || []).forEach((n) => wait.append(h("div", { class: "warnbox", text: n }))); }
      else if (ev.type === "chat_error") { wait.replaceChildren(h("div", { class: "warnbox", text: ev.message })); }
      else if (ev.type === "done") $("#chatSend").disabled = false;
    });
  } catch (e) { wait.remove(); $("#chatSend").disabled = false; throw e; }
}));
$("#chatClear").addEventListener("click", guard(async () => { await api("/api/chat", { method: "DELETE" }); $("#chatLog").replaceChildren(); }));

/* ---------- settings ---------- */
const loadSettings = guard(async () => {
  const d = await api("/api/models");
  const roles = $("#roles"); roles.replaceChildren();
  d.role_names.forEach((role) => {
    const sel = h("select", { class: "inp" }, h("option", { value: "", text: "—" }),
      d.models.map((m) => h("option", { value: m.name, text: m.name, selected: d.roles[role] === m.name })));
    sel.addEventListener("change", guard(async () => { await api("/api/roles", { method: "PUT", json: { [role]: sel.value } }); toast("✓"); }));
    roles.append(h("div", { class: "role" }, h("label", { text: t("role_" + role) }), sel));
  });
  const list = $("#modelList"); list.replaceChildren();
  d.models.forEach((m) => {
    const cb = h("input", { type: "checkbox", checked: m.enabled, "aria-label": m.name });
    cb.addEventListener("change", guard(async () => { await api(`/api/models/${encodeURIComponent(m.name)}`, { method: "PATCH", json: { enabled: cb.checked } }); }));
    const del = h("button", { class: "btn sm danger", text: t("remove") });
    del.addEventListener("click", guard(async () => { await api(`/api/models/${encodeURIComponent(m.name)}`, { method: "DELETE" }); loadSettings(); }));
    list.append(h("div", { class: "item" }, cb, h("div", { class: "grow" },
      h("div", { class: "t", text: m.name }),
      h("div", { class: "s", text: `${m.provider} · ${m.model_id} · ${m.api_key_env} (${m.key_set ? t("key_set") : t("key_missing")})` })), del));
  });
  const sel = $("#provSel"); if (!sel.children.length) d.providers.forEach((p) => sel.append(h("option", { value: p, text: p })));
});
$("#addForm").addEventListener("submit", guard(async (e) => {
  e.preventDefault();
  const o = Object.fromEntries(new FormData(e.target)); o.enabled = true;
  await api("/api/models", { method: "POST", json: o });
  e.target.reset(); toast("✓"); loadSettings();
}));

/* ---------- history ---------- */
const loadHistory = guard(async () => {
  const { projects } = await api("/api/history");
  const box = $("#historyList"); box.replaceChildren();
  if (!projects.length) { box.append(h("div", { class: "card muted", text: t("no_history") })); return; }
  projects.forEach((p) => {
    box.append(h("div", { class: "card" }, h("div", { class: "item", style: "border:0;padding:0" },
      h("div", { class: "grow" }, h("div", { class: "t", text: p.name }),
        h("div", { class: "s", text: `${p.language} · ${p.file_count} ${t("files")} · ${p.run_count} ${t("runs")} · ${p.review_count} ${t("reviews")} · ${new Date(p.created * 1000).toLocaleString()}` })),
      h("div", { class: "row", style: "margin:0" },
        h("button", { class: "btn sm", text: t("open"), onclick: guard(() => openProject(p.id)) }),
        h("button", { class: "btn sm danger", text: t("delete"), onclick: guard(async () => {
          if (!confirm(t("confirm_del"))) return;
          await api(`/api/projects/${p.id}`, { method: "DELETE" });
          if (S.project && S.project.id === p.id) { S.project = null; renderProjBar(); $("#wfBody").hidden = $("#rvBody").hidden = true; $("#wfEmpty").hidden = $("#rvEmpty").hidden = false; }
          loadHistory();
        }) })))));
  });
});
async function openProject(id) {
  const p = await api(`/api/projects/${id}`);
  setProject(p); S.uploaded = null; renderUploadResult();
  const runId = p.active_run || (p.last_run && p.last_run.id);
  if (runId) connectRun(runId); else resetSteps();
  await loadStoredReviews();
  showTab("workflow");
}

/* ---------- boot ---------- */
applyI18n();
loadInfo();
showTab(localStorage.getItem("tab") || "upload");
