from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import pytest
from starlette.websockets import WebSocketState

from realtime_agent.adapters.fastapi import FastApiWebSocketPort


class StubFastApiWebSocket:
    def __init__(self) -> None:
        self.client_state = WebSocketState.CONNECTING
        self.accept_calls = 0
        self.close_calls: list[tuple[int, str | None]] = []
        self.sent: list[tuple[str, object]] = []
        self._receive_queue: asyncio.Queue[object] = asyncio.Queue()

    async def accept(self) -> None:
        self.accept_calls += 1
        self.client_state = WebSocketState.CONNECTED

    async def send_text(self, value: str) -> None:
        self.sent.append(("text", value))

    async def send_bytes(self, value: bytes) -> None:
        self.sent.append(("bytes", value))

    async def send_json(self, value: object) -> None:
        self.sent.append(("json", value))

    async def receive(self) -> object:
        message = await self._receive_queue.get()
        if isinstance(message, Exception):
            raise message
        return message

    async def close(self, *, code: int = 1000, reason: str | None = None) -> None:
        self.close_calls.append((code, reason))
        self.client_state = WebSocketState.DISCONNECTED

    def push_receive(self, message: object) -> None:
        self._receive_queue.put_nowait(message)


@pytest.mark.asyncio
async def test_accept_is_idempotent() -> None:
    websocket = StubFastApiWebSocket()
    port = FastApiWebSocketPort(websocket)

    await port.accept()
    await port.accept()

    assert websocket.accept_calls == 1


@pytest.mark.asyncio
async def test_send_dispatches_on_payload_type() -> None:
    websocket = StubFastApiWebSocket()
    port = FastApiWebSocketPort(websocket)

    await port.send("hello")
    await port.send(b"bytes")
    await port.send(memoryview(b"buffer"))

    @dataclass
    class Payload:
        content: str

    await port.send(Payload("value"))

    assert websocket.sent == [
        ("text", "hello"),
        ("bytes", b"bytes"),
        ("bytes", b"buffer"),
        ("json", {"content": "value"}),
    ]


@pytest.mark.asyncio
async def test_receive_returns_json_payload() -> None:
    websocket = StubFastApiWebSocket()
    port = FastApiWebSocketPort(websocket)
    websocket.push_receive(
        {
            "type": "websocket.receive",
            "text": json.dumps({"foo": "bar"}),
        }
    )

    payload = await port.receive()

    assert payload == {"foo": "bar"}


@pytest.mark.asyncio
async def test_receive_returns_raw_text_when_not_json() -> None:
    websocket = StubFastApiWebSocket()
    port = FastApiWebSocketPort(websocket)
    websocket.push_receive({"type": "websocket.receive", "text": "plain"})

    payload = await port.receive()

    assert payload == "plain"


@pytest.mark.asyncio
async def test_receive_handles_bytes_payload() -> None:
    websocket = StubFastApiWebSocket()
    port = FastApiWebSocketPort(websocket)
    websocket.push_receive({"type": "websocket.receive", "bytes": bytearray(b"data")})

    payload = await port.receive()

    assert payload == b"data"


@pytest.mark.asyncio
async def test_receive_raises_on_disconnect() -> None:
    websocket = StubFastApiWebSocket()
    port = FastApiWebSocketPort(websocket)
    websocket.push_receive({"type": "websocket.disconnect", "code": 1001})

    with pytest.raises(ConnectionError):
        await port.receive()


@pytest.mark.asyncio
async def test_close_uses_configured_code_and_reason() -> None:
    websocket = StubFastApiWebSocket()
    port = FastApiWebSocketPort(websocket, close_code=4000, close_reason="shutdown")

    await port.close()

    assert websocket.close_calls == [(4000, "shutdown")]


