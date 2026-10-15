"""The memory gate's long window: every memory or record read whole, in one call.

`SANCHOPANZA_MEMORY_WINDOW` is `long` or `short`, and its default depends on where it is read:

- the library gate `memory_gate.gate` defaults to **long** (`GATE_DEFAULT`), confirmed there
  (below); `short` turns it off;
- the installed hook (`memory_hook`, at a session's first prompt) defaults to **short**
  (`HOOK_DEFAULT`): it judges records, not memory files, and the long window is not measured on
  them; `long` turns it on.

`short` is the shipped short window, whose requests, journal and log rows are the same to the
byte as before the long window existed (tests/test_memory_window.py pins them); any value other
than `short` or `long` is the short window too, in both places, with one line on stderr saying so.

Measured (lot L6, docs/results/2026-10-15-jev114-l6, A7), on the library call
`memory_gate.gate` over 36 LongMemEval S test questions: the gate's selection recall went from
0.72 to 0.91 with every session whole in one call under Jev's long-context header, on jev-1.13.0
and jev-1.14.0 alike (+18.5 points, Holm p 0.03), 3.1 points under BM25 top 3. Per prompt, one
long call (about 120k tokens, 0.005 USD, 1.5 s median and 2.5 s at most) replaced about 2.9
short triage calls (0.3 s each); the recall question is asked in both, and the short path cost
about 0.001 USD a prompt in all. The long call's cost grows with the memory: Jev charges 0.042 USD
a million input tokens, about 0.01 USD at the `LONG_WINDOW_CHARS` ceiling. Confirmed on the 84
unseen test questions on jev-1.13.0 (docs/results/2026-10-15-memgate-long): 0.726 to 0.905,
+17.8 points [+10.7, +25.7], reaching BM25 top 3.

Where it applies, and nowhere else (not the autopilot's recall, not any other point):

- `memory_gate.gate` (memory files; the path L6 measured, which no installed hook calls; on by
  default): the triage reads each memory whole, up to `LONG_LIMITS.page_chars`, all in one call
  under the long-context header, as L6 did, instead of 900 characters each in a tournament.
  `needs_recall` stays on the short window and without the header.
- `memory_hook` at a session's first prompt (records of earlier requests; installed by default;
  the long window only with `SANCHOPANZA_MEMORY_WINDOW=long`): the decider reads each candidate
  record whole (`Episode.text()`) instead of its 880-character page, on the same decider; the
  long-context twin only when the call is over Jev's short window (`SHORT_WINDOW_CHARS`). Not
  measured on records: they are bounded by code (request, report and output at about 1,000
  characters each), so L6's gain, found where evidence sat deep in a long session, may not carry
  over. `benchmarks/memgate_hook` is the replay that would measure it.

It falls back to the shipped short path, never in silence, when:

- the request (state and questions) is over `LONG_WINDOW_CHARS`; L6 never got there in A7 (its
  largest call was 124,851 tokens), so the measured path takes over rather than a middle cut,
  which L6 tried only on LongBench documents;
- the call needs the header and the decider has no long-context mode (`with_long_context`:
  Jev at TypeSafe's address and a `CappedDecider` around it; a CLM server, a proxy address, a
  recording, a local model or a general LLM have none);
- the job's budget is spent, or the long call's estimate (`providers.capped.estimate_usd` at the
  decider's `price_per_mtok`) does not fit what is left of it;
- the hook's time does not leave room for it, or it takes longer than its own deadline (the
  hook's `SANCHOPANZA_MEMORY_DECIDER_SECONDS` less `SHORT_RESERVE_S`, so the pages still run);
- it answers nothing (a 400 past 262k tokens, a spend cap, out of funds, a timeout), once.

Each fall back writes one line on stderr, a `memory_window` event in the journal and the reason
(`window_fallback`, with the call's own error in `long_error`) in the gate's report or the memory
log row.

What is enforced on spend: the job's cap (`Thresholds.max_usd`) is checked before the long call
against its estimate, the long call runs under what is left, and its decisions and dollars are
then added to the job's meter (`Squire.absorb`), so later decisions see them. A long call cut
by its deadline comes back with no bill while the server may still charge it: it is charged at
its estimate, on the job's meter and in the report (`long_usd`, with `long_usd_estimated`), and
a `CappedDecider` keeps its reservation in the ledger at the estimate too. A `CappedDecider`
passes its ledger and caps to the twin (the twin keeps its own in-process meter; the ledger and
the job's meter hold the spend), and the twin shares the out-of-funds breaker. Like any
decision, one call can still cost more than its estimate. The dollars are in the decision event,
the `memory_window` event (`usd`), the report (`long_usd`) and the log row.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
from collections.abc import Awaitable, Callable, Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from .. import _env
from ..budget import Meter
from ..contract import Decision, Question, State
from ..limits import Limits
from ..providers.capped import DEFAULT_PRICE_PER_MTOK, estimate_usd

if TYPE_CHECKING:
    from ..squire import Squire

SHORT = "short"
LONG = "long"
ENV = "MEMORY_WINDOW"  # SANCHOPANZA_MEMORY_WINDOW
# The window when the setting is unset: confirmed at the library gate (lot memgate-long), not
# measured at the installed hook, which stays on the shipped short window.
GATE_DEFAULT = LONG
HOOK_DEFAULT = SHORT
# Lot L6's `LONG_LIMITS`, and a record of the hook read as whole as a memory file.
LONG_LIMITS = Limits(page_chars=400_000, pages_per_call=1_000, memory_record_chars=400_000)
# Jev's long window is 262,144 tokens a request; at `CappedDecider`'s pessimistic 3 characters a
# token (Jev measured 4 to 7.4) that is 786k characters of request, questions included.
LONG_WINDOW_CHARS = 750_000
# Jev's default window, 64k tokens a request, at the same 3 characters a token.
SHORT_WINDOW_CHARS = 190_000
LONG_TIMEOUT_S = 8.0  # per request; L6's long calls took 2.5 s at most
SHORT_RESERVE_S = 3.0  # of the hook's decider time, kept for the pages after a slow long call
PREFIX = "sanchopanza memory gate: long window"

T = TypeVar("T")


def normalize_window(value: str) -> str:
    """`short` or `long`, in any case and with spaces; anything else is a `ValueError`."""
    window = str(value).strip().lower()
    if window not in (SHORT, LONG):
        raise ValueError(f"the memory window is short or long, not {value!r}")
    return window


def window_from_env(env: Mapping[str, str] | None = None, *, default: str = SHORT) -> str:
    """`SANCHOPANZA_MEMORY_WINDOW`: `long` or `short`; `default` when unset or blank (the
    library gate passes `GATE_DEFAULT`, the hook `HOOK_DEFAULT`). An unknown value is the short
    window, with one line on stderr: a hook must not fail on a typo."""
    raw = _env.get(ENV, "", env=env)
    if not raw.strip():
        return normalize_window(default)
    try:
        return normalize_window(raw)
    except ValueError:
        _say(f"SANCHOPANZA_MEMORY_WINDOW={raw.strip()!r} is not short or long; short used")
        return SHORT


def request_chars(state: State, questions: Mapping[str, Question]) -> int:
    """What a call would send, in characters: the state and the questions, as `CappedDecider`
    measures them for its estimate."""
    asked = {key: repr(question) for key, question in questions.items()}
    return len(json.dumps({"state": state, "questions": asked}, ensure_ascii=False, default=str))


def _say(text: str) -> None:
    with contextlib.suppress(Exception):  # stderr gone is no reason to break a prompt
        sys.stderr.write(f"{PREFIX}: {text}\n")


class _Watched:
    """A decider that keeps the last error of its calls, raised or answered, for the report."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.name = getattr(inner, "name", "?")
        self.accepts_attachments = getattr(inner, "accepts_attachments", False)
        self.error = ""

    async def decide(self, point: str, state: State, questions: Mapping[str, Question]) -> Decision:
        try:
            decision = await self._inner.decide(point, state, questions)
        except Exception as error:
            self.error = f"{error.__class__.__name__}: {error}"[:300]
            raise
        if decision.error:
            self.error = str(decision.error)[:300]
        return decision


def _decider_for(squire: Squire, header: bool) -> tuple[Any | None, str]:
    """The squire's own decider, or with `header` its long-context twin; (None, why) without."""
    if not header:
        return squire.decider, ""
    make = getattr(squire.decider, "with_long_context", None)
    name = getattr(squire.decider, "name", "?")
    if not callable(make):
        return None, f"the decider {name!r} has no long-context mode"
    try:
        return make(timeout_s=LONG_TIMEOUT_S), ""
    except Exception as error:  # noqa: BLE001 - a CLM server, a proxy, a wrapper over one
        return None, f"the decider {name!r} has no long-context mode ({error.__class__.__name__})"


def _note(squire: Squire, data: dict[str, Any]) -> dict[str, Any]:
    with contextlib.suppress(Exception):  # a journal that cannot write never costs the recall
        squire.journal.record("memory_window", data)
    return data


def _fall_back(
    squire: Squire,
    chars: int,
    reason: str,
    *,
    usd: float = 0.0,
    error: str = "",
    estimated: bool = False,
) -> dict[str, Any]:
    _say(f"{reason}; the short window was used")
    extra = {"error": error} if error else {}
    extra = {**extra, "usd_estimated": True} if estimated else extra
    _note(squire, {"window": SHORT, "chars": chars, "usd": usd, "fallback": reason, **extra})
    report = {"window": SHORT, "window_fallback": reason, "long_chars": chars, "long_usd": usd}
    report = {**report, "long_error": error} if error else report
    return {**report, "long_usd_estimated": True} if estimated else report


def _budget_refusal(
    squire: Squire, decider: Any, state: State, questions: Mapping
) -> tuple[str, float]:
    """(why the long call would break the job's cap, or "" when it fits; its estimate)."""
    if squire.exhausted:
        return "the job's budget is spent", 0.0
    price = float(getattr(decider, "price_per_mtok", DEFAULT_PRICE_PER_MTOK))
    estimate = estimate_usd(state, questions, price_per_mtok=price)
    left = squire.thresholds.max_usd - squire.meter.cost_usd
    if estimate > left:
        return (f"the long call would not fit the job's budget ({estimate:.6f} USD estimated, "
                f"{left:.6f} left)"), estimate  # fmt: skip
    return "", estimate


async def run_long(
    squire: Squire,
    state: State,
    questions: Mapping[str, Question],
    ask: Callable[[Squire], Awaitable[T]],
    answered: Callable[[T], bool],
    *,
    header: bool = True,
    deadline_s: float | None = None,
) -> tuple[T | None, dict[str, Any]]:
    """(what `ask` returned on the long squire, report), or (None, report) when the caller
    must take the short path. `state` and `questions` are the request `ask` will send, for its
    size and its estimate. `header`: always under the long-context header (the gate, as L6
    measured it); else only past `SHORT_WINDOW_CHARS` (the hook). `deadline_s` bounds the long
    call. The short window never comes here."""
    chars = request_chars(state, questions)
    if chars > LONG_WINDOW_CHARS:
        why = f"{chars} characters, over the long window's {LONG_WINDOW_CHARS}"
        return None, _fall_back(squire, chars, why)
    needs_header = header or chars > SHORT_WINDOW_CHARS
    decider, why = _decider_for(squire, needs_header)
    if decider is None:
        return None, _fall_back(squire, chars, why)
    why, estimate = _budget_refusal(squire, decider, state, questions)
    if why:
        return None, _fall_back(squire, chars, why)
    if deadline_s is not None and deadline_s <= 0:
        return None, _fall_back(squire, chars, "no time is left for a long call")
    watched = _Watched(decider)
    t, spent = squire.thresholds, squire.meter
    left = t.with_(max_usd=t.max_usd - spent.cost_usd,
                   max_decisions=t.max_decisions - spent.decisions)  # fmt: skip
    long = squire.fork(thresholds=left, decider=watched, limits=LONG_LIMITS)
    result: T | None = None
    timed_out = False
    try:
        pending = ask(long)
        result = await (pending if deadline_s is None else asyncio.wait_for(pending, deadline_s))
    except TimeoutError:
        timed_out = True
        watched.error = f"TimeoutError: no answer within {deadline_s:g} s"
    finally:
        squire.absorb(long.meter)  # the job's cap holds what the long call spent
    usd = long.meter.cost_usd
    if timed_out:
        # Cut in flight, the call came back with no bill, but the server may charge a request
        # it received: the job counts it at its estimate (a `CappedDecider` keeps it too).
        estimated = usd == 0.0
        if estimated:
            squire.absorb(Meter(cost_usd=estimate))
            usd = estimate
        why = f"the long call took over its {deadline_s:g} s"
        return None, _fall_back(
            squire, chars, why, usd=usd, error=watched.error, estimated=estimated
        )
    if result is None or not answered(result):
        why = f"the long call answered nothing ({watched.error or 'no error given'})"
        return None, _fall_back(squire, chars, why, usd=usd, error=watched.error)
    _note(squire, {"window": LONG, "chars": chars, "usd": usd, "header": needs_header})
    return result, {"window": LONG, "long_chars": chars, "long_usd": usd,
                    "long_header": needs_header}  # fmt: skip
