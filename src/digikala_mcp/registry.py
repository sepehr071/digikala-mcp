"""Collects tool functions from the tool modules; server.py registers them."""

from collections.abc import Callable
from typing import Any

TOOLS: list[tuple[Callable[..., Any], str]] = []


def tool(title: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Mark an async function as an MCP tool with a human-readable title."""

    def register(fn: Callable[..., Any]) -> Callable[..., Any]:
        TOOLS.append((fn, title))
        return fn

    return register
