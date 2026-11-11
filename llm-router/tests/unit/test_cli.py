"""CLI tests: provider chain building and output, with the router stubbed."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from llm_router import cli
from llm_router.config import RouterSettings
from llm_router.errors import AllProvidersFailedError
from llm_router.models import LLMResponse

if TYPE_CHECKING:
    import pytest


def test_build_providers_only_ollama_without_keys() -> None:
    providers = cli.build_providers(RouterSettings(_env_file=None))  # type: ignore[call-arg]
    assert [p.name for p in providers] == ["ollama"]


def test_build_providers_full_chain_with_keys() -> None:
    settings = RouterSettings(_env_file=None, anthropic_api_key="a", openai_api_key="o")  # type: ignore[call-arg]
    providers = cli.build_providers(settings, timeout_s=5.0)
    assert [p.name for p in providers] == ["anthropic", "openai", "ollama"]
    assert all(p.timeout_s == 5.0 for p in providers)


def test_no_prompt_prints_help() -> None:
    assert cli.main([]) == 1


def test_json_output(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    async def fake_generate(self: object, prompt: str, request_id: str | None = None) -> LLMResponse:  # noqa: ARG001
        return LLMResponse(text=f"echo {prompt}", provider="ollama", model="m", tokens_in=1, tokens_out=2)

    monkeypatch.setattr(cli.Router, "generate", fake_generate)
    assert cli.main(["hi", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok"
    assert out["text"] == "echo hi"


def test_text_output_on_error(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    async def failing(self: object, prompt: str, request_id: str | None = None) -> LLMResponse:  # noqa: ARG001
        raise AllProvidersFailedError(["ollama: down"])

    monkeypatch.setattr(cli.Router, "generate", failing)
    assert cli.main(["hi"]) == 1
    assert "All providers failed: ollama: down" in capsys.readouterr().out


def test_text_output_ok(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    async def fake_generate(self: object, prompt: str, request_id: str | None = None) -> LLMResponse:  # noqa: ARG001
        return LLMResponse(text="hello", provider="ollama", model="m", cached=True)

    monkeypatch.setattr(cli.Router, "generate", fake_generate)
    assert cli.main(["hi"]) == 0
    out = capsys.readouterr().out
    assert "[ollama/m]" in out
    assert "[cached]" in out
