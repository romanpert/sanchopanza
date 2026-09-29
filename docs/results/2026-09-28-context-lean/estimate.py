"""`run.py estimate`: the expected list-price cost of each session, from the task sizes. Free.

A model of the prompt cache as Claude Code uses it (1-hour writes at 2x input, reads at 0.1x):
every call re-reads the context so far; what is new since the last call is written once. Phase
A starts cold (the system prompt names the work folder, so no task shares a prefix). Phase B
forks phase A with a warm prefix, except in L, whose extra MCP tool changes the tool list and
so rewrites the whole prefix on its first call. After a compaction N pays the summary call and
rewrites only the summary; K and L rewrite from the first masked result (early in phase A).
Token counts use 0.33 tokens per character (the middle of `tasks.RATIOS`). Sonnet 5 is priced
with Haiku's token counts: if its tokenizer counts more (up to ~1.35x on the newer tokenizer),
cost and the compaction point move with it; run a phase-A pilot before the Sonnet plan.
"""

# ruff: noqa: E501
from __future__ import annotations

import json
from statistics import mean
from typing import Any

import arms
import run as driver
import tasks as gen

R = 0.33
A_CALLS = 15
B_CALLS = 24
B_OUTPUT = 4_000
SUMMARY_OUTPUT = 3_000
SUMMARY_KEEPS = 4_000  # tokens of the native summary left in context


def _usd(p: dict[str, float], read: float, write: float, out: float) -> float:
    return (read * p["cr"] + write * p["cw1h"] + out * p["out"]) / 1e6


def _ramp(start: float, end: float, n: int) -> float:
    return sum(start + (end - start) * i / max(n - 1, 1) for i in range(n))


def session_costs(cal: dict[str, Any], p: dict[str, float]) -> dict[str, float]:
    c = cal[f"r{R:.2f}"]
    a_end, after_log, peak = c["a_end"], c["after_log"], c["N_end_with_edits"]
    base = gen.EMPTY_SESSION
    a = _usd(p, _ramp(base, a_end, A_CALLS) - a_end, a_end, gen.A_OUTPUT)
    fire = gen.THRESHOLD
    fired_frac = 0.6  # share of phase-B calls before the compaction
    before = _ramp(after_log, fire, int(B_CALLS * fired_frac))
    growth = fire - a_end
    n_after = B_CALLS - int(B_CALLS * fired_frac)
    n_post = base + SUMMARY_KEEPS
    n_cost = _usd(p, before + fire + _ramp(n_post, n_post + (peak - fire), n_after),
                  growth + SUMMARY_KEEPS + (peak - fire), B_OUTPUT + SUMMARY_OUTPUT)  # fmt: skip
    freed = R * (cal["a_result_chars"] + cal["log_chars"] + 4 * 1_300)
    m_post = fire - freed
    m_rewrite = m_post - base
    k_cost = _usd(p, before + _ramp(m_post, m_post + (peak - fire), n_after),
                  growth + m_rewrite + (peak - fire), B_OUTPUT)  # fmt: skip
    cut = R * (cal["log_chars"] - gen.ARRIVAL_KEPT)
    l_cost = k_cost - _usd(p, cut * B_CALLS * 0.6, 0, 0) + _usd(p, 0, a_end * 0.95, 0)
    return {"A": a, "N": n_cost, "K": k_cost, "L": l_cost}


def main() -> int:
    facts = gen.load_facts(driver.TASKS_DIR)
    cals = [gen.calibration(driver.TASKS_DIR / "repos" / t, f) for t, f in facts.items()]
    out: dict[str, Any] = {"ratio_tokens_per_char": R, "per_session_usd": {}, "plan_usd": {}, "caps_usd": {}}
    total = 0.0
    for model in arms.MODELS.values():
        per = [session_costs(c, model.prices) for c in cals[: model.tasks]]
        means = {k: round(mean(x[k] for x in per), 4) for k in ("A", *model.arms)}
        plan = sum(x["A"] + sum(x[arm] for arm in model.arms) for x in per)
        caps = model.tasks * (1 + len(model.arms)) * model.cap
        out["per_session_usd"][model.key] = means
        out["plan_usd"][model.key] = round(plan, 2)
        out["caps_usd"][model.key] = round(caps, 2)
        total += plan
    out["plan_usd"]["total"] = round(total, 2)
    out["already_spent_usd"] = driver.spent()
    print(json.dumps(out, indent=1))
    return 0
