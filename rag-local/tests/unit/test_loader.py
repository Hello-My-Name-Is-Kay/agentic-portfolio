"""Unit tests for the document loader."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from rag_local.errors import DocumentIngestionError
from rag_local.loader import load_documents


class TestLoadDocuments:
    """Tests for the document loader."""

    def test_load_from_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "policy_001_test.md").write_text("# Test Policy\n\nThis is a test policy document.\n")
            (d / "policy_002_test.md").write_text("# Another Policy\n\nMore content here.\n")

            docs = load_documents(str(d))
            assert len(docs) == 2
            titles = {doc.metadata.get("doc_title", "") for doc in docs}
            assert "Test Policy" in titles
            assert "Another Policy" in titles

    def test_nonexistent_directory_raises(self) -> None:
        with pytest.raises(DocumentIngestionError, match="does not exist"):
            load_documents("/nonexistent/path")

    def test_no_markdown_files_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "readme.txt").write_text("Hello")
            with pytest.raises(DocumentIngestionError, match="No markdown files"):
                load_documents(str(d))

    def test_skip_empty_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "empty.md").write_text("")
            (d / "real.md").write_text("# Real\n\nContent.\n")
            docs = load_documents(str(d))
            assert len(docs) == 1

    def test_recursive_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            sub = d / "subdir"
            sub.mkdir()
            (sub / "nested.md").write_text("# Nested\n\nDeep content.\n")
            docs = load_documents(str(d))
            assert len(docs) == 1