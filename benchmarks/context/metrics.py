"""What an arm freed, what it lost of what the future used, and what a decider arm costs.

Per unit (one context of one session) and arm:

- `freed`: history tool-result characters taken out / all of them. A stub or a drop frees
  the whole result, a fastjev truncation frees what its note does not keep. The stub line
  itself (about 150 characters) is not subtracted.
- `recall`: NEEDED results kept literally / NEEDED results. A stubbed result counts as lost
  here even when it is archived; `recoverable` counts, separately, the needed results an
  archiving arm stubbed (the model can `Read` them back verbatim).
- `needed_chars_lost`: characters of NEEDED results not kept literally.
- `token_recall` (Amendment 1, secondary): of the distinctive tokens the future used from any
  history result, the share still present in at least one result the arm kept.

Pooled figures sum over units; confidence intervals are percentile bootstraps over units
(2,000 resamples, fixed seed), because results inside one session are not independent. The
paired comparison resamples the same units for both arms. McNemar is reported on the pooled
needed results for the record and is anti-conservative for the same reason.

Cost: a decider arm's Jev input is estimated from the states the points would send, built
here without calling anything, at `CHARS_PER_TOKEN` characters a token (3, the package's own
conservative figure for Jev) and the package's price per million input tokens.
"""

from __future__ import annotations

import json
import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import Any

from sanchopanza.context.rules import triage_rules
from sanchopanza.context.transcript import Call, task_of
from sanchopanza.points import context as points
from sanchopanza.points.hierarchy import MAX_ROUNDS, groups
from sanchopanza.providers.jev import DEFAULT_PRICE_PER_MTOK

BOOT = 2000
SEED = 20260928
CHARS_PER_TOKEN = 3.0
SURVIVAL = 0.5  # expected share of tournament candidates past round one, for the estimate


def freed_chars(call: Call, action: str) -> int:
    if action == "keep":
        return 0
    if action == "truncate":
        return max(0, call.chars - len(points.fastjev_truncated(call.result, call.is_error)))
    return call.chars


def unit_metrics(
    labels: Mapping[str, Mapping[str, Any]],
    calls: Sequence[Call],
    actions: Mapping[str, str],
    *,
    archives: bool,
    label_key: str = "needed",
) -> dict[str, Any]:
    total = freed = needed = kept = lost_chars = recoverable = 0
    used: set[str] = set()
    covered: set[str] = set()
    for call in calls:
        hits = set(labels[call.id].get("hits", ()))
        used |= hits
        if actions.get(call.id, "keep") == "keep":
            covered |= hits
        action = actions.get(call.id, "keep")
        total += call.chars
        freed += freed_chars(call, action)
        if not labels[call.id][label_key]:
            continue
        needed += 1
        if action == "keep":
            kept += 1
        else:
            lost_chars += call.chars
            recoverable += archives and action == "stub"
    return {
        "chars": total,
        "freed_chars": freed,
        "freed": freed / total if total else 0.0,
        "needed": needed,
        "needed_kept": kept,
        "recall": kept / needed if needed else None,
        "needed_chars_lost": lost_chars,
        "recoverable": recoverable,
        "tokens_used": len(used),
        "tokens_covered": len(used & covered),
    }


def pooled(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    chars = sum(r["chars"] for r in rows)
    needed = sum(r["needed"] for r in rows)
    recalls = [r["recall"] for r in rows if r["recall"] is not None]
    used = sum(r.get("tokens_used", 0) for r in rows)
    return {
        "units": len(rows),
        "freed": sum(r["freed_chars"] for r in rows) / chars if chars else 0.0,
        "recall": sum(r["needed_kept"] for r in rows) / needed if needed else None,
        "mean_unit_recall": sum(recalls) / len(recalls) if recalls else None,
        "needed": needed,
        "needed_lost": needed - sum(r["needed_kept"] for r in rows),
        "needed_chars_lost": sum(r["needed_chars_lost"] for r in rows),
        "recoverable": sum(r["recoverable"] for r in rows),
        "token_recall": (sum(r.get("tokens_covered", 0) for r in rows) / used if used else None),
    }


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[index]


def bootstrap(rows: Sequence[Mapping[str, Any]], key: str, *, seed: int = SEED) -> list | None:
    """95 % percentile interval of a pooled figure, resampling units."""
    if not rows:
        return None
    rng = random.Random(seed)
    values = []
    for _ in range(BOOT):
        sample = [rows[rng.randrange(len(rows))] for _ in rows]
        value = pooled(sample)[key]
        if value is not None:
            values.append(value)
    if not values:
        return None
    return [round(_percentile(values, 0.025), 4), round(_percentile(values, 0.975), 4)]


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    out = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in pooled(rows).items()}
    out["freed_ci"] = bootstrap(rows, "freed")
    out["recall_ci"] = bootstrap(rows, "recall")
    out["token_recall_ci"] = bootstrap(rows, "token_recall")
    return out


def mcnemar(a_only: int, b_only: int) -> float:
    """Exact two-sided binomial p for discordant pairs."""
    n = a_only + b_only
    if n == 0:
        return 1.0
    k = min(a_only, b_only)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2 * tail)


def paired(
    a: Sequence[Mapping[str, Any]],
    b: Sequence[Mapping[str, Any]],
    a_kept: Sequence[set[str]],
    b_kept: Sequence[set[str]],
    needed: Sequence[set[str]],
    *,
    seed: int = SEED,
) -> dict[str, Any]:
    """Arm a against arm b on the same units: recall and freed differences, bootstrapped."""
    rng = random.Random(seed)
    n = len(a)
    if n == 0:
        return {"units": 0}

    def diff(ids: Sequence[int]) -> tuple[float | None, float]:
        pa, pb = pooled([a[i] for i in ids]), pooled([b[i] for i in ids])
        recall = None if pa["recall"] is None else pa["recall"] - pb["recall"]
        return recall, pa["freed"] - pb["freed"]

    recall_d, freed_d = diff(range(n))
    samples = [diff([rng.randrange(n) for _ in range(n)]) for _ in range(BOOT)]
    recalls = [r for r, _ in samples if r is not None]
    a_only = sum(len((ka - kb) & nd) for ka, kb, nd in zip(a_kept, b_kept, needed, strict=True))
    b_only = sum(len((kb - ka) & nd) for ka, kb, nd in zip(a_kept, b_kept, needed, strict=True))
    return {
        "units": n,
        "recall_diff": None if recall_d is None else round(recall_d, 4),
        "recall_diff_ci": (
            [round(_percentile(recalls, 0.025), 4), round(_percentile(recalls, 0.975), 4)]
            if recalls
            else None
        ),
        "freed_diff": round(freed_d, 4),
        "freed_diff_ci": [
            round(_percentile([f for _, f in samples], 0.025), 4),
            round(_percentile([f for _, f in samples], 0.975), 4),
        ],
        "units_a_freed_at_least_b": sum(
            x["freed"] >= y["freed"] for x, y in zip(a, b, strict=True)
        ),
        "needed_kept_only_by_a": a_only,
        "needed_kept_only_by_b": b_only,
        "mcnemar_p": round(mcnemar(a_only, b_only), 4),
    }


# --- cost estimate, no call ------------------------------------------------------------------


def _tokens(state: Any, questions: Mapping[str, Any]) -> int:
    body = json.dumps(
        {"state": state, "questions": {k: asdict(q) for k, q in questions.items()}},
        ensure_ascii=False,
        default=str,
    )
    return math.ceil(len(body) / CHARS_PER_TOKEN)


def estimate_sanchopanza(messages: Sequence[Mapping[str, Any]], calls: Sequence[Call]) -> dict:
    verdicts = triage_rules(messages, calls)
    ask = [c.id for c in calls if verdicts[c.id].action == "ask"]
    hidden = {c.id: verdicts[c.id].reason for c in calls if verdicts[c.id].action == "stub"}
    if not ask:
        return {"asked": 0, "calls": 0, "calls_high": 0, "tokens": 0, "tokens_high": 0}
    task = task_of(messages)
    per_call = []
    for g in groups(len(ask), points.CALL_MAX):
        state, qs = points.prune_questions(
            task, messages, calls, candidates=[ask[i] for i in g], hidden=hidden
        )
        per_call.append(_tokens(state, qs))
    if len(ask) <= points.CALL_MAX:
        one = per_call[0]
        return {"asked": len(ask), "calls": 1, "calls_high": 1, "tokens": one, "tokens_high": one}
    # Past the cap: round one, then a final over the survivors (expected: half of them);
    # at worst every round up to MAX_ROUNDS asks every group again, then the final.
    mean = sum(per_call) / len(per_call)
    final = math.ceil(SURVIVAL * len(ask) / points.CALL_MAX)
    high = len(per_call) * (MAX_ROUNDS + 1)
    return {
        "asked": len(ask),
        "calls": len(per_call) + final,
        "calls_high": high,
        "tokens": round(sum(per_call) + final * mean),
        "tokens_high": round(high * mean),
    }


def estimate_tournament(messages: Sequence[Mapping[str, Any]], calls: Sequence[Call]) -> dict:
    """The experimental arm: `estimate_sanchopanza`'s arithmetic over every non-pinned call."""
    from sanchopanza.context.compact import _structural

    ask = [c.id for c in calls if _structural(c, len(messages), 6) is None]
    if not ask:
        return {"asked": 0, "calls": 0, "calls_high": 0, "tokens": 0, "tokens_high": 0}
    task = task_of(messages)
    per_call = []
    for g in groups(len(ask), points.CALL_MAX):
        state, qs = points.prune_questions(task, messages, calls, candidates=[ask[i] for i in g])
        per_call.append(_tokens(state, qs))
    if len(ask) <= points.CALL_MAX:
        one = per_call[0]
        return {"asked": len(ask), "calls": 1, "calls_high": 1, "tokens": one, "tokens_high": one}
    mean = sum(per_call) / len(per_call)
    final = math.ceil(SURVIVAL * len(ask) / points.CALL_MAX)
    high = len(per_call) * (MAX_ROUNDS + 1)
    return {
        "asked": len(ask),
        "calls": len(per_call) + final,
        "calls_high": high,
        "tokens": round(sum(per_call) + final * mean),
        "tokens_high": round(high * mean),
    }


def estimate_fastjev(messages: Sequence[Mapping[str, Any]], calls: Sequence[Call]) -> dict:
    total = len(messages)
    candidates = [i for i, c in enumerate(calls) if not points.fastjev_pinned(c, total)]
    batches = [
        candidates[i : i + points.CALL_MAX] for i in range(0, len(candidates), points.CALL_MAX)
    ]
    tokens = sum(_tokens(*points.fastjev_questions(messages, calls, b)) for b in batches)
    return {
        "asked": len(candidates),
        "calls": len(batches),
        "calls_high": len(batches),
        "tokens": tokens,
        "tokens_high": tokens,
    }


def usd(tokens: float) -> float:
    return tokens * DEFAULT_PRICE_PER_MTOK / 1_000_000
