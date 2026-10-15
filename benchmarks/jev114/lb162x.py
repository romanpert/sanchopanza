"""Lot lb162x: the expensive model in clean Claude Code (arm N) where lot lb162 did not run it,
with Jev 1.14's lb162 answers reused as recorded (no Jev call). Pre-registered in
docs/results/2026-10-16-lb162x/prereg.md; analysis in lb162x_stats.py; the paid driver (both
phases, one process) is benchmarks/h2h/h2h_lb162x.py.

- Phase B (first, the primary verdict): Opus 5.5 on all 162 tasks in a seeded random order.
- Phase A: Sonnet 5.5 on the 102 tasks Jev did not cover at 0.6, in a seeded random order.

    python benchmarks/jev114/lb162x.py --freeze-ids   # free: both orders (refuses to overwrite)
    python benchmarks/jev114/lb162x.py --dry          # free: tasks, cost, money rule, clock, power
    python benchmarks/jev114/lb162x.py --seal         # seal prereg.md + code + inputs
    python benchmarks/jev114/lb162x.py                # free: the analysis, summary.json

Money (enforced in the driver): each phase never passes its ceiling. Before each session the
driver gives it the cap `cap_for(spent, phase)`: the phase's full cap while the full cap plus one
worst turn fits under the ceiling, lowered to what is left after one worst turn when it does
not, and no session below the phase's floor (the phase stops, kind `ceiling`).
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import math
import pathlib
import random
import statistics
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
for extra in ("src", "benchmarks", "benchmarks/h2h"):
    sys.path.insert(0, str(REPO / extra))
sys.path.insert(0, str(HERE))

import b3conf_power as power  # noqa: E402
import lb162  # noqa: E402  (lot lb162: its tasks, rows, seal helpers and money constants)
import lb162x_stats as stats  # noqa: E402
import meter  # noqa: E402  (Claude Code's own price table)

OUT = REPO / "docs" / "results" / "2026-10-16-lb162x"
RUN_DIR = pathlib.Path("C:/sp-runs/lb162x")
SUMMARY = OUT / "summary.json"
ORDER_SEED = 20261016
N_TASKS, N_COVERED, N_UNCOVERED = 162, 60, 102
# lb162's recordings as committed (sha256 of their LF bytes): any difference refuses the lot.
RECORDED = {
    lb162.JEV_ROWS: "7a48cea771d3c547629d63f4230bea9f039ce93e9bb8d8487155f62d83eaa87f",
    lb162.COVERED_FILE: "4771d5744385fc6c6047b87be6fa6918c8c07ba907fe2ddb5c70a9831d38fc23",
    lb162.SONNET_ROWS: "b393b8cc41aff5bd769e776780d00a2e981f6f57fee489eb737d428de943f596",
}
FINAL = ("done", "ceiling")
MC_DRAWS = 5_000
MC_SEED = 20261016
POWER_DRAWS = 2_000


# ---- money ------------------------------------------------------------------------------------


def worst_turn_usd(model_id: str) -> float:
    """One turn rewriting the whole 1M-token window to the cache (the dearer write rate) and
    answering 32,000 tokens, at Claude Code's own rates (lb162's rule, any model)."""
    rates = meter.rates_of(meter.CLAUDE_CODE_RATES, model_id)
    write = max(rates.write_5m, rates.write_1h)
    window, out = lb162.SONNET_WINDOW_TOKENS, lb162.MAX_OUTPUT_TOKENS
    return round((window * write + out * rates.output) / 1e6, 4)


def rate_ratio(model_id: str, base_id: str) -> float:
    """The highest ratio of Claude Code's rate for `model_id` to `base_id`'s over every token
    kind: the same tokens cost at most this many times as much."""
    a = meter.rates_of(meter.CLAUDE_CODE_RATES, model_id)
    b = meter.rates_of(meter.CLAUDE_CODE_RATES, base_id)
    kinds = ("input", "output", "read", "write_5m", "write_1h")
    return max(getattr(a, k) / getattr(b, k) for k in kinds)


# Opus 5.5 has no LongBench session on record: its cost a task is planned as Sonnet's lb162 cost
# times this (2.0: input, output and cache writes are twice Sonnet's, reads equal).
OPUS_SCALE = rate_ratio(meter.OPUS_55, meter.SONNET_55)


@dataclass(frozen=True)
class Phase:
    """One phase of the lot: its model, tasks, money and files."""

    key: str
    name: str  # the session phase: private folder ~/.cache/sanchopanza/longdoc/h2h/<name>
    model: str  # h2h_gaia.MODELS key
    model_id: str
    ids_file: pathlib.Path
    n: int
    ceiling: float
    full_cap: float
    floor: float
    wall_mean_s: float  # the clock rule's mean session
    cost_scale: float  # the plan's cost a task: lb162's Sonnet sessions by band times this
    rows: pathlib.Path
    stop: pathlib.Path

    @property
    def arm(self) -> str:
        return f"{self.model}-CC"

    @property
    def worst_turn(self) -> float:
        return worst_turn_usd(self.model_id)

    @property
    def loop_reserve(self) -> float:
        """The phase loop's own check (browse/phase.py stops when spent + this > the ceiling):
        the floor cap plus one worst turn, the same line as `cap_for` returning None."""
        return round(self.floor + self.worst_turn, 4)


PHASE_B = Phase("B", "lb162x-opus", "OPUS", meter.OPUS_55, OUT / "opus-ids.txt", N_TASKS,
                ceiling=45.00, full_cap=stats.OPUS_FULL_CAP_USD, floor=1.00, wall_mean_s=60.0,
                cost_scale=OPUS_SCALE, rows=OUT / "opus-rows.jsonl",
                stop=OUT / "opus-stop.json")  # fmt: skip
PHASE_A = Phase("A", "lb162x-sonnet", "SONNET", meter.SONNET_55, OUT / "uncovered-ids.txt",
                N_UNCOVERED, ceiling=16.00, full_cap=stats.SONNET_FULL_CAP_USD, floor=0.50,
                wall_mean_s=38.0, cost_scale=1.0, rows=OUT / "sonnet-rows.jsonl",
                stop=OUT / "sonnet-stop.json")  # fmt: skip
ORDER = (PHASE_B, PHASE_A)  # B first: it carries the primary verdict
PHASES = {p.key: p for p in ORDER}


def cap_for(spent: float, phase: Phase) -> float | None:
    """The next session's --max-budget-usd: the full cap while cap + one worst turn fits under
    the ceiling, else what is left after the worst turn (down to the cent); None below the
    floor, which stops the phase (kind `ceiling`)."""
    room = math.floor(round((phase.ceiling - spent - phase.worst_turn) * 100, 6)) / 100
    cap = min(phase.full_cap, room)
    return cap if cap >= phase.floor else None


def sessions_until_stop(phase: Phase, cost: Any, n: int | None = None) -> int:
    """Sessions the money rule runs when session k costs `cost(cap)` (cut at cap + worst turn),
    up to `n`."""
    spent, ran = 0.0, 0
    while n is None or ran < n:
        cap = cap_for(spent, phase)
        if cap is None:
            break
        spent += min(cost(cap), cap + phase.worst_turn)
        ran += 1
    return ran


def guaranteed(phase: Phase) -> int:
    """At worst (every session at its cap plus one worst turn) the ceiling still runs this many."""
    return sessions_until_stop(phase, lambda cap: cap + phase.worst_turn)


def at_mean(phase: Phase, mean: float, n: int | None = None) -> int:
    """Sessions run when every session costs `mean` (at most its cap)."""
    return sessions_until_stop(phase, lambda cap: min(mean, cap), n)


# ---- lb162's recordings and the two orders ----------------------------------------------------


def recorded_problems() -> list[str]:
    """Empty when lb162's recordings are the committed ones and agree with each other."""
    found = [f"{p.name} is not lb162's recording" for p, sha in RECORDED.items()
             if not p.exists() or lb162.digest(p) != sha]  # fmt: skip
    if found:
        return found
    rows = lb162.read_jsonl(lb162.JEV_ROWS) or []
    if why := lb162.phase_j_final(rows, None):
        found.append(why)
    if [r["id"] for r in rows] != lb162.frozen_ids():
        found.append("lb162's rows are not its frozen ids")
    if lb162.read_ids(lb162.COVERED_FILE) != lb162.covered(rows):
        found.append("lb162's covered-ids.txt is not the derivation of its rows")
    counts = (len(lb162.covered(rows)), len(uncovered(rows)))
    if counts != (N_COVERED, N_UNCOVERED):
        found.append(f"{counts[0]} covered and {counts[1]} uncovered, expected 60 and 102")
    return found


def jev_rows() -> list[dict[str, Any]]:
    if found := recorded_problems():
        raise SystemExit("; ".join(found))
    return lb162.read_jsonl(lb162.JEV_ROWS) or []


def replay_problems() -> list[str]:  # pragma: no cover - needs the 465 MB cache
    """Free: a replay of lb162's recorded Jev answers gives its rows exactly (no call made)."""
    rows = asyncio.run(lb162.run_j(lb162.load_tasks(), None, lb162.ANSWERS,
                                   lb162.Stop(max_consecutive=None)))  # fmt: skip
    same = json.dumps(rows) == json.dumps(lb162.read_jsonl(lb162.JEV_ROWS))
    return [] if same else ["a replay of lb162's Jev answers does not give jev-scored.jsonl"]


def shuffled(ids: Sequence[str], seed: int = ORDER_SEED) -> list[str]:
    out = sorted(ids)
    random.Random(seed).shuffle(out)
    return out


def uncovered(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Phase A: lb162's asked tasks Jev did not cover at its cut, in the seeded order."""
    return shuffled([r["id"] for r in stats.lbs.asked(rows) if not stats.lbs.is_covered(r)])


def every_task(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Phase B: all of lb162's asked tasks, in the seeded order."""
    return shuffled([r["id"] for r in stats.lbs.asked(rows)])


def derive(phase: Phase, rows: Sequence[Mapping[str, Any]]) -> list[str]:
    return every_task(rows) if phase.key == "B" else uncovered(rows)


HEADS = {
    "B": "phase B: all {n} lb162 tasks",
    "A": "phase A: the {n} lb162 tasks Jev 1.14 did not cover at 0.6",
}


def freeze_ids() -> dict[str, str]:
    """Write each phase's order once; an existing file is left as it is (checked on read)."""
    rows = jev_rows()
    out = {}
    for phase in ORDER:
        if phase.ids_file.exists():
            out[phase.ids_file.name] = "frozen already"
            continue
        ids = derive(phase, rows)
        head = (f"# lot lb162x {HEADS[phase.key].format(n=len(ids))}, in "
                f"random.Random({ORDER_SEED}).shuffle order of the sorted ids")  # fmt: skip
        phase.ids_file.parent.mkdir(parents=True, exist_ok=True)
        phase.ids_file.write_text(head + "\n" + "".join(f"{i}\n" for i in ids), encoding="utf-8",
                                  newline="\n")  # fmt: skip
        out[phase.ids_file.name] = lb162.digest(phase.ids_file)
    return out


def frozen_order(phase: Phase, rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """The frozen file, refused unless it is the derivation of lb162's rows."""
    ids = lb162.read_ids(phase.ids_file)
    if ids != derive(phase, rows) or len(ids) != phase.n:
        raise SystemExit(f"{phase.ids_file.name} is missing or not the derivation of lb162's rows")
    return ids


# ---- the plan ---------------------------------------------------------------------------------


def costs_by_band(rows: Sequence[Mapping[str, Any]],
                  sonnet: Sequence[Mapping[str, Any]]) -> dict[str, list[float]]:  # fmt: skip
    """lb162's real Sonnet session costs, by the LongBench length band of their task."""
    band = {r["id"]: r["length"] for r in rows}
    out: dict[str, list[float]] = {}
    for s in sonnet:
        out.setdefault(band[s["id"]], []).append(float(s["usd"]))
    return out


def simulate(
    phase: Phase,
    bands: Sequence[str],
    costs: Mapping[str, Sequence[float]],
    scale: float = 1.0,
    draws: int = MC_DRAWS,
    seed: int = MC_SEED,
) -> dict[str, Any]:
    """The driver's money rule on `bands` (the frozen order), each session's cost drawn from
    `costs` of its band times the phase's scale times `scale`, a session past its cap cut at the
    cap."""
    rng = random.Random(seed)
    ran, spent_all, reduced = [], [], 0
    for _ in range(draws):
        spent, n = 0.0, 0
        for band in bands:
            cap = cap_for(spent, phase)
            if cap is None:
                break
            reduced += cap < phase.full_cap
            spent += min(rng.choice(costs[band]) * phase.cost_scale * scale, cap)
            n += 1
        ran.append(n)
        spent_all.append(spent)
    ran.sort()
    spent_all.sort()
    return {"scale": scale, "p_all": round(sum(x == len(bands) for x in ran) / draws, 3),
            "mean_sessions": round(statistics.mean(ran), 1), "p5_sessions": ran[draws // 20],
            "mean_usd": round(statistics.mean(spent_all), 2),
            "p95_usd": round(spent_all[draws * 19 // 20], 2),
            "reduced_cap_sessions_per_run": round(reduced / draws, 1)}  # fmt: skip


def opus_grade(rng: random.Random, jev_ok: bool, p: float, correlated: bool) -> bool:
    """One simulated Opus grade on a covered task with accuracy `p`: independent of Jev, or
    with lb162's Sonnet-Jev agreement on the covered (Sonnet right on 23 of the 31 Jev got and
    on 6 of the 29 it missed) shifted to reach `p`."""
    if not correlated:
        return rng.random() < p
    shift = p - 29 / 60
    return rng.random() < min(1.0, max(0.0, (23 / 31 if jev_ok else 6 / 29) + shift))


ACCURACIES = (0.5, 0.6, 0.65, 0.7, 0.75)


def power_b(rows: Sequence[Mapping[str, Any]], accuracies: Sequence[float] = ACCURACIES,
            draws: int = POWER_DRAWS, seed: int = MC_SEED) -> dict[str, Any]:  # fmt: skip
    """Chance of each verdict for phase B when Opus is right on a share `p` of the covered tasks
    (Jev's recorded grades fixed), every task with a session, from b3conf_power's normal CI."""
    asked = stats.lbs.asked(rows)
    cov = [(stats.lbs.is_covered(r), stats.lbs.jev_right(r)) for r in asked]
    out = {}
    for correlated in (True, False):
        rng = random.Random(seed)
        for p in accuracies:
            no_peor = peor = 0
            for _ in range(draws):
                sample = [power.Row(c, j, opus_grade(rng, j, p, correlated) if c else False, 0.0,
                                    0.0) for c, j in cov]  # fmt: skip
                _, lo, hi = power.paired_ci(sample)
                no_peor += lo > stats.MARGIN
                peor += hi < stats.MARGIN
            key = f"{'agreeing as Sonnet' if correlated else 'independent'} p={p:g}"
            out[key] = {"no_peor": round(no_peor / draws, 3), "peor": round(peor / draws, 3)}
    return out


def clock_line(phase: Phase, now: dt.datetime, todo: int) -> str:
    seconds = todo * phase.wall_mean_s * 1.5 + 600
    latest = dt.datetime.combine(now.date(), dt.time(23, 59, 59)) - dt.timedelta(seconds=seconds)
    return (
        f"clock {phase.key}: start after 08:00 and by {latest:%H:%M} ({todo} sessions x "
        f"{phase.wall_mean_s:g} s x 1.5 + 10 min = {seconds / 60:.0f} min before midnight)"
    )


def phase_lines(phase: Phase, rows: Sequence[Mapping[str, Any]],
                sonnet: Sequence[Mapping[str, Any]], now: dt.datetime) -> list[str]:  # fmt: skip
    by_id = {r["id"]: r for r in rows}
    order = lb162.read_ids(phase.ids_file) if phase.ids_file.exists() else derive(phase, rows)
    costs = costs_by_band(rows, sonnet)
    mean = {k: statistics.mean(v) * phase.cost_scale for k, v in costs.items()}
    bands = [by_id[i]["length"] for i in order]
    est = sum(mean[b] for b in bands)
    walls = {k: statistics.mean(float(s["wall_s"]) for s in sonnet if by_id[s["id"]]["length"] == k)
             for k in costs}  # fmt: skip
    per = est / len(order)
    stop_at = phase.ceiling - phase.loop_reserve
    return [
        f"phase {phase.key} ({phase.name}): {phase.model_id}, {len(order)} sessions, frozen file "
        f"{'present' if phase.ids_file.exists() else 'not written'}; first {order[:3]}",
        f"  by length {dict(sorted(Counter(bands).items()))}; by difficulty "
        f"{dict(sorted(Counter(by_id[i]['difficulty'] for i in order).items()))}",
        f"  cost a task (lb162's Sonnet sessions by band x {phase.cost_scale:g}): "
        + ", ".join(f"{k} {mean[k]:.4f}" for k in sorted(mean))
        + f"; expected {est:.2f} USD ({per:.4f} a task)",
        f"  money: ceiling {phase.ceiling:g} (hard, in code); cap {phase.full_cap:g} while spent + "
        f"{phase.full_cap:g} + worst turn {phase.worst_turn:g} <= {phase.ceiling:g} (spent <= "
        f"{phase.ceiling - phase.full_cap - phase.worst_turn:.2f}), then the room left, none "
        f"below {phase.floor:g} (spent > {stop_at:.2f} stops)",
        f"  guard: {at_mean(phase, per, len(order))} of {len(order)} sessions at the expected "
        f"mean ({at_mean(phase, per)} without the task limit), {at_mean(phase, per * 1.3)} at "
        f"1.3 x it; {guaranteed(phase)} guaranteed at worst",
        *(f"  simulated x{s:g}: {json.dumps(simulate(phase, bands, costs, s))}"
          for s in (1.0, 1.3, 1.6)),  # fmt: skip
        f"  wall: ~{sum(walls[b] for b in bands) / 60:.0f} min at lb162's Sonnet time by band, "
        f"~{len(order) * phase.wall_mean_s / 60:.0f} at the clock rule's {phase.wall_mean_s:g} s",
        "  " + clock_line(phase, now, len(order)),
    ]  # fmt: skip


def dry(now: dt.datetime | None = None, with_power: bool = True) -> list[str]:
    """Free: both phases in the driver's order, cost, the money rule simulated on lb162's real
    session costs, the clock, and phase B's power."""
    rows = jev_rows()
    sonnet = lb162.read_jsonl(lb162.SONNET_ROWS) or []
    when = now or dt.datetime.now()
    lines = [f"lb162's recordings: {'; '.join(recorded_problems()) or 'as committed'}; "
             f"Opus cost scale {OPUS_SCALE:g} (meter.CLAUDE_CODE_RATES)"]  # fmt: skip
    for phase in ORDER:
        lines += phase_lines(phase, rows, sonnet, when)
    if with_power:
        lines.append(f"phase B power ({POWER_DRAWS} draws): {json.dumps(power_b(rows))}")
    return lines


# ---- seal -------------------------------------------------------------------------------------

SEALED = (
    "benchmarks/jev114/lb162x.py", "benchmarks/jev114/lb162x_stats.py",
    "benchmarks/h2h/h2h_lb162x.py", "tests/test_lb162x.py",
    "docs/results/2026-10-16-lb162x/opus-ids.txt",
    "docs/results/2026-10-16-lb162x/uncovered-ids.txt",
    "docs/results/2026-10-15-lb162/ids.txt", "docs/results/2026-10-15-lb162/covered-ids.txt",
    "docs/results/2026-10-15-lb162/jev-scored.jsonl",
    "docs/results/2026-10-15-lb162/jev-answers-j14-L.jsonl",
    "docs/results/2026-10-15-lb162/sonnet-rows.jsonl",
    "benchmarks/jev114/lb162.py", "benchmarks/jev114/lb162_stats.py",
    "benchmarks/jev114/l6.py", "benchmarks/jev114/l6_analysis.py", "benchmarks/jev114/l4.py",
    "benchmarks/jev114/l4_stats.py", "benchmarks/jev114/b3conf_power.py", "benchmarks/meter.py",
    "benchmarks/h2h/h2h_lb162.py", "benchmarks/h2h/h2h_longdoc.py",
    "benchmarks/h2h/longdoc_data.py", "benchmarks/h2h/longdoc-dev-ids.txt",
    "benchmarks/h2h/offline_common.py", "benchmarks/h2h/h2h_gaia.py",
    "benchmarks/h2h/gaia_arms.py", "benchmarks/h2h/gaia_session.py",
    "benchmarks/h2h/gaia_stats.py", "benchmarks/h2h/gaia_data.py",
    "benchmarks/h2h/gaia_scorer.py", "benchmarks/h2h/s_line.py", "benchmarks/h2h/s_install.json",
    "benchmarks/h2h/local_hook.py", "benchmarks/h2h/deny_hook.py", "benchmarks/h2h/launch.ps1",
    "benchmarks/browse/phase.py",
)  # fmt: skip
SEALED_GLOBS = ("src/sanchopanza/**/*.py",)
SEALED_DATA = lb162.SEALED_DATA
DOCS_KEY = lb162.DOCS_KEY  # the 162 prepared documents


def sealed_paths() -> list[str]:
    globbed = sorted({p.relative_to(REPO).as_posix() for g in SEALED_GLOBS for p in REPO.glob(g)
                      if "__pycache__" not in p.parts})  # fmt: skip
    return [*SEALED, *(p for p in globbed if p not in SEALED)]


def manifest() -> dict[str, str]:
    doc = (OUT / "prereg.md").relative_to(REPO).as_posix()
    out = {p: lb162.digest(REPO / p) for p in (doc, *sealed_paths())}
    data = {f"~/{p}": lb162.raw_digest(pathlib.Path.home() / p) for p in SEALED_DATA}
    return out | data | {DOCS_KEY: lb162.docs_digest()}


def any_session() -> bool:
    return any(p.rows.exists() or p.stop.exists() for p in ORDER)


def seal(again: bool = False) -> str:
    found = manifest()
    value = lb162.combined(found)
    target = OUT / "prereg.sha256"
    if target.exists() and target.read_text().strip() not in ("", value):
        if not again:
            raise SystemExit("prereg.sha256 already holds another seal: nothing written")
        if any_session():
            raise SystemExit("sessions of this lot exist: a re-seal is an amendment, not a seal")
    (OUT / "prereg.manifest.json").write_text(json.dumps(found, indent=1) + "\n",
                                              encoding="utf-8", newline="\n")  # fmt: skip
    target.write_text(value + "\n", encoding="utf-8", newline="\n")
    return value


def require_prereg() -> None:
    target = OUT / "prereg.sha256"
    if not target.exists() or target.read_text().strip() != lb162.combined(manifest()):
        raise SystemExit("prereg.md, the code or the inputs differ from the seal: nothing spent")


def seal_state() -> str:
    target = OUT / "prereg.sha256"
    if not target.exists():
        return "not sealed"
    same = target.read_text().strip() == lb162.combined(manifest())
    return "sealed, matches" if same else "MISMATCH"


def docs_problems() -> list[str]:
    path = OUT / "prereg.manifest.json"
    if not path.exists():
        return []
    sealed = json.loads(path.read_text(encoding="utf-8")).get(DOCS_KEY)
    return [] if sealed == lb162.docs_digest() else ["the prepared documents differ from the seal"]


# ---- analysis and main ------------------------------------------------------------------------


def stop_of(phase: Phase) -> dict[str, Any] | None:
    return (lb162.read_jsonl(phase.stop) or [None])[0]


def pause_reasons(phase: Phase, stop: Mapping[str, Any] | None,
                  run_dir: pathlib.Path = RUN_DIR) -> list[str]:  # fmt: skip
    """Why no reading of `phase` may be made yet: a LIMIT.flag or STOP in the run folder, or the
    phase not ended by finishing or by its ceiling."""
    reasons = [f"{name} in the run folder" for name in ("LIMIT.flag", "STOP")
               if (run_dir / name).exists()]  # fmt: skip
    kind = (stop or {}).get("kind")
    if kind not in FINAL:
        reasons.append(f"phase {phase.key} {kind or 'not run'}")
    return reasons


def by_id(path: pathlib.Path) -> dict[str, dict[str, Any]]:
    return {r["id"]: r for r in lb162.read_jsonl(path) or []}


def analysis() -> dict[str, Any]:
    rows = jev_rows()
    opus, sonnet_a = by_id(PHASE_B.rows), by_id(PHASE_A.rows)
    sonnet_162 = by_id(lb162.SONNET_ROWS)
    stops = {p.key: (stop_of(p) or {}).get("kind") for p in ORDER}
    out = {
        "phase_b": stats.phase_b(rows, opus, pause_reasons(PHASE_B, stop_of(PHASE_B))),
        "phase_a": stats.phase_a(rows, sonnet_162, sonnet_a,
                                 pause_reasons(PHASE_A, stop_of(PHASE_A))),
        "opus_vs_sonnet": stats.opus_vs_sonnet(
            stats.tasks(rows, opus, PHASE_B.full_cap),
            stats.tasks(rows, {**sonnet_162, **sonnet_a}, PHASE_A.full_cap)),
        "stops": stops,
    }  # fmt: skip
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group()
    for flag in ("--freeze-ids", "--dry", "--plan", "--seal"):
        mode.add_argument(flag, action="store_true")
    ap.add_argument("--reseal", action="store_true", help="with --seal: replace a seal")
    args = ap.parse_args(argv)
    if args.freeze_ids:
        print(json.dumps(freeze_ids()))
        return 0
    if args.dry or args.plan:
        print("\n".join(dry()))
        print(f"seal: {seal_state()}", file=sys.stderr)
        return 0
    if args.seal:
        print(seal(again=args.reseal))
        return 0
    got = analysis()
    print(json.dumps({"phase_b": got["phase_b"]["primary"],
                      "phase_a": got["phase_a"]["saving"]}, indent=1))  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
