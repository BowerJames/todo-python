import pytest
from unittest.mock import AsyncMock, Mock
import json
import asyncio
from websockets.exceptions import ConnectionClosedOK
from realtime_agent.adapters.websockets import WebsocketsWebSocketPort

@pytest.mark.asyncio
async def test_websockets_websocket_port_build(monkeypatch: pytest.MonkeyPatch, websockets_client_connection_mock):
    websockets_websocket_port = WebsocketsWebSocketPort(websockets_client_connection_mock)

@pytest.mark.asyncio
async def test_websockets_websocket_port_recieves(monkeypatch: pytest.MonkeyPatch, websocket_port, websockets_client_connection_mock):
    recieve_mock = AsyncMock(return_value=json.dumps({"foo": "bar"}))
    with monkeypatch.context() as m:
        m.setattr(websockets_client_connection_mock, "recv", recieve_mock)
        assert await websocket_port.receive() == {"foo": "bar"}

@pytest.mark.asyncio
async def test_websockets_websocket_port_sends(monkeypatch: pytest.MonkeyPatch, websocket_port, websockets_client_connection_mock):
    send_mock = AsyncMock()
    with monkeypatch.context() as m:
        m.setattr(websockets_client_connection_mock, "send", send_mock)
        await websocket_port.send({"foo": "bar"})
        send_mock.assert_awaited_once_with(json.dumps({"foo": "bar"}))

@pytest.mark.asyncio
async def test_websockets_websocket_port_closes(monkeypatch: pytest.MonkeyPatch, websocket_port, websockets_client_connection_mock):
    close_mock = AsyncMock()
    with monkeypatch.context() as m:
        m.setattr(websockets_client_connection_mock, "close", close_mock)
        await websocket_port.close()
        close_mock.assert_awaited_once()

@pytest.mark.asyncio
@pytest.mark.timeout(2)
async def test_websockets_websocket_port_iterates(monkeypatch: pytest.MonkeyPatch, websocket_port, websockets_client_connection_mock):
    recieve_mock = AsyncMock(return_value=json.dumps({"foo": "bar"}))
    with monkeypatch.context() as m:
        m.setattr(websockets_client_connection_mock, "recv", recieve_mock)
        outputs = []
        count = 0
        async for message in websocket_port:
            outputs.append(message)
            count += 1
            if count == 5:
                break
        assert len(outputs) == 5
        assert outputs == [{"foo": "bar"}] * 5

@pytest.mark.asyncio
@pytest.mark.timeout(2)
async def test_websockets_websocket_port_iterates_closes(monkeypatch: pytest.MonkeyPatch, websocket_port, websockets_client_connection_mock):
    responses = [
        json.dumps({"foo": "bar"}),
        json.dumps({"foo": "baz"}),
        ConnectionClosedOK(None, None),
    ]
    recieve_mock = AsyncMock(side_effect=responses)
    with monkeypatch.context() as m:
        m.setattr(websockets_client_connection_mock, "recv", recieve_mock)
        async for message in websocket_port:
            pass

@pytest.mark.asyncio
@pytest.mark.timeout(2)
async def test_websockets_websocket_port_iterates_closes_with_error(monkeypatch: pytest.MonkeyPatch, websocket_port, websockets_client_connection_mock):
    
    exception = Exception("test")
    responses = [
        json.dumps({"foo": "bar"}),
        json.dumps({"foo": "baz"}),
        exception,
    ]
    recieve_mock = AsyncMock(side_effect=responses)
    with monkeypatch.context() as m:
        m.setattr(websockets_client_connection_mock, "recv", recieve_mock)
        try:
            async for message in websocket_port:
                pass
        except Exception as e:
            assert e is exception

