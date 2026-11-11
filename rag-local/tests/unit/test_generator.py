"""OllamaGenerator against httpx.MockTransport (no network)."""

from __future__ import annotations

import json

import httpx
import pytest
from tenacity import wait_none

from rag_local.config import Settings
from rag_local.errors import GenerationError
from rag_local.generator import OllamaGenerator, TransientGenerationError


def _generator(*responses: httpx.Response | Exception, seen: list[httpx.Request] | None = None) -> OllamaGenerator:
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        return item

    settings = Settings(_env_file=None, ollama_base_url="http://ollama.test/", max_new_tokens=99)  # type: ignore[call-arg]
    return OllamaGenerator(settings, transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(OllamaGenerator.generate.retry, "wait", wait_none())  # type: ignore[attr-defined]


OK = {"message": {"content": "  The tank must be full. [Document 1] "}, "prompt_eval_count": 50, "eval_count": 8}


def test_request_shape_and_parsing() -> None:
    seen: list[httpx.Request] = []
    resp = _generator(httpx.Response(200, json=OK), seen=seen).generate("Q?", system_prompt="Be precise")
    assert (resp.text, resp.tokens_in, resp.tokens_out, resp.cost_usd) == (
        "The tank must be full. [Document 1]",
        50,
        8,
        0.0,
    )
    assert str(seen[0].url) == "http://ollama.test/api/chat"
    body = json.loads(seen[0].content)
    assert body["options"] == {"num_predict": 99, "temperature": 0.1}
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert "llama3.2" in repr(resp)


def test_token_estimate_when_counts_missing() -> None:
    resp = _generator(httpx.Response(200, json={"message": {"content": "x" * 40}})).generate("y" * 80)
    assert (resp.tokens_in, resp.tokens_out) == (20, 10)


def test_retries_5xx_then_succeeds() -> None:
    seen: list[httpx.Request] = []
    gen = _generator(httpx.Response(503, text="loading"), httpx.Response(200, json=OK), seen=seen)
    assert gen.generate("Q?").text.startswith("The tank")
    assert len(seen) == 2


def test_timeout_retried_then_raised() -> None:
    seen: list[httpx.Request] = []
    gen = _generator(httpx.ReadTimeout("slow"), seen=seen)
    with pytest.raises(TransientGenerationError, match="timed out"):
        gen.generate("Q?")
    assert len(seen) == 3


def test_connection_error_is_transient() -> None:
    gen = _generator(httpx.ConnectError("refused"))
    with pytest.raises(TransientGenerationError, match="unreachable"):
        gen.generate("Q?")


def test_4xx_not_retried() -> None:
    seen: list[httpx.Request] = []
    with pytest.raises(GenerationError, match="HTTP 404") as info:
        _generator(httpx.Response(404, text="model not found"), seen=seen).generate("Q?")
    assert not isinstance(info.value, TransientGenerationError)
    assert len(seen) == 1


@pytest.mark.parametrize("body", [b"not json", b'{"unexpected": 1}', b"[1]"])
def test_bad_body(body: bytes) -> None:
    with pytest.raises(GenerationError):
        _generator(httpx.Response(200, content=body)).generate("Q?")


def test_empty_prompt() -> None:
    with pytest.raises(GenerationError, match="empty prompt"):
        _generator(httpx.Response(200, json=OK)).generate("  ")
