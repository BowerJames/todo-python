"""`websockets` client adapter implementing the :class:`WebSocketPort` protocol."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any, Callable

from websockets.asyncio.client import ClientConnection
from websockets.exceptions import ConnectionClosed, ConnectionClosedOK

from realtime_agent.session import WebSocketPort

__all__ = ["WebsocketsWebSocketPort"]


class WebsocketsWebSocketPort(WebSocketPort):
    """Bridge a :mod:`websockets` client connection to the ``WebSocketPort`` protocol."""

    __slots__ = (
        "_connection",
        "_close_code",
        "_close_reason",
        "_json_dumps",
        "_json_loads",
    )

    def __init__(
        self,
        connection: ClientConnection,
        *,
        close_code: int = 1000,
        close_reason: str | None = None,
        json_dumps: Callable[[Any], str] | None = None,
        json_loads: Callable[[str], Any] | None = None,
    ) -> None:
        self._connection = connection
        self._close_code = int(close_code)
        self._close_reason = close_reason
        self._json_dumps = json_dumps or json.dumps
        self._json_loads = json_loads or json.loads

    @property
    def connection(self) -> ClientConnection:
        """Return the underlying websockets client connection."""

        return self._connection

    async def accept(self) -> None:
        """Client connections are established immediately, so this is a no-op."""

        return None

    def __aiter__(self) -> "WebsocketsWebSocketPort":
        """Return the websocket port as an asynchronous iterator."""

        return self

    async def __anext__(self) -> Any:
        """Yield the next message until the websocket closes."""

        try:
            return await self.receive()
        except ConnectionClosedOK as exc:
            raise StopAsyncIteration from exc
        except ConnectionError as exc:
            raise StopAsyncIteration from exc

    async def send(self, message: Any) -> None:
        """Serialise and forward a message to the websocket server."""

        if isinstance(message, (bytes, bytearray, memoryview)):
            await self._connection.send(bytes(message))
            return

        if isinstance(message, str):
            await self._connection.send(message)
            return

        payload = self._normalise_payload(message)
        try:
            encoded = self._json_dumps(payload)
        except TypeError as exc:
            raise TypeError("Message is not JSON serialisable") from exc

        await self._connection.send(encoded)

    async def receive(self) -> Any:
        """Wait for the next message from the websocket server."""

        try:
            payload = await self._connection.recv()
        except ConnectionClosedOK:
            raise
        except ConnectionClosed as exc:  # pragma: no cover - defensive fallback
            frame = getattr(exc, "rcvd", None) or getattr(exc, "sent", None)
            code = getattr(frame, "code", None)
            reason = getattr(frame, "reason", None)
            details = f"code {code}" if code is not None else "unknown code"
            if reason:
                details = f"{details} ({reason})"
            raise ConnectionError(f"Websockets connection closed with {details}") from exc

        if isinstance(payload, (bytes, bytearray, memoryview)):
            return bytes(payload)

        if isinstance(payload, str):
            try:
                return self._json_loads(payload)
            except (TypeError, ValueError, json.JSONDecodeError):
                return payload

        return payload

    async def close(self) -> None:
        """Close the websocket connection."""

        kwargs: dict[str, Any] = {}
        if self._close_code != 1000:
            kwargs["code"] = self._close_code
        if self._close_reason is not None:
            kwargs["reason"] = self._close_reason

        await self._connection.close(**kwargs)

    def _normalise_payload(self, message: Any) -> Any:
        """Prepare arbitrary objects for JSON serialisation."""

        if is_dataclass(message):
            return asdict(message)

        if isinstance(message, dict):
            return {key: self._normalise_payload(value) for key, value in message.items()}

        if isinstance(message, (list, tuple, set, frozenset)):
            return [self._normalise_payload(item) for item in message]

        if isinstance(message, memoryview):
            return bytes(message)

        return message


