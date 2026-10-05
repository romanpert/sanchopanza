"""Browse, development: would a cheap check of an extraction's result have caught the wrong ones?

python benchmarks/browse/extract_replay.py --env-file PATH/.env     # asks Jev, under a ceiling
python benchmarks/browse/extract_replay.py                          # free: re-scores the cache

Confirmation 1 (README section 16) failed on answers, and every miss of the line arm was one
kind: an extraction whose result was implausible on its face - "60 pages of 22 quotes" on a
10-page site, the same six tablets counted four times - and believed. The line asked the agent to
check its account and the cheap model did not. That check is a substitution candidate: a
question the agent should have asked of a tool result it already holds, answered where it lands
(after the `browser_evaluate`), touching nothing cached.

So, offline, on every recorded session that answered from an extraction (at most three
navigations): the last `browser_evaluate` before the answer, the request, and whether the
session was right. The question goes to Jev; a rule with no model is the baseline it has to
beat. **Exploratory and post hoc**: these sessions include confirmation 1's, read after its
verdict, so nothing here confirms anything; it decides whether a check is worth registering.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import pathlib
import re
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sanchopanza.contract import Truth  # noqa: E402
from sanchopanza.policy import Thresholds  # noqa: E402
from sanchopanza.providers import create  # noqa: E402
from sanchopanza.squire import Squire  # noqa: E402
from sanchopanza.text import truncate  # noqa: E402


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


nav = _load("browse_nav_e2e", HERE / "nav_e2e.py")
RESULTS = nav.RESULTS
CACHE = RESULTS / "extract-replay-cache.jsonl"
SOURCES = ("nav-strategy", "nav-strategy-harm", "nav-confirm", "nav-hard")
CEILING_USD = 0.10
MAX_NAVIGATIONS = 3
_EVALUATE = "mcp__playwright__browser_evaluate"

QUESTION = Truth(
    "`result` is what a piece of code returned after collecting data across a website to "
    "answer `request`. Does it look complete and internally consistent, so that an answer "
    "built on it can be trusted?",
    criteria={
        "true": {
            "what": "The pages and items it reports fit the request and each other, nothing is "
            "duplicated, and the figure asked for follows from them",
            "examples": ["50 pages read, 1,000 books, 40 match: one count over all of them"],
        },
        "false": {
            "what": "It read only part of what was asked, counts the same items more than "
            "once, reports page or item totals that cannot be right, found nothing, or "
            "returned an error instead of data",
            "examples": [
                "the same 6 tablets on each of 4 pages, counted as 24",
                "'40 books across 3 pages' when the request covers the whole catalogue",
                "an error: execution context was destroyed",
            ],
        },
    },
)


def transcript_of(workdir: str) -> pathlib.Path | None:
    slug = re.sub(r"[^A-Za-z0-9]", "-", workdir)
    found = sorted((pathlib.Path.home() / ".claude" / "projects" / slug).glob("*.jsonl"))
    return found[0] if found else None


def last_extraction(path: pathlib.Path) -> dict[str, str] | None:
    """The last `browser_evaluate` of a transcript: its code and the text it returned."""
    calls: dict[str, str] = {}
    last: dict[str, str] | None = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            content = (json.loads(line).get("message") or {}).get("content")
        except ValueError:
            continue
        for block in content if isinstance(content, list) else []:
            if block.get("type") == "tool_use" and block.get("name") == _EVALUATE:
                calls[block["id"]] = str((block.get("input") or {}).get("function", ""))
            elif block.get("type") == "tool_result" and block.get("tool_use_id") in calls:
                body = block.get("content")
                text = body if isinstance(body, str) else " ".join(
                    str(b.get("text", "")) for b in body or [] if isinstance(b, dict)
                )  # fmt: skip
                last = {"code": calls[block["tool_use_id"]], "result": result_text(text)}
    return last


def result_text(text: str) -> str:
    """What the evaluate returned, without Playwright's echo of the code it ran."""
    return text.split("### Ran Playwright code")[0].replace("### Result", "").strip()


def rule_flags(result: str) -> bool:
    """The baseline with no model: an error, an empty result, or a zero count."""
    lowered = result.lower()
    return bool(
        "error" in lowered
        or not result.strip()
        or re.search(r'"[a-z_]*count[a-z_]*":\s*0\b', lowered)
    )


def cases() -> list[dict[str, Any]]:
    questions = {t[0]: t[2] for t in nav.EVERY_TASK}
    questions.update(
        {t[0]: t[2] for t in _load("browse_nav_confirm", HERE / "nav_confirm.py").TASKS}
    )
    out = []
    for source in SOURCES:
        for row in nav.done_sessions(RESULTS / f"{source}-sessions.jsonl"):
            navs = row.get("tools", {}).get("mcp__playwright__browser_navigate", 0)
            if row.get("not_run") or navs > MAX_NAVIGATIONS or row["task"] not in questions:
                continue
            path = transcript_of(row.get("workdir", ""))
            found = last_extraction(path) if path else None
            if not found:
                continue
            out.append({"source": source, "task": row["task"], "arm": row["arm"],
                        "run": row["run"], "right": bool(row["success"]),
                        "request": questions[row["task"]], **found})  # fmt: skip
    return out


async def judge(case: dict[str, Any], squire: Squire | None, cache: dict[str, Any]) -> float | None:
    state = {"request": truncate(case["request"], 500), "result": truncate(case["result"], 1600),
             "code": truncate(case["code"], 600)}  # fmt: skip
    key = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
    if key in cache:
        return cache[key]
    if squire is None or squire.meter.cost_usd >= CEILING_USD:
        return None
    decision = await squire.decide("extract_check", state, {"extract_ok": QUESTION})
    value = decision.answer("extract_ok").truth
    if value is not None:
        cache[key] = value
        with CACHE.open("a", encoding="utf-8") as sink:
            sink.write(json.dumps({"key": key, "extract_ok": value}) + "\n")
    return value


def auc(pos: list[float], neg: list[float]) -> float | None:
    pairs = [(p, n) for p in pos for n in neg]
    return round(sum((p > n) + 0.5 * (p == n) for p, n in pairs) / len(pairs), 3) if pairs else None


def rule_score(rows: list[dict[str, Any]]) -> dict[str, str]:
    wrong = [c for c in rows if not c["right"]]
    right = [c for c in rows if c["right"]]
    return {"wrong_caught": f"{sum(c['rule_flags'] for c in wrong)}/{len(wrong)}",
            "right_flagged": f"{sum(c['rule_flags'] for c in right)}/{len(right)}"}  # fmt: skip


async def main_async(key: str) -> dict[str, Any]:
    cache: dict[str, Any] = {}
    if CACHE.exists():
        for line in CACHE.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            cache[row["key"]] = row["extract_ok"]
    squire = (
        Squire(create("jev", api_key=key), thresholds=Thresholds(max_usd=CEILING_USD))
        if key
        else None
    )
    rows = cases()
    for case in rows:
        case["extract_ok"] = await judge(case, squire, cache)
        case["rule_flags"] = rule_flags(case["result"])
    judged = [c for c in rows if c["extract_ok"] is not None]
    right = [c["extract_ok"] for c in judged if c["right"]]
    wrong = [c["extract_ok"] for c in judged if not c["right"]]
    report = {
        "cases": len(rows), "judged": len(judged), "right": len(right), "wrong": len(wrong),
        "jev_usd_this_run": round(squire.meter.cost_usd, 5) if squire else 0.0,
        "auc_extract_ok_vs_right": auc(right, wrong),
        "by_cut": {str(c): {"wrong_caught": f"{sum(v < c for v in wrong)}/{len(wrong)}",
                            "right_flagged": f"{sum(v < c for v in right)}/{len(right)}"}
                   for c in (0.3, 0.5, 0.7)},
        "rule_over_all_cases": rule_score(rows),
        "detail": [{k: c[k] for k in ("source", "task", "arm", "run", "right", "extract_ok",
                                      "rule_flags")} | {"result": c["result"][:200]}
                   for c in rows],
    }  # fmt: skip
    (RESULTS / "extract-replay.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--env-file", default=None)
    args = ap.parse_args()
    key = nav.mcp.key_from(args.env_file) if args.env_file else ""
    report = asyncio.run(main_async(key))
    print(json.dumps({k: v for k, v in report.items() if k != "detail"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
