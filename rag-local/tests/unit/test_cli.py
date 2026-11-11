"""CLI tests with the pipeline replaced by a fake."""

from __future__ import annotations

import json
from typing import Any

import pytest

from rag_local import cli
from rag_local.errors import NoRelevantDocumentsError, RagError
from rag_local.pipeline import RagResult
from rag_local.retriever import RetrievedChunk


class FakePipeline:
    behaviour: Any = None

    def __init__(self, settings: Any) -> None:
        self.settings = settings

    def ingest(self, docs: list[Any]) -> int:
        return len(docs) * 3

    def query(self, question: str, top_k: int | None = None) -> RagResult:  # noqa: ARG002
        if isinstance(FakePipeline.behaviour, Exception):
            raise FakePipeline.behaviour
        chunk = RetrievedChunk("text", {"source": "/x/policy_004_fuel.md"}, 0.71234, 0.29)
        return RagResult(question=question, answer="Full tank. [Document 1]", citations=[chunk], confidence=0.712)


@pytest.fixture(autouse=True)
def fake_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    FakePipeline.behaviour = None
    monkeypatch.setattr(cli, "RagPipeline", FakePipeline)


def test_ingest_json(tmp_path: Any, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "a.md").write_text("# A\n\ntext")
    assert cli.main(["ingest", "--source", str(tmp_path), "--persist-dir", "/tmp/x", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert (out["documents_loaded"], out["chunks_ingested"], out["persist_dir"]) == (1, 3, "/tmp/x")


def test_ingest_text(tmp_path: Any, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "a.md").write_text("# A\n\ntext")
    assert cli.main(["ingest", "--source", str(tmp_path)]) == 0
    assert "Ingested 3 chunks from 1 documents" in capsys.readouterr().out


def test_query_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["query", "fuel?", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["answer"] == "Full tank. [Document 1]"
    assert out["citations"] == [{"source": "/x/policy_004_fuel.md", "filename": "policy_004_fuel.md", "score": 0.712}]


def test_query_text(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["query", "fuel?"]) == 0
    assert "policy_004_fuel.md" in capsys.readouterr().out


def test_no_relevant_docs_is_a_refusal_not_an_error(capsys: pytest.CaptureFixture[str]) -> None:
    FakePipeline.behaviour = NoRelevantDocumentsError("none")
    assert cli.main(["query", "weather?", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["code"] == "NO_RELEVANT_DOCS"
    assert cli.main(["query", "weather?"]) == 0
    assert "I don't know" in capsys.readouterr().out


@pytest.mark.parametrize(("exc", "code"), [(RagError("bad"), "RAG_ERROR"), (RuntimeError("boom"), "INTERNAL")])
def test_errors(exc: Exception, code: str, capsys: pytest.CaptureFixture[str]) -> None:
    FakePipeline.behaviour = exc
    assert cli.main(["query", "q", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["code"] == code
    assert cli.main(["query", "q"]) == 1


def test_interactive_with_json_rejected(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["query", "--json"]) == 1
    assert "requires a direct question" in capsys.readouterr().out


def test_interactive_session(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    answers = iter(["", "fuel?", "exit"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    assert cli.main(["query", "-i"]) == 0
    assert "Full tank." in capsys.readouterr().out


def test_interactive_eof(monkeypatch: pytest.MonkeyPatch) -> None:
    def eof(_prompt: str) -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)
    assert cli.main(["query"]) == 0
