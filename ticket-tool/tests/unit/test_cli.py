"""CLI tests against a temporary database (TICKET_DB_PATH)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from ticket_tool.cli import main

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def temp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TICKET_DB_PATH", str(tmp_path / "cli.db"))


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, Any]:
    code = main(list(argv))
    out = capsys.readouterr().out
    return code, json.loads(out) if "--json" in argv else out


def test_seed_and_list(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(capsys, "seed", "--json") == (0, {"status": "ok", "action": "seed", "created": 8})
    code, out = run(capsys, "list", "--status", "open", "--json")
    assert (code, out["count"]) == (0, 5)
    code, text = run(capsys, "list", "--priority", "critical")
    assert "Found 2 ticket(s)" in text


def test_create_get_update_delete_audit(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(capsys, "create", "-t", "Help", "-d", "Need help", "-c", "Jo", "--priority", "high", "--json")
    assert code == 0
    tid = str(out["ticket"][0]["id"])

    code, out = run(capsys, "get", tid, "--json")
    assert out["ticket"][0]["title"] == "Help"

    code, out = run(capsys, "update", tid, "--status", "resolved", "--resolution", "Fixed", "--json")
    assert out["ticket"][0]["status"] == "resolved"

    code, out = run(capsys, "delete", tid, "--idem-key", "del-1", "--json")
    assert out == {"status": "ok", "action": "delete", "ticket_id": int(tid)}

    code, out = run(capsys, "audit", "--ticket-id", tid, "--json")
    assert [e["action"] for e in out["entries"]] == ["delete", "update", "create"]


def test_text_output(capsys: pytest.CaptureFixture[str]) -> None:
    assert "Ticket created" in run(capsys, "create", "-t", "Help", "-d", "x", "-c", "Jo")[1]
    assert '"title": "Help"' in run(capsys, "get", "1")[1]
    assert "Ticket updated" in run(capsys, "update", "1", "--priority", "low")[1]
    assert "Found 2 audit entries" in run(capsys, "audit")[1]
    assert "Ticket 1 deleted" in run(capsys, "delete", "1", "--idem-key", "d")[1]


@pytest.mark.parametrize(
    "argv",
    [("get", "42"), ("update", "42", "--status", "closed"), ("delete", "42", "--idem-key", "k")],
)
def test_not_found(capsys: pytest.CaptureFixture[str], argv: tuple[str, ...]) -> None:
    code, out = run(capsys, *argv, "--json")
    assert (code, out["status"]) == (1, "error")
    assert "not found" in out["reason"]
    code, text = run(capsys, *argv)
    assert code == 1
    assert "Error: Ticket 42 not found" in text


def test_idempotent_create_conflict(capsys: pytest.CaptureFixture[str]) -> None:
    run(capsys, "create", "-t", "A", "-d", "x", "-c", "Jo", "--idem-key", "k1", "--json")
    code, out = run(capsys, "create", "-t", "B", "-d", "x", "-c", "Jo", "--idem-key", "k1", "--json")
    assert code == 1
    assert "different operation" in out["reason"]


def test_audit_disabled_by_env(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TICKET_ENABLE_AUDIT", "false")
    run(capsys, "create", "-t", "A", "-d", "x", "-c", "Jo")
    assert run(capsys, "audit", "--json")[1]["count"] == 0
