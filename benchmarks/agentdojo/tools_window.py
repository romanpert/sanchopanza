"""Does a tool window that follows the agent beat selecting once? Replayed on real trajectories.

    python benchmarks/agentdojo/tools_window.py --offline   # replay recordings only, free
    python benchmarks/agentdojo/tools_window.py             # records what is missing (~0.2 USD)

Run with the AgentDojo interpreter after `window_data.py --build`. Every decision goes
through `RecordingDecider` into `fixtures/tools-window.jsonl`, keyed by the hash of the state
and the questions, so a second run - and every policy variant below it - costs nothing, and a
policy change cannot be flattered by a new sample (method rule 9).

WHAT A MISS IS. At each ground-truth call the bench asks: was the group holding this tool in
the window when the agent needed it? If not, the agent had to find it itself - a tool search
round trip in a harness that offers one, a failed task in one that does not. The bench then
adds it (`ToolWindow.found`) and moves on, which is the search-fallback reading.

ARMS. Every window arm is the shipped `ToolWindow`, configured; none reimplements it.

    full          every group loaded, always. No misses by construction; the token ceiling.
    search        nothing preloaded: every group is a miss the first time it is used.
    once          the one-shot selection as it shipped on 2026-09-24 (full catalog on deferral).
    once+pre      the same, with the pre-registered prerequisites (`window_data.ALWAYS/REQUIRES`).
    turns+pre     once+pre, re-asked (append-only) on every new user turn.
    window+pre    turns+pre, plus `observe` after every tool result, scanned for injection.
    window-noscan window+pre without the injection scan. Same observe decisions, replayed.

SESSIONS. Each of the 97 tasks alone, and 40 sessions of three tasks from three different
suites (seed 7), which is the case the user asked about: the work changes under the agent.

COST MODEL, stated so it can be argued with. Sonnet 5 prices (2 / 10 USD per MTok, cached
read 0.1x, write 1.25x). A loaded schema is written once and read on every later request.
A miss is one extra request: the context so far read at cached price, plus 80 output tokens.
The context is 4,000 tokens of system and request plus the tool outputs so far at 3.5
characters per token plus the loaded schemas. Decisions are what the decider billed. The
dollar column is a model; the miss and token columns are counts.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import random
import sys
from dataclasses import dataclass
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "src"))
sys.path.insert(0, str(HERE.parents[1] / "benchmarks"))

from window_data import ALWAYS, OUT, catalog  # noqa: E402

FIXTURE = HERE.parents[1] / "fixtures" / "tools-window.jsonl"
SEED = 7
SESSIONS = 40
PRICE_IN, PRICE_OUT = 2.0e-6, 10.0e-6
READ, WRITE = 0.1, 1.25
BASE_CONTEXT = 4000
CHARS_PER_TOKEN = 3.5
MISS_OUTPUT = 80
MAX_RUN_USD = 0.45  # hard stop for a recording run; Roman's line is 0.50 without asking


@dataclass(frozen=True)
class Arm:
    name: str
    kind: str  # "full" | "search" | "window"
    prereq: bool = False
    wait: bool = False  # narrow even when the request defers (only with observe)
    turns: bool = False
    observe: bool = False
    scan: bool = True


ARMS = (
    Arm("full", "full"),
    Arm("search", "search"),
    Arm("once", "window"),
    Arm("once+pre", "window", prereq=True),
    Arm("turns+pre", "window", prereq=True, turns=True),
    Arm("window+pre", "window", prereq=True, wait=True, turns=True, observe=True),
    Arm("window-noscan", "window", prereq=True, wait=True, turns=True, observe=True, scan=False),
)


def decider(offline: bool) -> Any:
    from sanchopanza.providers import create
    from sanchopanza.providers.chain import FallbackDecider
    from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider

    recorded = RecordedDecider.from_file(FIXTURE)
    if offline:
        return recorded
    live = create("jev", api_key=os.environ.get("TYPESAFE_API_KEY"))
    return FallbackDecider([recorded, LiveSpend(RecordingDecider(live, FIXTURE))])


class LiveSpend:
    """Counts only what reaches the paid provider, and stops the run past the cap."""

    spent = 0.0

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.name = inner.name
        # The recording on disk is read once at start; without this, an arm that repeats an
        # earlier arm's question in the same run would pay for it again.
        self._memo: dict[str, Any] = {}

    async def decide(self, point: str, state: Any, questions: Any) -> Any:
        from sanchopanza.providers.recorded import key_of

        key = key_of(point, state, questions)
        if key in self._memo:
            return self._memo[key]
        if LiveSpend.spent > MAX_RUN_USD:
            raise SystemExit(f"live decision spend passed {MAX_RUN_USD} USD; stopped")
        decision = await self._inner.decide(point, state, questions)
        LiveSpend.spent += decision.cost_usd
        if not decision.failed:
            self._memo[key] = decision
        return decision


def sessions(trajs: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    single = [[t] for t in trajs]
    by_suite: dict[str, list[dict[str, Any]]] = {}
    for t in trajs:
        by_suite.setdefault(t["suite"], []).append(t)
    rng = random.Random(SEED)
    multi = []
    for _ in range(SESSIONS):
        suites = rng.sample(sorted(by_suite), 3)
        multi.append([rng.choice(by_suite[s]) for s in suites])
    return single + multi


class Ledger:
    """Tokens and dollars of one session under the cost model in the module docstring."""

    def __init__(self, sizes: dict[str, int], base_context: int = BASE_CONTEXT) -> None:
        self.sizes = sizes
        self.base_context = base_context
        self.loaded: set[str] = set()
        self.schema_usd = 0.0
        self.miss_usd = 0.0
        self.token_requests = 0  # sum over requests of schema tokens in context
        self.outputs_tokens = 0.0

    def load(self, groups: Any) -> None:
        for g in groups:
            if g not in self.loaded:
                self.loaded.add(g)
                self.schema_usd += self.sizes.get(g, 0) * PRICE_IN * WRITE

    def schema_tokens(self) -> int:
        return sum(self.sizes.get(g, 0) for g in self.loaded)

    def request(self) -> None:
        tokens = self.schema_tokens()
        self.token_requests += tokens
        self.schema_usd += tokens * PRICE_IN * READ

    def miss(self) -> None:
        context = self.base_context + self.outputs_tokens + self.schema_tokens()
        self.miss_usd += context * PRICE_IN * READ + MISS_OUTPUT * PRICE_OUT

    def read(self, text: str) -> None:
        self.outputs_tokens += len(text) / CHARS_PER_TOKEN


async def run_session(
    arm: Arm,
    tasks: list[dict[str, Any]],
    dec: Any,
    sizes: dict[str, int],
    base_context: int = BASE_CONTEXT,
) -> dict[str, Any]:
    from sanchopanza import MemoryJournal, Squire
    from sanchopanza.window import ToolWindow

    names = list(sizes)
    squire = Squire(dec, journal=MemoryJournal())
    squire._t = squire.thresholds.with_(max_decisions=10_000, max_usd=10.0)  # noqa: SLF001
    ledger = Ledger(sizes, base_context)
    window = None
    if arm.kind == "full":
        ledger.load(names)
    elif arm.kind == "search":
        if arm.prereq:
            ledger.load(ALWAYS)
    else:
        window = ToolWindow(
            squire,
            catalog(arm.prereq),
            always=ALWAYS if arm.prereq else (),
            wait_on_deferred=arm.wait,
            scan_untrusted=arm.scan,
        )
    held = lambda: set(window.window) if window else set(ledger.loaded)  # noqa: E731
    calls = misses = blocked = 0
    missed: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    for k, task in enumerate(tasks):
        if window is not None:
            if k == 0:
                ledger.load((await window.open(task["purpose"])).window)
            elif arm.turns:
                ledger.load((await window.observe(task["purpose"], trust="user")).window)
        for i, step in enumerate(task["steps"]):
            ledger.request()  # the request in which the agent decides this call
            calls += 1
            if step["group"] not in held():
                misses += 1
                ledger.miss()
                missed.append({"task": task["id"], "group": step["group"], "tool": step["tool"]})
                if window is not None:
                    window.found([step["group"]])
                    ledger.load(window.window)
                else:
                    ledger.load([step["group"]])
            ledger.read(step["output"])
            if window is not None and arm.observe:
                outside = set(sizes) - set(window.window)
                change = await window.observe(step["output"], trust="tool")
                blocked += change.blocked
                ledger.load(change.window)
                # The label, by construction: is the group called later in this same task?
                later = {s["group"] for s in task["steps"][i + 1 :]}
                observations.append(
                    {
                        "task": task["id"],
                        "step": i,
                        "probs": {g: p for g, p in change.probabilities.items() if g in outside},
                        "later": sorted(later & outside),
                        "added": list(change.added),
                    }
                )
        ledger.request()  # the final answer of the task
    used = {s["group"] for t in tasks for s in t["steps"]}
    final = held()
    return {
        "arm": arm.name,
        "session": "+".join(t["id"] for t in tasks),
        "tasks": len(tasks),
        "calls": calls,
        "misses": misses,
        "missed": missed,
        "blocked": blocked,
        "window": sorted(final),
        "unused": sorted(final - used),
        "schema_tokens_end": ledger.schema_tokens(),
        "token_requests": ledger.token_requests,
        "schema_usd": ledger.schema_usd,
        "miss_usd": ledger.miss_usd,
        "decision_usd": squire.meter.cost_usd,
        "decisions": squire.meter.decisions,
        "groups_needed": len(used),
        "observations": observations,
    }


def summarize(rows: list[dict[str, Any]], label: str) -> list[str]:
    lines = [
        f"### {label}",
        "",
        "| arm | sessions | calls | misses | sessions with a miss | groups held at end | "
        "of those unused | schema tok x req | USD schema | USD misses | USD decisions "
        "| USD total |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for arm in ARMS:
        r = [x for x in rows if x["arm"] == arm.name]
        if not r:
            continue
        n = len(r)
        tot = sum(x["schema_usd"] + x["miss_usd"] + x["decision_usd"] for x in r)
        lines.append(
            f"| {arm.name} | {n} | {sum(x['calls'] for x in r)} | {sum(x['misses'] for x in r)} | "
            f"{sum(1 for x in r if x['misses'])} | {sum(len(x['window']) for x in r) / n:.1f} | "
            f"{sum(len(x['unused']) for x in r) / n:.1f} | "
            f"{sum(x['token_requests'] for x in r) / n:,.0f} | "
            f"{sum(x['schema_usd'] for x in r):.4f} | {sum(x['miss_usd'] for x in r):.4f} | "
            f"{sum(x['decision_usd'] for x in r):.4f} | **{tot:.4f}** |"
        )
    return lines + [""]


async def main_async(offline: bool) -> int:
    trajs = json.loads((OUT / "trajectories.json").read_text(encoding="utf-8"))
    sizes = json.loads((OUT / "sizes.json").read_text(encoding="utf-8"))
    dec = decider(offline)
    rows = []
    for arm in ARMS:
        for tasks in sessions(trajs):
            rows.append(await run_session(arm, tasks, dec, sizes))
        print(f"  {arm.name}: done, live spend {LiveSpend.spent:.4f} USD", file=sys.stderr)
    # The counter rule: an arm that ran is not an arm that did what it is for. `search` must
    # miss on the first call of every session and `full` must never miss; if either does not,
    # the arms are wired to the wrong branch and every comparison below is meaningless.
    for r in rows:
        if r["arm"] == "search" and r["misses"] < r["groups_needed"]:
            raise SystemExit(f"search arm held a group it never found: {r['session']}")
        if r["arm"] == "full" and r["misses"]:
            raise SystemExit(f"full arm missed: {r['session']}")
    (OUT / "results.json").write_text(
        json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    single = [r for r in rows if r["tasks"] == 1]
    multi = [r for r in rows if r["tasks"] > 1]
    sweep = []
    for base in SWEEP:
        swept = []
        for arm in ARMS:
            for tasks in sessions(trajs):
                swept.append(await run_session(arm, tasks, dec, sizes, base))
        sweep.append((base, swept))
    text = "\n".join(
        summarize(single, "One task per session (97)")
        + summarize(multi, f"Three tasks per session, three suites ({SESSIONS}, seed {SEED})")
        + context_sweep(sweep)
        + derivation(single)
    )
    (OUT / "summary.md").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


SWEEP = (4_000, 20_000, 50_000)


def context_sweep(sweep: list[tuple[int, list[dict[str, Any]]]]) -> list[str]:
    """Total modelled USD per arm as the context at the moment of a miss grows."""
    head = (
        "| arm | "
        + " | ".join(f"{b // 1000}k single | {b // 1000}k multi" for b, _ in sweep)
        + " |"
    )
    lines = [
        "### Modelled USD as the base context grows (replayed; decisions unchanged)",
        "",
        head,
        "|---|" + "---|" * (2 * len(sweep)),
    ]
    for arm in ARMS:
        cells = []
        for _base, rows in sweep:
            for kind in (1, 3):
                r = [x for x in rows if x["arm"] == arm.name and x["tasks"] == kind]
                cells.append(
                    f"{sum(x['schema_usd'] + x['miss_usd'] + x['decision_usd'] for x in r):.3f}"
                )
        lines.append(f"| {arm.name} | " + " | ".join(cells) + " |")
    return lines + [""]


def _half(task_id: str) -> str:
    import hashlib

    return "derive" if hashlib.sha256(task_id.encode()).digest()[0] % 2 == 0 else "report"


def derivation(single: list[dict[str, Any]]) -> list[str]:
    """`window_add` from the observe answers: derived on one half of the tasks, reported on
    the other, at the most permissive threshold whose Wilson lower bound on precision clears
    the target. The label is by construction: the group is called later in the same task."""
    from thresholds import wilson_lower

    points: dict[str, list[tuple[float, bool]]] = {"derive": [], "report": []}
    for r in single:
        if r["arm"] != "window-noscan":
            continue
        for o in r["observations"]:
            for g, p in o["probs"].items():
                points[_half(o["task"])].append((p, g in o["later"]))

    def at(rows: list[tuple[float, bool]], cut: float) -> tuple[int, int, int]:
        acted = [y for p, y in rows if p >= cut]
        return len(acted), sum(acted), sum(y for _, y in rows)

    lines = [
        "### Deriving `window_add` (derive half / report half, by task id hash)",
        "",
        f"Observe answers: {len(points['derive'])} to derive on, {len(points['report'])} to "
        f"report on; positives {sum(y for _, y in points['derive'])} / "
        f"{sum(y for _, y in points['report'])}.",
        "",
        "| target | derived cut | report: added | of those needed later | precision | "
        "Wilson low | recall |",
        "|---|---|---|---|---|---|---|",
    ]
    for target in (0.5, 0.7, 0.8, 0.9):
        best = None
        for step in range(5, 100):
            cut = step / 100
            n, hits, pos = at(points["derive"], cut)
            if n and wilson_lower(hits, n) >= target:
                recall = hits / pos if pos else 0.0
                if best is None or recall > best[1]:
                    best = (cut, recall)
        if best is None:
            lines.append(f"| {target:.0%} | none clears it | | | | | |")
            continue
        n, hits, pos = at(points["report"], best[0])
        prec = hits / n if n else float("nan")
        lines.append(
            f"| {target:.0%} | {best[0]:.2f} | {n} | {hits} | {prec:.0%} | "
            f"{wilson_lower(hits, n):.0%} | {hits}/{pos} |"
        )
    return lines + [""]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--offline", action="store_true", help="replay recordings only; free")
    args = p.parse_args()
    return asyncio.run(main_async(args.offline))


if __name__ == "__main__":
    raise SystemExit(main())
