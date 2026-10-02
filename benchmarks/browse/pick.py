"""Browse, phase 4b: does a small model need the ranking to pick the right element?

python benchmarks/browse/pick.py --limit 20 --live   # development: 20 steps, its own file
python benchmarks/browse/pick.py --limit 20          # free: re-scores what is cached
python benchmarks/browse/pick.py --live              # all 82 steps

Phase 4's pilot (`nav-pilot.json`) found `claude-haiku-4-5` answering two 17-turn browsing
tasks as well as `claude-sonnet-5` at 2.4 times less, with nothing of ours in the session. On
tasks a cheap model can already do there is nothing for a ranking to add, so the claim has to
be tested where picking is hard: Mind2Web's real pages, 552 elements on average, with the
action the step needed known.

Phase 2d asked exactly this of Sonnet on these 82 steps (51.2 % from the whole page, 52.4 %
from Jev's top 20 in page order, an eighth of the cost). This asks it of Haiku. Three outcomes,
all worth having:

- Haiku is as good from the whole page as from the top 20: the ranking adds nothing, and the
  honest advice is "use the cheap model", with nothing of ours in it.
- Haiku is much worse from the whole page: the ranking is what makes the cheap model able.
  That is the claim, measured where it can fail.
- Haiku is worse even from the top 20: the cheap model cannot do this, and a cascade has to
  escalate - the margin (`calib.json`, section 3) is the knob that would decide when.

The rankings are replayed from `fixtures/browse-jev-confirm.jsonl` and cost nothing. The
answers are new `claude -p` sessions, on the subscription at list price.

Not comparable with Phase 2d's own numbers without this caveat: 2d answered through our
evaluation harness with a forced JSON schema, and that harness is not installed on this
machine, so this spawns `claude -p` itself and reads a number out of the reply. The SONNET20
arm is here for that reason: so Haiku is compared against Sonnet asked the same way.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sanchopanza.browse import Element, Ranked, in_page_order  # noqa: E402


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


answers = _load("browse_answers", HERE / "answers.py")
present = _load("browse_present", HERE / "present.py")
phase1 = answers.phase1

RESULTS = ROOT / "docs" / "results" / "2026-10-02-browse-nav"
CACHE = RESULTS / "pick-sessions.jsonl"
ARMS = {
    "HAIKU-FULL": ("claude-haiku-4-5", 0),
    "HAIKU20": ("claude-haiku-4-5", 20),
    "SONNET20": ("claude-sonnet-5", 20),
}
SESSION_MAX_USD = 0.60
CEILING_USD = 5.00
CONCURRENCY = 3
TIMEOUT_S = 300
_INT = re.compile(r"-?\d+")


def key_of(model: str, prompt: str) -> str:
    return hashlib.sha256(f"{model}\x00{prompt}".encode()).hexdigest()


class Cache:
    """Every session, keyed by model and prompt: a re-score costs nothing and never re-asks."""

    def __init__(self, path: pathlib.Path) -> None:
        self.path = path
        self.rows: dict[str, dict[str, Any]] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.rows[row["key"]] = row

    def get(self, key: str) -> dict[str, Any] | None:
        return self.rows.get(key)

    def put(self, key: str, row: dict[str, Any]) -> None:
        self.rows[key] = row
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as sink:
            sink.write(json.dumps({"key": key, **row}) + "\n")

    @property
    def spent_usd(self) -> float:
        return sum(float(r.get("list_usd") or 0.0) for r in self.rows.values())


def ask(model: str, prompt: str) -> dict[str, Any]:
    """One isolated `claude -p` with no tools: the goal, the elements, a number back."""
    argv = [
        shutil.which("claude") or "claude", "-p", "--model", model,
        "--append-system-prompt", answers.SYSTEM,
        "--setting-sources", "", "--strict-mcp-config",
        "--allowedTools", "", "--disallowedTools", "WebFetch WebSearch Bash Read Edit Write",
        "--output-format", "json", "--max-budget-usd", f"{SESSION_MAX_USD:g}",
    ]  # fmt: skip
    stripped = ("ANTHROPIC_", "CLAUDE_CODE_USE_", "AWS_BEARER_TOKEN_BEDROCK")
    env = {k: v for k, v in os.environ.items() if not k.startswith(stripped)}
    try:
        # The prompt goes in on stdin: a whole page of elements is past Windows's limit on
        # the length of a command line, and an argv of 100,000 characters fails to spawn.
        done = subprocess.run(
            argv, env=env, capture_output=True, timeout=TIMEOUT_S, input=prompt.encode("utf-8")
        )
        out = json.loads(done.stdout.decode("utf-8", errors="replace") or "{}")
    except (subprocess.TimeoutExpired, ValueError) as error:
        return {"ok": False, "reason": error.__class__.__name__, "list_usd": 0.0, "pick": None}
    reply = str(out.get("result") or "")
    found = _INT.search(reply)
    usage = out.get("usage") or {}
    return {
        "ok": not out.get("is_error", True),
        "reason": out.get("subtype") or "",
        "list_usd": float(out.get("total_cost_usd") or 0.0),
        "pick": int(found.group(0)) if found else None,
        "reply": reply[:200],
        # Kept because the absolute cost of a session here is mostly Claude Code's own prefix,
        # not the prompt: without these the per-step figures cannot be read at all.
        "input_tokens": int(usage.get("input_tokens") or 0),
        "cache_read": int(usage.get("cache_read_input_tokens") or 0),
        "cache_write": int(usage.get("cache_creation_input_tokens") or 0),
    }


async def main_async(limit: int, live: bool) -> dict[str, Any]:
    recorded = phase1.InOrder(phase1.CONFIRM_FIXTURE)
    phase1.STEPS = phase1.CONFIRM_STEPS
    rankings = {s["id"]: await present.ranked_of(s, recorded) for s in phase1.load_steps()}
    steps = present.confirm_steps()[: limit or None]
    cache = Cache(CACHE)
    gate = asyncio.Semaphore(CONCURRENCY)
    rows: list[dict[str, Any]] = []

    async def one(step: dict[str, Any], arm: str) -> dict[str, Any]:
        model, top = ARMS[arm]
        page = [Element.from_dict(e) for e in step["elements"]]
        if top:
            shown = in_page_order(rankings[step["id"]][:top], page)
            prompt = present.prompt(step, shown)
        else:
            shown = [(Ranked(e, None, 0.0), "") for e in page]
            prompt = answers.prompt(step, page)
        key = key_of(model, prompt)
        got = cache.get(key)
        if got is None:
            if not live:
                return {"id": step["id"], "arm": arm, "ok": False, "reason": "not cached"}
            if cache.spent_usd + SESSION_MAX_USD > CEILING_USD:
                return {"id": step["id"], "arm": arm, "ok": False, "reason": "ceiling"}
            async with gate:
                got = await asyncio.to_thread(ask, model, prompt)
            cache.put(key, got)
        pick = got.get("pick")
        inside = isinstance(pick, int) and 1 <= pick <= len(shown)
        chosen = shown[pick - 1][0].element.key if inside else None
        positives = set(step["positives"])
        return {
            "id": step["id"], "split": step["split"], "arm": arm, "ok": bool(got.get("ok")),
            "reason": got.get("reason", ""), "shown": len(shown),
            "positive_shown": any(r.element.key in positives for r, _ in shown),
            "right": chosen in positives, "list_usd": float(got.get("list_usd") or 0.0),
            "cached": got is not None,
        }  # fmt: skip

    for arm in ARMS:  # arm by arm, so a ceiling stops the cheapest arms last
        rows += await asyncio.gather(*(one(s, arm) for s in steps))
    report: dict[str, Any] = {"steps": len(steps), "development": True}
    for arm in ARMS:
        part = [r for r in rows if r["arm"] == arm]
        asked = [r for r in part if r["reason"] != "not cached"]
        if not asked:
            continue
        report[arm] = {
            "model": ARMS[arm][0],
            "steps": len(asked),
            "accuracy": round(sum(r["right"] for r in asked) / len(asked), 4),
            "wilson95": phase1.wilson(sum(r["right"] for r in asked), len(asked)),
            "failed_sessions": sum(not r["ok"] for r in asked),
            "positive_shown": round(sum(r["positive_shown"] for r in asked) / len(asked), 4),
            "list_usd_total": round(sum(r["list_usd"] for r in asked), 4),
            "list_usd_per_step": round(sum(r["list_usd"] for r in asked) / len(asked), 5),
        }
    for a, b in (("HAIKU20", "HAIKU-FULL"), ("HAIKU20", "SONNET20")):
        if a in report and b in report:
            pa = {r["id"]: r["right"] for r in rows if r["arm"] == a}
            pb = {r["id"]: r["right"] for r in rows if r["arm"] == b}
            both = [i for i in pa if i in pb]
            diffs = [int(pa[i]) - int(pb[i]) for i in both]
            report[f"{a}-minus-{b}"] = {
                "value": round(sum(diffs) / len(diffs), 4) if diffs else None,
                "bootstrap95": answers.bootstrap(diffs) if diffs else None,
                "steps": len(both),
            }
    report["reference_phase_2d_sonnet"] = {
        "FULL": 0.5122, "PAGE20": 0.5244,
        "note": "through our evaluation harness with a forced schema, not this spawner",
    }  # fmt: skip
    report["list_usd_spent_total"] = round(cache.spent_usd, 4)
    (RESULTS / "pick.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    (RESULTS / "pick-rows.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0, help="first N of the 82 steps")
    ap.add_argument("--arms", default="", help="comma-separated subset of " + ",".join(ARMS))
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()
    if args.arms:
        wanted = [a.strip().upper() for a in args.arms.split(",")]
        unknown = [a for a in wanted if a not in ARMS]
        if unknown:
            raise SystemExit(f"no such arm: {unknown}")
        for name in list(ARMS):
            if name not in wanted:
                del ARMS[name]
    print(json.dumps(asyncio.run(main_async(args.limit, args.live)), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
