from fastapi import WebSocket, FastAPI
from unittest.mock import create_autospec
import pytest

from realtime_agent.adapters.fastapi import FastApiWebSocketPort
from realtime_agent import WebSocketPort

@pytest.fixture
def fastapi_websocket_mock():
    return create_autospec(WebSocket)


@pytest.fixture
def app():
    app = FastAPI()

    @app.websocket("/ws")
    async def websocket(websocket: WebSocket):
        fast_api_websocket_port = FastApiWebSocketPort(websocket)
        await fast_api_websocket_port.accept()
        message = await fast_api_websocket_port.receive()
        message["lorem"] = "ipsum"
        await fast_api_websocket_port.send(message)
        await fast_api_websocket_port.close()
    return app
