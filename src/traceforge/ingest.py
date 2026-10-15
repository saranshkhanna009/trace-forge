"""Case and document ingestion with stable source provenance."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .models import Document, EvidenceChunk, IncidentCase


_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")


def stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(payload).hexdigest()[:16]}"


def load_case(case_dir: str | Path) -> IncidentCase:
    root = Path(case_dir)
    config_path = root / "case.json"
    if not config_path.is_file():
        raise FileNotFoundError(f"Case configuration does not exist: {config_path}")
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid case JSON: {config_path}: {exc}") from exc
    required = {
        "id",
        "asset_id",
        "asset_type",
        "description",
        "observed_at",
        "telemetry_file",
        "model_report_file",
        "documents_dir",
    }
    missing = sorted(required - config.keys())
    if missing:
        raise ValueError(f"Case configuration is missing fields: {', '.join(missing)}")
    fields = set(IncidentCase.__dataclass_fields__)
    values = {key: config[key] for key in fields if key in config}
    return IncidentCase(**values)


def load_csv_rows(path: str | Path) -> list[dict[str, str]]:
    """Load a UTF-8 CSV with line-aware diagnostics and stable row order."""

    import csv

    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"CSV file does not exist: {file_path}")
    with file_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header: {file_path}")
        if any(not name for name in reader.fieldnames):
            raise ValueError(f"CSV has an empty header field: {file_path}")
        rows: list[dict[str, str]] = []
        for line_number, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(f"CSV has too many fields at {file_path}:{line_number}")
            rows.append({key: value for key, value in row.items()})
    return rows


def _document_title(path: Path, text: str) -> str:
    for line in text.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            return match.group(1).strip()
    return path.stem.replace("-", " ").replace("_", " ").title()


def load_documents(corpus_dir: str | Path) -> list[Document]:
    root = Path(corpus_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"Documents directory does not exist: {root}")
    paths = sorted(
        path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in {".md", ".txt"}
    )
    documents: list[Document] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        relative_path = path.relative_to(root).as_posix()
        documents.append(
            Document(
                id=stable_id("doc", relative_path, text),
                path=relative_path,
                title=_document_title(path, text),
                text=text,
            )
        )
    return documents


def chunk_document(document: Document) -> list[EvidenceChunk]:
    chunks: list[EvidenceChunk] = []
    section = "Document"
    paragraph_start: int | None = None
    paragraph_lines: list[str] = []

    def flush() -> None:
        nonlocal paragraph_start, paragraph_lines
        if paragraph_start is None:
            paragraph_lines = []
            return
        raw_text = "".join(paragraph_lines)
        text = raw_text.strip()
        if text:
            leading = len(raw_text) - len(raw_text.lstrip())
            start = paragraph_start + leading
            end = start + len(text)
            chunks.append(
                EvidenceChunk(
                    id=stable_id("chunk", document.id, section, start, end, text),
                    document_id=document.id,
                    section=section,
                    start_char=start,
                    end_char=end,
                    text=text,
                )
            )
        paragraph_start = None
        paragraph_lines = []

    offset = 0
    for line in document.text.splitlines(keepends=True):
        heading = _HEADING_RE.match(line.rstrip("\r\n"))
        if heading:
            flush()
            section = heading.group(1).strip()
        elif line.strip():
            if paragraph_start is None:
                paragraph_start = offset
            paragraph_lines.append(line)
        else:
            flush()
        offset += len(line)
    flush()
    return chunks


def load_case_documents(case_dir: str | Path, case: IncidentCase) -> tuple[list[Document], list[EvidenceChunk]]:
    documents = load_documents(Path(case_dir) / case.documents_dir)
    chunks = [chunk for document in documents for chunk in chunk_document(document)]
    return documents, chunks
