"""Compatibility wrapper for realtime_agent.services.openai."""

from __future__ import annotations

from realtime_agent.services.openai import (
    OpenAIConnectionError,
    connect,
)

__all__ = [
    "OpenAIConnectionError",
    "connect",
]

