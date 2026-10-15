"""Lot lb102: Sonnet 5.5 in clean Claude Code (arm N) on the 102 LongBench v2 tasks Jev 1.14 did
not cover at 0.6 in lot lb162, to measure the router's saving that lb162 only estimated.
Pre-registered in docs/results/2026-10-16-lb102/prereg.md; analysis in lb102_stats.py; the paid
runner is benchmarks/h2h/h2h_lb102.py.

    python benchmarks/jev114/lb102.py --freeze-ids   # free: the 102 ids in their seeded order
    python benchmarks/jev114/lb102.py --dry          # free: the 102, cost and time from lb162
    python benchmarks/jev114/lb102.py --seal         # seal prereg.md + code + inputs
    python benchmarks/jev114/lb102.py                # free: the analysis, summary.json

No Jev call: Jev's answers and costs are lb162's recorded rows. Money (enforced in the runner):
the phase never passes CEILING_USD. Before each session the runner gives it the cap
`cap_for(spent)`: arm N's 3.00 USD while it fits, lowered to what is left after one worst turn
when it does not, and no session below CAP_FLOOR_USD.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import pathlib
import random
import statistics
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
for extra in ("src", "benchmarks", "benchmarks/h2h"):
    sys.path.insert(0, str(REPO / extra))
sys.path.insert(0, str(HERE))

import lb102_stats as stats  # noqa: E402
import lb162  # noqa: E402  (lot lb162: its tasks, rows, seal helpers and money constants)

OUT = REPO / "docs" / "results" / "2026-10-16-lb102"
IDS_FILE = OUT / "uncovered-ids.txt"
N_UNCOVERED = 102
ORDER_SEED = 20261016
RUN_DIR = pathlib.Path("C:/sp-runs/lb102")
SONNET_ROWS = OUT / "sonnet-rows.jsonl"
SONNET_STOP = OUT / "sonnet-stop.json"
SUMMARY = OUT / "summary.json"

# Money. The ceiling is the owner's (2026-10-15); the full cap and the worst turn are lb162's.
CEILING_USD = 16.00
FULL_CAP_USD = lb162.SONNET_CAP_USD  # 3.00, arm N's --max-budget-usd on LongBench
WORST_TURN_USD = lb162.WORST_TURN_USD  # 4.32: one turn rewriting 1M tokens + 32k out
# No session starts with a cap below this: 109 of the 110 arm N LongBench sessions on record
# (lb162's 60, 2026-10-06's 50) cost under 0.41 USD; one cost 1.87.
CAP_FLOOR_USD = 0.50
LOOP_RESERVE_USD = round(CAP_FLOOR_USD + WORST_TURN_USD, 4)  # the phase loop's own check
EST_FLAT_USD = 0.123  # Sonnet's mean a task on 2026-10-06 (lb162's estimate)
WALL_MEAN_S = 38.0  # the clock rule's mean session (2026-10-06, the slower of the two lots)
MC_DRAWS = 5_000
MC_SEED = 20261016


# ---- the 102 tasks ----------------------------------------------------------------------------


def jev_rows() -> list[dict[str, Any]]:
    rows = lb162.read_jsonl(lb162.JEV_ROWS)
    if rows is None or lb162.phase_j_final(rows, None):
        raise SystemExit("lb162's phase J rows are missing or not final")
    return rows


def uncovered(rows: Sequence[Mapping[str, Any]], seed: int = ORDER_SEED) -> list[str]:
    """lb162's asked tasks Jev did not cover at its cut, in a seeded random order (a ceiling stop
    leaves a random subset)."""
    ids = sorted(r["id"] for r in lb162.stats.asked(rows) if not lb162.stats.is_covered(r))
    random.Random(seed).shuffle(ids)
    return ids


def check_derivation(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Empty when lb162's files agree: 162 ids, the covered file is its derivation, 102 left."""
    found = []
    if [r["id"] for r in rows] != lb162.frozen_ids():
        found.append("lb162's rows are not its frozen ids")
    if lb162.read_ids(lb162.COVERED_FILE) != lb162.covered(rows):
        found.append("lb162's covered-ids.txt is not the derivation of its rows")
    if len(uncovered(rows)) != N_UNCOVERED:
        found.append(f"{len(uncovered(rows))} uncovered tasks, expected {N_UNCOVERED}")
    return found


def freeze_ids() -> str:
    if IDS_FILE.exists():
        raise SystemExit(f"{IDS_FILE.name} exists: the order is frozen")
    rows = jev_rows()
    if found := check_derivation(rows):
        raise SystemExit("; ".join(found))
    head = (f"# lot lb102: the {N_UNCOVERED} lb162 tasks Jev 1.14 did not cover at {lb162.TAU}, "
            f"in random.Random({ORDER_SEED}).shuffle order of the sorted ids")  # fmt: skip
    OUT.mkdir(parents=True, exist_ok=True)
    IDS_FILE.write_text(head + "\n" + "".join(f"{i}\n" for i in uncovered(rows)),
                        encoding="utf-8", newline="\n")  # fmt: skip
    return lb162.digest(IDS_FILE)


def frozen_order(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """The frozen file, refused unless it is the derivation of lb162's rows."""
    ids = lb162.read_ids(IDS_FILE)
    if ids != uncovered(rows):
        raise SystemExit(f"{IDS_FILE.name} is missing or not the derivation of lb162's rows")
    return ids


# ---- money ------------------------------------------------------------------------------------


def cap_for(spent: float, ceiling: float = CEILING_USD) -> float | None:
    """The next session's --max-budget-usd: the full cap while cap + one worst turn fits under
    the ceiling, else what is left after the worst turn (down to the cent); None below the
    floor, which stops the phase (kind `ceiling`)."""
    room = math.floor(round((ceiling - spent - WORST_TURN_USD) * 100, 6)) / 100
    cap = min(FULL_CAP_USD, room)
    return cap if cap >= CAP_FLOOR_USD else None


def costs_by_band(rows: Sequence[Mapping[str, Any]],
                  sonnet: Sequence[Mapping[str, Any]]) -> dict[str, list[float]]:  # fmt: skip
    """lb162's real Sonnet session costs, by the LongBench length band of their task."""
    band = {r["id"]: r["length"] for r in rows}
    out: dict[str, list[float]] = {}
    for s in sonnet:
        out.setdefault(band[s["id"]], []).append(float(s["usd"]))
    return out


def walls_by_band(rows: Sequence[Mapping[str, Any]],
                  sonnet: Sequence[Mapping[str, Any]]) -> dict[str, float]:  # fmt: skip
    band = {r["id"]: r["length"] for r in rows}
    out: dict[str, list[float]] = {}
    for s in sonnet:
        out.setdefault(band[s["id"]], []).append(float(s["wall_s"]))
    return {k: statistics.mean(v) for k, v in out.items()}


def simulate(bands: Sequence[str], costs: Mapping[str, Sequence[float]], scale: float = 1.0,
             draws: int = MC_DRAWS, seed: int = MC_SEED) -> dict[str, Any]:  # fmt: skip
    """The runner's money rule on `bands` (the frozen order), each session's cost drawn from
    `costs` of its band times `scale`, a session past its cap cut at the cap."""
    rng = random.Random(seed)
    ran, spent_all, reduced = [], [], 0
    for _ in range(draws):
        spent, n = 0.0, 0
        for band in bands:
            cap = cap_for(spent)
            if cap is None:
                break
            reduced += cap < FULL_CAP_USD
            spent += min(rng.choice(costs[band]) * scale, cap)
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


def clock_line(now: dt.datetime, todo: int) -> str:
    seconds = todo * WALL_MEAN_S * 1.5 + 600
    latest = dt.datetime.combine(now.date(), dt.time(23, 59, 59)) - dt.timedelta(seconds=seconds)
    return (f"clock: start after 08:00 and by {latest:%H:%M} ({todo} sessions x {WALL_MEAN_S:g} s "
            f"x 1.5 + 10 min = {seconds / 60:.0f} min must end before midnight)")  # fmt: skip


def dry(now: dt.datetime | None = None) -> list[str]:
    """Free: the 102 in their order with band and estimated cost, the totals, the money rule
    simulated on lb162's real session costs, and the clock."""
    rows = jev_rows()
    by_id = {r["id"]: r for r in rows}
    sonnet = lb162.read_jsonl(lb162.SONNET_ROWS) or []
    order = lb162.read_ids(IDS_FILE) if IDS_FILE.exists() else uncovered(rows)
    costs = costs_by_band(rows, sonnet)
    mean = {k: statistics.mean(v) for k, v in costs.items()}
    walls = walls_by_band(rows, sonnet)
    lines = [f"{k:3d} {i} {by_id[i]['length']:6s} {by_id[i]['difficulty']:4s} "
             f"{by_id[i]['chars']:>9,d} chars  est {mean[by_id[i]['length']]:.3f} USD"
             for k, i in enumerate(order, 1)]  # fmt: skip
    bands = [by_id[i]["length"] for i in order]
    est = sum(mean[b] for b in bands)
    lines += [
        f"{len(order)} sessions; frozen file {'present' if IDS_FILE.exists() else 'not written'}"
        f"; problems: {'; '.join(check_derivation(rows)) or 'none'}",
        f"by length {dict(sorted(Counter(bands).items()))}; by difficulty "
        f"{dict(sorted(Counter(by_id[i]['difficulty'] for i in order).items()))}",
        f"lb162's {len(sonnet)} real sessions by band (mean USD): "
        + ", ".join(f"{k} {mean[k]:.4f} (n {len(costs[k])}, max {max(costs[k]):.3f})"
                    for k in sorted(mean)),
        f"cost: est {est:.2f} USD by band from lb162; {len(order) * EST_FLAT_USD:.2f} at "
        f"2026-10-06's flat {EST_FLAT_USD}; ceiling {CEILING_USD:g} (hard, in code)",
        f"money rule: cap {FULL_CAP_USD:g} while spent + {FULL_CAP_USD:g} + {WORST_TURN_USD:g} "
        f"<= {CEILING_USD:g} (spent <= {CEILING_USD - FULL_CAP_USD - WORST_TURN_USD:.2f}), then "
        f"lowered to the room left, none below {CAP_FLOOR_USD:g} (spent > "
        f"{CEILING_USD - LOOP_RESERVE_USD:.2f} stops)",
        *(f"simulated x{s:g}: {json.dumps(simulate(bands, costs, s))}" for s in (1.0, 1.3, 1.6)),
        f"wall: ~{sum(walls[b] for b in bands) / 60:.0f} min at lb162's mean by band, "
        f"~{len(order) * WALL_MEAN_S / 60:.0f} at the clock rule's {WALL_MEAN_S:g} s",
        clock_line(now or dt.datetime.now(), len(order)),
    ]  # fmt: skip
    return lines


# ---- seal -------------------------------------------------------------------------------------

SEALED = (
    "benchmarks/jev114/lb102.py", "benchmarks/jev114/lb102_stats.py",
    "benchmarks/h2h/h2h_lb102.py", "tests/test_lb102.py",
    "docs/results/2026-10-16-lb102/uncovered-ids.txt",
    "docs/results/2026-10-15-lb162/ids.txt", "docs/results/2026-10-15-lb162/covered-ids.txt",
    "docs/results/2026-10-15-lb162/jev-scored.jsonl",
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
DOCS_KEY = lb162.DOCS_KEY  # the 162 prepared documents (the 102 among them)


def sealed_paths() -> list[str]:
    globbed = sorted({p.relative_to(REPO).as_posix() for g in SEALED_GLOBS for p in REPO.glob(g)
                      if "__pycache__" not in p.parts})  # fmt: skip
    return [*SEALED, *(p for p in globbed if p not in SEALED)]


def manifest() -> dict[str, str]:
    doc = (OUT / "prereg.md").relative_to(REPO).as_posix()
    out = {p: lb162.digest(REPO / p) for p in (doc, *sealed_paths())}
    data = {f"~/{p}": lb162.raw_digest(pathlib.Path.home() / p) for p in SEALED_DATA}
    return out | data | {DOCS_KEY: lb162.docs_digest()}


def seal(again: bool = False) -> str:
    found = manifest()
    value = lb162.combined(found)
    target = OUT / "prereg.sha256"
    if target.exists() and target.read_text().strip() not in ("", value):
        if not again:
            raise SystemExit("prereg.sha256 already holds another seal: nothing written")
        if SONNET_ROWS.exists():
            raise SystemExit("sessions of the 102 exist: a re-seal is an amendment, not a seal")
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


def pause_reasons(stop: Mapping[str, Any] | None, run_dir: pathlib.Path = RUN_DIR) -> list[str]:
    """Why no reading may be made yet: a LIMIT.flag or STOP in the run folder, or the phase not
    ended by finishing or by its ceiling."""
    reasons = [f"{name} in the run folder" for name in ("LIMIT.flag", "STOP")
               if (run_dir / name).exists()]  # fmt: skip
    kind = (stop or {}).get("kind")
    if kind not in ("done", "ceiling"):
        reasons.append(f"phase {kind or 'not run'}")
    return reasons


def by_id(path: pathlib.Path) -> dict[str, dict[str, Any]]:
    return {r["id"]: r for r in lb162.read_jsonl(path) or []}


def analysis() -> dict[str, Any]:
    rows = jev_rows()
    stop = (lb162.read_jsonl(SONNET_STOP) or [None])[0]
    out = stats.analyse(rows, by_id(lb162.SONNET_ROWS), by_id(SONNET_ROWS),
                        paused=pause_reasons(stop))  # fmt: skip
    out["sonnet_stop"] = (stop or {}).get("kind")
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group()
    for flag in ("--freeze-ids", "--dry", "--seal"):
        mode.add_argument(flag, action="store_true")
    ap.add_argument("--reseal", action="store_true", help="with --seal: replace a seal")
    args = ap.parse_args(argv)
    if args.freeze_ids:
        print(freeze_ids())
        return 0
    if args.dry:
        print("\n".join(dry()))
        print(f"seal: {seal_state()}", file=sys.stderr)
        return 0
    if args.seal:
        print(seal(again=args.reseal))
        return 0
    print(json.dumps(analysis()["primary"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
