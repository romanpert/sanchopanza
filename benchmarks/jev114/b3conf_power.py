"""B3 at the 0.6 cut: can a confirmation on fresh LongBench v2 tasks decide anything? Free.

Lot L6 (docs/results/2026-10-15-jev114-l6) found, post hoc, that Jev 1.14 with the long window
answering alone where its confidence is >= 0.6, and Sonnet 5.5 elsewhere, tied Sonnet's 31/50.
This module measures, from L6's recorded answers only, the chance that a confirmation reaches a
verdict, before anything is paid:

- **jev-only**: fresh tasks asked of Jev alone. With no Sonnet answer on them, hybrid minus
  Sonnet is estimated as coverage x (Jev's precision on the covered tasks - Sonnet's mean
  accuracy measured on L6's 50 tasks), the two samples independent.
- **paired**: fresh tasks where Sonnet also answers the covered ones (hybrid minus Sonnet only
  depends on those), the paired difference.

L6's 50 tasks stand in for the fresh population, resampled with replacement; the per-task
difference is the hybrid's gain on that task (0 outside the covered ones).

  PYTHONPATH=src python benchmarks/jev114/b3conf_power.py           # the tables in the README
  PYTHONPATH=src python benchmarks/jev114/b3conf_power.py --pool    # fresh pool, metadata only
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import random
import statistics
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCORED = ROOT / "docs" / "results" / "2026-10-15-jev114-l6" / "b3-scored.jsonl"
CELL = "j14-L"
TAU = 0.6
MARGINS = (-0.02, -0.05, -0.10)
SIZES = (50, 100, 162)
REPS = 5000
SEED = 20261015
Z = 1.959964
Z_POWER = 0.841621


@dataclass(frozen=True)
class Row:
    covered: bool
    jev_ok: bool
    sonnet_ok: bool
    sonnet_usd: float
    jev_usd: float


def load(path: pathlib.Path = SCORED, cell: str = CELL, tau: float = TAU) -> list[Row]:
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    out = []
    for r in rows:
        ans = r.get(cell) or {}
        p, letter = ans.get("p"), ans.get("letter")
        out.append(Row(
            covered=p is not None and letter is not None and p >= tau,
            jev_ok=letter is not None and letter == r["gold"],
            sonnet_ok=bool(r["sonnet"]["ok"]), sonnet_usd=float(r["sonnet"]["usd"]),
            jev_usd=float(ans.get("usd") or 0.0),
        ))  # fmt: skip
    return out


def sonnet_mean(rows: Sequence[Row]) -> float:
    return sum(r.sonnet_ok for r in rows) / len(rows)


def paired_ci(sample: Sequence[Row]) -> tuple[float, float, float]:
    """Hybrid minus Sonnet, paired: the gain is Jev - Sonnet on the covered tasks, 0 elsewhere."""
    x = [r.covered * (int(r.jev_ok) - int(r.sonnet_ok)) for r in sample]
    d, se = statistics.fmean(x), statistics.stdev(x) / math.sqrt(len(x))
    return d, d - Z * se, d + Z * se


def jev_only_ci(sample: Sequence[Row], s_bar: float, n_ref: int) -> tuple[float, float, float]:
    """Hybrid minus Sonnet with Sonnet's per-task answers unknown: coverage x (precision - s_bar),
    s_bar measured on another n_ref tasks (its variance added, the samples independent)."""
    x = [r.covered * (int(r.jev_ok) - s_bar) for r in sample]
    cov = sum(r.covered for r in sample) / len(sample)
    var = statistics.variance(x) / len(x) + cov * cov * s_bar * (1 - s_bar) / n_ref
    d = statistics.fmean(x)
    return d, d - Z * math.sqrt(var), d + Z * math.sqrt(var)


def power(rows: Sequence[Row], ci: Callable[[Sequence[Row]], tuple[float, float, float]],
          n: int, margin: float, reps: int = REPS, seed: int = SEED) -> dict:  # fmt: skip
    """Share of resampled confirmations whose CI lower bound clears the margin ("no peor"), whose
    upper bound falls below it ("peor"), and the median CI half-width."""
    rng = random.Random(seed)
    ok = bad = 0
    widths = []
    for _ in range(reps):
        _, lo, hi = ci([rows[rng.randrange(len(rows))] for _ in range(n)])
        ok += lo > margin
        bad += hi < margin
        widths.append((hi - lo) / 2)
    return {"n": n, "margin": margin, "no_peor": ok / reps, "peor": bad / reps,
            "half_width": statistics.median(widths)}  # fmt: skip


def n_for_power(rows: Sequence[Row], true_d: float, margin: float) -> int:
    """Paired tasks for 80 % power (one-sided 2.5 %) at a true hybrid gain true_d."""
    sd = statistics.stdev([r.covered * (int(r.jev_ok) - int(r.sonnet_ok)) for r in rows])
    return math.ceil(((Z + Z_POWER) * sd / (true_d - margin)) ** 2)


def describe(rows: Sequence[Row]) -> dict:
    cov = [r for r in rows if r.covered]
    unc = [r for r in rows if not r.covered]
    return {
        "tasks": len(rows), "covered": len(cov),
        "jev_right_covered": sum(r.jev_ok for r in cov),
        "sonnet_right_covered": sum(r.sonnet_ok for r in cov),
        "sonnet_right_uncovered": sum(r.sonnet_ok for r in unc),
        "discordant_covered": sum(r.jev_ok != r.sonnet_ok for r in cov),
        "sonnet_usd_covered_mean": statistics.fmean(r.sonnet_usd for r in cov),
        "sonnet_usd_mean": statistics.fmean(r.sonnet_usd for r in rows),
        "jev_usd_total": sum(r.jev_usd for r in rows),
    }  # fmt: skip


def report(rows: Sequence[Row]) -> dict:
    s_bar = sonnet_mean(rows)
    designs = {
        "jev_only": lambda s: jev_only_ci(s, s_bar, len(rows)),
        "paired": paired_ci,
    }
    table = [{"design": name, **power(rows, fn, n, m)}
             for m in MARGINS for name, fn in designs.items() for n in SIZES]  # fmt: skip
    needed = {f"{d:+.2f}": n_for_power(rows, d, MARGINS[0]) for d in (0.0, 0.02, 0.04)}
    return {"l6": describe(rows), "sonnet_mean": s_bar, "power": table,
            "paired_n_for_80pct_at_-2": needed}  # fmt: skip


def fresh_pool() -> dict:  # pragma: no cover - needs the 465 MB cache
    """Eligible LongBench v2 tasks outside the 60 drawn on 2026-10-06, by metadata only."""
    from collections import Counter

    sys.path.insert(0, str(ROOT / "benchmarks" / "h2h"))
    import longdoc_data as ld

    rows = json.loads(ld.RAW.read_text(encoding="utf-8"))
    used = {t.task_id for t in ld.load()}
    fresh = [r for r in ld.eligible(rows) if str(r["_id"]) not in used]
    return {"eligible": len(ld.eligible(rows)), "used": len(used), "fresh": len(fresh),
            "fresh_le_900k_chars": sum(len(r["context"]) <= 900_000 for r in fresh),
            "by_length": dict(Counter(r["length"] for r in fresh))}  # fmt: skip


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pool", action="store_true", help="count the fresh pool (needs the cache)")
    args = ap.parse_args(argv)
    out = fresh_pool() if args.pool else report(load())
    sys.stdout.write(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
