import pytest
from unittest.mock import AsyncMock, Mock
from realtime_agent.services.openai import connect
import websockets.asyncio.client as websockets
import os
from dotenv import load_dotenv
load_dotenv()

@pytest.mark.asyncio
async def test_cant_connect_without_api_key(monkeypatch: pytest.MonkeyPatch, model):
    connect_mock = AsyncMock()
    with monkeypatch.context() as m:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setattr(websockets, "connect", connect_mock)
        try:
            await connect(
                model=model,
            )
            pytest.fail("Expected to fail since the api key is not set as environment variable or provided as a configuration parameter")
        except Exception as e:
            assert issubclass(type(e), Exception)
    connect_mock.assert_not_called()
    connect_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_can_connect_with_api_key(monkeypatch: pytest.MonkeyPatch, model, api_key, mock_client_connection, url, headers, root_url):
    original_init = websockets.connect.__init__
    connect_init_mock = Mock()

    def wrapped_init(self, *args, **kwargs):
        connect_init_mock(self, *args, **kwargs)
        return original_init(self, *args, **kwargs)

    create_connection_mock = AsyncMock(return_value=mock_client_connection)
    with monkeypatch.context() as m:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setattr(websockets.connect, "__init__", wrapped_init)
        monkeypatch.setattr(websockets.connect, "create_connection", create_connection_mock)
        await connect(
            model=model,
            api_key=api_key,
            root_url=root_url,
        )
    connect_init_mock.assert_called_once()
    call_args = connect_init_mock.call_args
    assert len(call_args.args) >= 2
    assert call_args.args[1] == url
    assert call_args.kwargs.get("additional_headers") == headers
    create_connection_mock.assert_awaited_once_with()

@pytest.mark.asyncio
async def test_can_connect_with_env_api_key(monkeypatch: pytest.MonkeyPatch, model, api_key, mock_client_connection, url, headers, root_url):
    original_init = websockets.connect.__init__
    connect_init_mock = Mock()
    def wrapped_init(self, *args, **kwargs):
        connect_init_mock(self, *args, **kwargs)
        return original_init(self, *args, **kwargs)
    create_connection_mock = AsyncMock(return_value=mock_client_connection)
    with monkeypatch.context() as m:
        monkeypatch.setenv("OPENAI_API_KEY", api_key)
        monkeypatch.setattr(websockets.connect, "__init__", wrapped_init)
        monkeypatch.setattr(websockets.connect, "create_connection", create_connection_mock)
        await connect(
            model=model,
            root_url=root_url,
        )
    connect_init_mock.assert_called_once()
    call_args = connect_init_mock.call_args
    assert len(call_args.args) >= 2
    assert call_args.args[1] == url
    assert call_args.kwargs.get("additional_headers") == headers
    create_connection_mock.assert_awaited_once_with()

@pytest.mark.asyncio
@pytest.mark.timeout(10)
@pytest.mark.skip(reason="This test actually connects to the real OpenAI API and should only be run manually")
async def test_can_actually_connect_and_recieve_session_created_event(monkeypatch: pytest.MonkeyPatch):
    
    model = "gpt-realtime"
    root_url = "wss://api.openai.com/v1/realtime"
    ws = await connect(
        model=model,
        api_key=os.getenv("OPENAI_API_KEY"),
        root_url=root_url,
    )
    msg = await ws.receive()
    assert "type" in msg and msg["type"] == "session.created", f"Expected session.created event, got {msg}"
    