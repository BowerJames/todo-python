"""OpenAI realtime service connector placeholders."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import only for typing
    from realtime_agent.session import WebSocketPort

__all__ = [
    "OpenAIConnectionError",
    "connect",
    "get_connector",
]


class OpenAIConnectionError(RuntimeError):
    """Raised when the OpenAI realtime connector has not been configured."""


async def _default_connect(**config: Any) -> "WebSocketPort":  # pragma: no cover - default stub
    """Connect to the OpenAI realtime service.

    The default implementation acts as a placeholder and must be overridden
    by the application.  Tests typically monkeypatch this function.
    """

    raise OpenAIConnectionError(
        "OpenAI realtime connector is not configured. Monkeypatch "
        "`realtime_agent.services.openai.connect` with an implementation that "
        "returns a WebSocketPort-compatible object."
    )

connect = _default_connect
_DEFAULT_CONNECT = connect


def get_connector() -> Any:
    """Return the currently configured connector callable.

    This helper inspects the legacy ``realtime.services.openai`` module so that
    existing monkeypatches targeting the old import path continue to function.
    """

    legacy_module = sys.modules.get("realtime.services.openai")
    if legacy_module is not None:
        legacy_connect = getattr(legacy_module, "connect", None)
        if legacy_connect is not None and legacy_connect is not _DEFAULT_CONNECT:
            return legacy_connect
    return connect



