"""Read the end-to-end runs and say, paired by task, what each arm bought and what it cost.

    python benchmarks/agentdojo/e2e_report.py docs/results/2026-09-25-e2e/runs-10.jsonl

Free: arithmetic over the recorded rows. Two costs are reported because the arms differ in
how much of the prompt cache they can share across sessions: `full` and `search` send the
same `tools` array to every task, so a steady stream of sessions reads it from cache; the
sancho arm on a model without `tool_addition` sends the opened groups loaded, so its prefix
depends on the task. "as run" is what this run paid, sessions interleaved as in production;
"cold" re-prices every cache read as a first write, the price of a lone session.
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

from sanchopanza.eval.stats import bootstrap_difference, mcnemar, median, wilson  # noqa: E402

PRICE = {"in": 2.0e-6, "write": 2.5e-6, "read": 0.2e-6, "out": 10.0e-6}
ARMS = ("full", "search", "sancho")


def cold(row: dict) -> float:
    t = row["tokens"]
    return (
        t["input"] * PRICE["in"]
        + (t["cache_write"] + t["cache_read"]) * PRICE["write"]
        + t["output"] * PRICE["out"]
        + row.get("usd_jev", 0.0)
    )


def main(path: str) -> int:
    rows = [
        json.loads(line) for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines()
    ]
    errors = [r for r in rows if "error" in r]
    ok = [r for r in rows if "error" not in r]
    by = {(r["arm"], r["suite"], r["task"]): r for r in ok}
    keys = sorted({(r["suite"], r["task"]) for r in ok})
    paired = [k for k in keys if all((a, *k) in by for a in ARMS)]
    out = [
        f"{len(paired)} tasks with all three arms; {len(errors)} crashed runs excluded.",
        "",
        "| arm | success | 95 % Wilson | USD as run | USD cold | Jev USD | median s | "
        "mean turns | loads / searches |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for arm in ARMS:
        rs = [by[(arm, *k)] for k in paired]
        hits = sum(r["success"] for r in rs)
        p, lo, hi = wilson(hits, len(rs))
        out.append(
            f"| {arm} | {hits}/{len(rs)} | {lo:.0%}-{hi:.0%} | "
            f"{sum(r['usd_model'] + r['usd_jev'] for r in rs):.3f} | "
            f"{sum(cold(r) for r in rs):.3f} | "
            f"{sum(r['usd_jev'] for r in rs):.4f} | {median([r['seconds'] for r in rs]):.1f} | "
            f"{sum(r['turns'] for r in rs) / len(rs):.1f} | "
            f"{sum(r['loads'] for r in rs)} / {sum(r['searches'] for r in rs)} |"
        )
    out += [
        "",
        "Paired against `full` and `search` (McNemar exact; only discordant tasks count):",
        "",
    ]
    for a, b in (("sancho", "full"), ("sancho", "search"), ("search", "full")):
        sa = [by[(a, *k)]["success"] for k in paired]
        sb = [by[(b, *k)]["success"] for k in paired]
        only_a, only_b, pval = mcnemar(sa, sb)
        diff, dlo, dhi = bootstrap_difference(sa, sb)
        ca = sum(by[(a, *k)]["usd_model"] + by[(a, *k)]["usd_jev"] for k in paired)
        cb = sum(by[(b, *k)]["usd_model"] + by[(b, *k)]["usd_jev"] for k in paired)
        ta = median([by[(a, *k)]["seconds"] for k in paired])
        tb = median([by[(b, *k)]["seconds"] for k in paired])
        out.append(
            f"- **{a} vs {b}**: only {a} {only_a}, only {b} {only_b}, p = {pval:.2f}; success "
            f"difference {diff:+.0%} [{dlo:+.0%}, {dhi:+.0%}]; cost {ca / cb:.2f}x; "
            f"median time {ta / tb:.2f}x."
        )
    out += [
        "",
        "By suite (successes out of tasks):",
        "",
        "| suite | " + " | ".join(ARMS) + " |",
        "|---|---|---|---|",
    ]
    for suite in sorted({k[0] for k in paired}):
        ks = [k for k in paired if k[0] == suite]
        out.append(
            f"| {suite} ({len(ks)}) | "
            + " | ".join(str(sum(by[(a, *k)]["success"] for k in ks)) for a in ARMS)
            + " |"
        )
    disagree = [k for k in paired if len({by[(a, *k)]["success"] for a in ARMS}) > 1]
    out += ["", "Tasks where the arms disagree:", ""]
    for k in disagree:
        cells = ", ".join(f"{a} {'ok' if by[(a, *k)]['success'] else 'FAIL'}" for a in ARMS)
        s = by[("sancho", *k)]
        out.append(
            f"- `{k[0]}/{k[1]}`: {cells}; sancho window {s['window']}, "
            f"misses {s['misses']}, loads {s['loads']}"
        )
    text = "\n".join(out)
    print(text)
    pathlib.Path(path).with_suffix(".md").write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
