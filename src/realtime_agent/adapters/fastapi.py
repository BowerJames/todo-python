"""FastAPI websocket adapter implementing the :class:`WebSocketPort` protocol."""

from __future__ import annotations

import json
from typing import Any

from fastapi import WebSocket
from fastapi.encoders import jsonable_encoder
from starlette.websockets import WebSocketDisconnect, WebSocketState

from realtime_agent.session import WebSocketPort

__all__ = ["FastApiWebSocketPort"]


class FastApiWebSocketPort(WebSocketPort):
    """Bridge a FastAPI :class:`WebSocket` instance to the ``WebSocketPort`` protocol.

    The adapter normalises the FastAPI/Starlette websocket API into the minimal
    contract expected by the session runtime:

    * :meth:`accept` becomes idempotent and avoids duplicate accept calls.
    * :meth:`send` automatically picks the optimal FastAPI transport method based
      on the payload type (text, bytes, or JSON-serialisable objects).
    * :meth:`receive` unwraps Starlette's low-level message payloads and raises a
      :class:`ConnectionError` when the client disconnects.
    """

    __slots__ = ("_websocket", "_accepted", "_close_code", "_close_reason")

    def __init__(
        self,
        websocket: WebSocket,
        *,
        close_code: int = 1000,
        close_reason: str | None = None,
    ) -> None:
        self._websocket = websocket
        self._close_code = close_code
        self._close_reason = close_reason

        state = getattr(websocket, "client_state", None)
        self._accepted = state is WebSocketState.CONNECTED

    @property
    def websocket(self) -> WebSocket:
        """Return the underlying FastAPI websocket instance."""

        return self._websocket

    async def accept(self) -> None:
        """Accept the websocket connection if it has not been accepted already."""

        if self._accepted:
            return

        await self._websocket.accept()
        state = getattr(self._websocket, "client_state", None)
        if state is WebSocketState.CONNECTED:
            self._accepted = True
        elif state is WebSocketState.DISCONNECTED:
            self._accepted = False
        else:
            # Assume acceptance succeeded when the state is not explicitly reported.
            self._accepted = True

    def __aiter__(self) -> "FastApiWebSocketPort":
        """Return the port itself as an asynchronous iterator."""

        return self

    async def __anext__(self) -> Any:
        """Yield the next incoming message until the websocket closes."""

        try:
            return await self.receive()
        except WebSocketDisconnect as exc:
            # A graceful close from the client results in Starlette raising
            # ``WebSocketDisconnect``. Convert it to ``StopAsyncIteration`` so
            # ``async for`` loops terminate naturally.
            if getattr(exc, "code", 1000) == 1000:
                raise StopAsyncIteration from None
            raise StopAsyncIteration from exc

    async def send(self, message: Any) -> None:
        """Serialise and forward a message to the client."""

        if isinstance(message, (bytes, bytearray, memoryview)):
            await self._websocket.send_bytes(bytes(message))
            return

        if isinstance(message, str):
            await self._websocket.send_text(message)
            return

        payload = jsonable_encoder(message)
        await self._websocket.send_json(payload)

    async def receive(self) -> Any:
        """Wait for the next message from the client."""

        receive_json = getattr(self._websocket, "receive_json", None)
        if callable(receive_json):
            try:
                return await receive_json()
            except WebSocketDisconnect as exc:
                if getattr(exc, "code", 1000) == 1000:
                    raise
                raise ConnectionError("FastAPI websocket disconnected") from exc
            except (TypeError, ValueError, AttributeError, RuntimeError):
                # Fall back to the raw receive API when the FastAPI helper
                # cannot decode the payload or is otherwise unavailable.
                pass

        try:
            payload = await self._websocket.receive()
        except WebSocketDisconnect as exc:
            if getattr(exc, "code", 1000) == 1000:
                raise
            raise ConnectionError("FastAPI websocket disconnected") from exc

        return self._normalise_received_payload(payload)

    async def close(self) -> None:
        """Close the websocket connection."""

        kwargs: dict[str, Any] = {}
        if self._close_reason is not None:
            kwargs["reason"] = self._close_reason
        if self._close_code != 1000 or self._close_reason is not None:
            kwargs["code"] = self._close_code

        await self._websocket.close(**kwargs)

    def _normalise_received_payload(self, payload: Any) -> Any:
        """Convert the Starlette event payload into a plain value."""

        if not isinstance(payload, dict):
            return payload

        message_type = payload.get("type")

        if message_type == "websocket.disconnect":
            code = payload.get("code", self._close_code)
            reason = payload.get("reason")
            if code == 1000:
                raise WebSocketDisconnect(code, reason)
            raise ConnectionError(f"FastAPI websocket disconnected with code {code}")

        if message_type and message_type != "websocket.receive":
            return {k: v for k, v in payload.items() if k != "type"}

        if "json" in payload:
            return payload["json"]

        if "text" in payload and payload["text"] is not None:
            text = payload["text"]
            if isinstance(text, str):
                try:
                    return json.loads(text)
                except (TypeError, ValueError):
                    return text
            return text

        if "bytes" in payload and payload["bytes"] is not None:
            data = payload["bytes"]
            if isinstance(data, (bytearray, memoryview)):
                return bytes(data)
            return data

        return {k: v for k, v in payload.items() if k != "type"}


