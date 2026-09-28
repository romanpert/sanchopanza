"""The registered criteria of Amendment 2 (`prereg.md`), computed from the simulations' rows.

Arrival (rows: one per history tool result; only results the arrival gate sends to the
decider, `eligible`, count):

- saving: 1 - characters the agent receives (cut text plus the arrival header with an
  80-character archive path, or the whole result) / original characters, pooled;
- for NEEDED results: `all_kept`, every future-used token present literally; token retention,
  tokens kept / tokens; for arrival and for each baseline at the same characters per result;
- A1: token retention, arrival minus head+tail, paired bootstrap over units, lower bound > 0;
- A2: saving >= 0.40; A3: arrival's all-token retention >= 0.90.

Recall (rows: one per unit): R1: hit rate of the Jev recall minus BM25@1's, paired bootstrap
lower bound > 0, AND the Jev recall injected no more characters than BM25@1; R2: the same
against BM25@3, descriptive. The leakage audit (a hit whose query already held a needed token)
must be 0, or the recall run is invalid.

Criteria are judged on `test`; `dev` is reported as a sanity check only.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping, Sequence
from typing import Any

BOOT = 2000
SEED = 20260928
ARRIVAL_ARMS = ("arrival", "head_tail", "bm25", "random")
PATH_CHARS = 80  # a real archive path in the header, in place of the simulation's "ARCHIVE"


def _groups(rows: Sequence[Mapping[str, Any]]) -> list[list[Mapping[str, Any]]]:
    by: dict[str, list[Mapping[str, Any]]] = {}
    for r in rows:
        by.setdefault(r["unit"], []).append(r)
    return list(by.values())


def _boot(groups: Sequence[Sequence[Any]], stat: Callable[[list[Any]], float | None]) -> list:
    if not groups:
        return [None, None]
    rng = random.Random(SEED)
    values = []
    for _ in range(BOOT):
        sample = [x for _ in groups for x in groups[rng.randrange(len(groups))]]
        v = stat(sample)
        if v is not None:
            values.append(v)
    if not values:
        return [None, None]
    values.sort()
    return [round(values[int(0.025 * len(values))], 4), round(values[int(0.975 * len(values))], 4)]


def _retention(rows: Sequence[Mapping[str, Any]], arm: str) -> float | None:
    tokens = sum(r["tokens"] for r in rows)
    return sum(r[f"{arm}_tokens_kept"] for r in rows) / tokens if tokens else None


def _all_kept(rows: Sequence[Mapping[str, Any]], arm: str) -> float | None:
    return sum(r[f"{arm}_tokens_kept"] == r["tokens"] for r in rows) / len(rows) if rows else None


def _received(r: Mapping[str, Any]) -> int:
    return r["shown"] + (PATH_CHARS if r["cut"] else 0)


def arrival_split(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    eligible = [r for r in rows if r["eligible"]]
    needed = [r for r in eligible if r["needed"]]
    chars = sum(r["chars"] for r in eligible)
    out: dict[str, Any] = {
        "eligible_results": len(eligible),
        "cut": sum(r["cut"] for r in eligible),
        "needed": len(needed),
        "needed_cut": sum(r["cut"] for r in needed),
        "saving": round(1 - sum(_received(r) for r in eligible) / chars, 4) if chars else None,
        "saving_ci": _boot(
            _groups(eligible),
            lambda s: 1 - sum(_received(r) for r in s) / sum(r["chars"] for r in s),
        ),
        "saving_without_header": round(1 - sum(r["budget"] for r in eligible) / chars, 4)
        if chars
        else None,
        "arms": {},
        "recoverable": sum(r["cut"] and r["arrival_tokens_kept"] < r["tokens"] for r in needed),
    }
    for arm in ARRIVAL_ARMS:
        out["arms"][arm] = {
            "token_retention": _round(_retention(needed, arm)),
            "all_kept": _round(_all_kept(needed, arm)),
            "all_kept_ci": _boot(_groups(needed), lambda s, a=arm: _all_kept(s, a)),
        }
    for arm in ARRIVAL_ARMS[1:]:
        diff = _diff(needed, arm)
        out["arms"][arm]["arrival_minus_this_retention"] = _round(diff(needed))
        out["arms"][arm]["arrival_minus_this_retention_ci"] = _boot(_groups(needed), diff)
    return out


def _diff(rows: Sequence[Mapping[str, Any]], arm: str) -> Callable[[list[Any]], float | None]:
    def stat(sample: list[Any]) -> float | None:
        a, b = _retention(sample, "arrival"), _retention(sample, arm)
        return None if a is None or b is None else a - b

    return stat


def _round(x: float | None) -> float | None:
    return None if x is None else round(x, 4)


def judge_arrival(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    splits = {s: arrival_split([r for r in rows if r["split"] == s]) for s in ("dev", "test")}
    t = splits["test"]
    ht = t["arms"]["head_tail"]
    lower = ht["arrival_minus_this_retention_ci"][0]
    verdicts = {
        "A1": {
            "pass": lower is not None and lower > 0,
            "retention_diff_vs_head_tail": ht["arrival_minus_this_retention"],
            "ci": ht["arrival_minus_this_retention_ci"],
        },
        "A2": {"pass": t["saving"] is not None and t["saving"] >= 0.40, "saving": t["saving"]},
        "A3": {
            "pass": t["arms"]["arrival"]["all_kept"] is not None
            and t["arms"]["arrival"]["all_kept"] >= 0.90,
            "all_kept": t["arms"]["arrival"]["all_kept"],
        },
    }
    return {"splits": splits, "test_verdicts": verdicts}


def _rate(rows: Sequence[Mapping[str, Any]], arm: str) -> float | None:
    n = sum(r["arms"][arm]["needed_masked"] for r in rows)
    return sum(r["arms"][arm]["hits"] for r in rows) / n if n else None


def recall_split(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    groups = [[r] for r in rows]
    out: dict[str, Any] = {"units": len(rows), "arms": {}}
    for arm in ("jev", "bm25@1", "bm25@3"):
        out["arms"][arm] = {
            "needed_masked": sum(r["arms"][arm]["needed_masked"] for r in rows),
            "hits": sum(r["arms"][arm]["hits"] for r in rows),
            "hit_rate": _round(_rate(rows, arm)),
            "literal_hits": sum(r["arms"][arm]["literal_hits"] for r in rows),
            "injected": sum(r["arms"][arm]["injected"] for r in rows),
            "injected_chars": sum(r["arms"][arm]["injected_chars"] for r in rows),
            "leaks": sum(
                r["arms"][arm]["leak_prompt"] + r["arms"][arm]["leak_assistant"] for r in rows
            ),
        }
    for arm in ("bm25@1", "bm25@3"):

        def stat(sample: list[Any], a: str = arm) -> float | None:
            x, y = _rate(sample, "jev"), _rate(sample, a)
            return None if x is None or y is None else x - y

        out["arms"][arm]["jev_minus_this"] = _round(stat(list(rows)))
        out["arms"][arm]["jev_minus_this_ci"] = _boot(groups, stat)
    return out


def judge_recall(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    splits = {s: recall_split([r for r in rows if r["split"] == s]) for s in ("dev", "test")}
    t = splits["test"]["arms"]
    leaks = sum(splits[s]["arms"]["jev"]["leaks"] for s in splits)
    lower = t["bm25@1"]["jev_minus_this_ci"][0]
    chars_ok = t["jev"]["injected_chars"] <= t["bm25@1"]["injected_chars"]
    return {
        "splits": splits,
        "leakage_audit": leaks,
        "valid": leaks == 0,
        "test_verdicts": {
            "R1": {
                "pass": leaks == 0 and lower is not None and lower > 0 and chars_ok,
                "hit_rate_diff_vs_bm25@1": t["bm25@1"]["jev_minus_this"],
                "ci": t["bm25@1"]["jev_minus_this_ci"],
                "injected_chars_jev": t["jev"]["injected_chars"],
                "injected_chars_bm25@1": t["bm25@1"]["injected_chars"],
                "chars_within": chars_ok,
            },
            "R2_descriptive": {
                "hit_rate_diff_vs_bm25@3": t["bm25@3"]["jev_minus_this"],
                "ci": t["bm25@3"]["jev_minus_this_ci"],
                "injected_chars_bm25@3": t["bm25@3"]["injected_chars"],
            },
        },
    }


def judge(piece: str, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return judge_arrival(rows) if piece == "arrival" else judge_recall(rows)
