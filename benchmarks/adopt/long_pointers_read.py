"""The guard-pointers lot read as its prereg says
(docs/results/2026-10-16-guard-pointers/prereg.md): P (the default install, pointer guard)
against F (the same install with --guard-full), one run per arm and chain. Free: Docker for
`grade`, nothing else; no model, no API, no Jev.

    python benchmarks/adopt/long_pointers_read.py grade [--profile guardptr] [--root ...] [--final]
    python benchmarks/adopt/long_pointers_read.py read  [--profile guardptr] [--root ...] [--json f]

Per chain, on the calls both arms ran (`long_compact.chain_line` with the pair P, F: common calls,
each arm graded at its own snapshot after the last of them, every chain with the same per-test
timeout, `TEST_TIMEOUT`, registered before any run):
- quality: P - F in resolved rate over the bugs both were asked; over chains, the difference with
  whole chains resampled (`long_report.cluster_bootstrap`, its one-sided 95 % bound) AND the
  one-sided 95 % t bound of the mean per-chain difference (`t_low`). With five chains the
  bootstrap alone says "non-inferior" about twice as often as it should when P really loses the
  margin (simulated, `guardptr_power.py`); requiring both keeps that near 5 %.
- cost, secondary and descriptive: P/F on the common calls, `long_report.cost_ratio`.
- mechanism, descriptive (`mechanism`): per compaction, reads of an archived `guard-*.txt`,
  commands run again and files read again within `long_report.REREAD_WINDOW` requests after it;
  and per arm the guard's blocks (`carry`: chooser, characters, outputs archived).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import long_compact  # noqa: E402
import long_pointers  # noqa: E402
import long_report  # noqa: E402
import long_resume  # noqa: E402

PAIR = ("P", "F")
ROOTS = {
    "guardptr": Path(r"C:\sp-runs\L-guardptr"),
    "guardptr-30": Path(r"C:\sp-runs\L-guardptr30"),
    "guardptr-smoke": Path(r"C:\sp-runs\L-guardptr-smoke"),  # grade only: one chain, no rule
}
MARGINS = {"guardptr": 0.05, "guardptr-30": 0.07}  # non-inferiority, resolved rate (prereg 6)
MIN_CHAINS = 5
MIN_COMMON = {"guardptr": 30, "guardptr-30": 20}  # common calls for a chain to count
TEST_TIMEOUT = 300  # seconds per test in every grade of this lot (moto hung without, 2026-10-14)
T95_ONE_SIDED = {2: 6.314, 3: 2.920, 4: 2.132, 5: 2.015, 6: 1.943, 7: 1.895, 8: 1.860, 9: 1.833}
RULE = (
    "non-inferior: the one-sided 95 % lower bound of P - F in resolved rate is above -margin both "
    "by the cluster bootstrap (whole chains resampled) and by the t bound of the per-chain mean "
    "(with 'a smaller loss shown' added when the bootstrap's two-sided 95 % interval lies below "
    "0); worse: not non-inferior and that interval lies below 0; not shown: otherwise; no "
    "verdict: fewer than 5 chains with their minimum of common calls and both arms graded there, "
    "or any chain with an arm paused (limit, harness, ceiling) or a partial row"
)
ARCHIVED = re.compile(r"guard-[A-Za-z0-9_.-]+\.txt$")


# ---- quality and the rule ------------------------------------------------------------------------


def t_low(clusters: Sequence[Sequence[tuple[bool, bool]]]) -> float | None:
    """The one-sided 95 % t lower bound of the mean per-chain difference (None: under 2 chains)."""
    rates = [sum(t - c for t, c in chain) / len(chain) for chain in clusters if chain]
    if len(rates) < 2:
        return None
    t = T95_ONE_SIDED.get(len(rates) - 1, 1.645)
    return statistics.mean(rates) - t * statistics.stdev(rates) / math.sqrt(len(rates))


def quality(clusters: Sequence[Sequence[tuple[bool, bool]]]) -> dict[str, Any]:
    """Unrounded: the rule compares these; `published` rounds them for the reading."""
    diff, low, high = long_report.cluster_bootstrap(clusters)
    return {
        "difference": diff,
        "ci95": [low, high],
        "one_sided_low": long_report.one_sided_low(clusters),
        "t_low": t_low(clusters),
    }


def published(q: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if q is None:
        return None
    rounded = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in q.items()}
    return {**rounded, "ci95": [round(x, 4) for x in q["ci95"]]}


def cuts(row: Mapping[str, Any]) -> dict[str, int]:
    """Calls cut mid-run (charged at their cap; the arm went on: `resume_decision` "continue" on
    these chains' splits) and calls asked again after a cut that did nothing (`retried`)."""
    calls = row.get("calls") or []
    return {"cut": sum(str(c.get("status", "")).startswith("cut") or "deviation" in c
                       for c in calls),
            "retried": sum(bool(c.get("retried")) for c in calls),
            "set_aside": sum(c.get("status") == "SET ASIDE" for c in calls)}  # fmt: skip


def verdict(q: Mapping[str, Any] | None, chains: int, margin: float,
            min_chains: int = MIN_CHAINS) -> str:  # fmt: skip
    """`RULE`, applied."""
    if q is None or chains < min_chains or q.get("t_low") is None:
        return "no verdict"
    below = q["ci95"][1] < 0
    if q["one_sided_low"] > -margin and q["t_low"] > -margin:
        return "non-inferior, a smaller loss shown" if below else "non-inferior"
    return "worse" if below else "not shown"


def cost_reading(pairs: Sequence[tuple[float, float]]) -> dict[str, Any]:
    """P/F with its 95 % t interval, named (descriptive: the prereg's power table says five
    chains cannot show a 6 % saving)."""
    cost = long_report.cost_ratio(pairs)
    if "high" not in cost:
        return {**cost, "reading": "no interval"}
    name = ("cheaper shown" if cost["high"] < 1 else "dearer shown" if cost["low"] > 1
            else "no difference shown")  # fmt: skip
    return {**cost, "reading": name}


# ---- mechanism -----------------------------------------------------------------------------------


def _uses(entry: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    content = (entry.get("message") or {}).get("content") or []
    return [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]


def _command(block: Mapping[str, Any]) -> str:
    if block.get("name") not in ("Bash", "PowerShell"):
        return ""
    return str((block.get("input") or {}).get("command") or "").strip()


def mechanism(evidence: Path, window: int = long_report.REREAD_WINDOW) -> dict[str, int]:
    """Over the arm's transcripts: compactions; reads of an archived guard file (any time); and,
    within `window` requests after a compaction, commands run before it run again and paths read
    before it read again (an archived file is never a re-read)."""
    found = {"compactions": 0, "archive_reads": 0, "reruns": 0, "rereads": 0}
    for path in sorted(evidence.glob("transcript*.jsonl")):
        read, ran = set(), set()
        before_read, before_ran, since, requests = set(), set(), None, 0
        for entry in long_report._entries(path):
            if entry.get("type") == "system" and entry.get("subtype") == "compact_boundary":
                found["compactions"] += 1
                before_read, before_ran, since = set(read), set(ran), requests
                continue
            if entry.get("type") != "assistant":
                continue
            requests += 1
            near = since is not None and requests - since <= window
            for block in _uses(entry):
                paths, command = long_report._reads(block), _command(block)
                for one in paths:
                    if ARCHIVED.search(one.replace("\\", "/")):
                        found["archive_reads"] += 1
                    elif near and one in before_read:
                        found["rereads"] += 1
                if command and near and command in before_ran:
                    found["reruns"] += 1
                read.update(paths)
                if command:
                    ran.add(command)
    return found


def carry(row: Mapping[str, Any]) -> dict[str, Any]:
    """The guard's blocks over the arm's calls, from its own log (`long_pointers.guard_facts`)."""
    blocks = [g for call in row.get("calls") or [] for g in call.get("guard") or []]
    chars = [int(g.get("block_chars") or 0) for g in blocks]
    return {
        "blocks": len(blocks),
        "block_chars": chars,
        "median_block_chars": statistics.median(chars) if chars else None,
        "archived": sum(int(g.get("archived") or 0) for g in blocks),
        "choosers": sorted({str(g.get("chooser")) for g in blocks}),
        "failed": sum(long_pointers.FAILED_MARK in str(g.get("chooser") or "") for g in blocks),
    }


# ---- reading -------------------------------------------------------------------------------------


def _row(evidence: Path) -> dict[str, Any]:
    path = evidence / "row.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def paused(base: Path) -> list[str]:
    """Why a chain's rows are not final: an arm paused by the usage limit, an invariant's STOP or
    the ceiling (`long_resume.RESUMES`: a relaunch goes on from there), or a partial row (the
    runner died, or is still running). Such a chain is not scored (prereg, section 6)."""
    out = []
    for arm in PAIR:
        row = _row(base / arm)
        if row.get("partial"):
            out.append(f"{arm}: partial (the runner died or is running)")
        elif row.get("stopped") in long_resume.RESUMES:
            out.append(f"{arm}: stopped ({row['stopped']})")
    return out


def read(root: Path, chains: Sequence[str], profile: str = "guardptr") -> dict[str, Any]:
    margin, floor = MARGINS[profile], MIN_COMMON[profile]
    found = {c: line for c in chains if (line := long_compact.chain_line(root, c, PAIR))}
    base = {c: root / "runs" / f"{c}-{long_compact.MODEL}" for c in found}
    held = {c: why for c in found if (why := paused(base[c]))}
    counted = {c: v for c, v in found.items() if c not in held and v["common_calls"] >= floor
               and v["ratio"] and v["pairs"]}  # fmt: skip
    clusters = [v["pairs"] for v in counted.values()]
    q = quality(clusters) if clusters else None
    costs = [(v["arms"]["P"]["cost_common"], v["arms"]["F"]["cost_common"])
             for v in counted.values()]  # fmt: skip
    lines = {c: {**{k: v for k, v in line.items() if k != "pairs"},
                 "mechanism": {a: mechanism(base[c] / a) for a in PAIR},
                 "carry": {a: carry(_row(base[c] / a)) for a in PAIR},
                 "cuts": {a: cuts(_row(base[c] / a)) for a in PAIR}}
             for c, line in found.items()}  # fmt: skip
    return {"rule": RULE, "profile": profile, "margin": margin, "min_common": floor,
            "chains_read": len(found), "chains_counted": sorted(counted),
            "chains_paused": held, "quality": published(q),
            "verdict": "no verdict" if held else verdict(q, len(counted), margin),
            "cost": cost_reading(costs),
            "chains": lines}  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    import long_run

    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("grade", "read"))
    parser.add_argument("--profile", default="guardptr", choices=sorted(ROOTS))
    parser.add_argument("--root", default="")
    parser.add_argument("--json", default="")
    parser.add_argument("--final", action="store_true", help="grade: also the final grade")
    args = parser.parse_args(argv)
    root = Path(args.root) if args.root else ROOTS[args.profile]
    chains = list(long_run.PROFILES[args.profile].chains)
    if args.action == "grade":
        import run

        known = run.chains()
        with long_compact.per_test_timeout(TEST_TIMEOUT):
            for chain in chains:
                lines = long_compact.grade_common(root, chain, known, PAIR)
                lines += long_compact.grade_final(root, chain, known, PAIR) if args.final else []
                for line in lines:
                    print(line, flush=True)
        return 0
    if args.profile not in MARGINS:
        parser.error(f"{args.profile} is graded, not read: it has no rule")
    text = json.dumps(read(root, chains, args.profile), indent=1)
    print(text)
    if args.json:
        Path(args.json).write_text(text, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
