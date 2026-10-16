"""F2's analysis (docs/results/2026-10-16-memory-f2/prereg.md) and the pilot's automatic gate.

Triples are (scene, model, repetition) with all three arms run (no `cut`, every session on the
pinned Claude Code and the run's model). "Kept all" is task and fact and decision. Criteria, per
model: S not worse than H (the lower bound of the one-sided 95 % Tango score interval for the
paired difference S - H above -MARGIN) and, only if it holds, S better than N0 (one-sided exact
McNemar, p < 0.05); no harm (S's tests no more than floor(MARGIN x triples) below H's; S second
sessions sent back by a rule other than the scene's own C at most 5 %). Everything else is
reported, never deciding.

    python benchmarks/memory_carry/handoff_analyze.py RUN_DIR [--gate]
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter
from math import comb
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from handoff_cost import own_row  # noqa: E402
from scenes_handoff import HANDOFF  # noqa: E402

MARGIN = 0.125
ALPHA = 0.05
Z_ONE_SIDED_95 = 1.6448536269514722
SENDBACK_RATE = 0.05
MIN_TRIPLES = {"sonnet": 40, "opus": 20}  # fewer run: "sin veredicto"
ARMS = ("N0", "H", "S")
TOKEN_KINDS = ("input", "output", "cache_read", "cache_write")


# ---- statistics ----------------------------------------------------------------------------------


def tango_score(x: int, y: int, n: int, delta: float) -> float:
    """Tango's (1998) score statistic for H0: p(A) - p(B) = delta on paired binary data, with x
    pairs where only A succeeded and y where only B did (his b and c; his eq. 24-26 with his
    Delta = -delta)."""
    b = -x - y + (2 * n - x + y) * delta
    c = -y * delta * (1 - delta)
    q21 = (math.sqrt(max(b * b - 8 * n * c, 0.0)) - b) / (4 * n)
    var = n * (2 * q21 + delta * (1 - delta))
    num = x - y - n * delta
    if var <= 0:
        return math.inf if num > 0 else -math.inf if num < 0 else 0.0
    return num / math.sqrt(var)


def tango_bound(x: int, y: int, n: int, z: float, lower: bool = True) -> float:
    """One limit of Tango's score interval: the delta where the statistic equals z (lower) or
    -z (upper), by bisection on (-1, 1) (the statistic falls as delta rises)."""
    if n <= 0:
        return -1.0 if lower else 1.0
    lo, hi = -1.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        s = tango_score(x, y, n, mid)
        if (s > z) if lower else (s >= -z):
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def mcnemar(a_only: int, b_only: int) -> float:
    """One-sided exact p that A succeeds more often than B."""
    k = a_only + b_only
    return sum(comb(k, i) for i in range(a_only, k + 1)) / 2**k if k else 1.0


# ---- rows ----------------------------------------------------------------------------------------


def ran(row: dict[str, Any] | None) -> bool:
    return bool(row) and not row.get("cut") and not row.get("limit_hit") and \
        isinstance(row.get("kept_all"), bool)  # fmt: skip


def triples(rows: list[dict[str, Any]]) -> dict[tuple[str, str, int], dict[str, dict[str, Any]]]:
    out: dict[tuple[str, str, int], dict[str, dict[str, Any]]] = {}
    for r in rows:
        out.setdefault((r["scene"], r["model"], r["repeat"]), {})[r["arm"]] = r
    return out


def own_sendbacks(row: dict[str, Any], run: Path | None) -> int:
    """S's second session sent back by a rule other than the scene's own C (from hook-log)."""
    if not row.get("folder"):
        return 0
    log = Path(row["folder"]) / "hook-log.jsonl"
    if not log.exists():
        return 0
    session, false = 0, 0
    for line in log.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("event") == "SessionStart" and event.get("source") == "startup":
            session += 1
        if event.get("event") == "rules" and session >= 2:
            false += sum(1 for t in event.get("broken") or []
                         if HANDOFF[row["scene"]]["rule"] not in str(t))  # fmt: skip
    return int(false > 0)


def median(values: list[float]) -> float | None:
    return round(statistics.median(values), 6) if values else None


def compare(done: dict[Any, dict[str, dict[str, Any]]], a: str, b: str) -> dict[str, Any]:
    a_only = sum(1 for t in done.values() if t[a]["kept_all"] and not t[b]["kept_all"])
    b_only = sum(1 for t in done.values() if t[b]["kept_all"] and not t[a]["kept_all"])
    n = len(done)
    return {
        "a": a,
        "b": b,
        "triples": n,
        "a_only": a_only,
        "b_only": b_only,
        "difference": round((a_only - b_only) / n, 4) if n else None,
        "tango_lower_95_raw": tango_bound(a_only, b_only, n, Z_ONE_SIDED_95),
        "tango_lower_95": round(tango_bound(a_only, b_only, n, Z_ONE_SIDED_95), 4),
        "p_a_better": mcnemar(a_only, b_only),
        "p_b_better": mcnemar(b_only, a_only),
    }


def analyse(rows: list[dict[str, Any]], model: str, run: Path | None = None,
            planned: list[tuple[str, str, int]] | None = None) -> dict[str, Any]:  # fmt: skip
    mine = [own_row(r) for r in rows if r["model"] == model]  # H at its handoff's own cost
    all_t = triples(mine)
    done = {k: t for k, t in all_t.items() if all(ran(t.get(arm)) for arm in ARMS)}
    keys = set(planned or []) | set(all_t)
    not_run = sorted(f"{k[0]} r{k[2]}" for k in keys if k not in done)
    n = len(done)
    count = {arm: {c: sum(bool(t[arm].get(f"{c}_pass")) for t in done.values())
                   for c in ("task", "fact", "decision", "intact", "tests")}
             | {"kept_all": sum(t[arm]["kept_all"] for t in done.values())}
             for arm in ARMS}  # fmt: skip
    s_h, s_n0, h_n0 = compare(done, "S", "H"), compare(done, "S", "N0"), compare(done, "H", "N0")
    c1 = s_h["tango_lower_95_raw"] > -MARGIN
    c2 = s_n0["p_a_better"] < ALPHA
    harm_tests = count["S"]["tests"] >= count["H"]["tests"] - math.floor(MARGIN * n)
    false_sb = sum(own_sendbacks(t["S"], run) for t in done.values())
    harm_sb = false_sb <= SENDBACK_RATE * n
    enough = n >= MIN_TRIPLES.get(model, 0)
    criteria = {"1_s_not_worse_than_h": c1, "2_s_better_than_n0": c2 if c1 else None,
                "5a_tests": harm_tests, "5b_false_sendbacks": harm_sb,
                "false_sendbacks": false_sb}  # fmt: skip
    verdict = verdict_of(model, enough, c1, c2, harm_tests and harm_sb)
    return {"model": model, "triples": n, "not_run": not_run, "verdict": verdict,
            "criteria": criteria, "count": count, "S_vs_H": s_h, "S_vs_N0": s_n0,
            "H_vs_N0": h_n0, **reported(done), "touched": touched(mine),
            "not_run_reasons": dict(Counter(cut_kind(r) for r in mine if r.get("cut"))),
            **without_touched(done)}  # fmt: skip


def cut_kind(row: dict[str, Any]) -> str:
    """A NOT RUN row's reason without its details ("handoff: no text", "timeout", ...)."""
    cut = str(row.get("cut") or "")
    return cut if cut.startswith("handoff") else cut.split(":")[0].split(" (")[0]


def touched(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Per arm and session, how many sessions' tool calls named a harness file, by file."""
    out: dict[str, dict[str, int]] = {}
    for r in rows:
        for s in r.get("sessions") or []:
            for label in s.get("touched") or []:
                key = f"{r['arm']} {s.get('tag')}"
                out[key] = {**out.get(key, {}), label: out.get(key, {}).get(label, 0) + 1}
    return out


def s_second_touched(t: dict[str, dict[str, Any]]) -> bool:
    return any(s.get("tag") == "session-2" and s.get("touched")
               for s in t["S"].get("sessions") or [])  # fmt: skip


def without_touched(done: dict[Any, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    """Reported, never deciding: criteria 1 and 2 again without the triples whose S session 2
    touched a harness file (only when one did)."""
    kept = {k: t for k, t in done.items() if not s_second_touched(t)}
    if len(kept) == len(done):
        return {}
    s_h, s_n0 = compare(kept, "S", "H"), compare(kept, "S", "N0")
    return {
        "without_s2_touched": {
            "triples": len(kept),
            "dropped": sorted(f"{k[0]} r{k[2]}" for k in done if k not in kept),
            "1_s_not_worse_than_h": s_h["tango_lower_95_raw"] > -MARGIN,
            "2_s_better_than_n0": s_n0["p_a_better"] < ALPHA,
            "S_vs_H": s_h,
            "S_vs_N0": s_n0,
        }
    }


def verdict_of(model: str, enough: bool, c1: bool, c2: bool, c5: bool) -> str:
    """The prereg's verdict, the same for both models (Opus is labelled direction only): "S not
    worse than H" needs criteria 1 and 5; "S better than N0" needs 2 (read only when 1 holds)
    and 5; "not shown" otherwise; "sin veredicto" with too few triples."""
    if not enough:
        return "sin veredicto"
    claims = [text for ok, text in ((c1 and c5, "S not worse than H"),
                                    (c1 and c2 and c5, "S better than N0")) if ok]  # fmt: skip
    said = "; ".join(claims) or "not shown"
    return f"direction only: {said}" if model == "opus" else said


def reported(done: dict[Any, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    """Cost, tokens, the handoff's length and contents, memory and decider facts."""
    ts = list(done.values())
    cost = {arm: median([float(t[arm]["cost"]) + float(t[arm].get("jev_usd") or 0)
                         for t in ts]) for arm in ARMS}  # fmt: skip
    ratio = {f"S/{b}": median([(t["S"]["cost"] + float(t["S"].get("jev_usd") or 0))
                               / t[b]["cost"] for t in ts if t[b]["cost"]])
             for b in ("H", "N0")}  # fmt: skip
    tokens = {arm: {k: median([float((t[arm].get("tokens") or {}).get(k, 0)) for t in ts])
                    for k in TOKEN_KINDS} for arm in ARMS}  # fmt: skip
    hand = [t["H"].get("handoff") or {} for t in ts]
    chars = [int(h.get("chars") or 0) for h in hand]
    out_tokens = [int((h.get("tokens") or {}).get("output", 0)) for h in hand]
    names = Counter((bool(h.get("names", {}).get("C")), bool(h.get("names", {}).get("D")))
                    for h in hand)  # fmt: skip
    suspect = sum(1 for t in ts if float((t["H"].get("handoff") or {}).get(
        "cost_reported_total", (t["H"].get("handoff") or {}).get("cost")) or 0)
                  >= float((t["H"]["sessions"][0] or {}).get("cost") or 0) > 0)  # fmt: skip
    return {"cost_median_usd": cost, "cost_ratio_median": ratio, "tokens_median": tokens,
            "handoff_chars": {"median": median(chars), "max": max(chars, default=None)},
            "handoff_output_tokens": {"median": median(out_tokens),
                                      "max": max(out_tokens, default=None)},
            "handoff_names": {"C": sum(n for (c, _), n in names.items() if c),
                              "D": sum(n for (_, d), n in names.items() if d),
                              "both": names.get((True, True), 0)},
            "handoff_cost_at_least_session_1": suspect,
            "given_in_S": sum(1 for t in ts if t["S"].get("given")),
            "native_after_1": {arm: sum(1 for t in ts if t[arm].get("native_after_1"))
                               for arm in ARMS},
            "jev": {k: sum(int(t["S"].get(k) or 0) for t in ts)
                    for k in ("jev_decisions", "jev_failed")},
            "subagents": {arm: sum(int(t[arm].get("subagents") or 0) for t in ts)
                          for arm in ARMS},
            "crossed_midnight": sum(1 for t in ts for arm in ARMS
                                    if t[arm].get("crossed_midnight"))}  # fmt: skip


# ---- the pilot's gate ----------------------------------------------------------------------------


def gate(rows: list[dict[str, Any]], planned: list[tuple[str, str, str, int]]) -> dict[str, Any]:
    """The automatic gate after f2-pilot (prereg, "Pilot and its gate"). Every planned arm must
    have a row. (a) H's handoff was captured in every triple; (b) every check returned a boolean
    in every arm (no arm cut); (c) no scene has every arm failing `task`; (d) N0 did not keep
    all in every triple; (e) S's memory hook answered SessionStart in both sessions of every S
    arm. Passes only when all five hold. (a) means, in every H row: no cut at the handoff, a
    non-empty text, a reported cost, `context_carried` True (None fails) and session 2's first
    prompt in its transcript equal to the handoff byte for byte (`pasted_verbatim` True)."""
    by_key = {(r["scene"], r["model"], r["arm"], r["repeat"]): r for r in rows}
    missing = [f"{s} {a} r{r}" for s, m, a, r in planned if (s, m, a, r) not in by_key]
    have = [by_key[p] for p in planned if p in by_key]
    h_rows = [r for r in have if r["arm"] == "H"]
    a_ok = not missing and len(h_rows) == len({(s, r) for s, _, _, r in planned}) and all(
        not str(r.get("cut") or "").startswith("handoff")
        and (r.get("handoff") or {}).get("chars", 0) > 0
        and (r.get("handoff") or {}).get("cost_reported")
        and (r.get("handoff") or {}).get("context_carried") is True
        and r.get("pasted_verbatim") is True for r in h_rows)  # fmt: skip
    fields = ("tests_pass", "task_pass", "fact_pass", "decision_pass", "intact_pass", "kept_all")
    b_ok = not missing and all(not r.get("cut") and all(isinstance(r.get(f), bool)
                                                        for f in fields) for r in have)  # fmt: skip
    scenes = sorted({s for s, _, _, _ in planned})
    all_fail = [s for s in scenes if all(r.get("task_pass") is False for r in have
                                         if r["scene"] == s)
                and any(r["scene"] == s for r in have)]  # fmt: skip
    c_ok = not missing and not all_fail
    n0 = [r for r in have if r["arm"] == "N0"]
    d_ok = not missing and bool(n0) and not all(r.get("kept_all") is True for r in n0)
    s_rows = [r for r in have if r["arm"] == "S"]
    e_ok = not missing and bool(s_rows) and all(int(r.get("hook_starts") or 0) >= 2
                                                for r in s_rows)  # fmt: skip
    reasons = [text for ok, text in (
        (not missing, f"arms without a row: {', '.join(missing)}"),
        (a_ok, "(a) a handoff was not captured in every H triple"),
        (b_ok, "(b) a check did not return a boolean, or an arm was cut, in some arm"),
        (c_ok, f"(c) every arm failed task in: {', '.join(all_fail)}"),
        (d_ok, "(d) N0 kept all in every pilot triple: no room"),
        (e_ok, "(e) S's memory hook did not answer SessionStart in both sessions of every S arm"),
    ) if not ok]  # fmt: skip
    return {"pass": not reasons, "a": a_ok, "b": b_ok, "c": c_ok, "d": d_ok, "e": e_ok,
            "reasons": reasons, "arms": len(have), "planned": len(planned),
            "cut": {f"{r['scene']} {r['arm']} r{r['repeat']}": r["cut"] for r in have
                    if r.get("cut")}}  # fmt: skip


def gate_text(result: dict[str, Any]) -> str:
    head = "PASS: f2-sonnet may run" if result["pass"] else "FAIL: nothing larger runs"
    lines = [f"# F2 pilot gate: {head}", "",
             f"Arms with a row: {result['arms']} of {result['planned']}.", ""]  # fmt: skip
    lines += [f"- ({k}) {'holds' if result[k] else 'fails'}" for k in ("a", "b", "c", "d", "e")]
    lines += ["", *[f"- {r}" for r in result["reasons"]]]
    lines += [f"- cut: {k}: {v}" for k, v in result["cut"].items()]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run")
    parser.add_argument("--gate", action="store_true")
    args = parser.parse_args(argv)
    import handoff

    run = Path(args.run)
    rows = handoff.rows_of(run)
    name = run.name if run.name in handoff.RUNS else "f2-sonnet"
    plan = handoff.build_plan(name)
    if args.gate:
        result = gate(rows, plan)
        print(gate_text(result))
        print(json.dumps(result, indent=1))
        return 0 if result["pass"] else 5
    model = handoff.RUNS[name]["model"]
    planned = sorted({(s, m, r) for s, m, _, r in plan})
    print(json.dumps(analyse(rows, model, run, planned), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
