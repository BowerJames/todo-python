"""OpenAI realtime service connector placeholders."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import only for typing
    from realtime_agent import WebSocketPort

__all__ = [
    "OpenAIConnectionError",
    "connect",
]


class OpenAIConnectionError(RuntimeError):
    """Raised when the OpenAI realtime connector has not been configured."""


async def connect(**config: Any) -> "WebSocketPort":  # pragma: no cover - default stub
    """Connect to the OpenAI realtime service.

    The default implementation acts as a placeholder and must be overridden
    by the application.  Tests typically monkeypatch this function.
    """

    raise OpenAIConnectionError(
        "OpenAI realtime connector is not configured. Monkeypatch"
        " `realtime.services.openai.connect` with an implementation that"
        " returns a WebSocketPort-compatible object."
    )

