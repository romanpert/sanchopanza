"""Browse, phase 2d: does Sonnet choose as well from Jev's top k shown in page order?

python benchmarks/browse/present.py --dev --live      # Phase 2c's 60 steps: development only
python benchmarks/browse/present.py --dev             # free: replays the session cache
python benchmarks/browse/present.py --record-hash
python benchmarks/browse/present.py --confirm --live  # the 82 unused steps, prereg-present.md
python benchmarks/browse/present.py --confirm         # free: replays the session cache

Phase 2c (`answers.py`) lost 5 points showing Jev's top 20 in rank order. `diagnose.py` found
that in 6 of the 7 steps it lost the target was among the 20: identical lines a ranked list
cannot tell apart, and picks from the first rows. `browse.in_page_order` shows the kept
elements in the page's order, a repeated line saying which one it is. The FULL arm is not asked
again: its answers are Phase 2c's, replayed from the same cache. The dev run scores on steps
already seen, so it claims nothing; a gain goes to new steps under a registration.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import pathlib
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sanchopanza.browse import Element, Ranked, in_page_order, rank  # noqa: E402
from sanchopanza.eval import harness as _harness  # noqa: E402
from sanchopanza.policy import Thresholds  # noqa: E402
from sanchopanza.squire import Squire  # noqa: E402


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


answers = _load("browse_answers", HERE / "answers.py")
phase = _load("browse_phase", HERE / "phase.py")
phase1 = answers.phase1
RESULTS = answers.RESULTS
CACHE = ROOT / "fixtures" / "cli" / "browse-answers-present.jsonl"
PREREG = RESULTS / "prereg-present.md"
ARMS = {"PAGE20": 20, "PAGE30": 30}
DEV_CEILING_USD = 2.00
CONFIRM_CEILING_USD = 15.00  # prereg-present.md
SESSION_MAX_USD = 0.10  # a top-30 prompt is ~3,300 tokens; Phase 2c's TOP averaged 0.011
FULL_SESSION_MAX_USD = answers.SESSION_MAX_USD  # 0.60, as in Phase 2c


def require_prereg() -> None:
    registered = PREREG.with_suffix(".sha256")
    if not registered.exists() or registered.read_text().strip() != answers.digest(PREREG):
        raise SystemExit(
            "prereg-present.md missing or changed since it was registered: nothing spent"
        )


def confirm_steps() -> list[dict[str, Any]]:
    """Phase 1c's steps that Phase 2c (and this phase's development run) did not use."""
    used = {s["id"] for s in answers.chosen_steps()}
    return [s for s in phase1.load_steps() if s["id"] not in used]


def prompt(step: dict[str, Any], shown: list[tuple[Ranked, str]]) -> str:
    """Phase 2c's prompt, with each repeated line's note after it."""
    done = "\n".join(step["previous"]) or "(none)"
    lines = "\n".join(
        f"{i}. {r.element.line()}" + (f" ({note})" if note else "")
        for i, (r, note) in enumerate(shown, 1)
    )
    return (
        f"Goal: {step['task']}\n\nActions already taken:\n{done}\n\nElements:\n{lines}\n\n"
        "Which element should be acted on next? Reply with its number."
    )


async def ranked_of(step: dict[str, Any], recorded: Any) -> list[Ranked]:
    elements = [Element.from_dict(e) for e in step["elements"]]
    squire = Squire(recorded, thresholds=Thresholds(max_usd=1.0, max_decisions=500))
    ranked = await rank(
        step["task"], elements, squire=squire, done=step["previous"], keep=max(ARMS.values())
    )
    if all(r.p is None for r in ranked):
        raise SystemExit(f"step {step['id']}: no Phase 1c recording")
    return ranked


def full_answers() -> dict[str, dict[str, Any]]:
    path = RESULTS / "answers-confirm.jsonl"
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    return {r["id"]: r for r in rows if r["arm"] == "FULL"}


async def run(live: bool, confirm: bool) -> dict[str, Any]:
    h = _harness.load()
    ceiling = CONFIRM_CEILING_USD if confirm else DEV_CEILING_USD

    def client(session_max: float) -> Any:
        return h.ClaudeCLI(
            model=answers.MODEL, system=answers.SYSTEM, ceiling_usd=ceiling,
            max_budget_usd=session_max, concurrency=answers.CONCURRENCY,
            cache=h.SessionCache(CACHE), count_cached=True,
            spawn=None if live else answers.refuse_to_spawn,
        )  # fmt: skip

    cli, full_cli = client(SESSION_MAX_USD), client(FULL_SESSION_MAX_USD)
    budget = phase.PhaseBudget(ceiling, concurrency=answers.CONCURRENCY)  # one, for both
    recorded = phase1.InOrder(phase1.CONFIRM_FIXTURE)
    phase1.STEPS = phase1.CONFIRM_STEPS  # Phase 1c's steps, not Phase 1's
    all_steps = phase1.load_steps()
    rankings_by_id = {}
    for s in all_steps:  # every step in Phase 1c's order: InOrder serves the recording so
        rankings_by_id[s["id"]] = await ranked_of(s, recorded)
    steps = confirm_steps() if confirm else answers.chosen_steps()
    rankings = [rankings_by_id[s["id"]] for s in steps]
    arms = (["FULL"] if confirm else []) + list(ARMS)

    async def one(step: dict[str, Any], ranked: list[Ranked], arm: str) -> dict[str, Any]:
        page = [Element.from_dict(e) for e in step["elements"]]
        if arm == "FULL":
            shown = [(Ranked(e, None, 0.0), "") for e in page]
            text, runner, cap = answers.prompt(step, page), full_cli, FULL_SESSION_MAX_USD
        else:
            shown = in_page_order(ranked[: ARMS[arm]], page)
            text, runner, cap = prompt(step, shown), cli, SESSION_MAX_USD
        pos = set(step["positives"])
        try:
            session = await budget.run(runner, cap, text, schema=answers.SCHEMA)
        except RuntimeError as error:
            return {"id": step["id"], "arm": arm, "ok": False, "reason": str(error)}
        pick = (session.structured or {}).get("element")
        ok_pick = isinstance(pick, int) and 1 <= pick <= len(shown)
        key = shown[pick - 1][0].element.key if ok_pick else None
        return {
            "id": step["id"], "split": step["split"], "arm": arm, "ok": session.ok,
            "reason": session.reason, "shown": len(shown),
            "positive_shown": any(r.element.key in pos for r, _ in shown),
            "notes": sum(bool(n) for _, n in shown), "right": key in pos,
            "list_usd": session.list_cost_usd, "cached": session.cached,
        }  # fmt: skip

    rows = await asyncio.gather(
        *(one(s, r, arm) for s, r in zip(steps, rankings, strict=True) for arm in arms)
    )
    full = {r["id"]: r for r in rows if r["arm"] == "FULL"} if confirm else full_answers()
    report: dict[str, Any] = {"steps": len(steps), "dev": not confirm}
    report["FULL"] = {
        "accuracy": round(sum(full[s["id"]].get("right", False) for s in steps) / len(steps), 4),
        "failed_sessions": sum(not full[s["id"]].get("ok", False) for s in steps),
        "list_usd_total": round(sum(full[s["id"]].get("list_usd", 0.0) for s in steps), 4),
        "source": "asked anew" if confirm else "Phase 2c, replayed",
    }
    for arm in ARMS:
        rs = [r for r in rows if r["arm"] == arm]
        diffs = [int(r.get("right", False)) - int(full[r["id"]].get("right", False)) for r in rs]
        report[arm] = {
            "accuracy": round(sum(r.get("right", False) for r in rs) / len(rs), 4),
            "failed_sessions": sum(not r.get("ok", False) for r in rs),
            "positive_shown": round(sum(r.get("positive_shown", False) for r in rs) / len(rs), 4),
            "list_usd_total": round(sum(r.get("list_usd", 0.0) for r in rs), 4),
            "minus_FULL": round(sum(diffs) / len(diffs), 4),
            "bootstrap95": answers.bootstrap(diffs),
        }
    report["list_usd_spent"] = round(sum(r.get("list_usd", 0.0) for r in rows), 4)
    (RESULTS / ("present-confirm.jsonl" if confirm else "present-dev.jsonl")).write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dev", action="store_true")
    mode.add_argument("--confirm", action="store_true")
    mode.add_argument("--record-hash", action="store_true")
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()
    if args.record_hash:
        registered = PREREG.with_suffix(".sha256")
        if registered.exists() and registered.read_text().strip() != answers.digest(PREREG):
            raise SystemExit(f"{registered.name} holds a different hash: nothing written")
        registered.write_text(answers.digest(PREREG) + "\n", encoding="utf-8")
        print(PREREG.name, answers.digest(PREREG))
        return 0
    if args.confirm and args.live:
        require_prereg()
    report = asyncio.run(run(args.live, args.confirm))
    name = "present-confirm.json" if args.confirm else "present-dev.json"
    (RESULTS / name).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
