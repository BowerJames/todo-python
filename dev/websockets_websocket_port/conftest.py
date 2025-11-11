import pytest
import unittest.mock as mock

from websockets.asyncio.client import connect, ClientConnection

from realtime_agent.adapters.websockets import WebsocketsWebSocketPort

@pytest.fixture
def websockets_client_connection_mock(monkeypatch: pytest.MonkeyPatch):
    client_connection_mock = mock.create_autospec(ClientConnection)
    return client_connection_mock

@pytest.fixture
def websocket_port(websockets_client_connection_mock):
    return WebsocketsWebSocketPort(websockets_client_connection_mock)