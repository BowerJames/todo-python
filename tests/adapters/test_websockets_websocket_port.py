from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

from realtime_agent.adapters.websockets import WebsocketsWebSocketPort


class StubClientConnection:
    def __init__(self) -> None:
        self.sent: list[object] = []
        self.close_calls: list[tuple[int, str]] = []
        self._receive_queue: asyncio.Queue[object] = asyncio.Queue()

    async def send(self, value: object) -> None:
        self.sent.append(value)

    async def recv(self) -> object:
        message = await self._receive_queue.get()
        if isinstance(message, Exception):
            raise message
        return message

    async def close(self, *, code: int = 1000, reason: str = "") -> None:
        self.close_calls.append((code, reason))

    def push_receive(self, value: object) -> None:
        self._receive_queue.put_nowait(value)


@pytest.mark.asyncio
async def test_accept_is_noop() -> None:
    connection = StubClientConnection()
    port = WebsocketsWebSocketPort(connection)

    await port.accept()


@pytest.mark.asyncio
async def test_send_dispatches_on_payload_type() -> None:
    connection = StubClientConnection()
    port = WebsocketsWebSocketPort(connection)

    await port.send("hello")
    await port.send(b"bytes")
    await port.send(memoryview(b"buffer"))

    @dataclass
    class Payload:
        content: str

    await port.send(Payload("value"))

    assert connection.sent == [
        "hello",
        b"bytes",
        b"buffer",
        '{"content": "value"}',
    ]


@pytest.mark.asyncio
async def test_receive_decodes_json_text() -> None:
    connection = StubClientConnection()
    port = WebsocketsWebSocketPort(connection)
    connection.push_receive('{"foo": "bar"}')

    payload = await port.receive()

    assert payload == {"foo": "bar"}


@pytest.mark.asyncio
async def test_receive_returns_raw_text_when_not_json() -> None:
    connection = StubClientConnection()
    port = WebsocketsWebSocketPort(connection)
    connection.push_receive("plain text")

    payload = await port.receive()

    assert payload == "plain text"


@pytest.mark.asyncio
async def test_receive_returns_bytes_payload() -> None:
    connection = StubClientConnection()
    port = WebsocketsWebSocketPort(connection)
    connection.push_receive(bytearray(b"data"))

    payload = await port.receive()

    assert payload == b"data"


@pytest.mark.asyncio
async def test_receive_reraises_connection_closed_ok() -> None:
    connection = StubClientConnection()
    port = WebsocketsWebSocketPort(connection)
    connection.push_receive(ConnectionClosedOK(None, None))

    with pytest.raises(ConnectionClosedOK):
        await port.receive()


@pytest.mark.asyncio
async def test_receive_wraps_connection_closed_error() -> None:
    connection = StubClientConnection()
    port = WebsocketsWebSocketPort(connection)
    connection.push_receive(ConnectionClosedError(None, None))

    with pytest.raises(ConnectionError):
        await port.receive()


@pytest.mark.asyncio
async def test_close_uses_configured_code_and_reason() -> None:
    connection = StubClientConnection()
    port = WebsocketsWebSocketPort(connection, close_code=4000, close_reason="shutdown")

    await port.close()

    assert connection.close_calls == [(4000, "shutdown")]


@pytest.mark.asyncio
async def test_async_iteration_stops_on_disconnect() -> None:
    connection = StubClientConnection()
    port = WebsocketsWebSocketPort(connection)
    connection.push_receive(ConnectionClosedOK(None, None))

    with pytest.raises(StopAsyncIteration):
        await port.__anext__()


