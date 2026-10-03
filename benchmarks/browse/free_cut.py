"""Browse, development: where a "cut losses" rule would have fired on recorded free sessions.

python benchmarks/browse/free_cut.py                       # free: rules without Jev, cached Jev
python benchmarks/browse/free_cut.py --env-file PATH/.env  # asks Jev too, under 0.50 USD

Offline, on the calibration phase's sessions (`calib-sessions.jsonl`) and the pilot's
(`free-sessions.jsonl`), from Claude Code's own transcripts. For every session: its cost after
each API call (`free_trace.trajectory`), when the gold answer first reached the agent (in a
tool result) and when it first said it, and when its own final answer first reached it.

Then each candidate rule is replayed: the first call at which it would have stopped the
session. A stop on a wrong session saves what the session spent after it; a stop on a right
session loses the answer (and saves its money too, which is not a saving anyone wants). Rules:

- `budget`: spent a fraction f of the cap. The baseline any rule must beat.
- `oracle`: spent f of the cap and the gold answer has not reached the agent. Not a live rule
  (it reads the gold); the bound for a perfect "no candidate yet" detector.
- `jev_none`: spent f of the cap and Jev's `goal_met` (the loop guard's own question,
  `points.loop`, on what the agent has said and the result in front of it) has never reached
  t. A live rule.
- `jev_now`: as `jev_none`, but on the latest judgement only.
- `streak`: N WebSearch calls in a row with nothing else between (searching, not reading).
- `streak_jev`: N WebSearch calls since the last call Jev judged at or above t.

BrowseComp gold answers are decrypted into memory only: what is written here is task ids,
grades, call indices and dollars, never a question, a query or an answer.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import importlib.util
import json
import pathlib
import re
import statistics
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from sanchopanza.harness import loop_hook  # noqa: E402
from sanchopanza.points import loop as point  # noqa: E402
from sanchopanza.policy import Thresholds  # noqa: E402
from sanchopanza.providers import create  # noqa: E402
from sanchopanza.squire import Squire  # noqa: E402


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


calib = _load("browse_free_calib", HERE / "free_calib.py")
free = calib.free
trace = free.trace
nav = free.nav
OUT = free.RESULTS / "calib-cut.json"
JEV_CACHE = free.RESULTS / "calib-cut-jev.jsonl"  # state hash -> goal_met; no text
JEV_CEILING_USD = 0.50
JEV_CONCURRENCY = 6
SOURCES = {"calib": calib.SESSIONS, "pilot": free.SESSIONS}
FRACTIONS = (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
STREAKS = (3, 4, 5, 6, 8, 10, 12)
JEV_CUTS = (0.1, 0.25, 0.5, 0.75)
AT_CAP = 0.9  # a session that spent this share of its cap is "at its cap"
# Every AssistantBench reply read by hand (2026-10-03) against the gold and the question. The
# runner's substring grade passes a reply that names the gold while answering something else,
# and fails one that adds a ticker. The analysis runs on these verdicts; `grade_runner` keeps the
# runner's. Only verdicts that differ are listed.
HAND: dict[tuple[str, str], tuple[bool, str]] = {
    ("AB4e615af6", "SONNET"): (False, "answers 'None'; names the gold only as a venue too far"),
    ("AB4dbedc5e", "SONNET"): (False, "answers 130-210 USD saved; 55 is a ticket price in it"),
    ("AB55f42584", "SONNET"): (False, "answers Damages; names CSI: Cyber as not on Prime"),
    ("ABe6bc9808", "SONNET"): (False, "no figure; cites the gold as a 'suspicious benchmark' leak"),
    ("AB6f224e77", "HAIKU"): (False, "four names, three of them wrong"),
    ("ABefc0f3a4", "SONNET"): (True, "the gold fund, with 'ticker FPADX/FPEMX' added"),
}
# Wrong against the gold, plausibly right today (AssistantBench answers drift): not regraded.
DRIFT = {
    ("ABc7afe008", "SONNET"): "a Knives Out film released in 2025, after the gold was written",
    ("ABc7afe008", "HAIKU"): "the same 2025 film",
    ("AB9e31099f", "SONNET"): "includes the gold's people plus executives who joined in 2024-25",
}


# --- pure: matching, views, rules -------------------------------------------------------------


def matcher(gold: str) -> Callable[[str], bool]:
    """Does a text contain the gold answer? Numbers as numbers within 1 % (as `free.graded`);
    anything else as a normalised substring."""
    want = free._norm(gold)
    if re.fullmatch(r"-?\d+(\.\d+)?", want):
        target = float(want)

        def number(text: str) -> bool:
            found = re.findall(r"-?\d+(?:\.\d+)?", free._norm(text))
            return any(abs(float(x) - target) <= max(abs(target) * 0.01, 1e-9) for x in found)

        return number
    return lambda text: bool(want) and want in free._norm(text)


def cumulative(flags: Sequence[bool]) -> list[bool]:
    out, seen = [], False
    for flag in flags:
        seen = seen or bool(flag)
        out.append(seen)
    return out


def cut_at(view: Mapping[str, Any], rule: str, **p: float) -> int | None:
    """The first call index after which `rule` stops the session; None if it never does. A
    stop at the last call saves nothing, so it does not count."""
    traj, cap, n = view["traj"], view["cap"], len(view["traj"])
    jev = view.get("jev") or [None] * n
    streak, since = 0, 0
    best = 0.0
    for i in range(n - 1):
        spent = traj[i] >= p.get("f", 0.0) * cap
        best = max(best, jev[i] or 0.0)
        searches, others = view["searches"][i], view["others"][i]
        streak = streak + searches if searches and not others else 0
        since = 0 if (jev[i] or 0.0) >= p.get("t", 1.1) else since + searches
        if rule == "budget" and spent:
            return i
        if rule == "oracle" and spent and not view["gold_seen"][i]:
            return i
        if rule == "jev_none" and spent and jev[i] is not None and best < p["t"]:
            return i
        if rule == "jev_now" and spent and jev[i] is not None and jev[i] < p["t"]:
            return i
        if rule == "streak" and streak >= p["n"]:
            return i
        if rule == "streak_jev" and jev[i] is not None and since >= p["n"]:
            return i
    return None


def evaluate(views: Sequence[Mapping[str, Any]], rule: str, **p: float) -> dict[str, Any]:
    """What the rule saves on wrong sessions and what it costs on right ones."""
    wrong = [v for v in views if not v["success"]]
    right = [v for v in views if v["success"]]

    def saved(group: Sequence[Mapping[str, Any]]) -> tuple[int, float]:
        cuts = [(v, cut_at(v, rule, **p)) for v in group]
        hit = [(v, i) for v, i in cuts if i is not None]
        return len(hit), sum(v["traj"][-1] - v["traj"][i] for v, i in hit)

    wrong_cut, wrong_usd = saved(wrong)
    right_cut, right_usd = saved(right)
    spent_wrong = sum(v["traj"][-1] for v in wrong)
    return {
        "rule": rule,
        **p,
        "wrong_cut": f"{wrong_cut}/{len(wrong)}",
        "usd_saved_on_wrong": round(wrong_usd, 3),
        "share_of_wrong_spend_saved": round(wrong_usd / spent_wrong, 3) if spent_wrong else None,
        "right_cut_answers_lost": f"{right_cut}/{len(right)}",
        "usd_saved_on_right": round(right_usd, 3),
        "_lost": right_cut,
        "_saved": wrong_usd,
    }


def view_of(
    row: Mapping[str, Any], calls: Sequence[Mapping[str, Any]], gold: str, cap: float
) -> dict[str, Any]:
    """Everything the rules read, per call. No text survives into it."""
    traj = trace.trajectory(calls, row["list_usd"], row.get("usd_by_model") or {})
    gold_in = matcher(gold)
    final = next((c["text"] for c in reversed(calls) if not c["sidechain"] and c["text"]), "")
    own = nav.answer_line(final)
    own_in = matcher(own) if own else (lambda _t: False)
    seen = [gold_in(c["results"]) for c in calls]
    said = [gold_in(c["text"]) for c in calls]
    return {
        "source": row["_source"],
        "task": row["task"],
        "set": row["task"][:2],
        "arm": row["arm"],
        "success": bool(row["success"]),
        "grade_runner": bool(row.get("grade_runner", row["success"])),
        "drift": bool(row.get("drift")),
        "answered": bool(own),
        "list_usd": row["list_usd"],
        "cap": cap,
        "at_cap": row["list_usd"] >= AT_CAP * cap,
        "traj": traj,
        "searches": [c["tools"].count("WebSearch") for c in calls],
        "others": [sum(t != "WebSearch" for t in c["tools"]) for c in calls],
        "gold_seen": cumulative([s or t for s, t in zip(seen, said, strict=True)]),
        "gold_first_seen": next((i for i, s in enumerate(seen) if s), None),
        "gold_first_said": next((i for i, s in enumerate(said) if s), None),
        "own_first_seen": next(
            (i for i, c in enumerate(calls) if own and own_in(c["results"])), None
        ),
        "web_search": sum(c["tools"].count("WebSearch") for c in calls),
        "web_fetch": sum(c["tools"].count("WebFetch") for c in calls),
        "browser": trace.browser_opened(calls),
        "narrated_calls": sum(bool(c["text"].strip()) for c in calls),
    }


def describe(views: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    def med(xs: list[float]) -> float | None:
        return round(statistics.median(xs), 3) if xs else None

    def at(v: Mapping[str, Any], i: int | None) -> float | None:
        return v["traj"][i] if i is not None else None

    out: dict[str, Any] = {
        "sessions": len(views),
        "right": sum(v["success"] for v in views),
        "mean_usd": round(statistics.mean(v["list_usd"] for v in views), 3) if views else None,
        "median_usd": med([v["list_usd"] for v in views]),
        "at_cap": sum(v["at_cap"] for v in views),
        "median_calls": med([len(v["traj"]) for v in views]),
        "web_search": sum(v["web_search"] for v in views),
        "web_fetch": sum(v["web_fetch"] for v in views),
        "opened_browser": sum(v["browser"] for v in views),
    }
    for label, group in (("right", [v for v in views if v["success"]]),
                         ("wrong", [v for v in views if not v["success"]])):  # fmt: skip
        seen = [v for v in group if v["gold_first_seen"] is not None]
        out[f"{label}_sessions"] = {
            "n": len(group),
            "median_usd": med([v["list_usd"] for v in group]),
            "median_calls": med([len(v["traj"]) for v in group]),
            "gold_reached_agent": len(seen),
            "gold_said_in_narration": sum(v["gold_first_said"] is not None for v in group),
            "median_share_of_cap_when_gold_first_reached": med(
                [at(v, v["gold_first_seen"]) / v["cap"] for v in seen]
            ),
            "median_share_of_calls_when_gold_first_reached": med(
                [(v["gold_first_seen"] + 1) / len(v["traj"]) for v in seen]
            ),
            "median_share_of_cap_when_own_answer_first_reached": med(
                [
                    at(v, v["own_first_seen"]) / v["cap"]
                    for v in group
                    if v["own_first_seen"] is not None
                ]
            ),
            "mean_share_of_cap_at_quarter_of_calls": [
                round(
                    statistics.mean(
                        v["traj"][min(len(v["traj"]) - 1, int(q * len(v["traj"])))] / v["cap"]
                        for v in group
                    ),
                    3,
                )
                if group
                else None
                for q in (0.25, 0.5, 0.75)
            ],  # fmt: skip
        }
    return out


def sweep(views: Sequence[Mapping[str, Any]], with_jev: bool) -> list[dict[str, Any]]:
    out = [evaluate(views, "budget", f=f) for f in FRACTIONS]
    out += [evaluate(views, "oracle", f=f) for f in FRACTIONS]
    out += [evaluate(views, "streak", n=n) for n in STREAKS]
    if with_jev:
        out += [evaluate(views, r, f=f, t=t) for r in ("jev_none", "jev_now")
                for f in FRACTIONS for t in JEV_CUTS]  # fmt: skip
        out += [evaluate(views, "streak_jev", n=n, t=t) for n in STREAKS for t in JEV_CUTS]
    return out


def best(rows: Sequence[Mapping[str, Any]], live: bool) -> list[dict[str, Any]]:
    """Most saved on wrong sessions at each number of answers lost (0, 1, 2)."""
    pool = [r for r in rows if not live or r["rule"] != "oracle"]
    picks = []
    for lost in (0, 1, 2):
        ok = [r for r in pool if r["_lost"] == lost]
        if ok:
            picks.append(max(ok, key=lambda r: r["_saved"]))
    return [{k: v for k, v in r.items() if not k.startswith("_")} for r in picks]


# --- reading the sessions (local only) --------------------------------------------------------


def golds() -> dict[str, tuple[str, str]]:
    """tid -> (question, gold), in memory only."""
    out = {t["tid"]: (t["question"], t["gold"]) for t in free.assistantbench(100)}
    rows = list(csv.DictReader((free.CACHE / "browsecomp.csv").open(encoding="utf-8")))
    for i, row in enumerate(rows):
        out[f"BC{i}"] = (
            free._xor(row["problem"], row["canary"]),
            free._xor(row["answer"], row["canary"]),
        )
    return out


def sessions() -> list[dict[str, Any]]:
    rows = []
    for source, path in SOURCES.items():
        for row in free.nav.phase.counted(nav.done_sessions(path)):
            key = (row["task"], row["arm"])
            hand = HAND.get(key, (bool(row["success"]), ""))[0]
            rows.append({**row, "_source": source, "grade_runner": row["success"],
                         "success": hand, "drift": key in DRIFT})  # fmt: skip
    return rows


# --- Jev, cached ------------------------------------------------------------------------------


class Cache:
    def __init__(self, path: pathlib.Path) -> None:
        self.path, self.rows = path, {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.rows[row["key"]] = row["goal_met"]

    def put(self, key: str, value: float) -> None:
        self.rows[key] = value
        with self.path.open("a", encoding="utf-8") as sink:
            sink.write(json.dumps({"key": key, "goal_met": value}) + "\n")


def jev_states(calls: Sequence[Mapping[str, Any]], question: str) -> list[dict[str, Any] | None]:
    """The loop guard's state at each call that got a tool result, None elsewhere."""
    out: list[dict[str, Any] | None] = []
    actions: list[str] = []
    said: list[dict[str, Any]] = []
    for call in calls:
        said.append({"role": "assistant", "content": [{"type": "text", "text": call["text"]}]})
        for tool, given in zip(call["tools"], call["inputs"], strict=True):
            actions.append(f"{tool.split('__')[-1]} {loop_hook.short_input(tool, given)}".strip())
        if not call["results"].strip():
            out.append(None)
            continue
        done = loop_hook.established(said, call["results"], question)
        state, _ = point.questions(
            goal=question,
            done=f"{done}\n\nActions taken:\n" + "\n".join(actions[-loop_hook.ACTIONS :]),
        )
        out.append(state)
    return out


async def judge_all(
    states: list[dict[str, Any] | None], squire: Squire | None, cache: Cache
) -> list[float | None]:
    gate = asyncio.Semaphore(JEV_CONCURRENCY)
    question = point.questions(goal="g", done="d")[1]

    async def one(state: dict[str, Any] | None) -> float | None:
        if state is None:
            return None
        key = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
        if key in cache.rows:
            return cache.rows[key]
        if squire is None:
            return None
        async with gate:
            if squire.meter.cost_usd >= JEV_CEILING_USD * 0.98:
                return None
            decision = await squire.decide("loop", state, question)
        met = decision.answer("goal_met").truth
        if met is None:
            return None
        cache.put(key, met)
        return met

    return list(await asyncio.gather(*(one(s) for s in states)))


def carry(values: Sequence[float | None]) -> list[float | None]:
    """A call with no tool result keeps the last judgement."""
    out, last = [], None
    for value in values:
        last = value if value is not None else last
        out.append(last)
    return out


async def main_async(key: str) -> dict[str, Any]:
    known = golds()
    limits = Thresholds(max_usd=JEV_CEILING_USD, max_decisions=20_000)
    squire = Squire(create("jev", api_key=key), thresholds=limits) if key else None
    cache = Cache(JEV_CACHE)
    views = []
    for row in sessions():
        question, gold = known[row["task"]]
        calls = trace.load_calls(trace.folder_of(row["workdir"]))
        if not calls:
            continue
        view = view_of(row, calls, gold, float(row.get("cap_usd") or free.SESSION_MAX_USD))
        states = jev_states(calls, question)
        judged = await judge_all(states, squire, cache)
        view["jev_states"] = sum(x is not None for x in states)
        view["jev"] = carry(judged) if any(j is not None for j in judged) else None
        view["jev_judged"] = sum(j is not None for j in judged)
        views.append(view)
    # A session with no tool result (one reply, no call) has nothing to judge and is never cut.
    with_jev = bool(views) and all(v["jev_judged"] == v["jev_states"] for v in views)
    groups = {
        f"{arm}-{s}": [v for v in views if v["arm"] == arm and v["set"] == s]
        for arm in ("SONNET", "HAIKU")
        for s in ("AB", "BC")
    }
    groups = {k: g for k, g in groups.items() if g}
    groups["ALL"] = views
    report: dict[str, Any] = {
        "sessions": len(views),
        "jev_usd_this_run": round(squire.meter.cost_usd, 5) if squire else 0.0,
        "jev_complete": with_jev,
        "regraded_by_hand": {f"{t}-{a}": f"{v} ({why})" for (t, a), (v, why) in HAND.items()},
        "drift_flagged": {f"{t}-{a}": why for (t, a), why in DRIFT.items()},
        "describe": {k: describe(g) for k, g in groups.items()},
        "best_live": {k: best(sweep(g, with_jev), live=True) for k, g in groups.items()},
        "best_any": {k: best(sweep(g, with_jev), live=False) for k, g in groups.items()},
        "sweep_all": [
            {k: v for k, v in r.items() if not k.startswith("_")} for r in sweep(views, with_jev)
        ],
        "per_session": [
            {
                k: v[k]
                for k in (
                    "source",
                    "task",
                    "arm",
                    "success",
                    "grade_runner",
                    "drift",
                    "answered",
                    "list_usd",
                    "cap",
                    "at_cap",
                    "gold_first_seen",
                    "gold_first_said",
                    "own_first_seen",
                    "web_search",
                    "web_fetch",
                    "browser",
                    "narrated_calls",
                )
            }
            | {
                "calls": len(v["traj"]),
                "jev_judged": v.get("jev_judged", 0),
                "jev_max": round(max((x or 0) for x in v["jev"]), 3) if v.get("jev") else None,
            }
            for v in views
        ],  # fmt: skip
    }
    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--env-file", default=None)
    args = ap.parse_args()
    key = nav.mcp.key_from(args.env_file)
    report = asyncio.run(main_async(key))
    print(json.dumps({k: report[k] for k in ("sessions", "jev_usd_this_run", "jev_complete",
                                              "describe", "best_live")}, indent=1))  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
