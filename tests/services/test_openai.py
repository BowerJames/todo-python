import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from realtime_agent.services import openai


@pytest.mark.asyncio
async def test_connect_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_REALTIME_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    connect_mock = AsyncMock()
    monkeypatch.setattr(openai.websockets_client, "connect", connect_mock)

    with pytest.raises(openai.OpenAIConnectionError):
        await openai.connect(model="gpt-realtime")

    connect_mock.assert_not_called()


@pytest.mark.asyncio
async def test_connect_requires_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_REALTIME_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    connect_mock = AsyncMock()
    monkeypatch.setattr(openai.websockets_client, "connect", connect_mock)

    with pytest.raises(openai.OpenAIConnectionError):
        await openai.connect(api_key="token")

    connect_mock.assert_not_called()


@pytest.mark.asyncio
async def test_connect_uses_environment_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    monkeypatch.setenv("OPENAI_REALTIME_MODEL", "gpt-env")
    monkeypatch.setenv("OPENAI_REALTIME_URL", "wss://example.test/realtime")

    connection = object()
    connect_mock = AsyncMock(return_value=connection)
    monkeypatch.setattr(openai.websockets_client, "connect", connect_mock)

    adapter_factory = Mock(return_value="adapter-result")

    result = await openai.connect(adapter_factory=adapter_factory)

    connect_mock.assert_awaited_once()
    url = connect_mock.call_args.args[0]
    assert url == "wss://example.test/realtime?model=gpt-env"
    headers = connect_mock.call_args.kwargs["additional_headers"]
    assert headers["Authorization"] == "Bearer env-key"
    adapter_factory.assert_called_once_with(connection)
    assert result == "adapter-result"


@pytest.mark.asyncio
async def test_connect_builds_url_and_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = object()
    connect_mock = AsyncMock(return_value=connection)
    monkeypatch.setattr(openai.websockets_client, "connect", connect_mock)

    adapter_factory = Mock(return_value="adapter")
    headers = {"X-Test": "value"}

    result = await openai.connect(
        model="gpt-custom",
        api_key="token",
        root_url="https://api.test/realtime",
        headers=headers,
        adapter_factory=adapter_factory,
        ping_interval=5,
    )

    connect_mock.assert_awaited_once()
    url = connect_mock.call_args.args[0]
    assert url == "wss://api.test/realtime?model=gpt-custom"
    additional_headers = connect_mock.call_args.kwargs["additional_headers"]
    assert additional_headers["Authorization"] == "Bearer token"
    assert additional_headers["X-Test"] == "value"
    assert connect_mock.call_args.kwargs["ping_interval"] == 5
    adapter_factory.assert_called_once_with(connection)
    assert result == "adapter"


def test_connect_requires_websockets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openai, "websockets_client", None)

    with pytest.raises(openai.OpenAIConnectionError):
        asyncio.run(openai.connect(model="gpt", api_key="token"))


def test_build_connection_url_adds_model_parameter() -> None:
    url = openai._build_connection_url("wss://host/path", "gpt")
    assert url == "wss://host/path?model=gpt"


def test_build_connection_url_converts_http_scheme() -> None:
    url = openai._build_connection_url("https://host/path", "gpt")
    assert url == "wss://host/path?model=gpt"


def test_build_connection_url_rejects_invalid_scheme() -> None:
    with pytest.raises(openai.OpenAIConnectionError):
        openai._build_connection_url("ftp://host/path", "gpt")


def test_build_connection_url_requires_scheme() -> None:
    with pytest.raises(openai.OpenAIConnectionError):
        openai._build_connection_url("host/path", "gpt")


def test_prepare_headers_merges_custom_headers() -> None:
    headers = openai._prepare_headers("token", {"X-Trace": "1"})
    assert headers == {"Authorization": "Bearer token", "X-Trace": "1"}


def test_resolve_first_returns_first_non_empty() -> None:
    assert openai._resolve_first(None, "", "value", "other") == "value"
    assert openai._resolve_first(None, None) is None

