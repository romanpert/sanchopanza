"""One place that knows what a call to the big model cost, and writes it down.

    from meter import Meter, PRICES

    meter = Meter("claude-opus-5", ledger=Path("run/usage.jsonl"))
    response = client.messages.create(...)
    meter.add(response, label="annotate:mw-17")
    print(meter.summary())

Why this file exists. The prices and the cache arithmetic were copied in
`benchmarks/ab/run.py` and `benchmarks/cache/run.py`, and a third tool - the second annotator
of 2026-09-24 - was written without any, so a run that cost real money produced no measured
figure at all. The estimate was stated out loud beforehand and never checked afterwards,
which is the failure this module exists to make impossible: **there is now one thing to reach
for, and reaching for it is less work than not.**

What it measures, and what it does not. `Meter.cost()` is a *client-side estimate*: list
prices times reported tokens. It is exact arithmetic over the numbers the API returns, and it
is still not a bill. Discounts, tier pricing and anything the account negotiated live on the
invoice, not here. The authoritative figure is the organization's Usage and Cost report,
which needs an **Admin API key** (`sk-ant-admin...`); a normal `sk-ant-api...` key is refused
with a 401 and the message "The Admin API requires an Admin API key or an organization-scoped
API key". Treat this module as the thing that catches an unmeasured run, and the Usage and
Cost report as the thing that settles what was paid.

Cache arithmetic. A cached read costs 0.1x base input, a five-minute write 1.25x and a
one-hour write 2x. `cache_creation_input_tokens` does not say which TTL was used, so the
multiplier is a parameter: pass `cache_ttl="1h"` on a meter for a job that sets
`ENABLE_PROMPT_CACHING_1H`, or the figure understates the write side by 60 %.

**Server tools are billed per request as well as per token, and this file does not know
about that.** Measured on a real agent job on 2026-09-24: `web_search` charged exactly
**0.0100 USD per request** on top of the tokens its results consumed, twice over (0.1300 USD
across 13 searches, 0.1000 USD across 10). Those tokens are billed against
`claude-haiku-4-5`, a model the job never configured, and on that job search came to **31 to
36 % of the whole bill** while the decision layer came to 0.08 %. So on a harness that
searches, `Meter.cost()` understates the truth by whatever the per-request fees add up to,
and the model breakdown looks like somebody else's spending. Read the SDK's own
`model_usage` / `ResultMessage.total_cost_usd` beside this, and the organization's cost
report above both (`benchmarks/billed.py`).

`cache_read_input_tokens` sitting at zero across repeated calls with a shared prefix is the
expensive silent failure, so `summary()` reports it whether or not anyone asked.
"""

from __future__ import annotations

import json
import pathlib
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any

# Anthropic list prices, USD per million tokens (input, output).
# Checked against the vendor's model table on 2026-09-24.
PRICES: dict[str, tuple[float, float]] = {
    "claude-fable-5-1": (10.00, 50.00),
    "claude-fable-5": (10.00, 50.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-5-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
}
CACHE_READ = 0.10
CACHE_WRITE = {"5m": 1.25, "1h": 2.00}


class UnknownModel(KeyError):
    """Raised rather than guessing a price. A silent default is how a bill goes unnoticed."""


def price_of(model: str) -> tuple[float, float]:
    try:
        return PRICES[model]
    except KeyError as error:
        raise UnknownModel(
            f"no list price for {model!r}; add it to benchmarks/meter.py PRICES rather than "
            "letting a run report a cost computed from the wrong number"
        ) from error


@dataclass(slots=True)
class Usage:
    """Token counts, summed. Every field is reported by the API; none is inferred."""

    calls: int = 0
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    seconds: float = 0.0

    def add(self, usage: Any, seconds: float = 0.0) -> None:
        self.calls += 1
        self.input += getattr(usage, "input_tokens", 0) or 0
        self.output += getattr(usage, "output_tokens", 0) or 0
        self.cache_read += getattr(usage, "cache_read_input_tokens", 0) or 0
        self.cache_write += getattr(usage, "cache_creation_input_tokens", 0) or 0
        self.seconds += seconds

    def cost(self, model: str, *, cache_ttl: str = "5m") -> float:
        """List-price estimate. Cached reads at 0.1x, writes at the TTL's multiplier."""
        rate_in, rate_out = price_of(model)
        write = CACHE_WRITE[cache_ttl]
        return (
            self.input * rate_in
            + self.cache_read * rate_in * CACHE_READ
            + self.cache_write * rate_in * write
            + self.output * rate_out
        ) / 1_000_000

    def uncached_cost(self, model: str) -> float:
        """What the same tokens would have cost with no cache at all.

        The difference against `cost` is what the prompt cache is worth on this run. It is
        also the number that makes a zero in `cache_read` visible as money rather than as a
        field nobody read.
        """
        rate_in, rate_out = price_of(model)
        total_in = self.input + self.cache_read + self.cache_write
        return (total_in * rate_in + self.output * rate_out) / 1_000_000


class Meter:
    """Accumulates usage across calls, optionally appending one line per call to a ledger.

    Thread and coroutine safe for the accumulate-and-append pattern used by the benchmarks:
    a lock guards both the counters and the append, so concurrent workers cannot interleave.
    """

    def __init__(
        self,
        model: str,
        *,
        ledger: pathlib.Path | str | None = None,
        cache_ttl: str = "5m",
    ) -> None:
        price_of(model)  # fail now, not after spending
        if cache_ttl not in CACHE_WRITE:
            raise ValueError(f"cache_ttl must be one of {sorted(CACHE_WRITE)}")
        self.model = model
        self.cache_ttl = cache_ttl
        self.total = Usage()
        self.by_label: dict[str, Usage] = {}
        self._ledger = pathlib.Path(ledger) if ledger else None
        self._lock = threading.Lock()
        if self._ledger is not None:
            self._ledger.parent.mkdir(parents=True, exist_ok=True)

    def add(self, response: Any, *, label: str = "", seconds: float = 0.0) -> None:
        """Record one response. `label` groups calls, e.g. an arm name or a case id."""
        usage = getattr(response, "usage", None)
        if usage is None:
            raise ValueError("response carries no usage; nothing to meter")
        with self._lock:
            self.total.add(usage, seconds)
            group = self.by_label.setdefault(label, Usage())
            group.add(usage, seconds)
            if self._ledger is not None:
                row = {
                    "ts": time.time(),
                    "label": label,
                    "model": getattr(response, "model", self.model),
                    "input": getattr(usage, "input_tokens", 0) or 0,
                    "output": getattr(usage, "output_tokens", 0) or 0,
                    "cache_read": getattr(usage, "cache_read_input_tokens", 0) or 0,
                    "cache_write": getattr(usage, "cache_creation_input_tokens", 0) or 0,
                    "seconds": round(seconds, 3),
                }
                with self._ledger.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    @property
    def cost(self) -> float:
        return self.total.cost(self.model, cache_ttl=self.cache_ttl)

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "cache_ttl": self.cache_ttl,
            "cost_usd": round(self.cost, 6),
            "uncached_cost_usd": round(self.total.uncached_cost(self.model), 6),
            "usage": asdict(self.total),
            "by_label": {k: asdict(v) for k, v in sorted(self.by_label.items())},
        }

    def summary(self) -> str:
        """One block, always including the cache line, because a zero there is the bug."""
        u = self.total
        cost = self.cost
        uncached = u.uncached_cost(self.model)
        lines = [
            f"{u.calls} calls to {self.model}: {u.input:,} input, {u.output:,} output, "
            f"{u.cache_read:,} cached read, {u.cache_write:,} cached write",
            f"cost (list prices, client-side estimate): {cost:.4f} USD"
            + (f", {cost / u.calls * 1e6:.1f} millionths per call" if u.calls else ""),
        ]
        if u.cache_read or u.cache_write:
            saved = uncached - cost
            lines.append(
                f"without the cache the same tokens would be {uncached:.4f} USD: "
                f"the cache is worth {saved:.4f} USD here ({saved / uncached:.0%})"
            )
        elif u.calls > 1:
            lines.append(
                "cache_read_input_tokens is ZERO across every call. If these calls shared a "
                "prefix, something is invalidating it and the run is paying full price in "
                "silence."
            )
        return "\n".join(lines)

    def write(self, path: pathlib.Path | str) -> None:
        path = pathlib.Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.as_dict(), ensure_ascii=False, indent=1), encoding="utf-8")


# ---- Claude Code sessions: two price bases, transcripts, modelUsage ---------------------------
#
# Claude Code's `costUSD` and `--max-budget-usd` use its own table, which is not the owner's.
# Fitted exactly (residual < 1e-15) on 64 sessions each of the F1 gate (2026-10-05, 2.1.287):
# Sonnet 5.5 at 2/10 (cache read 0.2, 1-hour write 4) and Opus 5.5 at 4/20 (read 0.2, write 8);
# Haiku 4.5 on 35 phase-A sessions at 1/5. The owner meters Sonnet 5.5 at 3/15 and Opus 5.5 at
# 5/25 with reads at 0.1x and 1-hour writes at 2x (long-session prereg, decision 7).


@dataclass(frozen=True, slots=True)
class Rates:
    """USD per million tokens of each kind a request reports."""

    input: float
    output: float
    read: float
    write_5m: float
    write_1h: float

    @classmethod
    def listed(cls, rate_in: float, rate_out: float) -> Rates:
        """The vendor's rule: reads 0.1x input, writes 1.25x (5 minutes) or 2x (1 hour)."""
        return cls(rate_in, rate_out, rate_in * CACHE_READ, rate_in * CACHE_WRITE["5m"],
                   rate_in * CACHE_WRITE["1h"])  # fmt: skip


SONNET_55, OPUS_55, HAIKU_45 = "claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-4-5-20251001"
OWNER_RATES: dict[str, Rates] = {
    SONNET_55: Rates.listed(3.0, 15.0),
    OPUS_55: Rates.listed(5.0, 25.0),
    HAIKU_45: Rates.listed(1.0, 5.0),
}
CLAUDE_CODE_RATES: dict[str, Rates] = {
    SONNET_55: Rates(2.0, 10.0, 0.2, 2.5, 4.0),
    OPUS_55: Rates(4.0, 20.0, 0.2, 5.0, 8.0),
    HAIKU_45: Rates.listed(1.0, 5.0),
}


def rates_of(table: dict[str, Rates], model: str) -> Rates:
    try:
        return table[model]
    except KeyError as error:
        raise UnknownModel(f"no rates for {model!r} in this table; add them") from error


def claude_code_cap(owner_usd: float, model: str) -> float:
    """The `--max-budget-usd` that never lets a call pass `owner_usd` at the owner's prices:
    the owner cap times the lowest ratio of Claude Code's rate to the owner's over every token
    kind (pre-mortem h: "4.5" passed as is was 6.75 at 3/15 on Sonnet). Rounded down to cents."""
    cc, owner = rates_of(CLAUDE_CODE_RATES, model), rates_of(OWNER_RATES, model)
    kinds = ("input", "output", "read", "write_5m", "write_1h")
    ratio = min(getattr(cc, k) / getattr(owner, k) for k in kinds)
    return int(owner_usd * ratio * 100 + 1e-9) / 100


def model_usage_cost(model_usage: dict[str, Any], table: dict[str, Rates],
                     write: str = "write_1h") -> float:  # fmt: skip
    """A result's `modelUsage` (every model, subagents included) priced with `table`. It does
    not split writes by TTL: Claude Code writes 1-hour entries (every write of B2 was)."""
    total = 0.0
    for model, u in model_usage.items():
        r = rates_of(table, model)
        total += (int(u.get("inputTokens") or 0) * r.input
                  + int(u.get("outputTokens") or 0) * r.output
                  + int(u.get("cacheReadInputTokens") or 0) * r.read
                  + int(u.get("cacheCreationInputTokens") or 0) * getattr(r, write))  # fmt: skip
    return total / 1e6


@dataclass(frozen=True, slots=True)
class Request:
    """One API request of a session, as its transcript or stream reports it."""

    id: str
    model: str
    input: int
    output: int
    read: int
    write_5m: int
    write_1h: int
    sidechain: bool = False

    @property
    def context(self) -> int:
        """Tokens the request read: its whole prompt."""
        return self.input + self.read + self.write_5m + self.write_1h

    def cost(self, table: dict[str, Rates]) -> float:
        r = rates_of(table, self.model)
        return (self.input * r.input + self.output * r.output + self.read * r.read
                + self.write_5m * r.write_5m + self.write_1h * r.write_1h) / 1e6  # fmt: skip


def request_of(message: dict[str, Any], sidechain: bool = False) -> Request | None:
    usage = message.get("usage")
    if not isinstance(usage, dict) or not message.get("id"):
        return None
    written = int(usage.get("cache_creation_input_tokens") or 0)
    split = usage.get("cache_creation") or {}
    w5 = int(split.get("ephemeral_5m_input_tokens") or 0)
    w1 = int(split.get("ephemeral_1h_input_tokens") or 0)
    if w5 + w1 != written:  # no split reported: Claude Code's writes are 1-hour
        w5, w1 = 0, written
    return Request(str(message["id"]), str(message.get("model") or ""),
                   int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0),
                   int(usage.get("cache_read_input_tokens") or 0), w5, w1, sidechain)  # fmt: skip


def requests_in(lines: list[str]) -> tuple[Request, ...]:
    """Every request of a transcript or a stream-json, once: Claude Code writes one line per
    content block, each with the message's usage, so they are deduplicated by `message.id`
    (the last line wins). `<synthetic>` messages (no request made) are left out."""
    found: dict[str, Request] = {}
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict) or event.get("type") != "assistant":
            continue
        message = event.get("message")
        one = request_of(message, bool(event.get("isSidechain"))) if isinstance(message, dict) \
            else None  # fmt: skip
        if one is not None and one.model != "<synthetic>":
            found[one.id] = one
    return tuple(found.values())


def transcript_requests(path: pathlib.Path) -> tuple[Request, ...]:
    return requests_in(path.read_text(encoding="utf-8", errors="replace").splitlines())


def usage_delta(now: dict[str, Any], before: dict[str, Any]) -> dict[str, Any]:
    """A resumed session's `modelUsage` is its running total: this call's share, per model."""
    keys = ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens")
    return {m: {k: int(u.get(k) or 0) - int((before.get(m) or {}).get(k) or 0) for k in keys}
            for m, u in now.items()}  # fmt: skip


def reconcile(requests: tuple[Request, ...], model_usage: dict[str, Any],
              table: dict[str, Rates]) -> dict[str, Any]:  # fmt: skip
    """The requests a stream or transcript shows against what `modelUsage` counted for the same
    span. What modelUsage has and the requests do not (a headless compaction call, pre-mortem 7)
    is `unlogged`, priced as 1-hour writes; the total is the larger of the two per token kind."""
    seen = {"inputTokens": 0, "outputTokens": 0, "cacheReadInputTokens": 0,
            "cacheCreationInputTokens": 0}  # fmt: skip
    by_model: dict[str, dict[str, int]] = {}
    for r in requests:
        row = by_model.setdefault(r.model, dict(seen))
        for key, value in (("inputTokens", r.input), ("outputTokens", r.output),
                           ("cacheReadInputTokens", r.read),
                           ("cacheCreationInputTokens", r.write_5m + r.write_1h)):  # fmt: skip
            row[key] += value
    unlogged = {m: {k: max(int(u.get(k) or 0) - by_model.get(m, seen)[k], 0) for k in seen}
                for m, u in model_usage.items()}  # fmt: skip
    logged_usd = sum(r.cost(table) for r in requests)
    extra_usd = model_usage_cost(unlogged, table)
    missing = sorted(set(by_model) - set(model_usage))
    return {"logged_usd": round(logged_usd, 6), "unlogged_usd": round(extra_usd, 6),
            "total_usd": round(logged_usd + extra_usd, 6), "unlogged": unlogged,
            "models": sorted(set(by_model) | set(model_usage)),
            "not_in_model_usage": missing}  # fmt: skip


def first_write_flags(requests: tuple[Request, ...], over: int = 50_000) -> dict[str, Any]:
    """Pre-mortem 5: a resumed call whose first request writes more than `over` tokens rewrote
    the cached prefix (a pause past the cache's life, a changed prefix). Its first request's
    read and write, and whether it is flagged."""
    if not requests:
        return {"read": 0, "write": 0, "flagged": False}
    first = requests[0]
    written = first.write_5m + first.write_1h
    return {"read": first.read, "write": written, "flagged": written > over}


@dataclass(slots=True)
class Timed:
    """Context manager returning elapsed seconds, so `add(..., seconds=t.seconds)` is easy."""

    seconds: float = field(default=0.0)
    _start: float = field(default=0.0)

    def __enter__(self) -> Timed:
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_: object) -> None:
        self.seconds = time.perf_counter() - self._start
