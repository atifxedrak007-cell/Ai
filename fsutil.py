"""Workspace file helpers: safe uploads, zip-slip-safe extraction, listing, source collection."""
import os
import re
import shutil
import stat
import zipfile
from pathlib import Path

import config

IGNORE_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".home", "target", "build", "dist",
               ".cache", ".mypy_cache", ".pytest_cache", ".idea", ".vscode"}
SKIP_FILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Cargo.lock", "composer.lock"}
TEXT_EXTS = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".go", ".rs", ".c", ".h", ".cpp", ".cc", ".hpp",
             ".java", ".php", ".rb", ".sh", ".html", ".css", ".json", ".toml", ".yml", ".yaml", ".md", ".txt",
             ".sql", ".kt", ".swift", ".cs", ".lua", ".ini", ".cfg"}
TEXT_NAMES = {"Makefile", "Dockerfile", "requirements.txt", "Gemfile"}
MAX_FILES, MAX_TOTAL_BYTES = 5000, 200 * 1024 * 1024


def safe_part(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .")[:120]


def safe_relpath(filename: str) -> str:
    """Sanitised relative path (subfolders kept, '..' rejected)."""
    parts = [p for p in (filename or "").replace("\\", "/").split("/") if p not in ("", ".")]
    if not parts or ".." in parts:
        raise ValueError(f"Unsafe file name: {filename!r}")
    cleaned = [safe_part(p) for p in parts]
    if not all(cleaned):
        raise ValueError(f"Unsafe file name: {filename!r}")
    return "/".join(cleaned)


def safe_extract(zip_path, dest: Path) -> int:
    """Extract a zip into dest. Rejects the whole archive on zip-slip / absolute paths.

    Symlink entries are skipped; limits guard against zip bombs. Returns file count.
    """
    dest = Path(dest).resolve()
    count = 0
    with zipfile.ZipFile(zip_path) as z:
        infos = [i for i in z.infolist() if not i.filename.startswith("__MACOSX/")]
        if len(infos) > MAX_FILES:
            raise ValueError("Zip has too many files.")
        if sum(i.file_size for i in infos) > MAX_TOTAL_BYTES:
            raise ValueError("Zip is too large when extracted.")
        entries = []
        for i in infos:
            name = i.filename.replace("\\", "/")
            if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
                raise ValueError(f"Unsafe path in zip: {i.filename!r}")
            parts = [p for p in name.split("/") if p not in ("", ".")]
            if ".." in parts:
                raise ValueError(f"Unsafe path in zip: {i.filename!r}")
            if parts:
                entries.append((i, parts))
        # Drop a single wrapping top-level folder (project.zip -> project/...).
        strip = (len({p[0] for _, p in entries}) == 1
                 and all(len(p) > 1 for i, p in entries if not i.is_dir()))
        for info, parts in entries:
            if stat.S_ISLNK((info.external_attr >> 16) & 0xFFFF):
                continue
            if strip:
                parts = parts[1:]
            if not parts:
                continue
            target = dest.joinpath(*[safe_part(p) or "_" for p in parts]).resolve()
            if target != dest and dest not in target.parents:  # zip-slip guard
                raise ValueError(f"Unsafe path in zip: {info.filename!r}")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
            count += 1
    return count


def save_uploads(files, ws: Path) -> list:
    """Save uploaded FileStorage objects into ws (zip files are extracted)."""
    ws = Path(ws).resolve()
    saved = []
    for f in files:
        rel = safe_relpath(f.filename)
        if rel.lower().endswith(".zip"):
            tmp = config.DATA_DIR / f"upload_{os.getpid()}_{id(f)}.zip"
            f.save(tmp)
            try:
                safe_extract(tmp, ws)
            except zipfile.BadZipFile:
                raise ValueError(f"{rel} is not a valid zip file.")
            finally:
                tmp.unlink(missing_ok=True)
            saved.append(rel)
            continue
        target = (ws / rel).resolve()
        if ws not in target.parents:
            raise ValueError(f"Unsafe file name: {rel!r}")
        target.parent.mkdir(parents=True, exist_ok=True)
        f.save(target)
        saved.append(rel)
    return saved


def iter_files(ws: Path):
    ws = Path(ws)
    for root, dirs, files in os.walk(ws):
        dirs[:] = sorted(d for d in dirs if d not in IGNORE_DIRS)
        for name in sorted(files):
            yield Path(root) / name


def list_files(ws: Path, limit=1000) -> list:
    out = []
    for p in iter_files(ws):
        try:
            out.append({"path": p.relative_to(ws).as_posix(), "size": p.stat().st_size})
        except OSError:
            continue
        if len(out) >= limit:
            break
    return out


def read_text(path: Path, limit: int):
    """Read up to `limit` chars of a text file; None if binary."""
    try:
        with open(path, "rb") as f:
            raw = f.read(limit * 4 + 1)
    except OSError:
        return None
    if b"\0" in raw[:4096]:
        return None
    text = raw.decode("utf-8", errors="replace")
    return text if len(text) <= limit else text[:limit] + "\n... [truncated]"


def collect_sources(ws: Path, max_total=60000, max_file=15000) -> str:
    """Concatenate readable source files (shallow + code first) for the reviewers."""
    cands = []
    for p in iter_files(ws):
        if p.name in SKIP_FILES or not (p.suffix.lower() in TEXT_EXTS or p.name in TEXT_NAMES):
            continue
        try:
            if p.stat().st_size > 400_000:
                continue
        except OSError:
            continue
        rel = p.relative_to(ws).as_posix()
        cands.append((rel.count("/"), p.suffix in (".md", ".txt", ".json"), rel, p))
    cands.sort()
    chunks, used = [], 0
    for _, _, rel, p in cands:
        text = read_text(p, max_file)
        if text is None:
            continue
        piece = f"=== FILE: {rel} ===\n{text}\n"
        if used + len(piece) > max_total:
            chunks.append("=== (more files omitted: size limit reached) ===")
            break
        chunks.append(piece)
        used += len(piece)
    return "\n".join(chunks) or "(no readable source files)"
