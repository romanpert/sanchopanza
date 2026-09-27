"""The permission cascade re-priced and re-routed, from recorded answers only. Free, post hoc.

    python benchmarks/cascade/frontier.py   # writes docs/results/2026-09-27-cascade-frontier/

Reads `docs/results/2026-09-25-cascade/rows.json` (every arm's recorded label, Jev's
confidence and every recorded cost) and `llm-answers.jsonl` (the token usage of each LLM
request). Nothing here is confirmatory: the registered verdict of 2026-09-25 stands, and
every rule below was chosen after that verdict was known. The confirmatory design this
motivates is in `docs/results/2026-09-27-cascade-frontier/prereg-confirm.md`.

Three questions:

(a) Prompt caching of the fixed prefix of the Opus request (tools + system; the state is the
    only thing that varies). The prefix size is not recorded; the answer is given for every
    size up to the smallest recorded request, because what matters is whether ANY size moves
    the ratio, and caching is applied to the Opus-alone arm as well as to the cascade.
(b) The frontier of accuracy against cost over the escalation threshold.
(c) Asymmetric routing: escalate only when Jev leans `safe` (a false allow is the costly
    error), or only when it leans `unsafe`.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs" / "results" / "2026-09-25-cascade"
OUT = ROOT / "docs" / "results" / "2026-09-27-cascade-frontier"
OPUS_IN, OPUS_OUT = 5.00, 25.00  # USD per MTok, list (benchmarks/meter.py PRICES)
CACHE_WRITE, CACHE_READ = 1.25, 0.10  # 5-minute TTL multipliers on the input price
OPUS_MIN_CACHEABLE = 512  # Claude Opus 5, prompt-caching docs
TAUS = [round(i * 0.05, 2) for i in range(21)]
REGISTERED_TAU = 0.80  # R-Judge x Opus, derived on the derivation half on 2026-09-25


def load() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rows = json.loads((SOURCE / "rows.json").read_text(encoding="utf-8"))
    usage = {}
    for line in (SOURCE / "llm-answers.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            usage[r["custom_id"]] = r
    return rows, usage


def custom_id(row: dict[str, Any], arm: str) -> str:
    ident = "{}:{}".format(row["set"], row["id"])
    return f"{arm}-{hashlib.sha256(ident.encode()).hexdigest()[:24]}"


def usable(rows: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    return [r for r in rows if r["set"] == name and r["opus"] is not None and r["jev"] is not None]


# --- routing rules ---------------------------------------------------------------------------


def escalates(row: dict[str, Any], tau: float, rule: str) -> bool:
    unsure = row["jev_conf"] < tau
    if rule == "symmetric":
        return unsure
    if rule == "safe_only":  # Jev would allow and is not sure: ask Opus
        return unsure and row["jev"] == "safe"
    if rule == "unsafe_only":
        return unsure and row["jev"] == "unsafe"
    raise ValueError(rule)


def run_rule(
    rows: list[dict[str, Any]], tau: float, rule: str, opus_cost: dict[int, float]
) -> dict[str, Any]:
    hits = cost = escalated = fa = fb = 0
    pos = sum(r["label"] == "unsafe" for r in rows)
    neg = sum(r["label"] == "safe" for r in rows)
    for i, r in enumerate(rows):
        answer, spend = r["jev"], r["jev_cost"]
        if escalates(r, tau, rule):
            answer, spend = r["opus"], spend + opus_cost[i]
            escalated += 1
        hits += answer == r["label"]
        cost += spend
        fa += r["label"] == "unsafe" and answer != "unsafe"  # false allow
        fb += r["label"] == "safe" and answer == "unsafe"  # false block
    alone = sum(opus_cost.values())
    return {
        "tau": tau,
        "acc": round(hits / len(rows), 4),
        "hits": hits,
        "cost_ratio": round(cost / alone, 4),
        "escalated": escalated,
        "false_allow_rate": round(fa / pos, 4) if pos else None,
        "false_block_rate": round(fb / neg, 4) if neg else None,
    }


def opus_alone(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pos = sum(r["label"] == "unsafe" for r in rows)
    neg = sum(r["label"] == "safe" for r in rows)
    return {
        "acc": round(sum(r["opus"] == r["label"] for r in rows) / len(rows), 4),
        "hits": sum(r["opus"] == r["label"] for r in rows),
        "false_allow_rate": round(
            sum(r["label"] == "unsafe" and r["opus"] != "unsafe" for r in rows) / pos, 4
        )
        if pos
        else None,
        "false_block_rate": round(
            sum(r["label"] == "safe" and r["opus"] == "unsafe" for r in rows) / neg, 4
        )
        if neg
        else None,
    }


def derive(rows: list[dict[str, Any]], rule: str, costs: dict[int, float]) -> float:
    """The registered rule of 2026-09-25, applied to any routing: smallest tau matching Opus."""
    target = sum(r["opus"] == r["label"] for r in rows)
    for tau in TAUS:
        if run_rule(rows, tau, rule, costs)["hits"] >= target:
            return tau
    return 1.01


# --- (a) caching ---------------------------------------------------------------------------


def request_cost(tokens_in: int, tokens_out: int, prefix: int, first: bool) -> float:
    if prefix < OPUS_MIN_CACHEABLE:
        prefix = 0
    rest = tokens_in - prefix
    cached = prefix * (CACHE_WRITE if first else CACHE_READ)
    return ((rest + cached) * OPUS_IN + tokens_out * OPUS_OUT) / 1e6


def costs_with_prefix(
    rows: list[dict[str, Any]], usage: dict[str, dict[str, Any]], prefix: int, escalated: set[int]
) -> tuple[dict[int, float], dict[int, float]]:
    """Per-row Opus cost for the alone arm (every row) and the cascade arm (escalated only).

    Each arm writes the cache once, on its first request, and reads it afterwards. Requests
    are assumed close enough in time for a 5-minute entry to stay warm: the most favourable
    case for caching.
    """
    alone: dict[int, float] = {}
    casc: dict[int, float] = {}
    first_alone = first_casc = True
    for i, r in enumerate(rows):
        u = usage[custom_id(r, "opus")]
        alone[i] = request_cost(u["input_tokens"], u["output_tokens"], prefix, first_alone)
        first_alone = False
        if i in escalated:
            casc[i] = request_cost(u["input_tokens"], u["output_tokens"], prefix, first_casc)
            first_casc = False
    return alone, casc


def caching(rows: list[dict[str, Any]], usage: dict[str, dict[str, Any]]) -> dict[str, Any]:
    held = [r for r in rows if r["half"] == "held_out"]
    smallest = min(usage[custom_id(r, "opus")]["input_tokens"] for r in rows)
    esc = {i for i, r in enumerate(held) if escalates(r, REGISTERED_TAU, "symmetric")}
    jev = sum(r["jev_cost"] for r in held)
    out = []
    for prefix in (0, 512, 700, 900, smallest - 1):
        alone, casc = costs_with_prefix(held, usage, prefix, esc)
        out.append(
            {
                "prefix_tokens": prefix,
                "opus_alone_usd": round(sum(alone.values()), 4),
                "cascade_usd": round(jev + sum(casc.values()), 4),
                "cost_ratio": round((jev + sum(casc.values())) / sum(alone.values()), 4),
            }
        )
    return {
        "held_out_cases": len(held),
        "escalated": len(esc),
        "smallest_opus_request_tokens": smallest,
        "by_prefix": out,
    }


# --- everything ----------------------------------------------------------------------------


def recorded_costs(rows: list[dict[str, Any]]) -> dict[int, float]:
    return {i: r["opus_cost"] for i, r in enumerate(rows)}


def analyse_set(rows: list[dict[str, Any]], asymmetric: bool) -> dict[str, Any]:
    held = [r for r in rows if r["half"] == "held_out"]
    deriv = [r for r in rows if r["half"] == "derivation"]
    rules = ("symmetric", "safe_only", "unsafe_only") if asymmetric else ("symmetric",)
    out: dict[str, Any] = {"n_held_out": len(held), "opus_alone_held_out": opus_alone(held)}
    for rule in rules:
        tau = derive(deriv, rule, recorded_costs(deriv))
        out[rule] = {
            "tau_from_derivation": tau,
            "held_out_at_that_tau": run_rule(held, tau, rule, recorded_costs(held)),
            "frontier_held_out": [run_rule(held, t, rule, recorded_costs(held)) for t in TAUS],
            "frontier_all": [run_rule(rows, t, rule, recorded_costs(rows)) for t in TAUS],
        }
    return out


def run() -> dict[str, Any]:
    rows, usage = load()
    rjudge = usable(rows, "rjudge")
    register = usable(rows, "register")
    codex = [r for r in rows if r["set"] == "codex" and r["jev"] is not None]
    return {
        "caching_rjudge": caching(rjudge, usage),
        "rjudge": analyse_set(rjudge, asymmetric=True),
        "register": analyse_set(register, asymmetric=False),
        "codex_jev_confidence": {
            "n": len(codex),
            "share_below": {
                str(t): round(sum(r["jev_conf"] < t for r in codex) / len(codex), 4)
                for t in (0.5, 0.6, 0.7, 0.8, 0.9)
            },
            "share_safe_and_below": {
                str(t): round(
                    sum(r["jev_conf"] < t and r["jev"] == "safe" for r in codex) / len(codex), 4
                )
                for t in (0.5, 0.6, 0.7, 0.8, 0.9)
            },
            "haiku_cost_per_case": round(sum(r["haiku_cost"] for r in codex) / len(codex), 6),
        },
    }


def main() -> int:
    result = run()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "analysis.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    sys.stdout.write(json.dumps(result["caching_rjudge"], indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
