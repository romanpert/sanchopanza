"""Decision providers. Each one is a file that implements `Decider`; nothing else changes.

    create("jev", api_key=...)            TypeSafe Jev over HTTP
    create("recorded", path=...)          replays a fixture; tests and dry runs, free
    create("null")                        answers nothing; every policy uses its default
    create("llm", complete=...)           any LLM forced into a JSON schema
    create("local", handlers=...)         your own classifiers, embeddings, vision models
    FallbackDecider([a, b])               first provider that answers wins
    RoutedDecider({"routing": a}, b)      one provider per decision point
    CascadeDecider(a, b, tau=0.4)         b only for the questions a was unsure of
    CachedDecider(a, ttl_seconds=3600)    a repeat within the TTL: same answer, not paid again

Third-party packages register more under the `sanchopanza.providers` entry-point group.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..contract import Decider
    from .cached import CachedDecider
    from .chain import CascadeDecider, FallbackDecider, RoutedDecider
    from .fixed import FixedDecider
    from .local import LocalDecider
    from .null import NullDecider
    from .recorded import RecordedDecider, RecordingDecider, key_of, order_of

__all__ = [
    "CachedDecider",
    "CascadeDecider",
    "FallbackDecider",
    "FixedDecider",
    "LocalDecider",
    "NullDecider",
    "RecordedDecider",
    "RecordingDecider",
    "RoutedDecider",
    "create",
    "key_of",
    "order_of",
]

# Resolved on first use (PEP 562), and the entry-point scan only when a name is not built in:
# `importlib.metadata` alone was a fifth of the hook's start-up.
_LAZY = {
    "CachedDecider": "cached",
    **dict.fromkeys(("CascadeDecider", "FallbackDecider", "RoutedDecider"), "chain"),
    "FixedDecider": "fixed",
    "LocalDecider": "local",
    "NullDecider": "null",
    **dict.fromkeys(("RecordedDecider", "RecordingDecider", "key_of", "order_of"), "recorded"),
}


def __getattr__(name: str) -> Any:
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f".{module}", __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY))


_BUILTIN = {
    "null": "sanchopanza.providers.null:NullDecider",
    "recorded": "sanchopanza.providers.recorded:RecordedDecider",
    "jev": "sanchopanza.providers.jev:JevDecider",
    "clm": "sanchopanza.providers.jev:clm",
    "llm": "sanchopanza.providers.llm:LLMDecider",
    "local": "sanchopanza.providers.local:LocalDecider",
}


def _load(target: str) -> type:
    module_name, _, attr = target.partition(":")
    module = __import__(module_name, fromlist=[attr])
    return getattr(module, attr)


def available() -> dict[str, str]:
    """Provider names and where they come from, built-ins plus installed entry points."""
    from importlib.metadata import entry_points

    found = dict(_BUILTIN)
    for ep in entry_points(group="sanchopanza.providers"):
        found.setdefault(ep.name, ep.value)
    return found


def create(name: str, **kwargs: Any) -> Decider:
    """Instantiate a provider by name. Import errors surface as-is: missing extras are loud."""
    targets = _BUILTIN if name in _BUILTIN else available()
    if name not in targets:
        raise KeyError(f"unknown provider {name!r}; known: {sorted(targets)}")
    cls = _load(targets[name])
    if name == "recorded" and "path" in kwargs:
        return cls.from_file(kwargs["path"])
    return cls(**kwargs)
