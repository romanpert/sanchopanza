"""Lot memgate-hook: the installed memory hook's long window, replayed on SWE-chat records.
Pre-registered (draft) in docs/results/2026-10-16-memgate-hook/prereg.md.

    python benchmarks/memgate_hook/memgate_hook.py --build         # free: items into the cache
    python benchmarks/memgate_hook/memgate_hook.py --dry           # free: calls, cost, power
    python benchmarks/memgate_hook/memgate_hook.py --seal          # seal prereg.md + code
    python benchmarks/memgate_hook/memgate_hook.py --smoke --live  # 4 requests, own sub-cap
    python benchmarks/memgate_hook/memgate_hook.py --run --live    # spends (caps in code)
    python benchmarks/memgate_hook/memgate_hook.py --run           # free: replay only
    python benchmarks/memgate_hook/memgate_hook.py                 # analysis, free

The library gate `memory_gate.gate` reads memories whole by default since the memgate-long
confirmation; the installed hook (`memory_hook`, `sanchopanza install`) stays on the short window
because it judges records of earlier requests, not memory files, and nothing measured the long
window there. This lot replays the hook's own recall at a session's first prompt
(`memory_hook.recall`, as installed: decider mode, `MEMORY_PROMPT=first`, the v5 name gate, the
shipped K, cut and character cap) on the first request of every later session of the three
SWE-chat sets of docs/results/2026-10-01-memory-real (`selection.json`, `-2`, `-3`), in two arms
on the same requests: `S`, nothing set (the hook's default, each candidate as its 880-character
page), and `L`, `SANCHOPANZA_MEMORY_WINDOW=long` (each candidate whole, `Episode.text()`). The
records, BM25's candidates, the gate and the labels (`lineage`/`file`/none, by code from the
transcripts) are the same in both arms; only the decider's reading differs.

Every live call goes through `CappedDecider` on this lot's own ledger (LEDGER_PATH) and caps,
wrapped in lot memgate-long's `StopDead` (a cap refusal ends the lot with the completed pairs;
an outage, a wrong model or 3 failed calls in a row is a pause that writes nothing). Answers
are recorded per arm in OUT (hashed keys, no text) by lot L4's recorded-first `Arm`; a relaunch
replays them free. Scored rows hold ids, record keys, labels, probabilities and what was shown:
no text. The record texts stay in the cache (CACHE). The key comes from TYPESAFE_API_KEY or the
`.env` that SANCHOPANZA_KEYS_ENV names, inside the process, never printed.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import os
import pathlib
import random
import sys
import tempfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
MEMORY_REAL = REPO / "benchmarks" / "memory_real"
for extra in (REPO / "src", MEMORY_REAL, HERE):
    sys.path.insert(0, str(extra))

# memory_real first: its `labels` module must be the one cached before lot L6 puts
# benchmarks/memory_gate (which has another `labels`) on the path. Every benchmark module is
# imported here, none inside a function, so a test can load this file and take them out again.
import build  # noqa: E402
import build_v4b  # noqa: E402
import memgate_hook_analysis as an  # noqa: E402
import replay_v5  # noqa: E402

sys.path.insert(0, str(REPO / "benchmarks" / "memgate_long"))
import memgate_long as mgl  # noqa: E402  (StopDead, halts, the seal's hashing; lot L4's Arm)

from sanchopanza.context import episodes as ep  # noqa: E402
from sanchopanza.harness import memory_hook as mh  # noqa: E402

l4 = mgl.l4

OUT = REPO / "docs" / "results" / "2026-10-16-memgate-hook"
CACHE = build.CACHE  # ~/.cache/sanchopanza/memory-real (SWE-chat transcripts, never the repo)
ITEMS = CACHE / "items-memgate-hook.jsonl"  # first requests only, every set; text: cache only
SELECTIONS = (
    build.OUT / "selection.json",
    build.OUT / "selection-2.json",
    build.OUT / "selection-3.json",
)
LEDGER_PATH = pathlib.Path("C:/sp-runs/memgate-hook/ledger.json")  # this lot's own ledger
LEDGER_CAP_USD = 0.60  # the whole lot, smoke included: 3x the dry estimate, under 1 USD
BATCH, BATCH_CAP_USD = "memgate-hook", 0.60
SMOKE_BATCH, SMOKE_CAP_USD = "memgate-hook-smoke", 0.05
SMOKE_REQUESTS = 4  # the first decided requests of the seeded order, out of the run
MODEL = mgl.MODEL  # jev-1.13.0, the production DEFAULT_MODEL and the installed hook's
ARMS = ("S", "L")
ORDER_SEED = 20261016
PAIR_EST_USD = 0.003  # a pair's soft-stop estimate (S + L + a fallback), pessimistic
MIN_REQUESTS = 30  # requests with a related candidate, for any verdict
RELATED = frozenset({"lineage", "file"})
MEDIAN_USD = 71e-6  # Jev's median billed request (owner's measure), the second estimate
TIMEOUT_S = 30.0
# Every variable the hook reads at a prompt: unset before each call, so the installed defaults
# apply, then the arm's own.
HOOK_VARS = ("MEMORY_WINDOW", "MEMORY_K", "MEMORY_KEEP_AT", "MEMORY_CHARS",
             "MEMORY_DECIDER_SECONDS", "MEMORY_PROMPT_NAMED", "MEMORY_SELECT", "MEMORY_PROMPT",
             "MEMORY_STORE", "MEMORY_STORE_LOG", "MEMORY_TREE", "MEMORY_STORE_KEY")  # fmt: skip


# ---- items ------------------------------------------------------------------------------------


def build_items(path: pathlib.Path = ITEMS) -> int:
    """Every later session's first request with a pool, from the three sets' groups, through
    `build_v4b.items_for` (labels as build.py). Free; written to the cache, never the repo."""
    n = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for selection in SELECTIONS:
            name = selection.stem
            for g in json.loads(selection.read_text(encoding="utf-8"))["groups"]:
                for item in build_v4b.items_for(g["sessions"], g["group"], g["split"]):
                    if item["first"] and item["pool"]:
                        row = {**item, "set": name, "cluster": f"{name}:{g['group']}"}
                        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                        n += 1
    return n


def load_items(path: pathlib.Path = ITEMS) -> list[dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"{path} is missing: run --build first (free)")
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        rows.append({**item, "pool": [ep.Episode.from_dict(d) for d in item["pool"]]})
    return rows


def item_id(item: Mapping[str, Any]) -> str:
    return f"{item['session']}-{item['index']:03d}"


def launch_order(items: Sequence[Mapping[str, Any]]) -> list[int]:
    """Indexes of `items` in a seeded order (ORDER_SEED) over their sorted ids."""
    ids = sorted(range(len(items)), key=lambda n: item_id(items[n]))
    random.Random(ORDER_SEED).shuffle(ids)
    return ids


def first_prompt(item: Mapping[str, Any]) -> str:
    """The session's first prompt whole, as UserPromptSubmit carries it (replay_v5's rule)."""
    return replay_v5.first_prompt(item["session"], item["request"])


# ---- one request through the installed hook ---------------------------------------------------


@contextlib.contextmanager
def hook_env(window: str, root: pathlib.Path, log: pathlib.Path) -> Iterator[None]:
    """The installed hook's environment for one arm: every HOOK_VARS unset (both spellings),
    then decider mode at a first prompt, the store under `root`, the log at `log`, no working
    tree (no cwd), and `MEMORY_WINDOW=long` for L only. Restored after."""
    names = [f"{p}{v}" for v in HOOK_VARS for p in ("SANCHOPANZA_", "SANCHO_")]
    saved = {k: os.environ.get(k) for k in names}
    for k in names:
        os.environ.pop(k, None)
    os.environ.update({"SANCHOPANZA_MEMORY_SELECT": "decider",
                       "SANCHOPANZA_MEMORY_PROMPT": "first",
                       "SANCHOPANZA_MEMORY_STORE": str(root / "store"),
                       "SANCHOPANZA_MEMORY_STORE_LOG": str(log),
                       "SANCHOPANZA_MEMORY_TREE": "off"})  # fmt: skip
    if window == "L":
        os.environ["SANCHOPANZA_MEMORY_WINDOW"] = "long"
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def prompt_row(log: pathlib.Path) -> dict[str, Any]:
    rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines() if x.strip()]
    found = [r for r in rows if r.get("event") == "UserPromptSubmit"]
    return found[-1] if found else {}


async def ask_hook(item: Mapping[str, Any], window: str, decider: Any, root: pathlib.Path,
                   prompt: str) -> dict[str, Any]:  # fmt: skip
    """`memory_hook.recall` on the item's first prompt, its pool saved as the store holds it,
    with a fresh squire on `decider` (as one hook process has; the run keeps one event loop so
    the client is shared). The hook's log row, reduced to what is scored: keys, probabilities,
    shown, window, no text."""
    from sanchopanza.redact import redact_secrets
    from sanchopanza.squire import Squire

    project = root / "projects" / f"g{item['group']}-{item['session'][:8]}"
    log = root / "logs" / f"{item_id(item)}-{window}.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with hook_env(window, root, log):
        store = mh.store_for({"transcript_path": str(project / "t.jsonl")})
        ep.save(store, item["pool"], keep_days=10_000)
        event = {"hook_event_name": "UserPromptSubmit", "session_id": item["session"],
                 "transcript_path": str(project / "absent.jsonl"), "cwd": "",
                 "prompt": prompt}  # fmt: skip
        squire = Squire(decider, redact=redact_secrets)
        await mh.recall(event, squire)
    row = prompt_row(log) if log.exists() else {}
    probabilities = row.get("probabilities")
    timed_out = "timed out" in str(row.get("reason", ""))  # asked, and the hook's time ran out
    out: dict[str, Any] = {
        "candidates": list(row.get("candidates") or []),
        "asked": probabilities is not None or timed_out,
        "probabilities": probabilities or {},
        "shown": list(row.get("shown") or []),
        "reason": row.get("reason", ""),
    }  # fmt: skip
    for key in ("window", "window_fallback", "long_usd", "long_header"):
        if key in row:
            out[key] = row[key] if key != "window_fallback" else _fallback_class(row[key])
    if "long_error" in row:
        out["long_error"] = str(row["long_error"]).split(":", 1)[0][:60]  # a class, no text
    return out


def _fallback_class(reason: str) -> str:
    """A fall back's cause as a short class, no text from the request."""
    for needle, name in (("over the long window", "too_long"), ("long-context mode", "no_mode"),
                         ("budget", "budget"), ("no time", "no_time"), ("took over", "late"),
                         ("answered nothing", "no_answer")):  # fmt: skip
        if needle in reason:
            return name
    return "other"


def score_row(item: Mapping[str, Any], arms: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """One request's scored row: ids, the candidates' labels, each arm's reduced row."""
    candidates = next((a["candidates"] for a in arms.values() if a["candidates"]), [])
    labels = {k: item["labels"].get(k, "none") for k in candidates}
    related_pool = any(v in RELATED for v in item["labels"].values())
    return {"id": item_id(item), "set": item["set"], "cluster": item["cluster"],
            "pool": len(item["pool"]), "related_in_pool": related_pool,
            "labels": labels, **{arm: dict(arms[arm]) for arm in arms}}  # fmt: skip


# ---- deciders ---------------------------------------------------------------------------------


class DryDecider:
    """Answers every question at 0.5 (under the hook's 0.8 cut: nothing enters, so no arm
    falls back) at no cost, and tallies each request: recorded already (free) or live, its
    size and its pessimistic estimate (`CappedDecider`'s, a token per three characters)."""

    name = "dry"
    accepts_attachments = False
    model = MODEL

    def __init__(self, tally: dict[str, Any], recorded: Any | None = None) -> None:
        self.tally, self.recorded = tally, recorded

    async def decide(self, point: str, state: Any, questions: Mapping[str, Any]) -> Any:
        from sanchopanza.answers import truth
        from sanchopanza.contract import Decision
        from sanchopanza.providers.capped import DEFAULT_PRICE_PER_MTOK, estimate_usd

        size = len(json.dumps({"state": state, "questions": {k: repr(q) for k, q in
                                                             questions.items()}},
                              ensure_ascii=False, default=str))  # fmt: skip
        known = self.recorded is not None and bool(
            (await self.recorded.decide(point, state, questions)).answers
        )
        t = self.tally
        t["calls"] = t.get("calls", 0) + 1
        t["recorded"] = t.get("recorded", 0) + known
        t["chars"] = [*t.get("chars", []), size]
        if not known:
            usd = estimate_usd(state, questions, price_per_mtok=DEFAULT_PRICE_PER_MTOK)
            t["estimate_usd"] = t.get("estimate_usd", 0.0) + usd
        answers = {k: truth(0.5) for k in questions}
        return Decision(point, answers, self.name, MODEL)


def jev_inner(arm: str) -> Any:
    from sanchopanza.providers.jev import JevDecider

    del arm  # the hook's long arm needs the header only past Jev's short window (`--dry`)
    return JevDecider(model=MODEL, long_context=False, images=False, timeout_s=TIMEOUT_S)


def arm_deciders(name: str, live: bool, batch: str, cap_usd: float,
                 make_inner: Callable[[str], Any] = jev_inner) -> dict[str, Any]:  # fmt: skip
    """One recorded-first `l4.Arm` per arm (answers in OUT), live through this lot's ledger and
    `cap_usd` on `batch` when `live`, each live call inside lot memgate-long's `StopDead`."""
    gate = asyncio.Semaphore(1)
    capped: dict[str, Any] = {}
    if live:
        from sanchopanza.budget import SpendLedger
        from sanchopanza.providers import CappedDecider

        ledger = SpendLedger(LEDGER_PATH, cap_usd=LEDGER_CAP_USD)
        for arm in ARMS:
            inner = CappedDecider(make_inner(arm), ledger=ledger, batch=batch, max_usd=cap_usd)
            capped[arm] = mgl.StopDead(inner, arm)
    return {arm: l4.Arm(arm, OUT / f"{name}-answers-{arm}.jsonl", MODEL, capped.get(arm), gate)
            for arm in ARMS}  # fmt: skip


def spent(batch: str | None = None) -> float:
    from sanchopanza.budget import SpendLedger

    if not LEDGER_PATH.exists():
        return 0.0
    return SpendLedger(LEDGER_PATH, cap_usd=LEDGER_CAP_USD).spent(batch)


def room(batch: str, cap_usd: float) -> float:
    return min(cap_usd - spent(batch), LEDGER_CAP_USD - spent())


# ---- the run ----------------------------------------------------------------------------------


async def run(items: Sequence[Mapping[str, Any]], deciders: Mapping[str, Any], *, live: bool,
              batch: str, cap_usd: float, root: pathlib.Path) -> list[dict[str, Any]]:  # fmt: skip
    """Every item in order, both arms back to back (S first at even positions, L first at odd).
    Live, a pair is not started when PAIR_EST_USD would not fit in the room left; a halt drops
    the pair it hit and ends the run."""
    mgl.reset()
    rows: list[dict[str, Any]] = []
    for position, item in enumerate(items):
        if live and room(batch, cap_usd) < PAIR_EST_USD:
            print(f"soft stop before request {position}: the cap would not hold", file=sys.stderr)
            break
        prompt = first_prompt(item)
        order = ARMS if position % 2 == 0 else ARMS[::-1]
        got = {arm: await ask_hook(item, arm, deciders[arm], root / arm, prompt) for arm in order}
        if mgl.HALTED:
            print(f"stopped at request {position}, dropped: {mgl.HALTED[0]}", file=sys.stderr)
            break
        rows = [*rows, score_row(item, {arm: got[arm] for arm in ARMS}) | {"rank": position}]
    return rows


def split_smoke(items: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    """(smoke, run): the first SMOKE_REQUESTS items of the seeded order the hook would ask
    (a candidate passes the name gate, free to check), and every other item in that order."""
    order = [items[n] for n in launch_order(items)]
    smoke: list[dict[str, Any]] = []
    for item in order:
        if len(smoke) == SMOKE_REQUESTS:
            break
        if would_ask(item):
            smoke = [*smoke, item]
    ids = {item_id(i) for i in smoke}
    return smoke, [i for i in order if item_id(i) not in ids]


def would_ask(item: Mapping[str, Any]) -> bool:
    """Free: BM25 proposes a candidate and one passes the v5 name gate (the hook asks then)."""
    from sanchopanza.redact import redact_secrets

    prompt = redact_secrets(first_prompt(item)).strip()
    found = mh.candidates(prompt, item["pool"], mh.K)
    folded = mh._fold(prompt)
    return bool(found) and any(mh.gate_passes(prompt, e, folded) for e in found)


# ---- dry --------------------------------------------------------------------------------------


def dry(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Free: both arms through the hook with `DryDecider` (recorded answers counted as free),
    the calls a live run would make, their size and cost, the populations and the power."""
    from sanchopanza.harness import memory_window as mw

    smoke, rest = split_smoke(items)
    tallies: dict[str, dict[str, Any]] = {arm: {} for arm in ARMS}
    recorded = {arm: l4.Arm(arm, OUT / f"run-answers-{arm}.jsonl", MODEL, None,
                            asyncio.Semaphore(1)).recorded for arm in ARMS}  # fmt: skip
    deciders = {arm: DryDecider(tallies[arm], recorded[arm]) for arm in ARMS}
    with tempfile.TemporaryDirectory() as tmp:
        rows = asyncio.run(run(rest, deciders, live=False, batch=BATCH, cap_usd=BATCH_CAP_USD,
                               root=pathlib.Path(tmp)))  # fmt: skip
    asked = [r for r in rows if r["S"]["asked"] or r["L"]["asked"]]
    with_related = [r for r in asked if any(v in RELATED for v in r["labels"].values())]
    out_arms = {}
    for arm in ARMS:
        t = tallies[arm]
        chars = sorted(t.get("chars", [0]))
        live_calls = t.get("calls", 0) - t.get("recorded", 0)
        out_arms[arm] = {
            "calls": t.get("calls", 0), "recorded_free": t.get("recorded", 0),
            "live_calls": live_calls, "chars_median": chars[len(chars) // 2],
            "chars_max": chars[-1],
            "over_short_window": sum(c > mw.SHORT_WINDOW_CHARS for c in chars),
            "estimate_usd_pessimistic": round(t.get("estimate_usd", 0.0), 4),
            "estimate_usd_at_median": round(live_calls * MEDIAN_USD, 4),
        }  # fmt: skip
    fallbacks = sum("window_fallback" in r["L"] for r in rows)
    expected = sum(max(a["estimate_usd_pessimistic"], a["estimate_usd_at_median"])
                   for a in out_arms.values())  # fmt: skip
    smoke_usd = expected / max(1, len(asked)) * SMOKE_REQUESTS
    return {
        "items": len(items), "smoke_requests": len(smoke), "run_requests": len(rest),
        "asked": len(asked), "asked_same_in_both_arms":
            all(r["S"]["asked"] == r["L"]["asked"] for r in rows),
        "candidates_same_in_both_arms":
            all(r["S"]["candidates"] == r["L"]["candidates"] for r in asked),
        "asked_with_related_candidate": len(with_related),
        "asked_without_related_candidate": len(asked) - len(with_related),
        "by_set": {s: sum(r["set"] == s for r in asked) for s in sorted({r["set"] for r in rows})},
        "arms": out_arms, "long_fallbacks_in_dry": fallbacks,
        "expected_usd": round(expected, 4), "smoke_expected_usd": round(smoke_usd, 4),
        "caps": {"ledger": LEDGER_CAP_USD, "batch": BATCH_CAP_USD, "smoke": SMOKE_CAP_USD},
        "ledger": str(LEDGER_PATH), "ledger_spent": round(spent(), 6),
        "power": an.power_table(len(with_related)),
        "sealed": seal_ok(),
    }  # fmt: skip


# ---- seal -------------------------------------------------------------------------------------

SEALED_FIXED = (
    "benchmarks/memgate_hook/memgate_hook.py", "benchmarks/memgate_hook/memgate_hook_analysis.py",
    "tests/test_memgate_hook.py", "benchmarks/memgate_long/memgate_long.py",
    "benchmarks/jev114/l4.py", "benchmarks/jev114/l4_stats.py", "benchmarks/jev114/l6.py",
    "benchmarks/memory_real/build.py", "benchmarks/memory_real/build_v4.py",
    "benchmarks/memory_real/build_v4b.py", "benchmarks/memory_real/labels.py",
    "benchmarks/memory_real/replay_v5.py", "benchmarks/memory_real/replay_v4b.py",
    "benchmarks/memory_real/replay_v4.py", "benchmarks/memory_real/score.py",
    "benchmarks/memory_real/variants_v4b.py",
    "docs/results/2026-10-01-memory-real/selection.json",
    "docs/results/2026-10-01-memory-real/selection-2.json",
    "docs/results/2026-10-01-memory-real/selection-3.json",
)  # fmt: skip
SEALED_GLOBS = ("src/sanchopanza/**/*.py",)
# Built from the cached SWE-chat transcripts (not redistributed), hashed under the home folder.
SEALED_DATA = (".cache/sanchopanza/memory-real/items-memgate-hook.jsonl",)


def sealed_paths() -> tuple[str, ...]:
    found = {p.relative_to(REPO).as_posix() for g in SEALED_GLOBS for p in REPO.glob(g)
             if "__pycache__" not in p.parts}  # fmt: skip
    return (*SEALED_FIXED, *sorted(found - set(SEALED_FIXED)))


def manifest() -> dict[str, str]:
    def digest(path: pathlib.Path, text: bool) -> str:
        data = path.read_bytes()
        return hashlib.sha256(data.replace(b"\r\n", b"\n") if text else data).hexdigest()

    doc = (OUT / "prereg.md").relative_to(REPO).as_posix()
    out = {p: digest(REPO / p, True) for p in (doc, *sealed_paths())}
    return out | {f"~/{p}": digest(pathlib.Path.home() / p, False) for p in SEALED_DATA}


def seal(again: bool = False) -> str:
    """prereg.manifest.json and prereg.sha256 (memgate-long's scheme). A different seal there is
    refused unless `again`, and `again` is refused once this lot spent or recorded anything."""
    found = manifest()
    value = mgl.l6.combined(found)
    target = OUT / "prereg.sha256"
    if target.exists() and target.read_text().strip() not in ("", value) and not again:
        raise SystemExit("prereg.sha256 already holds another seal: nothing written")
    if again and (spent() > 0 or any(OUT.glob("*-answers-*.jsonl"))):
        raise SystemExit("answers or spend exist already: no re-seal, nothing written")
    (OUT / "prereg.manifest.json").write_text(json.dumps(found, indent=1) + "\n",
                                              encoding="utf-8", newline="\n")  # fmt: skip
    target.write_text(value + "\n", encoding="utf-8", newline="\n")
    return value


def seal_ok() -> bool:
    target = OUT / "prereg.sha256"
    if not target.exists():
        return False
    try:
        return target.read_text().strip() == mgl.l6.combined(manifest())
    except OSError:
        return False


# ---- live -------------------------------------------------------------------------------------


def go_live() -> None:
    if not seal_ok():
        raise SystemExit("prereg.md, the code or the inputs differ from the seal: nothing spent")
    l4.load_key()
    mgl.no_retry_on_429()
    mgl.preflight_or_stop()


def write_rows(name: str, rows: list[dict[str, Any]]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}-scored.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows),
                                              encoding="utf-8", newline="\n")  # fmt: skip


def read_rows(name: str) -> list[dict[str, Any]] | None:
    path = OUT / f"{name}-scored.jsonl"
    if not path.exists():
        return None
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]


def finish(name: str, rows: list[dict[str, Any]], batch: str, cap_usd: float) -> int:
    """memgate-long's rule: a pause (or a cap refusal with room left: a ledger fault) writes
    nothing and exits 2; a cap stop writes the completed pairs; no rows, nothing written."""
    kind = mgl.halt_kind()
    if kind == mgl.CAP and room(batch, cap_usd) >= PAIR_EST_USD:
        print(f"{name}: PAUSE, the ledger refused with room left: {mgl.HALTED[0]}",
              file=sys.stderr)  # fmt: skip
        return 2
    if kind == mgl.PAUSE:
        print(f"{name}: PAUSE, rows not written: {mgl.HALTED[0]}", file=sys.stderr)
        return 2
    if not rows:
        print(f"{name}: no request completed, nothing written", file=sys.stderr)
        return 2
    write_rows(name, rows)
    return 0


def execute(name: str, items: list[dict[str, Any]], *, live: bool, batch: str,
            cap_usd: float) -> list[dict[str, Any]]:  # fmt: skip
    async def both() -> list[dict[str, Any]]:  # one loop: the arms' clients live in it
        deciders = arm_deciders(name, live, batch, cap_usd)
        with tempfile.TemporaryDirectory() as tmp:
            return await run(items, deciders, live=live, batch=batch, cap_usd=cap_usd,
                             root=pathlib.Path(tmp))  # fmt: skip

    return asyncio.run(both())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true", help="free: items into the cache")
    parser.add_argument("--dry", "--plan", action="store_true", help="free: calls and cost")
    parser.add_argument("--run", action="store_true", help="ask (replay first) and score")
    parser.add_argument("--live", action="store_true", help="ask Jev what is not recorded")
    parser.add_argument("--smoke", action="store_true", help="the smoke's requests only")
    parser.add_argument("--seal", action="store_true", help="seal prereg.md and the code")
    parser.add_argument("--reseal", action="store_true", help="with --seal: replace a seal")
    args = parser.parse_args(argv)
    if args.build:
        print(f"{build_items()} first requests written to the cache", file=sys.stderr)
        return 0
    if args.seal:
        print(seal(again=args.reseal))
        return 0
    if args.dry:
        print(json.dumps(dry(load_items()), indent=1))
        return 0
    smoke_items, run_items = split_smoke(load_items())
    if args.smoke:
        if args.live:
            go_live()
        rows = execute("smoke", smoke_items, live=args.live, batch=SMOKE_BATCH,
                       cap_usd=SMOKE_CAP_USD)  # fmt: skip
        return finish("smoke", rows, SMOKE_BATCH, SMOKE_CAP_USD)
    if args.run:
        if args.live and read_rows("run") is not None:
            print("run: scored already, frozen: not asked again", file=sys.stderr)
        elif args.live:
            go_live()
            rows = execute("run", run_items, live=True, batch=BATCH, cap_usd=BATCH_CAP_USD)
            if finish("run", rows, BATCH, BATCH_CAP_USD):
                return 2
        else:
            done = read_rows("run")
            todo = run_items if done is None else run_items[: len(done)]
            rows = execute("run", todo, live=False, batch=BATCH, cap_usd=BATCH_CAP_USD)
            write_rows("replay" if done is None else "run", rows)
    return analyse_and_write()


def analyse_and_write() -> int:
    rows = read_rows("run")
    if rows is None:
        print("no run-scored.jsonl yet: nothing to analyse", file=sys.stderr)
        return 0
    summary = an.analyse(rows, min_requests=MIN_REQUESTS)
    summary["spent"] = {"batch": round(spent(BATCH), 6), "smoke": round(spent(SMOKE_BATCH), 6),
                        "ledger": round(spent(), 6)}  # fmt: skip
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8",
                                      newline="\n")  # fmt: skip
    print(json.dumps(summary["verdict"], indent=1), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
