"""
Document text extractor — supports PDF and DOCX.
"""
from __future__ import annotations
import re
from pathlib import Path


def extract(path: str | Path) -> str:
    """Return clean plain-text content from a PDF or DOCX file."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)
    elif suffix in (".docx", ".doc"):
        return _extract_docx(path)
    elif suffix in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="replace")
    else:
        raise ValueError(f"Unsupported file type: {suffix}")


def _extract_pdf(path: Path) -> str:
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("Run: pip install pdfplumber")

    pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n\n".join(pages)


def _extract_docx(path: Path) -> str:
    try:
        from docx import Document
    except ImportError:
        raise ImportError("Run: pip install python-docx")

    doc = Document(str(path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def chunk(text: str, max_size: int = 8000, overlap: int = 200) -> list[str]:
    """Split long text into overlapping chunks."""
    if len(text) <= max_size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + max_size
        # Try to break at a sentence boundary
        if end < len(text):
            boundary = text.rfind(". ", start, end)
            if boundary > start + max_size // 2:
                end = boundary + 1
        chunks.append(text[start:end].strip())
        start = end - overlap
    return chunks


def clean(text: str) -> str:
    """Remove excessive whitespace and control characters."""
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[^\x20-\x7E\n]', '', text)
    return text.strip()
