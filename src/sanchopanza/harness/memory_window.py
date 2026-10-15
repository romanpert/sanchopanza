"""The memory gate's long window: every memory or record read whole, in one call, with Jev's
long-context header on that call only. Opt-in: `SANCHOPANZA_MEMORY_WINDOW=long`. Unset, or any
other value, is the shipped short window, and its requests are the same to the byte
(tests/test_memory_window.py pins their recording keys).

Measured (lot L6, docs/results/2026-10-15-jev114-l6, A7): on 36 LongMemEval S test questions
the gate's recall went from 0.72 to 0.91 with every session whole in one call, on jev-1.13.0
and jev-1.14.0 alike (+18.5 points, Holm p 0.03), 3.1 points under BM25 top 3, at about
0.005 USD a prompt against 0.001. A long call took 1.5 s (median; 2.5 s at most, about 125k
tokens) where a short one took 0.3 s. The confirmation on 84 unseen questions is pending.

Where it applies, and nowhere else (not the autopilot's recall, not any other point):

- `memory_gate.gate` (memory files; the path L6 measured): the triage reads each memory whole,
  up to `LONG_LIMITS.page_chars`, all in one call, instead of 900 characters each in a
  tournament. `needs_recall` stays on the short window.
- `memory_hook` at a prompt (records of earlier requests; installed by default): the decider
  reads each candidate record whole (`Episode.text()`) instead of its 880-character page. Not
  measured on records: they are bounded by code (request, report and output at about 1,000
  characters each), so the gain L6 found where evidence sat deep in a long session may not
  carry over.

It falls back to the short path, never in silence, when:

- what the call would read is over `LONG_WINDOW_CHARS` (L6 never got there in A7: its largest
  payload was 124,851 tokens, so it is the shipped, measured path that takes over, not a middle
  cut, which L6 tried only on LongBench documents);
- the decider has no long-context mode (`with_long_context`: Jev, and a `CappedDecider` around
  it; a recording, a local model or a general LLM have none);
- the job's budget is spent;
- the long call answers nothing (a 400 past 262k tokens, a timeout), once.

In the hook, `SANCHOPANZA_MEMORY_DECIDER_SECONDS` (15) still bounds the whole choice, long call
and fall back together: past it nothing is injected and the log row says the decider timed out.

Each fall back writes one line on stderr, a `memory_window` event in the journal and the reason
in the gate's report or the memory log row. Cost: the long call's dollars are in its decision
event, in that `memory_window` event (`usd`), in the report (`long_usd`) and in the log row; the
long squire's per-job cap is what the squire it came from has left, and a `CappedDecider` gives a
twin under the same ledger and caps.
"""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Awaitable, Callable, Iterable, Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from .. import _env
from ..limits import Limits

if TYPE_CHECKING:
    from ..squire import Squire

SHORT = "short"
LONG = "long"
ENV = "MEMORY_WINDOW"  # SANCHOPANZA_MEMORY_WINDOW
# Lot L6's `LONG_LIMITS`, and a record of the hook read as whole as a memory file.
LONG_LIMITS = Limits(page_chars=400_000, pages_per_call=1_000, memory_record_chars=400_000)
# Jev's long window is 262,144 tokens a request. At `CappedDecider`'s pessimistic 3 characters a
# token (Jev measured 4 to 7.4) that is 786k characters; the rest is room for the questions.
LONG_WINDOW_CHARS = 750_000
LONG_TIMEOUT_S = 30.0  # per request; L6's long calls took 2.5 s at most
PREFIX = "sanchopanza memory gate: long window"

T = TypeVar("T")


def window_from_env(env: Mapping[str, str] | None = None) -> str:
    """`long` when `SANCHOPANZA_MEMORY_WINDOW` says so (any case, spaces ignored), else `short`."""
    return LONG if _env.get(ENV, "", env=env).strip().lower() == LONG else SHORT


def payload_chars(prompt: str, texts: Iterable[str]) -> int:
    """What a long call would read, in characters: the prompt and every text whole."""
    return len(prompt) + sum(len(text) for text in texts)


def long_squire(squire: Squire) -> tuple[Squire | None, str]:
    """(the squire for the one long call, "") or (None, why there is none).

    Same thresholds, journal and redactor; the decider's long-context twin; `LONG_LIMITS`; and
    as per-job cap what `squire` has left, so the two together stay under the job's cap."""
    if squire.exhausted:
        return None, "the job's budget is spent"
    make = getattr(squire.decider, "with_long_context", None)
    name = getattr(squire.decider, "name", "?")
    if not callable(make):
        return None, f"the decider {name!r} has no long-context mode"
    try:
        twin = make(timeout_s=LONG_TIMEOUT_S)
    except Exception as error:  # noqa: BLE001 - a wrapper over a decider without one
        return None, f"the decider {name!r} has no long-context mode ({error.__class__.__name__})"
    t, spent = squire.thresholds, squire.meter
    left = t.with_(max_usd=t.max_usd - spent.cost_usd,
                   max_decisions=t.max_decisions - spent.decisions)  # fmt: skip
    return squire.fork(thresholds=left, decider=twin, limits=LONG_LIMITS), ""


def _note(squire: Squire, data: dict[str, Any]) -> dict[str, Any]:
    with contextlib.suppress(Exception):  # a journal that cannot write never costs the recall
        squire.journal.record("memory_window", data)
    return data


def _fall_back(squire: Squire, chars: int, reason: str, usd: float = 0.0) -> dict[str, Any]:
    with contextlib.suppress(Exception):  # stderr gone is no reason to break a prompt
        sys.stderr.write(f"{PREFIX}: {reason}; the short window was used\n")
    _note(squire, {"window": SHORT, "chars": chars, "usd": usd, "fallback": reason})
    return {"window": SHORT, "window_fallback": reason, "long_chars": chars, "long_usd": usd}


async def run_long(
    squire: Squire,
    chars: int,
    ask: Callable[[Squire], Awaitable[T]],
    answered: Callable[[T], bool],
) -> tuple[T | None, dict[str, Any]]:
    """(what `ask` returned on the long squire, report) or (None, report) when the caller
    must take the short path; the report says which and why, and costs nothing to the default
    path, which never comes here."""
    if chars > LONG_WINDOW_CHARS:
        why = f"{chars} characters, over the long window's {LONG_WINDOW_CHARS}"
        return None, _fall_back(squire, chars, why)
    long, why = long_squire(squire)
    if long is None:
        return None, _fall_back(squire, chars, why)
    result = await ask(long)
    usd = long.meter.cost_usd
    if not answered(result):
        return None, _fall_back(squire, chars, "the long call answered nothing", usd)
    _note(squire, {"window": LONG, "chars": chars, "usd": usd})
    return result, {"window": LONG, "long_chars": chars, "long_usd": usd}
