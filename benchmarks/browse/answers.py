"""Browse, phase 2c: does Sonnet choose as well from Jev's top 20 as from the whole page?

python benchmarks/browse/answers.py --record-hash
python benchmarks/browse/answers.py --pilot --live      # 3 steps per arm, excluded
python benchmarks/browse/answers.py --live
python benchmarks/browse/answers.py                     # free: replays the session cache

Registered in `prereg-confirm.md` (Phase 2c; prompt and schema from `prereg-phase2-amendment.md`).
Phase 1 failed its bar, so the original Phase 2 never ran; this one runs on the confirmation steps
and only once Phase 1c has confirmed. JEV-BLEND's ranking is rebuilt from Phase 1c's recording
(`fixtures/browse-jev-confirm.jsonl`), never asked again. Sessions go through
our own evaluation harness (`claude -p`, list prices; not directly comparable with the API) and
are cached in `fixtures/cli/browse-answers-confirm.jsonl`.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import pathlib
import random
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sanchopanza.browse import Element, rank  # noqa: E402
from sanchopanza.eval import harness as _harness  # noqa: E402
from sanchopanza.policy import Thresholds  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider  # noqa: E402
from sanchopanza.squire import Squire  # noqa: E402


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


phase1 = _load("browse_run", HERE / "run.py")
RESULTS = phase1.RESULTS
AMENDMENT = RESULTS / "prereg-phase2-amendment.md"
MONEY_AMENDMENT = RESULTS / "prereg-confirm-amendment.md"
CACHE = ROOT / "fixtures" / "cli" / "browse-answers-confirm.jsonl"
MODEL = "claude-sonnet-5"
SYSTEM = (
    "You operate a web browser for a user. You see the user's goal, the actions already "
    "taken, and the page's elements, numbered. Choose the one element to act on next "
    "(click, type into, or select). Reply with its number only."
)
SCHEMA = {
    "type": "object",
    "properties": {"element": {"type": "integer"}},
    "required": ["element"],
    "additionalProperties": False,
}
PER_SPLIT = 20
TOP = 20
PILOT = 3
CEILING_USD = 12.00  # prereg-confirm-amendment.md (was 8.00)
SESSION_MAX_USD = 0.60
CONCURRENCY = 3


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def require_registered() -> None:
    phase1.require_prereg(phase1.CONFIRM_PREREG)
    registered = RESULTS / "prereg-phase2-amendment.sha256"
    if not registered.exists() or registered.read_text().strip() != digest(AMENDMENT):
        raise SystemExit("prereg-phase2-amendment.md missing or changed: nothing spent")
    money = MONEY_AMENDMENT.with_suffix(".sha256")
    if not money.exists() or money.read_text().strip() != digest(MONEY_AMENDMENT):
        raise SystemExit("prereg-confirm-amendment.md missing or changed: nothing spent")
    if not confirmed():
        raise SystemExit("Phase 1c did not confirm (prereg-confirm.md): Phase 2c does not run")


def confirmed() -> bool:
    """Phase 1c's registered rule: Recall@20 >= 0.80 and its Wilson lower bound >= 0.70."""
    path = RESULTS / "analysis-confirm.json"
    if not path.exists():
        return False
    r20 = json.loads(path.read_text(encoding="utf-8"))["JEV-BLEND"]["recall@20"]
    return r20["value"] >= 0.80 and r20["wilson95"][0] >= 0.70


def chosen_steps() -> list[dict[str, Any]]:
    phase1.STEPS = phase1.CONFIRM_STEPS
    steps = phase1.load_steps()
    out = []
    for split in ("test_website", "test_domain", "test_task"):
        out += [s for s in steps if s["split"] == split][:PER_SPLIT]
    return out


def prompt(step: dict[str, Any], elements: list[Element]) -> str:
    done = "\n".join(step["previous"]) or "(none)"
    lines = "\n".join(f"{i}. {e.line()}" for i, e in enumerate(elements, 1))
    return (
        f"Goal: {step['task']}\n\nActions already taken:\n{done}\n\nElements:\n{lines}\n\n"
        "Which element should be acted on next? Reply with its number."
    )


async def top_of(step: dict[str, Any], recorded: RecordedDecider) -> list[Element]:
    """JEV's ranking, replayed from Phase 1: nothing is asked again."""
    elements = [Element.from_dict(e) for e in step["elements"]]
    squire = Squire(recorded, thresholds=Thresholds(max_usd=1.0, max_decisions=500))
    ranked = await rank(step["task"], elements, squire=squire, done=step["previous"], keep=TOP)
    if all(r.p is None for r in ranked):
        raise SystemExit(f"step {step['id']}: no Phase 1 recording; run Phase 1 first")
    return [r.element for r in ranked]


async def refuse_to_spawn(*_: Any) -> tuple[int, bytes, bytes]:
    raise RuntimeError("not in the cache and not --live: nothing spent")


def bootstrap(diffs: list[int], reps: int = 5000) -> list[float]:
    rng = random.Random(2032)
    n = len(diffs)
    means = sorted(sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(reps))
    return [round(means[int(0.025 * reps)], 4), round(means[int(0.975 * reps)], 4)]


async def run(live: bool, pilot: bool) -> dict[str, Any]:
    h = _harness.load()
    cache = h.SessionCache(CACHE)
    cli = h.ClaudeCLI(
        model=MODEL,
        system=SYSTEM,
        ceiling_usd=CEILING_USD,
        max_budget_usd=SESSION_MAX_USD,
        concurrency=CONCURRENCY,
        cache=cache,
        count_cached=True,
        spawn=None if live else refuse_to_spawn,
    )
    recorded = phase1.InOrder(phase1.CONFIRM_FIXTURE)
    steps = chosen_steps()
    if pilot:
        steps = [s for i, s in enumerate(steps) if i % PER_SPLIT < PILOT]

    async def one(step: dict[str, Any], arm: str) -> dict[str, Any]:
        full = [Element.from_dict(e) for e in step["elements"]]
        shown = full if arm == "FULL" else await top_of(step, recorded)
        try:
            session = await cli.run(prompt(step, shown), schema=SCHEMA)
        except RuntimeError as error:
            return {"id": step["id"], "arm": arm, "ok": False, "reason": str(error)}
        pick = (session.structured or {}).get("element")
        key = shown[pick - 1].key if isinstance(pick, int) and 1 <= pick <= len(shown) else None
        return {
            "id": step["id"],
            "split": step["split"],
            "arm": arm,
            "ok": session.ok,
            "reason": session.reason,
            "shown": len(shown),
            "positive_shown": any(e.key in step["positives"] for e in shown),
            "right": key in set(step["positives"]),
            "input_tokens": session.input_tokens + session.cache_read_tokens
            + session.cache_write_tokens,
            "list_usd": session.list_cost_usd,
            "cached": session.cached,
        }  # fmt: skip

    rows = await asyncio.gather(*(one(s, arm) for s in steps for arm in ("FULL", "TOP")))
    by = {arm: [r for r in rows if r["arm"] == arm] for arm in ("FULL", "TOP")}
    report: dict[str, Any] = {"steps": len(steps), "pilot": pilot}
    for arm, rs in by.items():
        report[arm] = {
            "accuracy": round(sum(r.get("right", False) for r in rs) / len(rs), 4),
            "failed_sessions": sum(not r.get("ok", False) for r in rs),
            "positive_shown": round(sum(r.get("positive_shown", False) for r in rs) / len(rs), 4),
            "input_tokens_mean": round(sum(r.get("input_tokens", 0) for r in rs) / len(rs)),
            "list_usd_total": round(sum(r.get("list_usd", 0.0) for r in rs), 4),
        }
    paired = {r["id"]: r for r in by["FULL"]}
    diffs = [
        int(t.get("right", False)) - int(paired[t["id"]].get("right", False)) for t in by["TOP"]
    ]
    report["TOP_minus_FULL"] = {
        "value": round(sum(diffs) / len(diffs), 4),
        "bootstrap95": bootstrap(diffs),
    }
    jev = [json.loads(x) for x in phase1.CONFIRM_FIXTURE.read_text(encoding="utf-8").splitlines()]
    report["cli_spent_usd"] = round(cli.spent_usd, 4)
    report["jev_usd_per_step_phase1c"] = round(
        sum(x["cost_usd"] for x in jev) / max(1, len(phase1.load_steps())), 6
    )
    (RESULTS / ("answers-confirm-pilot.jsonl" if pilot else "answers-confirm.jsonl")).write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--record-hash", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--pilot", action="store_true")
    args = ap.parse_args()
    if args.record_hash:
        for path in (AMENDMENT, MONEY_AMENDMENT):
            path.with_suffix(".sha256").write_text(digest(path) + "\n")
            print(path.name, digest(path))
        return 0
    if args.live:
        require_registered()
    report = asyncio.run(run(args.live, args.pilot))
    name = "answers-confirm-pilot.json" if args.pilot else "answers-confirm.json"
    (RESULTS / name).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
