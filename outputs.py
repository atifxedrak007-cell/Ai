"""Turn AI text into UI blocks and save large code as real files (never archives).

Block types returned to the UI:
  {"type": "text",  "content": str}                       plain text (no copy button)
  {"type": "note",  "content": str}                       <note> card (copy button)
  {"type": "code",  "lang", "file", "content"}            small code card (copy button)
  {"type": "file",  "project_id", "name", "lang", "size", "lines", "preview"}  large code saved to disk
"""
import re
from pathlib import Path

import config

LIMIT_LINES = 150
LIMIT_BYTES = 8 * 1024
PREVIEW_LINES = 15

LANG_EXT = {
    "python": "py", "py": "py", "javascript": "js", "js": "js", "node": "js", "typescript": "ts", "ts": "ts",
    "tsx": "tsx", "jsx": "jsx", "html": "html", "css": "css", "java": "java", "c": "c", "cpp": "cpp",
    "c++": "cpp", "go": "go", "golang": "go", "rust": "rs", "rs": "rs", "php": "php", "bash": "sh",
    "sh": "sh", "shell": "sh", "zsh": "sh", "json": "json", "yaml": "yml", "yml": "yml", "toml": "toml",
    "sql": "sql", "ruby": "rb", "rb": "rb", "kotlin": "kt", "swift": "swift", "markdown": "md",
    "md": "md", "xml": "xml", "text": "txt", "txt": "txt", "csharp": "cs", "c#": "cs", "cs": "cs",
    "lua": "lua", "dart": "dart", "ini": "ini",
}
EXT_LANG = {}
for _l, _e in LANG_EXT.items():
    EXT_LANG.setdefault(_e, _l)

TAG_RE = re.compile(r"<(note|code)\b([^>]*)>(.*?)(?:</\1\s*>|\Z)", re.S | re.I)
ATTR_RE = re.compile(r"""(\w+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")
FENCE_RE = re.compile(r"```([\w+#.\-]*)[ \t]*\n(.*?)(?:\n```|\Z)", re.S)
PID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def _attrs(s):
    return {m.group(1).lower(): (m.group(2) if m.group(2) is not None else m.group(3)) for m in ATTR_RE.finditer(s)}


def ext_for(lang: str) -> str:
    lang = (lang or "").strip().lower()
    if lang in LANG_EXT:
        return LANG_EXT[lang]
    return lang if re.fullmatch(r"[a-z0-9]{1,5}", lang) else "txt"


def safe_filename(name: str, lang: str, fallback: str) -> str:
    """Sanitise an AI-supplied filename (basename only) and make sure it has an extension."""
    name = (name or "").replace("\\", "/").split("/")[-1].strip()
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name).lstrip(".")[:100]
    if not name:
        name = fallback
    if "." not in name:
        name += "." + ext_for(lang)
    return name


def _clean_code(body: str) -> str:
    body = body.strip("\n")
    m = re.match(r"^```[\w+#.\-]*[ \t]*\n(.*?)(?:\n```)?\s*$", body, re.S)  # stray fences inside tags
    return m.group(1) if m else body


def _unique_path(directory: Path, name: str) -> Path:
    p = directory / name
    stem, dot, ext = name.rpartition(".")
    n = 2
    while p.exists():
        p = directory / (f"{stem}_{n}.{ext}" if dot else f"{name}_{n}")
        n += 1
    return p


def _code_block(lang, fname, body, pid, label, counter):
    body = _clean_code(body)
    if not lang and fname and "." in fname:
        lang = EXT_LANG.get(fname.rsplit(".", 1)[-1].lower(), "")
    lang = (lang or "text").lower()
    lines = body.count("\n") + 1
    size = len(body.encode("utf-8"))
    if lines <= LIMIT_LINES and size <= LIMIT_BYTES:
        return {"type": "code", "lang": lang, "file": fname or "", "content": body}
    # Large: save as a real file with the proper extension (no ZIP, no archive).
    pid = pid if PID_RE.match(pid or "") else "chat"
    directory = config.OUTPUTS_DIR / pid
    directory.mkdir(parents=True, exist_ok=True)
    path = _unique_path(directory, safe_filename(fname, lang, f"{label}_{counter}"))
    path.write_text(body + "\n", encoding="utf-8")
    return {"type": "file", "project_id": pid, "name": path.name, "lang": lang, "size": path.stat().st_size,
            "lines": lines, "preview": "\n".join(body.split("\n")[:PREVIEW_LINES])}


def build_blocks(text: str, project_id: str = "chat", label: str = "output") -> list:
    blocks, counter, pos = [], [0], 0

    def add_text(chunk):
        # Models sometimes ignore the tag rules and use markdown fences: still make them code cards.
        p = 0
        for m in FENCE_RE.finditer(chunk):
            _push_text(chunk[p:m.start()])
            counter[0] += 1
            blocks.append(_code_block(m.group(1), "", m.group(2), project_id, label, counter[0]))
            p = m.end()
        _push_text(chunk[p:])

    def _push_text(s):
        if s.strip():
            blocks.append({"type": "text", "content": s.strip()})

    for m in TAG_RE.finditer(text):
        add_text(text[pos:m.start()])
        pos = m.end()
        kind, attrs, body = m.group(1).lower(), _attrs(m.group(2)), m.group(3)
        if kind == "note":
            if body.strip():
                blocks.append({"type": "note", "content": body.strip()})
        else:
            counter[0] += 1
            blocks.append(_code_block(attrs.get("lang", ""), attrs.get("file", ""), body, project_id, label, counter[0]))
    add_text(text[pos:])
    return blocks


def resolve(project_id: str, name: str):
    """Safe lookup of a saved output file; returns Path or None."""
    if not PID_RE.match(project_id or "") or not name or "/" in name or "\\" in name or name.startswith("."):
        return None
    p = (config.OUTPUTS_DIR / project_id / name).resolve()
    base = (config.OUTPUTS_DIR / project_id).resolve()
    return p if base in p.parents and p.is_file() else None
