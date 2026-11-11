"""Provider tests against httpx.MockTransport (no network)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from llm_router.errors import ProviderError, ProviderTimeoutError, RetryableProviderError
from llm_router.providers import AnthropicProvider, OllamaProvider, OpenAIProvider


class Server:
    """Replays queued responses (or exceptions) and records requests."""

    def __init__(self, *responses: httpx.Response | Exception) -> None:
        self._responses = list(responses)
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]
        if isinstance(item, Exception):
            raise item
        return item

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def body(self, i: int = 0) -> Any:
        return json.loads(self.requests[i].content)


ANTHROPIC_OK = {"content": [{"type": "text", "text": " Hi "}], "usage": {"input_tokens": 1000, "output_tokens": 2000}}
OPENAI_OK = {"choices": [{"message": {"content": "Hello"}}], "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
OLLAMA_OK = {"response": "Local", "prompt_eval_count": 7, "eval_count": 3}


async def test_anthropic_request_and_parsing() -> None:
    server = Server(httpx.Response(200, json=ANTHROPIC_OK))
    provider = AnthropicProvider(api_key="k", model="m", transport=server.transport)
    resp = await provider.generate("Hello", request_id="r1")
    assert (resp.text, resp.provider, resp.tokens_in, resp.tokens_out) == ("Hi", "anthropic", 1000, 2000)
    assert resp.cost_usd == pytest.approx(1000 / 1e6 * 3 + 2000 / 1e6 * 15)
    req = server.requests[0]
    assert str(req.url) == "https://api.anthropic.com/v1/messages"
    assert req.headers["x-api-key"] == "k"
    assert server.body()["messages"] == [{"role": "user", "content": "Hello"}]


async def test_openai_request_and_parsing() -> None:
    server = Server(httpx.Response(200, json=OPENAI_OK))
    provider = OpenAIProvider(api_key="k", transport=server.transport)
    resp = await provider.generate("Hello")
    assert (resp.text, resp.tokens_in, resp.tokens_out) == ("Hello", 10, 5)
    assert server.requests[0].headers["authorization"] == "Bearer k"


async def test_ollama_request_and_parsing() -> None:
    server = Server(httpx.Response(200, json=OLLAMA_OK))
    provider = OllamaProvider(base_url="http://ollama.test/", model="llama3.2", transport=server.transport)
    resp = await provider.generate("Hello")
    assert (resp.text, resp.tokens_in, resp.tokens_out, resp.cost_usd) == ("Local", 7, 3, 0.0)
    assert str(server.requests[0].url) == "http://ollama.test/api/generate"
    assert server.body()["stream"] is False


async def test_ollama_estimates_tokens_when_missing() -> None:
    server = Server(httpx.Response(200, json={"response": "x" * 40}))
    resp = await OllamaProvider(transport=server.transport).generate("y" * 80)
    assert (resp.tokens_in, resp.tokens_out) == (20, 10)


@pytest.mark.parametrize("status", [429, 500, 503])
async def test_transient_http_errors_are_retried(status: int) -> None:
    server = Server(httpx.Response(status, text="busy"), httpx.Response(200, json=OPENAI_OK))
    provider = OpenAIProvider(api_key="k", max_retries=2, retry_wait_s=0, transport=server.transport)
    resp = await provider.generate("Hello")
    assert resp.text == "Hello"
    assert len(server.requests) == 2


async def test_timeouts_retried_then_raised() -> None:
    server = Server(httpx.ReadTimeout("slow"))
    provider = OllamaProvider(max_retries=2, retry_wait_s=0, timeout_s=1, transport=server.transport)
    with pytest.raises(ProviderTimeoutError, match="timeout after 1"):
        await provider.generate("Hello")
    assert len(server.requests) == 3


async def test_connection_error_is_retryable() -> None:
    server = Server(httpx.ConnectError("refused"))
    provider = OllamaProvider(max_retries=0, transport=server.transport)
    with pytest.raises(RetryableProviderError, match="connection failed"):
        await provider.generate("Hello")
    assert len(server.requests) == 1


@pytest.mark.parametrize(("status", "message"), [(401, "authentication failed"), (400, "HTTP 400")])
async def test_client_errors_are_not_retried(status: int, message: str) -> None:
    server = Server(httpx.Response(status, text="nope"))
    provider = AnthropicProvider(api_key="k", max_retries=3, retry_wait_s=0, transport=server.transport)
    with pytest.raises(ProviderError, match=message) as info:
        await provider.generate("Hello")
    assert not isinstance(info.value, RetryableProviderError)
    assert len(server.requests) == 1


@pytest.mark.parametrize("body", [b"not json", b"[1, 2]"])
async def test_bad_body_raises(body: bytes) -> None:
    server = Server(httpx.Response(200, content=body))
    with pytest.raises(ProviderError):
        await OpenAIProvider(api_key="k", transport=server.transport).generate("Hello")


@pytest.mark.parametrize(
    "provider", [AnthropicProvider(api_key="k"), OpenAIProvider(api_key="k"), OllamaProvider()], ids=str
)
async def test_empty_prompt_rejected(provider: Any) -> None:
    with pytest.raises(ProviderError, match="empty prompt"):
        await provider.generate("   ")


@pytest.mark.parametrize("cls", [AnthropicProvider, OpenAIProvider])
def test_api_key_required(cls: Any) -> None:
    with pytest.raises(ProviderError, match="API key is required"):
        cls(api_key="")
