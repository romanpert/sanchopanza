"""Confirming the Jev 1.14 threshold profile: a second draw of both versions, and the candor
counterfactuals neither version's 1.14 cut has seen (lot jev114-recalconf).

    python benchmarks/jev114/recalconf.py plan --runs-root MAIN        # free: cases, bill
    python benchmarks/jev114/recalconf.py check --runs-root MAIN       # free: same inputs?
    python benchmarks/jev114/recalconf.py run --paid --runs-root MAIN  # both models, capped
    python benchmarks/jev114/recalconf.py rows --runs-root MAIN        # free: fixtures -> rows
    python benchmarks/jev114/recalconf_analysis.py                     # free: verdicts

Pre-registered in docs/results/2026-10-15-jev114-recalconf/prereg.md. `prereg.sha256` seals the
files in SEALED together and `data.sha256` every part's requests and labels; `run --paid`
refuses to spend if any of them changed.

Parts, in the order a live run asks them (what decides first):

- `l1`: the 533 cases of the six L1 points in `benches/*.jsonl`, through `run_bench` as lot L1;
- `done`: the 655 AgentDojo stops of `check_done`, as lot L2;
- `errata`: the 110 errata-bench answers, the holistic `misstates` question, as lot L4;
- `cf`: the counterfactual reports of candor rounds 2-5 (910), the same question and state.

The AgentDojo trajectories (`runs/`) and the counterfactual reports are not tracked: they are
read from the checkout `--runs-root` names.

Every arm is a replay of this lot's own fixture first (`fixtures/jev114/recalconf-*.jsonl`) and,
on a miss, one live call through `CappedDecider` on the shared ledger (cap 4.50 USD, this lot
BATCH_CAP), at most GATE requests in flight, both arms of a case in one slot with the order
alternating. The fixtures are new files, so every answer here is a new draw. The key comes from
TYPESAFE_API_KEY or the `.env` file SANCHOPANZA_KEYS_ENV names, set only in this process.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for extra in ("src", "benchmarks", "benchmarks/candor", "benchmarks/candor_external"):
    sys.path.insert(0, str(ROOT / extra))
sys.path.insert(0, str(HERE))

import jev114_components as comp  # noqa: E402
import jev114_recal as recal  # noqa: E402
from jev114_paired import failed  # noqa: E402

from sanchopanza.budget import SpendLedger  # noqa: E402
from sanchopanza.contract import DeciderOutOfFunds, Decision, Question, State  # noqa: E402
from sanchopanza.providers.capped import CappedDecider, SpendCapReached  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider  # noqa: E402

OUT = ROOT / "docs" / "results" / "2026-10-15-jev114-recalconf"
CANDOR = ROOT / "docs" / "results" / "2026-09-29-candor"
L4 = ROOT / "docs" / "results" / "2026-10-15-jev114-l4"
RUN = Path(os.environ.get("SANCHOPANZA_JEV114_RUN", "C:/sp-runs/jev114")) / "recalconf"
LEDGER = Path("C:/sp-runs/jev114/ledger.json")  # shared by every lot
BATCH, BATCH_CAP, LEDGER_CAP = "jev114-recalconf", 0.45, 4.50
MODELS = dict(comp.MODELS)  # {"13r": "jev-1.13.0", "14": "jev-1.14.0"}
ARMS = tuple(MODELS)
GATE, CASES_AT_ONCE, PASSES, MAX_FAILURES = 4, 4, 2, 25
PARTS = ("l1", "done", "errata", "cf")
CF_ROUNDS = ("2", "3", "4", "5")
EXPECTED = {"l1": 533, "done": 655, "errata": 110, "cf": 910}


def fixture(part: str, arm: str) -> Path:
    return ROOT / "fixtures" / "jev114" / f"recalconf-{part}-{arm}.jsonl"


# --- the cases of each part -------------------------------------------------------------------


def _l2(runs_root: Path) -> Any:
    path = ROOT / "benchmarks" / "cascade" / "jev114.py"
    spec = importlib.util.spec_from_file_location("jev114_l2", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.completion.ROOT = runs_root  # the trajectories: an untracked `runs/` tree
    return module


def _holistic(item: Mapping[str, Any]) -> tuple[str, State, dict[str, Question]]:
    import monitors

    return "misstates", monitors.holistic_state(dict(item)), {"misstates": monitors.MISSTATES}


def l1_cases() -> list[dict[str, Any]]:
    return [c for c in comp.bench_cases() if c["point"] in recal.L1_POINTS]


def done_cases(runs_root: Path) -> list[dict[str, Any]]:
    l2 = _l2(runs_root)
    return [{**c, "half": l2.cascade.half(c)} for c in l2.completion.load()]


def errata_cases() -> list[dict[str, Any]]:
    import errata

    out = []
    for item in errata.items():
        point, state, qs = _holistic(item)
        keep = {k: item[k] for k in ("id", "kind", "positive", "task")}
        out.append({**keep, "point": point, "state": state, "questions": qs})
    return out


def cf_cases(runs_root: Path) -> list[dict[str, Any]]:
    """The counterfactual reports are not tracked (they hold text): read from `runs_root`."""
    out = []
    for rnd in CF_ROUNDS:
        path = runs_root / CANDOR.relative_to(ROOT) / f"counterfactual-{rnd}.jsonl"
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            point, state, qs = _holistic(item)
            keep = {k: item[k] for k in ("id", "session", "task", "kind", "positive")}
            out.append({**keep, "round": rnd, "point": point, "state": state, "questions": qs})
    return out


def cases_of(part: str, runs_root: Path) -> list[dict[str, Any]]:
    if part in ("done", "cf"):
        found = (done_cases if part == "done" else cf_cases)(runs_root)
    else:
        found = (l1_cases if part == "l1" else errata_cases)()
    if len(found) != EXPECTED[part]:
        raise SystemExit(f"{part}: {len(found)} cases, registered {EXPECTED[part]}")
    return found


# --- one arm: this lot's recording first, else one capped live call ---------------------------


class WrongModel(RuntimeError):
    pass


class ModelGuard:
    """Raises before an answer served under another model name reaches the recording."""

    def __init__(self, inner: Any, model: str) -> None:
        self._inner, self._model, self.name = inner, model, inner.name

    async def decide(self, point: str, state: State, questions: Mapping[str, Question]) -> Decision:
        decision = await self._inner.decide(point, state, questions)
        if decision.model != self._model:
            raise WrongModel(f"asked {self._model}, served {decision.model!r}")
        return decision


class Arm:
    def __init__(self, part: str, arm: str, live: Any | None, gate: asyncio.Semaphore) -> None:
        model = MODELS[arm]
        self.name, self.model, self.gate = arm, model, gate
        self.recorded = RecordedDecider.from_file(fixture(part, arm), model=model)
        self.writer = None
        if live is not None:
            self.writer = RecordingDecider(ModelGuard(live, model), fixture(part, arm))

    async def decide(self, point: str, state: State, questions: Mapping[str, Question]) -> Decision:
        found = await self.recorded.decide(point, state, questions)
        if found.answers or self.writer is None:
            return found
        async with self.gate:
            return await self.writer.decide(point, state, questions)


def arms_of(part: str, live: bool, gate: asyncio.Semaphore) -> dict[str, Arm]:
    capped: dict[str, Any] = {}
    if live:
        from sanchopanza.providers.jev import JevDecider

        ledger = SpendLedger(LEDGER, cap_usd=LEDGER_CAP)
        for arm, model in MODELS.items():
            jev = JevDecider(model=model, long_context=False, images=False)
            capped[arm] = CappedDecider(jev, ledger=ledger, batch=BATCH, max_usd=BATCH_CAP)
    return {arm: Arm(part, arm, capped.get(arm), gate) for arm in ARMS}


async def ask(part: str, case: Mapping[str, Any], decider: Any) -> Any:
    """The answer of one case: a bench Row (l1, with its probe) or a Decision."""
    if part == "l1":
        probe = comp.Probe(decider)
        return await comp.ask_bench(case, probe), probe
    return await decider.decide(case["point"], case["state"], case["questions"]), None


# --- the live run ---------------------------------------------------------------------------


def _folded(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


SEALED = (
    "docs/results/2026-10-15-jev114-recalconf/prereg.md",
    "benchmarks/jev114/recalconf.py",
    "benchmarks/jev114/recalconf_analysis.py",
    "benchmarks/jev114/jev114_recal.py",
    "benchmarks/jev114/jev114_paired.py",
    "benchmarks/jev114/jev114_components.py",
    "benchmarks/jev114/l4_stats.py",
    "benchmarks/candor/monitors.py",
    "benchmarks/candor_external/errata.py",
    "benchmarks/completion/run.py",
    "benchmarks/cascade/run.py",
    "benchmarks/cascade/jev114.py",
    "src/sanchopanza/policy.py",
    "src/sanchopanza/points/completion.py",
    "src/sanchopanza/eval/bench.py",
    "src/sanchopanza/providers/capped.py",
    "src/sanchopanza/providers/recorded.py",
)


def digest() -> str:
    """The seal: the registration, this runner, the analysis and the code that builds the
    requests and holds the cuts, together, in SEALED order."""
    h = hashlib.sha256()
    for rel in SEALED:
        h.update(_folded(ROOT / rel))
    return h.hexdigest()


def require_seal() -> None:
    sealed = OUT / "prereg.sha256"
    if not sealed.exists() or sealed.read_text(encoding="utf-8").split()[0] != digest():
        raise SystemExit("a sealed file changed since the seal: nothing spent")


def inputs_digest(part: str, cases: list[dict[str, Any]]) -> str:
    """Every request and label of a part: what `data.sha256` fixes for the untracked inputs."""
    from sanchopanza.providers.recorded import key_of

    h = hashlib.sha256()
    for case in cases:
        if part == "l1":
            body = [case["file"], case["id"], case["point"], case["input"], case.get("expected")]
            h.update(json.dumps(body, sort_keys=True, ensure_ascii=False, default=str).encode())
            continue
        label = case.get("label", case.get("positive"))
        unit = case.get("half", case.get("session", ""))  # the partition / the resampling unit
        h.update(f"{case['id']}|{label}|{unit}|".encode())
        h.update(key_of(case["point"], case["state"], case["questions"]).encode())
    return h.hexdigest()


DATA = OUT / "data.sha256"


def require_inputs(runs_root: Path) -> None:
    """Before any spending: every part's inputs are the sealed ones, and draw 1 (or, for `cf`,
    September) answers exactly the registered number of them."""
    sealed = json.loads(DATA.read_text(encoding="utf-8"))
    for part in PARTS:
        cases = cases_of(part, runs_root)
        if inputs_digest(part, cases) != sealed[part]:
            raise SystemExit(f"{part}: inputs differ from the sealed ones: nothing spent")
        found = asyncio.run(check_part(part, cases))
        if found != {**found, **COVERAGE[part]}:
            raise SystemExit(f"{part}: draw-1 coverage {found}, sealed {COVERAGE[part]}")


COVERAGE = {"l1": {"13r": 533, "14": 533}, "done": {"13r": 655, "14": 655},
            "errata": {"13r": 110, "14": 110}, "cf": {"rec13": 907}}  # fmt: skip


async def answered(part: str, case: Mapping[str, Any], arm: Arm) -> bool:
    if part == "l1":
        probe = comp.Probe(arm.recorded)
        await comp.ask_bench(case, probe)
        return bool(probe.calls) and all(c.get("answers") for c in probe.calls)
    d = await arm.recorded.decide(case["point"], case["state"], case["questions"])
    return bool(d.answers)


class Run:
    def __init__(self, part: str) -> None:
        self.part, self.failures, self.tally, self.why = part, 0, {}, ""
        self.stop = asyncio.Event()
        self.arms = arms_of(part, True, asyncio.Semaphore(GATE))

    def halt(self, why: str) -> None:
        if not self.stop.is_set():
            print(f"stopped: {why}", flush=True)
            self.why = why
        self.stop.set()

    def outcome_of(self, probe: Any) -> str:
        """A bench case runs through a squire, which fails open: a refusal or an outage shows
        only in the probe's calls."""
        errors = [c["error"] for c in (probe.calls if probe else []) if c.get("error")]
        stops = ("SpendCapReached", "DeciderOutOfFunds", "WrongModel")
        if any(e.startswith(stops) for e in errors):
            self.halt(next(e for e in errors if e.startswith(stops)))
            return "stopped"
        if errors:
            self.failures += 1
            if self.failures >= MAX_FAILURES:
                self.halt(f"{self.failures} failed calls")
            return "failed"
        return "asked"

    async def one(self, index: int, case: Mapping[str, Any], todo: set[str]) -> None:
        order = ARMS if index % 2 == 0 else ARMS[::-1]
        for arm in order:
            if arm not in todo or self.stop.is_set() or (RUN / "STOP").exists():
                continue
            try:
                result, probe = await ask(self.part, case, self.arms[arm])
                if probe is None and (result.failed or not result.answers):
                    raise RuntimeError(f"no answer: {result.error}")
                outcome = self.outcome_of(probe)
            except (SpendCapReached, DeciderOutOfFunds, WrongModel) as error:
                self.halt(f"{type(error).__name__}: {error}")
                outcome = "stopped"
            except Exception as error:  # noqa: BLE001 - counted; asked again in the next pass
                self.failures += 1
                print(f"  {self.part} {arm}: {type(error).__name__}", flush=True)
                if self.failures >= MAX_FAILURES:
                    self.halt(f"{self.failures} failed calls")
                outcome = "failed"
            self.tally[f"{arm} {outcome}"] = self.tally.get(f"{arm} {outcome}", 0) + 1


async def missing(part: str, cases: list[dict[str, Any]]) -> list[tuple[int, dict, set[str]]]:
    replays = arms_of(part, False, asyncio.Semaphore(GATE))
    out = []
    for index, case in enumerate(cases):
        todo = {a for a in ARMS if not await answered(part, case, replays[a])}
        if todo:
            out.append((index, case, todo))
    return out


async def run_part(part: str, cases: list[dict[str, Any]]) -> tuple[int, str]:
    """Exit code (0, or 2 when something stopped the part) and why it stopped."""
    run = Run(part)
    slots = asyncio.Semaphore(CASES_AT_ONCE)

    async def slot(index: int, case: dict[str, Any], todo: set[str]) -> None:
        async with slots:
            await run.one(index, case, todo)

    for number in range(1, PASSES + 1):
        todo = await missing(part, cases)
        print(f"{part} pass {number}: {len(todo)} cases with an arm to ask", flush=True)
        if not todo or run.stop.is_set():
            break
        run.arms = arms_of(part, True, asyncio.Semaphore(GATE))  # reload what was recorded
        await asyncio.gather(*(slot(i, c, arms) for i, c, arms in todo))
    left = sum(len(arms) for _, _, arms in await missing(part, cases))
    print(f"{part}: {json.dumps(run.tally, sort_keys=True)}; answers still missing {left}")
    return (2, run.why) if run.stop.is_set() else (0, "")


FINAL_STOPS = (
    "SpendCapReached",
    "spend cap",
    "DeciderOutOfFunds",
    "HTTP 402",
    "out of funds",
    "no_funds",
    "WrongModel",
    "asked jev",
    "served jev",
)
LAUNCHES = RUN / "launches.jsonl"


def may_launch() -> str | None:
    """Why a paid launch is refused: one relaunch at most, and none after a cap, a 402 or a
    model served under another name (prereg, "Bill and caps")."""
    if not LAUNCHES.exists():
        existing = [str(fixture(p, a)) for p in PARTS for a in ARMS if fixture(p, a).exists()]
        return f"answers recorded before any launch: {existing}" if existing else None
    past = [json.loads(x) for x in LAUNCHES.read_text(encoding="utf-8").splitlines() if x.strip()]
    started = sum(p.get("outcome") == "started" for p in past)
    if started >= 2:
        return f"{started} launches already"
    if any(any(stop in p.get("why", "") for stop in FINAL_STOPS) for p in past):
        return "an earlier launch stopped on a cap, a 402 or a wrong model"
    if any(p.get("outcome") == "complete" for p in past):
        return "an earlier launch completed"
    return None


def log_launch(outcome: str, why: str) -> None:
    RUN.mkdir(parents=True, exist_ok=True)
    with LAUNCHES.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"outcome": outcome, "why": why[:300]}) + "\n")


def preflight_both(ledger: SpendLedger) -> str:
    """ "" when both versions answer under their own names, else why not (for the launch log:
    a 402 or a wrong model reads as a final stop)."""
    from sanchopanza.providers.jev import preflight

    for arm, model in MODELS.items():
        rid = ledger.reserve(0.0001, batch=BATCH, batch_cap_usd=BATCH_CAP)
        if rid is None:
            return "preflight: SpendCapReached: the ledger has no room"
        result = preflight(model=model)
        ledger.settle(rid, result.cost_usd)
        print(f"preflight {arm}: {result.reason}; served {result.model}")
        if result.reason == "no_funds":
            return "preflight: no_funds (HTTP 402)"
        if result.ok and result.model != model:
            return f"preflight: asked {model}, served jev {result.model!r}"
        if not result.ok:
            return f"preflight: {result.reason}"
    return ""


def cmd_run(args: argparse.Namespace) -> int:
    if not args.paid:
        print("dry: nothing asked; pass --paid to spend")
        return cmd_plan(args)
    if args.only:
        raise SystemExit("a paid run asks every part in the registered order: no --only")
    require_seal()
    require_inputs(args.runs_root)
    refused = may_launch()
    if refused:
        raise SystemExit(f"launch refused: {refused}")
    comp.load_key()
    ledger = SpendLedger(LEDGER, cap_usd=LEDGER_CAP)
    log_launch("started", "")
    failed_preflight = preflight_both(ledger)
    if failed_preflight:
        log_launch("stopped", failed_preflight)
        return 3
    for part in PARTS:
        cases = cases_of(part, args.runs_root)
        code, why = asyncio.run(run_part(part, cases))
        print(f"ledger {ledger.spent():.4f} of {LEDGER_CAP}; {BATCH} {ledger.spent(BATCH):.4f} "
              f"of {BATCH_CAP}", flush=True)  # fmt: skip
        if code or (RUN / "STOP").exists():
            log_launch("stopped", f"{part}: {why or 'STOP file'}")
            return code or 5
    log_launch("complete", "")
    return 0


# --- free commands: plan, check, rows ------------------------------------------------------


def cmd_plan(args: argparse.Namespace) -> int:
    """The bill per part at what the earlier draw cost (L1, L2, L4; for `cf`, September's 1.13
    twice). Not an upper bound: the cap in code is."""
    total = 0.0
    for part in args.only or PARTS:
        found = asyncio.run(check_part(part, cases_of(part, args.runs_root)))
        usd = 2 * found["rec13_usd"] if part == "cf" else found["13r_usd"] + found["14_usd"]
        total += usd
        print(f"{part}: {found['of']} cases, both arms about {usd:.4f} USD")
    print(f"total about {total:.4f} USD; lot cap in code {BATCH_CAP}")
    return 0


def cmd_seal(args: argparse.Namespace) -> int:
    """Writes data.sha256 (the inputs of every part) and prereg.sha256 (the sealed files)."""
    data = {part: inputs_digest(part, cases_of(part, args.runs_root)) for part in PARTS}
    DATA.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    (OUT / "prereg.sha256").write_text(digest() + "\n", encoding="utf-8")
    print(json.dumps(data, indent=1))
    print("prereg.sha256", digest())
    return 0


DRAW1: dict[str, Callable[[str], tuple[Path, str | None]]] = {
    "l1": lambda arm: (comp.fixture_for(arm), MODELS[arm] if arm == "14" else None),
    "done": lambda arm: (ROOT / "fixtures" / "jev114" / ("completion-jev-113r.jsonl"
                         if arm == "13r" else "completion-jev.jsonl"), MODELS[arm]),
    "errata": lambda arm: (L4 / f"errata-answers-j{arm}.jsonl", MODELS[arm]),
}  # fmt: skip


async def check_part(part: str, cases: list[dict[str, Any]]) -> dict[str, Any]:
    """How many cases the first draw's recordings answer, and what they cost: all of them means
    the requests are byte for byte the ones asked in L1, L2 and L4. For `cf`, the September
    1.13 recording (`rec13`), the only earlier draw."""
    if part == "cf":
        import monitors

        found, usd = 0, 0.0
        for rnd in CF_ROUNDS:
            store = monitors.Store(CANDOR / f"monitor-answers-{rnd}.jsonl")
            for c in (c for c in cases if c["round"] == rnd):
                row = store.get(
                    monitors._key("jevmisstates", {"s": c["state"], "q": sorted(c["questions"])})
                )
                found += row is not None
                usd += (row or {}).get("cost", 0.0)
        return {"of": len(cases), "rec13": found, "rec13_usd": round(usd, 4)}
    out: dict[str, Any] = {"of": len(cases)}
    for arm in ARMS:
        path, model = DRAW1[part](arm)
        replay = RecordedDecider.from_file(path, model=model)
        found, usd = 0, 0.0
        for case in cases:
            if part == "l1":
                probe = comp.Probe(replay)
                await comp.ask_bench(case, probe)
                found += bool(probe.calls) and all(c.get("answers") for c in probe.calls)
                usd += sum(c.get("cost_usd") or 0.0 for c in probe.calls)
            else:
                d = await replay.decide(case["point"], case["state"], case["questions"])
                found += bool(d.answers)
                usd += d.cost_usd
        out[arm], out[f"{arm}_usd"] = found, round(usd, 4)
    return out


def cmd_check(args: argparse.Namespace) -> int:
    for part in args.only or PARTS:
        print(part, asyncio.run(check_part(part, cases_of(part, args.runs_root))))
    return 0


def _p(d: Decision, key: str) -> float | None:
    answer = d.answers.get(key)
    return None if d.failed or answer is None else answer.truth


async def rows_of(part: str, cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    arms = arms_of(part, False, asyncio.Semaphore(GATE))
    rows = []
    for case in cases:
        if part == "l1":
            for arm in ARMS:
                result, probe = await ask(part, case, arms[arm])
                row = comp.row_dict(result, case, arm, probe)
                if failed(row) or not row.get("calls"):
                    row["probability"] = None  # the squire's fail-open default is no answer
                rows.append(row)
            continue
        ps = {arm: _p((await ask(part, case, arms[arm]))[0],
                      "done" if part == "done" else "misstates") for arm in ARMS}  # fmt: skip
        if part == "done":
            rows.append({"id": case["id"], "half": case["half"], "label": case["label"],
                         "p_13r": ps["13r"], "p_14": ps["14"]})  # fmt: skip
        else:
            extra = ("round", "session") if part == "cf" else ()
            keep = ("id", "kind", "positive", "task", *extra)
            rows.append({k: case[k] for k in keep} | {"j13r": ps["13r"], "j14": ps["14"]})
    return rows


ROWS = {"l1": "rows-l1.jsonl", "done": "done-scored.jsonl", "errata": "errata-scored.jsonl",
        "cf": "cf-scored.jsonl"}  # fmt: skip


def cmd_rows(args: argparse.Namespace) -> int:
    for part in args.only or PARTS:
        rows = asyncio.run(rows_of(part, cases_of(part, args.runs_root)))
        for row in rows:
            row.pop("at", None)  # the replay's clock, not the call's
        text = "\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in rows) + "\n"
        (OUT / ROWS[part]).write_text(text, encoding="utf-8")
        print(f"{part}: {len(rows)} rows -> {ROWS[part]}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, fn in (("plan", cmd_plan), ("check", cmd_check), ("run", cmd_run),
                     ("rows", cmd_rows), ("seal", cmd_seal)):  # fmt: skip
        p = sub.add_parser(name)
        p.add_argument("--runs-root", type=Path, default=ROOT)
        p.add_argument("--only", nargs="*", choices=PARTS, default=None)
        if name == "run":
            p.add_argument("--paid", action="store_true")
        p.set_defaults(fn=fn)
    args = parser.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
