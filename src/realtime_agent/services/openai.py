"""OpenAI realtime service connector."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

try:  # pragma: no cover - import is validated through usage
    import websockets.asyncio.client as websockets_client
except ImportError:  # pragma: no cover - surfaced at runtime
    websockets_client = None  # type: ignore[assignment]
    ClientConnection = Any  # type: ignore[assignment]
else:  # pragma: no cover - import is validated through usage
    ClientConnection = websockets_client.ClientConnection

if TYPE_CHECKING:  # pragma: no cover - import only for typing
    from realtime_agent.adapters.websockets import WebsocketsWebSocketPort
    from realtime_agent.session import WebSocketPort

__all__ = [
    "OpenAIConnectionError",
    "connect",
    "get_connector",
]

DEFAULT_REALTIME_URL = "wss://api.openai.com/v1/realtime"
MODEL_ENV_KEYS = ("OPENAI_REALTIME_MODEL", "OPENAI_MODEL")
URL_ENV_KEYS = ("OPENAI_REALTIME_URL", "OPENAI_REALTIME_ROOT_URL")


class OpenAIConnectionError(RuntimeError):
    """Raised when the OpenAI realtime connector has not been configured."""


def _resolve_first(*values: str | None) -> str | None:
    """Return the first non-empty value."""

    for value in values:
        if value:
            return value
    return None


def _build_connection_url(base_url: str, model: str) -> str:
    """Compose the websocket URL with the desired model."""

    if not base_url:
        raise OpenAIConnectionError("OpenAI realtime base URL is not configured")
    parsed = urlparse(base_url)
    if not parsed.scheme:
        raise OpenAIConnectionError(
            f"OpenAI realtime URL must define a scheme, got {base_url!r}"
        )
    if parsed.scheme not in {"ws", "wss"}:
        scheme_map = {"http": "ws", "https": "wss"}
        converted = scheme_map.get(parsed.scheme)
        if converted is None:
            raise OpenAIConnectionError(
                f"OpenAI realtime URL must use ws or wss scheme, got {base_url!r}"
            )
        parsed = parsed._replace(scheme=converted)

    existing_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    existing_params["model"] = model
    query = urlencode(existing_params)
    return urlunparse(parsed._replace(query=query))


def _prepare_headers(api_key: str, extra_headers: Mapping[str, str] | None) -> dict[str, str]:
    headers: dict[str, str] = {"Authorization": f"Bearer {api_key}"}
    if extra_headers:
        headers.update(extra_headers)
    return headers


async def connect(
    *,
    model: str | None = None,
    api_key: str | None = None,
    root_url: str | None = None,
    headers: Mapping[str, str] | None = None,
    adapter_factory: Callable[[ClientConnection], "WebSocketPort"] | None = None,
    **connection_kwargs: Any,
) -> "WebSocketPort" | ClientConnection:
    """Establish a realtime websocket connection to OpenAI.

    Parameters
    ----------
    model:
        The realtime model identifier. If omitted, the connector will look up
        ``OPENAI_REALTIME_MODEL`` then ``OPENAI_MODEL`` from the environment.
    api_key:
        Optional API key. Falling back to the ``OPENAI_API_KEY`` environment
        variable if not provided.
    root_url:
        Base realtime endpoint. Defaults to ``OPENAI_REALTIME_URL`` then
        ``OPENAI_REALTIME_ROOT_URL`` environment variables before using the
        canonical OpenAI realtime endpoint.
    headers:
        Additional HTTP headers to send during the websocket handshake.
    adapter_factory:
        Callable used to wrap the low-level :class:`ClientConnection`. Defaults
        to :class:`~realtime_agent.adapters.websockets.WebsocketsWebSocketPort`.
        Pass ``None`` to receive the raw client connection.
    connection_kwargs:
        Extra keyword arguments forwarded to :func:`websockets.asyncio.client.connect`.
    """

    if websockets_client is None:
        raise OpenAIConnectionError(
            "The `websockets` package is required to establish realtime connections"
        )

    api_key = _resolve_first(api_key, os.getenv("OPENAI_API_KEY"))
    if not api_key:
        raise OpenAIConnectionError(
            "OpenAI API key is required. Provide `api_key` or set OPENAI_API_KEY."
        )

    model = _resolve_first(model, *(os.getenv(key) for key in MODEL_ENV_KEYS))
    if not model:
        raise OpenAIConnectionError(
            "OpenAI realtime model is required. Provide `model` or set "
            "OPENAI_REALTIME_MODEL / OPENAI_MODEL."
        )

    root_url = _resolve_first(
        root_url,
        *(os.getenv(key) for key in URL_ENV_KEYS),
        DEFAULT_REALTIME_URL,
    )
    assert root_url is not None  # for type-checkers

    connection_url = _build_connection_url(root_url, model)
    handshake_headers = _prepare_headers(api_key, headers)

    connector = websockets_client.connect(
        connection_url, additional_headers=handshake_headers, **connection_kwargs
    )
    connection: ClientConnection = await connector

    if adapter_factory is None:
        from realtime_agent.adapters.websockets import WebsocketsWebSocketPort

        adapter_factory = WebsocketsWebSocketPort

    return adapter_factory(connection)


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



