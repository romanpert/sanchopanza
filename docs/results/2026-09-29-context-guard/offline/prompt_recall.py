"""Part 2 (offline): what to recall at the prompt, the new prompt as the question. See
../prereg-prompt-recall.md (and its amendments 1 and 2).

    python prompt_recall.py free                                  # recent, bm25, rule: no call
    python prompt_recall.py jev --env-file PATH --cap 0.08        # + judge and cascade, recorded
    python prompt_recall.py jev --replay                          # free, from the recordings

Units: every recorded phase A with the phase-B prompt that followed it. Candidates: the product's
own pool (`guard.pieces_of`: every line of every output that cannot be read again). Arms use
the product's functions: `rule` is `guard.choose` over `guard.candidates`, `judge` is the
tournament of `guard.choose_by_judge`, `cascade` is `guard.cascade_order` (the rule first, the
decider at the frontier). Measure: every needed value inside the chosen lines, at 400 and 1,000
characters, per condition (literal prompt, two oblique prompts, and shifted outputs).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import random
import re
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
RUN = HERE.parent
RESULTS = RUN.parent
ROOT = RESULTS.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(RUN))

from sanchopanza.context import guard  # noqa: E402
from sanchopanza.context.transcript import Call, calls, history_from_claude_code  # noqa: E402
from sanchopanza.text import bm25_scores  # noqa: E402

CACHE = Path.home() / ".cache" / "sanchopanza"
RECORDINGS = CACHE / "context-guard" / "recordings" / "prompt-recall-2stage.jsonl"  # amendment 4
BUDGETS = (400, 1000)
MODEL = "jev-1.13.0"
OUT = HERE / "prompt_recall.json"
OBLIQUE = {
    "oblique_en": (
        "Finish the release: put the identifier the one-off issuing script gave us into the "
        "release module, and make the calibration check use the limit and the reference that "
        "the diagnostic run complained about."
    ),
    "oblique_es": (
        "Termina la publicacion: pon en el modulo de release el identificador que nos dio el "
        "script de un solo uso, y haz que la comprobacion de calibracion use el limite y la "
        "referencia de la que se quejo la ejecucion de diagnostico."
    ),
}
CONDITIONS = ("literal", "oblique_en", "oblique_es", "shifted", "shifted_en")
# Amendment 5: the cascade as a package (`context.keep`), on two conditions written before any
# arm was run on them, plus two seen ones. Its own recordings; the earlier run stays as run.
KEEP_CONDITIONS = ("literal", "shifted_en", "json_en", "vague")
KEEP_NEW = ("json_en", "vague")
KEEP_RECORDINGS = CACHE / "context-guard" / "recordings" / "prompt-recall-keep.jsonl"
KEEP_OUT = HERE / "prompt_recall_keep.json"
OBLIQUE2_EN = (
    "Wrap up: put the identifier we were issued earlier into the release module, and make the "
    "calibration check use the threshold and the reference that the diagnostic run reported."
)
VAGUE = "Carry on with the remaining steps of the task."
WORDS2 = ("quartz", "fennel", "harbor", "ember", "willow", "cobalt", "lark", "sable", "thistle",
          "birch", "otter", "maple", "heron", "flint", "juniper", "pebble")  # fmt: skip
WORDS = ("zeta", "ambar", "norte", "cobre", "lince", "marea", "tilo", "brasa", "olmo", "duna",
         "garza", "roble", "nube", "salvia", "cierzo", "trigo")  # fmt: skip
PROBE_LINE = re.compile(r"ProbeError: drift (\S+) exceeds tolerance (\S+) \(code (\S+)\)")


def _module(path: Path, name: str) -> Any:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _phase_b_prompt(path: Path) -> str:
    """A run's phase-B prompt, read from its N session (the prompt after phase A's)."""
    if not path.exists():
        return ""
    messages, _ = history_from_claude_code(path)
    prompts = list(guard.requests_of(messages, budget=100_000))
    return prompts[-1] if len(prompts) > 1 else ""


def units() -> list[dict[str, Any]]:
    import run as guard_run  # this run's driver first: it and the lean run both have `tasks.py`

    out: list[dict[str, Any]] = []
    e2e = _module(RESULTS / "2026-09-28-context-e2e" / "tasks.py", "pr_e2e_tasks")
    for i in range(12):
        f, *_ = e2e.facts_for(i)
        path = CACHE / "context-e2e" / "runs" / f.task / "A" / "session.jsonl"
        prompt = _phase_b_prompt(CACHE / "context-e2e" / "runs" / f.task / "N" / "session.jsonl")
        if path.exists() and prompt:
            out.append({"unit": f"e2e/{f.task}", "split": "dev", "path": path, "prompt": prompt,
                        "needed": {"token": f.token, "probe": f.code,
                                   "tolerance": f.tolerance}})  # fmt: skip
    lean = _module(RESULTS / "2026-09-28-context-lean" / "tasks.py", "pr_lean_tasks")
    for i in range(8):
        f, *_ = lean.facts_for(i)
        path = CACHE / "context-lean" / "haiku" / "runs" / f.task / "A" / "session.jsonl"
        prompt = _phase_b_prompt(
            CACHE / "context-lean" / "haiku" / "runs" / f.task / "N" / "session.jsonl"
        )
        if path.exists() and prompt:
            out.append({"unit": f"lean/{f.task}", "split": "dev", "path": path,
                        "prompt": prompt, "needed": {"token": f.token}})  # fmt: skip
    for task, f in guard_run.gen.load_facts(guard_run.TASKS_DIR).items():
        path = CACHE / "context-guard" / "haiku" / "runs" / task / "A" / "session.jsonl"
        if path.exists():
            out.append({"unit": f"guard/{task}", "split": "test", "path": path,
                        "prompt": guard_run.PROMPT_B,
                        "needed": {"token": f["token"], "probe": f["probe_code"],
                                   "tolerance": f["tolerance"]}})  # fmt: skip
    return out


def shifted(unit: dict[str, Any], history: list[Call]) -> tuple[list[Call], dict[str, str]]:
    """Amendment 2: the needed values and their wording rewritten, before any arm sees them."""
    rng = random.Random(f"shifted-{unit['unit']}")
    token = "-".join(rng.sample(WORDS, 3))
    code = "ref-" + "-".join(rng.sample(WORDS, 2))
    needed = {"token": token}
    if "probe" in unit["needed"]:
        needed = {**needed, "probe": code, "tolerance": unit["needed"]["tolerance"]}

    def rewrite(text: str) -> str:
        text = text.replace(
            "release token: " + unit["needed"]["token"], "identificador de publicacion: " + token
        )
        text = text.replace(unit["needed"]["token"], token)
        if "probe" in unit["needed"]:
            text = PROBE_LINE.sub(
                lambda m: f"La sonda se desvio {m.group(1)}, por encima del margen "
                          f"{m.group(2)} (referencia {code})", text)  # fmt: skip
            text = text.replace(unit["needed"]["probe"], code)
        return text.replace("FAIL", "MAL")

    return [replace(c, result=rewrite(c.result)) for c in history], needed


def as_json(unit: dict[str, Any], history: list[Call]) -> tuple[list[Call], dict[str, str]]:
    """Amendment 5: the needed lines become JSON records with new wording and word codes."""
    rng = random.Random(f"json-{unit['unit']}")
    handle = "-".join(rng.sample(WORDS2, 3))
    ticket = "tk-" + "-".join(rng.sample(WORDS2, 2))
    needed = {"token": handle}
    if "probe" in unit["needed"]:
        needed = {**needed, "probe": ticket, "tolerance": unit["needed"]["tolerance"]}

    def rewrite(text: str) -> str:
        text = text.replace("release token: " + unit["needed"]["token"],
                            '{"event": "grant", "handle": "' + handle + '"}')  # fmt: skip
        text = text.replace(unit["needed"]["token"], handle)
        if "probe" in unit["needed"]:
            text = PROBE_LINE.sub(lambda m: '{"level": "error", "msg": "sensor spread above '
                                  f'allowance", "spread": {m.group(1)}, "allowance": {m.group(2)}, '
                                  f'"ticket": "{ticket}"}}', text)  # fmt: skip
            text = text.replace(unit["needed"]["probe"], ticket)
        return text

    return [replace(c, result=rewrite(c.result)) for c in history], needed


def setting(unit: dict[str, Any], condition: str) -> tuple[list[Call], str, dict[str, str]]:
    messages, _ = history_from_claude_code(unit["path"])
    history = calls(messages)
    if condition == "json_en":
        moved, needed = as_json(unit, history)
        return moved, OBLIQUE2_EN, needed
    if condition == "vague":
        return history, VAGUE, unit["needed"]
    if condition == "literal":
        return history, unit["prompt"], unit["needed"]
    if condition in ("shifted", "shifted_en"):
        moved, needed = shifted(unit, history)
        return moved, OBLIQUE["oblique_es" if condition == "shifted" else "oblique_en"], needed
    return history, OBLIQUE[condition], unit["needed"]


def text_of(facts: Sequence[guard.Fact]) -> str:
    return "\n".join(f.line for f in facts)


def score(needed: dict[str, str], text: str) -> dict[str, Any]:
    found = {k: guard.contains(text, v) for k, v in needed.items()}
    return {"all": all(found.values()), **found, "chars": len(text)}


def rule_at(history: list[Call], prompt: str, budget: int) -> tuple[guard.Fact, ...]:
    return guard.choose(guard.candidates(history, guard.focus_of([prompt])), budget)


def free_arms(
    history: list[Call], prompt: str, pieces: list[guard.Fact]
) -> dict[str, dict[int, str]]:
    recent = sorted(pieces, key=lambda f: (-f.call, -f.rank))
    scores = bm25_scores(prompt, [f.line for f in pieces])
    bm25 = [
        pieces[i]
        for i in sorted(range(len(pieces)), key=lambda i: (-scores[i], -pieces[i].call))
    ]
    return {
        "recent": {b: text_of(guard._fit(recent, b)) for b in BUDGETS},
        "bm25": {b: text_of(guard._fit(bm25, b)) for b in BUDGETS},
        "rule": {b: text_of(rule_at(history, prompt, b)) for b in BUDGETS},
    }


def decided_arms(history: list[Call], prompt: str, pieces: list[guard.Fact],
                 verdicts: Sequence[tuple[bool, float | None]] | None
                 ) -> dict[str, dict[int, str]]:  # fmt: skip
    out: dict[str, dict[int, str]] = {"judge": {}, "cascade": {}}
    for b in BUDGETS:
        judged: list[guard.Fact] = []
        if verdicts is not None and len(verdicts) == len(pieces):
            kept = [(p if p is not None else 0.0, i) for i, (k, p) in enumerate(verdicts) if k]
            judged = [pieces[i] for _, i in sorted(kept, key=lambda x: (-x[0], -pieces[x[1]].call))]
        out["judge"][b] = text_of(guard._fit(judged, b))
        rule_lines = frozenset(f.line for f in rule_at(history, prompt, b))
        out["cascade"][b] = text_of(
            guard._fit(guard.cascade_order(pieces, rule_lines, verdicts), b)
        )
    return out


def summarize(rows: list[dict[str, Any]], arms: Sequence[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for condition in CONDITIONS:
        for split in ("test", "dev", "all"):
            part = [r for r in rows if r["condition"] == condition
                    and (split == "all" or r["split"] == split)
                    # rows past an exhausted cap are not scored
                    and r.get("decided", True) is not False]
            block: dict[str, Any] = {"units": len(part)}
            for arm in arms:
                for b in BUDGETS:
                    hits = sum(r[arm][str(b)]["all"] for r in part if arm in r)
                    block[f"{arm}@{b}"] = f"{hits}/{len(part)}"
            out[f"{condition}/{split}"] = block
    return out


def require_prereg() -> None:
    path = RUN / "prereg-prompt-recall.md"
    want = (RUN / "prereg-prompt-recall.sha256").read_text().split()[-1]  # the last amendment
    if hashlib.sha256(path.read_bytes()).hexdigest() != want:
        raise SystemExit("prereg changed since it was hashed: nothing spent")


def make_squire(replay: bool, env_file: Path | None, cap: float) -> Any:
    from sanchopanza.policy import Thresholds
    from sanchopanza.providers import RecordedDecider, RecordingDecider
    from sanchopanza.redact import redact_secrets
    from sanchopanza.squire import Squire

    if replay:
        decider: Any = RecordedDecider.from_file(RECORDINGS)
    else:
        require_prereg()
        if env_file is None:
            raise SystemExit("--env-file is required for a live run")
        from sanchopanza.providers.jev import JevDecider

        key = next(v.strip().strip("'\"") for n, _, v in
                   (line.partition("=") for line in env_file.read_text("utf-8").splitlines())
                   if n.strip() == "TYPESAFE_API_KEY")  # fmt: skip
        RECORDINGS.parent.mkdir(parents=True, exist_ok=True)
        decider = RecordingDecider(JevDecider(key, model=MODEL), RECORDINGS)
    return Squire(decider, thresholds=Thresholds().with_(max_usd=cap, max_decisions=100_000),
                  redact=redact_secrets)  # fmt: skip


def run(mode: str, replay: bool, env_file: Path | None, cap: float) -> dict[str, Any]:
    squire = make_squire(replay, env_file, cap) if mode == "jev" else None
    rows: list[dict[str, Any]] = []
    failures = 0

    async def go() -> None:  # one event loop for every decider call
        nonlocal failures
        for unit in units():
            for condition in CONDITIONS:
                history, prompt, needed = setting(unit, condition)
                pieces = guard.pieces_of(history)
                texts = free_arms(history, prompt, pieces)
                if squire is not None:
                    try:
                        verdicts = await guard.judge_verdicts(squire, pieces, prompt)
                    except Exception:  # noqa: BLE001 - counted, never hidden
                        verdicts, failures = None, failures + 1
                    texts = {**texts, **decided_arms(history, prompt, pieces, verdicts)}
                rows.append({"unit": unit["unit"], "split": unit["split"], "condition": condition,
                             "pieces": len(pieces),
                             "decided": (not squire.exhausted) if squire is not None else None,
                             **{arm: {str(b): score(needed, t[b]) for b in BUDGETS}
                                for arm, t in texts.items()}})  # fmt: skip

    asyncio.run(go())
    arms = ("recent", "bm25", "rule") + (("judge", "cascade") if squire is not None else ())
    report: dict[str, Any] = {"mode": "replay" if replay else mode, "rows": rows,
                              "summary": summarize(rows, arms),
                              "decider_failures": failures}  # fmt: skip
    if squire is not None:
        report = {
            **report,
            "jev_usd": round(squire.meter.cost_usd, 6),
            "exhausted": squire.exhausted,
        }
    return report


def run_keep(replay: bool, env_file: Path | None, cap: float) -> dict[str, Any]:
    """Amendment 5: `keep` (the product's cascade) on KEEP_CONDITIONS, the earlier judge on
    KEEP_NEW only, both at the same budgets and measure; free arms alongside."""
    from sanchopanza.context import keep

    global RECORDINGS
    RECORDINGS = KEEP_RECORDINGS
    squire = make_squire(replay, env_file, cap)
    rows: list[dict[str, Any]] = []
    failures = {"keep": 0, "judge": 0}

    async def go() -> None:
        work = [(u, c) for c in KEEP_CONDITIONS for u in units()]
        for unit, condition in work:
            history, prompt, needed = setting(unit, condition)
            pieces = guard.pieces_of(history)
            texts = free_arms(history, prompt, pieces)
            row: dict[str, Any] = {"unit": unit["unit"], "split": unit["split"],
                                   "condition": condition, "pieces": len(pieces)}  # fmt: skip
            scores = await keep.score(squire, pieces, [prompt])  # once; fitted per budget
            if scores == keep.FAILED:
                failures["keep"] += 1
            for b in BUDGETS:
                facts, chooser, _ = keep.fit(history, [prompt], pieces, scores, b)
                texts.setdefault("keep", {})[b] = text_of(facts)
                row.setdefault("keep_chooser", {})[str(b)] = chooser
            row["decided_keep"] = not squire.exhausted
            rows.append({**row, **{a: {str(b): score(needed, t[b]) for b in BUDGETS}
                                   for a, t in texts.items()}})  # fmt: skip
        for row, (unit, condition) in zip(list(rows), work, strict=True):
            if condition not in KEEP_NEW:
                continue
            history, prompt, needed = setting(unit, condition)
            pieces = guard.pieces_of(history)
            try:
                verdicts = await guard.judge_verdicts(squire, pieces, prompt)
            except Exception:  # noqa: BLE001 - counted, never hidden
                verdicts, failures["judge"] = None, failures["judge"] + 1
            judged = decided_arms(history, prompt, pieces, verdicts)["judge"]
            row["judge"] = {str(b): score(needed, judged[b]) for b in BUDGETS}
            row["decided_judge"] = not squire.exhausted

    asyncio.run(go())
    return {"mode": "replay" if replay else "keep", "rows": rows, "failures": failures,
            "summary": summarize_keep(rows), "jev_usd": round(squire.meter.cost_usd, 6),
            "exhausted": squire.exhausted}  # fmt: skip


def summarize_keep(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for condition in KEEP_CONDITIONS:
        for split in ("test", "dev", "all"):
            part = [r for r in rows if r["condition"] == condition
                    and (split == "all" or r["split"] == split)]  # fmt: skip
            block: dict[str, Any] = {"units": len(part)}
            for arm in ("recent", "bm25", "rule", "keep", "judge"):
                ok = [r for r in part if arm in r and r.get(f"decided_{arm}", True)]
                for b in BUDGETS:
                    if ok:
                        block[f"{arm}@{b}"] = f"{sum(r[arm][str(b)]['all'] for r in ok)}/{len(ok)}"
            out[f"{condition}/{split}"] = block
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("free", "jev", "keep"))
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument("--cap", type=float, default=None,
                        help="decider USD cap (default as registered: 0.40 jev, 0.19 keep)")
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "keep":
        report = run_keep(args.replay, args.env_file, 0.19 if args.cap is None else args.cap)
        KEEP_OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
        print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=1))
        return 0
    report = run(args.mode, args.replay, args.env_file, 0.40 if args.cap is None else args.cap)
    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
