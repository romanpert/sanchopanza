"""A decider's long-context twin, or why it has none: the one place that asks for it.

Jev at TypeSafe's address has the mode (`JevDecider.with_long_context`), and so do a
`CappedDecider` and a `CachedDecider` around it, which forward to their inner decider's twin.
A CLM server, a proxy address, a recording, a local model or a general LLM have none: either
no `with_long_context` at all, or one that raises. Used by `harness.memory_window` and
`points.longdoc`.
"""

from __future__ import annotations

from typing import Any


def long_context_twin(decider: Any, timeout_s: float) -> tuple[Any | None, str]:
    """`decider.with_long_context(timeout_s=timeout_s)`, or (None, why) when it has no such
    mode. Never raises: the caller falls back or escalates with the reason."""
    make = getattr(decider, "with_long_context", None)
    name = getattr(decider, "name", "?")
    if not callable(make):
        return None, f"the decider {name!r} has no long-context mode"
    try:
        return make(timeout_s=timeout_s), ""
    except Exception as error:  # noqa: BLE001 - a CLM server, a proxy, a wrapper over one
        return None, f"the decider {name!r} has no long-context mode ({error.__class__.__name__})"
