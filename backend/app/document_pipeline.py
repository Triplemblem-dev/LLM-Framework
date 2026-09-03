"""Document pipeline: validate, extract, chunk, and embed.

Runs synchronously inside the upload request (Decision-equivalent to the rest of v1: no
background job infra yet). Document.status/error record whether it worked so the frontend
can distinguish a saved source file from one that is searchable by the model.
"""

import hashlib
import io
from pathlib import Path
import re
import uuid
from dataclasses import dataclass

from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.models import Document, DocumentChunk, DocumentStatus
from app.ollama_client import embed

ALLOWED_EXTENSIONS = {"md": "md", "markdown": "md", "txt": "txt", "pdf": "pdf"}

CHUNK_CHAR_LIMIT = 1500
CHUNK_OVERLAP = 150
EMBED_BATCH_SIZE = 32

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")


def sanitize_filename(filename: str) -> str:
    name = filename.strip().replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "upload"
    return name[:200]


def detect_source_type(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: .{ext or '?'} (allowed: md, txt, pdf)")
    return ALLOWED_EXTENSIONS[ext]


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class Page:
    text: str
    page_number: int | None


def _strip_repeated_noise(pages: list[Page]) -> list[Page]:
    """Drop short lines that repeat across most pages - running headers/footers/page numbers."""
    if len(pages) < 4:
        return pages
    line_page_counts: dict[str, int] = {}
    for page in pages:
        for line in {ln.strip() for ln in page.text.splitlines() if ln.strip()}:
            if len(line) < 80:
                line_page_counts[line] = line_page_counts.get(line, 0) + 1
    threshold = max(3, int(len(pages) * 0.6))
    noisy = {line for line, count in line_page_counts.items() if count >= threshold}
    if not noisy:
        return pages
    cleaned = []
    for page in pages:
        kept = [ln for ln in page.text.splitlines() if ln.strip() not in noisy]
        cleaned.append(Page(text="\n".join(kept), page_number=page.page_number))
    return cleaned


def extract_pages(data: bytes, source_type: str) -> list[Page]:
    if source_type in ("md", "txt"):
        return [Page(text=data.decode("utf-8", errors="replace"), page_number=None)]
    if source_type == "pdf":
        reader = PdfReader(io.BytesIO(data))
        pages = [Page(text=page.extract_text() or "", page_number=i) for i, page in enumerate(reader.pages, start=1)]
        pages = [p for p in pages if p.text.strip()]
        return _strip_repeated_noise(pages)
    raise ValueError(f"Unsupported source type: {source_type}")


def pdf_to_markdown(data: bytes, filename: str) -> str:
    """Extract a text-based PDF into readable Markdown while preserving page boundaries.

    This intentionally does not perform OCR. Returning a clear error for image-only PDFs is
    safer than producing an empty or misleading export.
    """
    pages = extract_pages(data, "pdf")
    if not pages:
        raise ValueError("No extractable text found. This PDF may be scanned and require OCR.")

    title = Path(filename).stem.strip() or "Document"
    title = re.sub(r"[\r\n\t]+", " ", title).strip()
    output = [f"# {title}", ""]
    for page in pages:
        text = "\n".join(line.rstrip() for line in page.text.replace("\r\n", "\n").splitlines()).strip()
        if not text:
            continue
        output.extend([f"## Page {page.page_number}", "", text, ""])
    return "\n".join(output).rstrip() + "\n"


@dataclass
class ChunkDraft:
    content: str
    heading: str | None
    page_number: int | None


def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _pack_paragraphs(paragraphs: list[str]) -> list[str]:
    """Greedy-packs paragraphs into ~CHUNK_CHAR_LIMIT chunks with trailing overlap, hard-splitting
    any single paragraph that alone exceeds the limit."""
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        pieces = [para]
        if len(para) > CHUNK_CHAR_LIMIT:
            pieces = [para[i : i + CHUNK_CHAR_LIMIT] for i in range(0, len(para), CHUNK_CHAR_LIMIT)]
        for piece in pieces:
            candidate = f"{current}\n\n{piece}" if current else piece
            if len(candidate) > CHUNK_CHAR_LIMIT and current:
                chunks.append(current)
                current = current[-CHUNK_OVERLAP:] + "\n\n" + piece
            else:
                current = candidate
    if current.strip():
        chunks.append(current)
    return chunks


def _chunk_markdown(text: str) -> list[ChunkDraft]:
    lines = text.splitlines()
    sections: list[tuple[str | None, list[str]]] = []
    heading: str | None = None
    buffer: list[str] = []
    for line in lines:
        match = HEADING_RE.match(line)
        if match:
            if buffer:
                sections.append((heading, buffer))
            heading = match.group(2).strip()
            buffer = []
        else:
            buffer.append(line)
    if buffer:
        sections.append((heading, buffer))

    drafts: list[ChunkDraft] = []
    for section_heading, body_lines in sections:
        paragraphs = _split_paragraphs("\n".join(body_lines))
        for chunk_text in _pack_paragraphs(paragraphs):
            drafts.append(ChunkDraft(content=chunk_text, heading=section_heading, page_number=None))
    return drafts


def build_chunks(pages: list[Page], source_type: str) -> list[ChunkDraft]:
    if source_type == "md":
        full_text = "\n".join(p.text for p in pages)
        return _chunk_markdown(full_text)

    drafts: list[ChunkDraft] = []
    for page in pages:
        paragraphs = _split_paragraphs(page.text)
        for chunk_text in _pack_paragraphs(paragraphs):
            drafts.append(ChunkDraft(content=chunk_text, heading=None, page_number=page.page_number))
    return drafts


def process_document(db: Session, document: Document, data: bytes) -> None:
    try:
        pages = extract_pages(data, document.source_type)
        drafts = build_chunks(pages, document.source_type)
        if not drafts:
            document.status = DocumentStatus.failed
            document.error = "No extractable text found in this file."
            db.commit()
            return

        embeddings: list[list[float]] = []
        for i in range(0, len(drafts), EMBED_BATCH_SIZE):
            batch = [d.content for d in drafts[i : i + EMBED_BATCH_SIZE]]
            embeddings.extend(embed(batch))

        if len(embeddings) != len(drafts):
            raise ValueError("Ollama returned fewer embeddings than the document requires.")

        # A retry must replace any partial or stale index instead of appending
        # duplicate chunks. Keep the existing rows until extraction and
        # embedding both succeed so a failed retry cannot destroy usable data.
        db.query(DocumentChunk).filter_by(document_id=document.id).delete(synchronize_session=False)
        for index, (draft, vector) in enumerate(zip(drafts, embeddings)):
            db.add(
                DocumentChunk(
                    id=uuid.uuid4(),
                    document_id=document.id,
                    scope_id=document.scope_id,
                    chunk_index=index,
                    heading=draft.heading,
                    page_number=draft.page_number,
                    content=draft.content,
                    embedding=vector,
                )
            )
        document.status = DocumentStatus.ready
        document.chunk_count = len(drafts)
        document.error = None
        db.commit()
    except Exception as exc:  # noqa: BLE001 - convert any pipeline failure into a stored status
        db.rollback()
        document.status = DocumentStatus.failed
        document.chunk_count = 0
        document.error = str(exc)[:2000]
        db.commit()
