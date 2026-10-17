"""Lot longdoc-free's dev2 reading: the sealed dev's rules (dev_read.py, stats.py) applied to the
router with the BM25 prefilter before Jev. Free: reads public rows and the lot's ledgers only.

    python -I benchmarks/longdoc_free/dev2_read.py   # docs/results/2026-10-17-lfree-dev2/dev2.json

Registered in docs/results/2026-10-17-lfree-dev2/prereg-dev2.md. Inputs: dev2's gate p per
question (`jev-dev2.jsonl`, phase dev2 of jev_phase.py), dev2's N and H sessions
(`dev2-sonnet-rows.jsonl`, `dev2-haiku-rows.jsonl`, stage dev2 of h2h_lfree.py) and, reused, the
sealed dev's H0 and HC sessions (`../2026-10-16-longdoc-free/dev-*-rows.jsonl`, pinned below by
sha256: a changed file refuses the reading). H0 and HC enter no R - N: H0 only the with-H0
money and the descriptive controls, HC the memory rule. The dev's own N is read only for the
descriptive N(dev2) - N(dev) on the same questions (the arm's run-to-run variance); the dev's H
only for its mean F1 beside dev2's.

`dev_read.read` does the rest, unchanged in its rules: read at all (35 of 41), memory (HC), the
cut (`stats.dev_cut`), n for the confirmation's 310 questions, and the money. Two inputs differ
from the dev, both registered: the confirmation's Jev cap is what the lot's 14.30 USD leaves
after every Jev ledger of the lot (dev, probe, dev2), and its Haiku phase is H alone (no H0;
the with-H0 figure is reported beside it). Added, reported: the router against N and the saving
with the novel bootstrap at the cut, every cut's point estimates, Jev's real cost a question
from the recording, and the confirmation's expected money.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import statistics
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def _load(name: str, path: Path) -> Any:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


dev_read = _load("lf_dev_read", HERE / "dev_read.py")
stats = dev_read.stats
jp = _load("lf_jev_phase", HERE / "jev_phase.py")

DEV_DIR = jp.RESULTS
DEV2_DIR = jp.DEV2_DIR
# The sealed dev's rows dev2 reads (H0 and HC reused; N for the rerun's comparison), sha256
# with LF line ends (paid_once.digest).
REUSED_SHA256 = {
    "dev-sonnet-rows.jsonl": "6b83cb45f607a00404900cf08881d5c5c0d6133d892e929e1fc49ab9a51533d8",
    "dev-haiku-rows.jsonl": "0b52f1c81701fdfbde5c4fba87d34c714f2625aaddc679984166332e6a3bca09",
}
REUSED_VARIANTS = ("H0", "HC")
NEW_VARIANTS = ("N", "H")
CONFIRM_HAIKU_ARMS = ("H",)
# The confirmation's Jev plan at K = 200 (`jev_phase.py dry --phase confirm --prefilter-k 200`,
# the stub, free, 2026-10-17: 310 questions, 3,196 tournament, 1,513 sentence and 310 gate calls);
# the plan is this pessimistic estimate times jev_phase.PROBE_STUB_RATIO (3.139 USD).
CONFIRM_STUB_PESSIMISTIC_USD = 2.2152


# The code the reading runs (and the dev rows it reads), checked against dev2's instrument
# commit before anything is read: the reading runs in a checkout where these equal it.
READING_INSTRUMENT = ("src", "benchmarks", jp.IDS_REL, *jp.DEV_ROWS)  # as the Claude lot's
PAUSE_FILES = ("LIMIT.flag", "STOP")


def require_reading_instrument() -> str:
    """paid_once's instrument check over READING_INSTRUMENT: HEAD descends from the commit
    prereg-dev2.md names and nothing under those paths differs from it or is uncommitted."""
    the_lot = dataclasses.replace(jp.lot(jp.DEV2), instrument=READING_INSTRUMENT)
    return jp.paid_once.require_instrument(the_lot)


def pause_reasons(phases: Sequence[Any], final: Any, run_dir: Path) -> list[str]:
    """Why dev2 may not be read yet (lb162x's pattern): a LIMIT.flag or STOP in the lot's run
    folder, or a Claude phase without a final kind (`h2h_lfree.final_kind`: a smoke that
    passed, a phase done or at its ceiling)."""
    reasons = [f"{name} in the run folder" for name in PAUSE_FILES if (run_dir / name).exists()]
    return [*reasons, *(f"phase {p.key} not over" for p in phases if final(p) is None)]


def same_day(dates: Mapping[str, Sequence[str]]) -> bool:
    """Whether N's and H's sessions all ran on one day (reported, not a verdict change)."""
    return len({*dates.get("D2N", ()), *dates.get("D2H", ())}) <= 1


def require_reused(folder: Path = DEV_DIR) -> None:
    for name, sha in REUSED_SHA256.items():
        jp.paid_once.require_file(folder / name, sha)


def combine(dev_rows: Sequence[Mapping[str, Any]],
            dev2_rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:  # fmt: skip
    """The dev's H0 and HC sessions and dev2's N and H: one session per question and arm."""
    stray = sorted({r["variant"] for r in dev2_rows} - set(NEW_VARIANTS))
    if stray:
        raise SystemExit(f"dev2's rows hold arms it does not run: {stray}")
    return [*(r for r in dev_rows if r["variant"] in REUSED_VARIANTS), *dev2_rows]


def _diff(a: Any, b: Any) -> Any:
    return stats.mean_diff(a, b)


def by_cut(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Point estimates at every cut (descriptive): coverage, covered questions, covered H - N,
    R - N and the saving."""
    out = {}
    for cut in stats.CUTS:
        chosen = [r for r in rows if stats.covered(r, cut)]
        h_n = _diff(lambda r: r["f1"]["H"], lambda r: r["f1"]["N"])
        r_n = _diff(lambda r, c=cut: stats.router_f1(r, c), lambda r: r["f1"]["N"])
        out[str(cut)] = {"coverage": round(stats.coverage(rows, cut), 3), "covered": len(chosen),
                         "covered_h_minus_n": round(h_n(chosen), 2) if chosen else None,
                         "router_minus_n": round(r_n(rows), 2) if rows else None,
                         "saving": round(stats.saving(cut)(rows), 4) if rows else None}  # fmt: skip
    return out


def _interval(found: Any, digits: int) -> dict[str, Any]:
    return {"estimate": round(found.estimate, digits), "low": round(found.low, digits),
            "high": round(found.high, digits), "clusters": found.clusters}  # fmt: skip


def at_cut(rows: Sequence[Mapping[str, Any]], cut: float) -> dict[str, Any]:
    """R - N in points and the saving at the cut, percentile bootstraps resampling novels."""
    router = stats.bootstrap(rows, _diff(lambda r: stats.router_f1(r, cut), lambda r: r["f1"]["N"]))
    saved = stats.bootstrap(rows, stats.saving(cut))
    return {"cut": cut, "router_minus_n": _interval(router, 2), "saving": _interval(saved, 4),
            "coverage": round(stats.coverage(rows, cut), 3)}  # fmt: skip


def rerun_n(jev2: Sequence[Mapping[str, Any]], dev_rows: Sequence[Mapping[str, Any]],
            dev2_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:  # fmt: skip
    """N(dev2) - N(dev) on the questions both ran, descriptive (no verdict): the mean in F1
    points with the novel bootstrap, the SD of the per-question difference, how many questions
    moved, and both runs' cost."""
    novel = {int(r["id"]): r["novel"] for r in jev2}
    old = {int(r["id"]): r for r in dev_rows if r["variant"] == "N"}
    new = {int(r["id"]): r for r in dev2_rows if r["variant"] == "N"}
    both = sorted(set(old) & set(new) & set(novel))
    if not both:
        return None
    rows = [{"novel": novel[i], "a": float(new[i].get("f1") or 0.0),
             "b": float(old[i].get("f1") or 0.0)} for i in both]  # fmt: skip
    diff = [100.0 * (r["a"] - r["b"]) for r in rows]
    found = stats.bootstrap(rows, _diff(lambda r: r["a"], lambda r: r["b"]))
    return {"questions": len(both), "n_dev2_minus_n_dev": _interval(found, 2),
            "sd_points": round(statistics.stdev(diff), 2) if len(diff) > 1 else 0.0,
            "moved": sum(d != 0 for d in diff),
            "usd_dev": round(sum(float(old[i]["usd"]) for i in both), 4),
            "usd_dev2": round(sum(float(new[i]["usd"]) for i in both), 4)}  # fmt: skip


def expected_confirm(money: Mapping[str, Mapping[str, float]], jev_each: float) -> dict[str, Any]:
    """The confirmation's expected money at dev2's means: Claude with and without H0, and Jev."""

    def mean(arm: str) -> float:
        return float(money.get(arm, {}).get("mean_usd", 0.0))

    n = dev_read.CONFIRM_ITEMS
    return {"claude_without_h0": round(n * (mean("N") + mean("H")), 2),
            "claude_with_h0": round(n * (mean("N") + mean("H") + mean("H0")), 2),
            "jev": round(n * jev_each, 2)}  # fmt: skip


def read(
    jev2: Sequence[Mapping[str, Any]],
    dev_rows: Sequence[Mapping[str, Any]],
    dev2_rows: Sequence[Mapping[str, Any]],
    *,
    jev_spent: float,
    jev_planned: float,
    confirm_planned: float,
    claude_spent: float,
    jev_room: float,
    paused: Sequence[str] = (),
) -> dict[str, Any]:
    """`dev_read.read` on dev2's sessions with the confirmation's Jev cap at `jev_room` and its
    Haiku phase H alone; then the intervals, every cut and the expected money. `jev_planned`
    and `confirm_planned` are in the same unit (the stub's pessimistic estimate times
    PROBE_STUB_RATIO), so their ratio carries dev2's real over its plan to the confirmation.
    Not run without a complete phase J2; not read while `paused` (`pause_reasons`) says why."""
    if not jev2:
        return {"status": "not run", "why": "no jev-dev2.jsonl: phase J2 did not complete",
                "seal_confirmation": False}  # fmt: skip
    if paused:
        return {"status": "not read", "why": "; ".join(paused), "paused": list(paused),
                "seal_confirmation": False}  # fmt: skip
    sessions = combine(dev_rows, dev2_rows)
    out = dev_read.read(jev2, sessions, jev_spent, jev_planned, confirm_planned, claude_spent,
                        jev_cap=jev_room, haiku_arms=CONFIRM_HAIKU_ARMS)  # fmt: skip
    ratio = out["jev"]["settled_over_pessimistic"]
    out["confirm_money_with_h0"] = dev_read.confirm_money(
        out["money"], claude_spent, ratio, confirm_planned, jev_cap=jev_room
    )
    rows = dev_read.stats_rows(jev2, sessions, jev_spent)
    out["by_cut"] = by_cut(rows)
    out["at_cut"] = at_cut(rows, out["cut"]) if out["cut"] is not None else None
    out["expected_confirm_usd"] = expected_confirm(out["money"], jev_spent / len(jev2))
    out["n_rerun"] = rerun_n(jev2, dev_rows, dev2_rows)  # descriptive, not a verdict
    dev_h = [float(r.get("f1") or 0.0) for r in dev_rows if r["variant"] == "H"]
    new_h = [float(r.get("f1") or 0.0) for r in dev2_rows if r["variant"] == "H"]
    out["vs_dev"] = {
        "h_mean_f1_dev": round(100 * statistics.fmean(dev_h), 2) if dev_h else None,
        "h_mean_f1_dev2": round(100 * statistics.fmean(new_h), 2) if new_h else None,
        "jev_a_question_dev2": round(jev_spent / len(jev2), 4),
    }
    return {"status": "run", **out}


def jev_by_question(the_lot: Any, rows: Sequence[Mapping[str, Any]], k: int) -> dict[str, Any]:
    """Jev's real cost per question from the lot's recording (every recorded call's billed
    `cost_usd`: tournament, sentences, gate), as probe_read counts it."""
    probe_read = _load("lf_probe_read", HERE / "probe_read.py")
    dry = probe_read.dry
    from sanchopanza.providers.recorded import RecordedDecider

    lines = probe_read.recorded_lines(the_lot)
    costs = {str(x["key"]): float(x.get("cost_usd") or 0.0) for x in lines}
    counting = dry.Counting(RecordedDecider(lines), costs, answered_only=True)
    asker = dry.asker_over(None, counting)
    dry.run(list(rows), asker, k)
    usd = [sum(counting.by_row.get(str(r["id"]), {}).get(f"usd_{p}", 0.0) for p in dry.POINTS)
           for r in rows]  # fmt: skip
    return {"questions": len(usd), "complete": not asker.failed_keys,
            "mean_usd": round(statistics.fmean(usd), 4) if usd else None,
            "p90_usd": round(dev_read.percentile(usd, 0.9), 4) if usd else None,
            "max_usd": round(max(usd), 4) if usd else None}  # fmt: skip


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.parse_args(argv)
    require_reading_instrument()
    require_reused()
    the_lot = jp.lot(jp.DEV2)
    past = jp.paid_once.history(the_lot)
    jev2 = dev_read.read_jsonl(DEV2_DIR / "jev-dev2.jsonl")
    if not past or past[-1].get("stop_kind") is not None:
        jev2 = []  # phase J2 did not end with every call answered: dev2 is not run
    spent = {phase: jp.paid_once.spent(jp.lot(phase)) for phase in ("dev", jp.PROBE, jp.DEV2)}
    h2h = _load("lf_h2h", HERE.parent / "h2h" / "h2h_lfree.py")
    claude = h2h.stage_spent("dev") + h2h.stage_spent("dev2")
    planned = (float(past[0]["plan"]["pessimistic_usd"]) * jp.PROBE_STUB_RATIO) if past else 0.0
    got = read(
        jev2,
        [*dev_read.read_jsonl(DEV_DIR / "dev-sonnet-rows.jsonl"),
         *dev_read.read_jsonl(DEV_DIR / "dev-haiku-rows.jsonl")],
        [*dev_read.read_jsonl(DEV2_DIR / "dev2-sonnet-rows.jsonl"),
         *dev_read.read_jsonl(DEV2_DIR / "dev2-haiku-rows.jsonl")],
        jev_spent=spent[jp.DEV2],
        jev_planned=planned,
        confirm_planned=CONFIRM_STUB_PESSIMISTIC_USD * jp.PROBE_STUB_RATIO,
        claude_spent=claude,
        jev_room=jp.JEV_LOT_USD - sum(spent.values()),
        paused=pause_reasons(h2h.STAGES["dev2"], h2h.final_kind, h2h.RUN_DIR),
    )  # fmt: skip
    dates = h2h.phase_dates("dev2")
    got["session_dates"] = dates
    got["n_and_h_same_day"] = same_day(dates)  # reported, not a verdict change
    if got["status"] == "run":
        got["jev_by_question"] = jev_by_question(the_lot, jp.load_rows(jp.DEV2), jp.PROBE_K)
    got["jev_ledgers_usd"] = {k: round(v, 6) for k, v in spent.items()}
    got["claude_spent_usd"] = round(claude, 4)
    (DEV2_DIR / "dev2.json").write_text(json.dumps(got, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(got, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
