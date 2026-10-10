"""Language detection for an uploaded project."""
from collections import Counter
from pathlib import Path

from . import fsutil

EXT_LANG = {".py": "python", ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
            ".jsx": "javascript", ".ts": "typescript", ".tsx": "typescript", ".go": "go", ".rs": "rust",
            ".c": "c", ".cpp": "cpp", ".cc": "cpp", ".java": "java", ".php": "php", ".rb": "ruby",
            ".sh": "bash", ".html": "html"}


def detect_language(ws: Path):
    """Returns (language, {language: file_count}). Marker files win over extensions."""
    ws = Path(ws)
    counts = Counter()
    for p in fsutil.iter_files(ws):
        lang = EXT_LANG.get(p.suffix.lower())
        if lang:
            counts[lang] += 1
    has = lambda n: (ws / n).exists()  # noqa: E731
    if has("package.json"):
        ts = has("tsconfig.json") or counts["typescript"] > counts["javascript"]
        return ("typescript" if ts else "javascript"), dict(counts)
    for marker, lang in (("go.mod", "go"), ("Cargo.toml", "rust"), ("pom.xml", "java"),
                         ("build.gradle", "java"), ("composer.json", "php"), ("Gemfile", "ruby"),
                         ("requirements.txt", "python"), ("pyproject.toml", "python")):
        if has(marker):
            return lang, dict(counts)
    if counts:
        return counts.most_common(1)[0][0], dict(counts)
    return "unknown", {}
