import pytest
from fastapi import WebSocket
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from realtime_agent.adapters.fastapi import FastApiWebSocketPort

@pytest.mark.asyncio
async def test_fastapi_websocket_port_build(monkeypatch: pytest.MonkeyPatch, fastapi_websocket_mock: WebSocket):
    fastapi_websocket_port = FastApiWebSocketPort(fastapi_websocket_mock)

@pytest.mark.asyncio
async def test_fastapi_websocket_port_accept(monkeypatch: pytest.MonkeyPatch, fastapi_websocket_mock: WebSocket):
    accept_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(fastapi_websocket_mock, "accept", accept_mock)
    fastapi_websocket_port = FastApiWebSocketPort(fastapi_websocket_mock)
    await fastapi_websocket_port.accept()
    accept_mock.assert_awaited_once()

@pytest.mark.asyncio
async def test_fastapi_websocket_port_send(monkeypatch: pytest.MonkeyPatch, fastapi_websocket_mock: WebSocket):
    send_mock = AsyncMock(return_value=None)
    message = {
        "foo": "bar"
    }
    monkeypatch.setattr(fastapi_websocket_mock, "send_json", send_mock)
    fastapi_websocket_port = FastApiWebSocketPort(fastapi_websocket_mock)
    await fastapi_websocket_port.send(message)
    send_mock.assert_awaited_once_with(message)


@pytest.mark.asyncio
async def test_fastapi_websocket_port_receive(monkeypatch: pytest.MonkeyPatch, fastapi_websocket_mock: WebSocket):
    message = {
        "foo": "bar"
    }
    receive_mock = AsyncMock(return_value=message)
    monkeypatch.setattr(fastapi_websocket_mock, "receive_json", receive_mock)
    fastapi_websocket_port = FastApiWebSocketPort(fastapi_websocket_mock)
    await fastapi_websocket_port.receive()
    receive_mock.assert_awaited_once()

@pytest.mark.asyncio
async def test_fastapi_websocket_port_close(monkeypatch: pytest.MonkeyPatch, fastapi_websocket_mock: WebSocket):
    close_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(fastapi_websocket_mock, "close", close_mock)
    fastapi_websocket_port = FastApiWebSocketPort(fastapi_websocket_mock)
    await fastapi_websocket_port.close()
    close_mock.assert_awaited_once()

def test_fastapi_websocket_port_websocket(app):
    client = TestClient(app)
    message = {
        "foo": "bar"
    }
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json(message)
        received_message = websocket.receive_json()
        assert received_message == {
            "foo": "bar",
            "lorem": "ipsum"
        }