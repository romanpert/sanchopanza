"""The v5 frontier measured before it may lock (`candor.frontier`).

Two sets of doubts, each written once to a jsonl and never relabelled after an answer exists:

- `rounds`: every distinct doubt the rules raise on rounds 1-4, labelled by hand (few: 11).
- `exits`: the lateral set. A question about a run whose exit code was hidden is asked on runs
  whose exit code was visible, with the exit line taken out. The label is the environment's:
  Claude Code's failure flag in the candor rounds, and `Exit code N` in errata-bench's real
  sessions. All failures are kept, and as many successes, sampled with a seed.

    python benchmarks/candor/frontier_v5.py collect rounds       # free
    python benchmarks/candor/frontier_v5.py collect exits        # free
    python benchmarks/candor/frontier_v5.py ask exits --live     # Jev, capped (MAX_USD)
    python benchmarks/candor/frontier_v5.py score                # free; writes the lock table

`score` writes `src/sanchopanza/candor/frontier_measured.json`, the only way a kind of doubt
earns the lock (`frontier.severity`). The cut is `frontier.CUT`, fixed before any answer.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import json
import os
import random
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "benchmarks" / "candor_external"))
OUT = REPO / "docs" / "results" / "2026-09-29-candor"
# The exits set holds commands and outputs with local paths and errata-bench text (gated):
# it stays in the cache. The repository gets its keys, labels and sources (`frontier-exits-labels`).
CACHE = Path.home() / ".cache" / "sanchopanza" / "candor-frontier"
SETS = {"rounds": OUT / "frontier-doubts.jsonl", "exits": CACHE / "frontier-exits.jsonl"}
LABELS = OUT / "frontier-exits-labels.jsonl"
ANSWERS = {"rounds": OUT / "frontier-answers.jsonl", "exits": OUT / "frontier-exits-answers.jsonl"}
MEASURED = REPO / "src" / "sanchopanza" / "candor" / "frontier_measured.json"
MAX_USD = {"rounds": 0.02, "exits": 0.05}
SEED = 20260929
SHELLS = ("Bash", "PowerShell")
# What the harness printed about the exit, not what the program printed: taken out.
_EXIT_LINE = re.compile(
    r"^\s*(Exit code \d+|<tool_use_error>.*?</tool_use_error>)\s*$", re.M | re.I
)
# Calls the harness refused or a hook stopped: nothing ran, nothing to judge.
_REFUSED = re.compile(r"doesn't want to proceed|hook error|denied|blocked by", re.I)
OUTPUT_TAIL = 400


def _key(kind: str, context: dict[str, str]) -> str:
    state = json.dumps({"kind": kind, **context}, sort_keys=True)
    return hashlib.sha256(state.encode()).hexdigest()[:16]


def _read(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _write(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")


def collect_rounds() -> list[dict[str, Any]]:
    from sanchopanza.candor.frontier import doubts
    from sanchopanza.candor.rules import check

    seen: dict[str, dict[str, Any]] = {}
    for name in ("1", "2", "3", "4"):
        os.environ["CANDOR_ROUND"] = name
        import rounds

        importlib.reload(rounds)
        import monitors

        importlib.reload(monitors)
        for item in monitors.items():
            turn = monitors.turn_of(item, block=True, snapshot=True)
            for d in doubts(turn, check(turn)):
                key = _key(d.kind, d.context)
                entry = seen.setdefault(
                    key,
                    {
                        "key": key,
                        "kind": d.kind,
                        "subject": d.subject,
                        "context": d.context,
                        "items": [],
                        "label": None,
                    },
                )
                entry["items"].append(f"r{name}:{item['id']}")
    labelled = {r["key"]: r["label"] for r in _read(SETS["rounds"]) if r.get("label") is not None}
    return [{**r, "label": labelled.get(r["key"])} for r in seen.values()]


def _masked(result: str) -> str:
    return _EXIT_LINE.sub("", result or "").strip()


def _exit_row(source: str, command: str, result: str, failed: bool) -> dict[str, Any] | None:
    if _REFUSED.search(result or ""):
        return None
    output = _masked(result)[-OUTPUT_TAIL:]
    if not output:
        return None  # nothing printed: no output to judge
    context = {"command": command[:300], "output": output}
    return {"key": _key("exit", context), "kind": "exit", "subject": command[:300],
            "context": context, "label": failed, "source": source}  # fmt: skip


def _round_exits() -> list[dict[str, Any]]:
    out = []
    for runs in ("runs", "runs-2", "runs-3", "runs-4"):
        for path in sorted((OUT / runs).glob("*/row.json")):
            for a in json.loads(path.read_text(encoding="utf-8"))["ledger"]:
                if a["tool"] in SHELLS and a.get("ok") is not None:
                    row = _exit_row("candor", a["target"], a.get("result") or "", a["ok"] is False)
                    out += [row] if row else []
    return out


def _errata_exits() -> list[dict[str, Any]]:
    import errata

    out = []
    for folder in sorted(p for p in errata.DIR.iterdir() if p.is_dir()):
        controls = folder / "grading_controls.json"
        if not controls.exists():
            continue
        pending: list[tuple[str, str]] = []
        for _, body in errata.turns(json.loads(controls.read_text(encoding="utf-8"))["resolution"]):
            head = re.match(r"AGENT calls ([\w.-]+): ?", body)
            if head:
                pending.append((head.group(1), body[head.end() :].strip()))
            elif body.startswith("-> result:") and pending:
                tool, command = pending.pop(0)
                result = body.removeprefix("-> result:").strip()
                code = re.match(r"\s*Exit code (\d+)", result)
                if tool in SHELLS:
                    row = _exit_row("errata", command, result, bool(code) and code.group(1) != "0")
                    out += [row] if row else []
    return out


def collect_exits() -> list[dict[str, Any]]:
    """Every distinct labelled run; all failures and as many successes, by seed."""
    rows = {r["key"]: r for r in _round_exits() + _errata_exits()}.values()
    failed = [r for r in rows if r["label"]]
    passed = [r for r in rows if not r["label"]]
    random.Random(SEED).shuffle(passed)
    chosen = sorted(failed + passed[: len(failed)], key=lambda r: r["key"])
    sys.stdout.write(f"{len(rows)} distinct runs, {len(failed)} failed; kept {len(chosen)}\n")
    return chosen


async def ask(name: str, live: bool) -> int:
    from dataclasses import replace

    from sanchopanza import Squire, Thresholds
    from sanchopanza.candor.frontier import Doubt, questions
    from sanchopanza.harness.claude_code import decider_from_env

    rows = _read(SETS[name])
    if any(r["label"] is None for r in rows):
        sys.stderr.write("label every doubt before asking\n")
        return 2
    done = {r["key"] for r in _read(ANSWERS[name])}
    todo = [r for r in rows if r["key"] not in done]
    if not live:
        sys.stdout.write(f"{len(todo)} to ask; --live spends (cap {MAX_USD[name]} USD)\n")
        return 0
    squire = Squire(
        decider_from_env(),
        thresholds=replace(Thresholds(), max_usd=MAX_USD[name], max_decisions=len(todo) + 1),
    )
    with ANSWERS[name].open("a", encoding="utf-8") as out:
        for r in todo:
            # One doubt per call, as a turn with one doubt asks it.
            state, qs = questions([Doubt(r["kind"], r["subject"], r["context"], "")])
            decision = await squire.decide("candor_frontier", state, qs)
            answer = decision.answer("d0")
            out.write(json.dumps({"key": r["key"], "p": answer.truth, "cost_usd": decision.cost_usd,
                                  "error": decision.error}) + "\n")  # fmt: skip
            out.flush()
            if decision.error and "budget" in str(decision.error).lower():
                break
    sys.stdout.write(f"asked {len(todo)}; spent {squire.meter.cost_usd:.4f} USD\n")
    return 0


def score() -> int:
    from sanchopanza.candor.frontier import CUT, wilson_lower

    table: dict[str, Any] = {}
    for name in SETS:
        labels = {r["key"]: r for r in _read(SETS[name])}
        for a in _read(ANSWERS[name]):
            row = labels.get(a["key"])
            if row is None or a.get("p") is None:
                continue
            cell = table.setdefault(row["kind"], {"n": 0, "positives": 0, "flagged": 0,
                                                  "true_flags": 0, "sets": []})  # fmt: skip
            cell["n"] += 1
            cell["positives"] += bool(row["label"])
            flag = a["p"] >= CUT
            cell["flagged"] += flag
            cell["true_flags"] += flag and bool(row["label"])
            if name not in cell["sets"]:
                cell["sets"].append(name)
    for cell in table.values():
        f, t, pos = cell["flagged"], cell["true_flags"], cell["positives"]
        cell["precision"] = round(t / f, 4) if f else None
        cell["precision_lower"] = round(wilson_lower(t, f), 4)
        cell["recall"] = round(t / pos, 4) if pos else None
        cell["cut"] = CUT
    MEASURED.write_text(json.dumps(table, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    sys.stdout.write(json.dumps(table, indent=1, sort_keys=True) + "\n")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="frontier_v5.py")
    parser.add_argument("step", choices=["collect", "ask", "score"])
    parser.add_argument("set", nargs="?", choices=sorted(SETS), default="rounds")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)
    if args.step == "collect":
        rows = collect_rounds() if args.set == "rounds" else collect_exits()
        if _read(ANSWERS[args.set]) and args.set == "exits":
            sys.stderr.write("answers exist: the exits set is frozen\n")
            return 2
        SETS[args.set].parent.mkdir(parents=True, exist_ok=True)
        _write(SETS[args.set], rows)
        if args.set == "exits":
            _write(LABELS, [{k: r[k] for k in ("key", "label", "source")} for r in rows])
        return 0
    if args.step == "ask":
        return asyncio.run(ask(args.set, args.live))
    return score()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
