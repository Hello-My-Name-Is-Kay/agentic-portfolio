"""Document loader for markdown policy files.

Reads policy documents from a directory, constructs Document objects
with source metadata.
"""

from __future__ import annotations

from rag_local.logging import get_logger
from pathlib import Path

from rag_local.chunker import Document
from rag_local.errors import DocumentIngestionError

log = get_logger(__name__)


def load_documents(source_dir: str) -> list[Document]:
    """Load all markdown documents from a directory.

    Reads all .md files recursively from the source directory and
    wraps each into a Document with source metadata.

    Args:
        source_dir: Path to directory containing markdown files.

    Returns:
        List of Document objects.

    Raises:
        DocumentIngestionError: If the directory is missing, empty, or unreadable.
    """
    source_path = Path(source_dir).resolve()

    if not source_path.exists():
        raise DocumentIngestionError(f"Source directory does not exist: {source_dir}")
    if not source_path.is_dir():
        raise DocumentIngestionError(f"Source path is not a directory: {source_dir}")

    md_files = sorted(source_path.rglob("*.md"))
    if not md_files:
        raise DocumentIngestionError(f"No markdown files found in {source_dir}")

    documents: list[Document] = []
    for file_path in md_files:
        try:
            content = file_path.read_text(encoding="utf-8")
        except (IOError, PermissionError) as exc:
            log.warning("loader.unreadable", path=str(file_path), error=str(exc))
            continue

        if not content.strip():
            log.warning("loader.empty_file", path=str(file_path))
            continue

        documents.append(
            Document(
                page_content=content,
                metadata={
                    "source": str(file_path),
                    "filename": file_path.name,
                    "doc_title": _extract_title(content, file_path.stem),
                },
            )
        )

    log.info("loader.loaded", count=len(documents), source=source_dir)
    return documents


def _extract_title(content: str, fallback: str) -> str:
    """Extract the first H1 heading from markdown content."""
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("# ") and not line.startswith("## "):
            return line[2:].strip()
    return fallback.replace("_", " ").title()