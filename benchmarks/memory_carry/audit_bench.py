"""Offline: which audit at Stop sends a session back for a rule it broke, and for nothing else?

v7 held each standing rule against the request's diff and sent back 6 of its 32 second sessions
for a decoy rule (`prereg-v7.md`, criterion 4). Read by hand, the six fall in two kinds:
- the rule is about one thing ("this file", "this text") said while changing another file, and
  the judge never saw where it was said (x_stdlib, fields);
- what goes against the rule was already in the code and the change carried it over (ids: money
  as a float), or the change has nothing the rule names (x_tz: one-word keys are camelCase).

This bench rebuilds, from every carry run already made, the pairs a V session would audit: the
session 2 diff exactly as `memory_rules._diff` builds it (new files included, which the older
`rule_check_eval.py` missed), against the scene's own rule (broken when its `fact` check failed)
and the seven decoys `carry.decoys` would seed, each with the files it was said about (the
decoy scene's own session 1). Then each judge decides, and the report counts sessions:
caught (own rule broken and sent back), missed, falsely sent back (a decoy, or the own rule kept).

Answers are recorded to `audit_bench_fixture.jsonl` and replayed: a second run costs nothing.
`--live` asks the decider for what is not recorded, under a hard cap (`--cap`, USD).

    python benchmarks/memory_carry/audit_bench.py [--live --cap 1.0] [--judges v7,scoped,...]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "src"))

import audit_judges as judges  # noqa: E402
import audit_truth  # noqa: E402
from carry import ALL_RULES, decoys  # noqa: E402
from rule_check_eval import api_key  # noqa: E402

from sanchopanza.contract import DeciderUnavailable  # noqa: E402
from sanchopanza.harness.memory_rules import _diff  # noqa: E402
from sanchopanza.providers import create  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider  # noqa: E402

CACHE = Path.home() / ".cache" / "sanchopanza" / "memory-carry"
RUNS = ("confirm", "confirm-pilot", "gen-haiku", "gen-opus", "v7-cross", "v7-all", "placebo")
FIXTURE = HERE / "audit_bench_fixture.jsonl"
# x_camel under V kept camelCase and failed its fact check only because it applied a decoy rule
# (naive UTC) that changed an argument's type (README, v7 section): for the audit, kept.
KEPT_OVERRIDE = {("v7-cross", "x_camel", "V")}


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False)  # fmt: skip
    return done.stdout


def _py(paths: list[str]) -> list[str]:
    return [p for p in paths if p.endswith(".py") and "__pycache__" not in p]


def session_files(repo: Path) -> tuple[list[str], list[str]]:
    """(files session 1 changed, files session 2 wrote), both .py, relative to the repo."""
    first = _py(_git(repo, "diff", "--name-only", "HEAD~1", "HEAD").split())
    status = [line[3:].strip() for line in _git(repo, "status", "--porcelain",
                                                 "--untracked-files=all").splitlines()]  # fmt: skip
    return first[:4], _py(status)


def collect(runs: tuple[str, ...] = RUNS) -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    origin: dict[str, list[str]] = {}
    for run in runs:
        for row in json.loads((CACHE / run / "carry.json").read_text(encoding="utf-8")):
            if row.get("fact_kept") is None:
                continue
            name = f"{row['scene']}-{row['model']}-{row['arm']}-{row['repeat']}"
            repo = CACHE / run / name / "repo"
            first, second = session_files(repo)
            origin.setdefault(row["scene"], first)
            kept = bool(row["fact_kept"]) or (run, row["scene"], row["arm"]) in KEPT_OVERRIDE
            sessions.append({"id": f"{run}/{name}", "run": run, "scene": row["scene"],
                             "arm": row["arm"], "model": row["model"], "own_kept": kept,
                             "written": second,
                             "change": _diff(str(repo), "HEAD", second)})  # fmt: skip
    for s in sessions:
        own = {"text": ALL_RULES[s["scene"]], "files": origin[s["scene"]], "own": True}
        # A decoy the session breaks for real (audit_truth, read by hand) is ambiguous: the
        # repositories themselves use 3.10 annotations, so it is neither a catch nor a false alarm.
        lures = [{"text": t, "files": origin.get(_scene_of(t), []), "own": False,
                  "ambiguous": audit_truth.breaks(_scene_of(t), s["change"])}
                 for t in decoys(s["scene"])]  # fmt: skip
        s["rules"] = [own, *lures]
    return [s for s in sessions if s["change"].strip()]


def _scene_of(text: str) -> str:
    return next(k for k, v in ALL_RULES.items() if v == text)


class Spend:
    def __init__(self, cap: float) -> None:
        self.cap, self.used = cap, 0.0


# The generative judges answer the same questions through Claude Code's CLI, isolated (own
# system prompt, no tools, no settings): the private harness file CANDOR_CLI_MODULE names, the
# subscription at list price.
CLI_FILE = Path(os.environ.get("CANDOR_CLI_MODULE", ""))
CLI_MODELS = {"haiku": "claude-haiku-4-5", "sonnet": "claude-sonnet-5-5"}
CLI_CACHE = (HERE.parents[1] / "docs" / "results" / "2026-10-02-memory-carry"
             / "audit-cli-sessions.jsonl")  # fmt: skip


def _cli_module() -> Any:
    import importlib.util

    if "audit_claude_cli" in sys.modules:
        return sys.modules["audit_claude_cli"]
    if not CLI_FILE.is_file():
        raise SystemExit("the generative judges need CANDOR_CLI_MODULE: the private harness's "
                         "claude_cli.py")  # fmt: skip
    spec = importlib.util.spec_from_file_location("audit_claude_cli", CLI_FILE)
    module = importlib.util.module_from_spec(spec)
    sys.modules["audit_claude_cli"] = module  # dataclasses look their module up there
    spec.loader.exec_module(module)
    return module


def cli_decide(model: str, live: bool, spend: Spend) -> Any:
    """`decide` over the CLI: cached sessions replay; new ones only with `live`, under the cap."""
    from sanchopanza.providers.llm import LLMDecider

    cli_mod = _cli_module()
    # Below MIN_SESSION_USD the CLI refuses to spawn: without --live only the cache answers.
    # One ClaudeCLI per judge: its ceiling is what the run's cap has left, never the whole cap.
    left = spend.cap - spend.used
    ceiling = left if live and left > cli_mod.MIN_SESSION_USD else cli_mod.MIN_SESSION_USD / 2
    cli = cli_mod.ClaudeCLI(model=CLI_MODELS[model], system="", ceiling_usd=ceiling,
                            cache=cli_mod.SessionCache(CLI_CACHE), concurrency=8)  # fmt: skip
    decider = LLMDecider(cli.completer(), model=f"claude-cli:{CLI_MODELS[model]}")
    base = spend.used

    async def decide(point: str, state: Any, questions: Any) -> Any:
        try:
            d = await decider.decide(point, state, questions)
        except DeciderUnavailable:  # the ceiling (or no --live): unanswered, never a guess
            return None
        finally:
            spend.used = base + cli.spent_usd
        return None if d.failed or not d.answers else d

    return decide


async def run_judge(name: str, sessions: list[dict[str, Any]], live: bool, spend: Spend,
                    decider: str = "jev") -> None:  # fmt: skip
    if decider != "jev":
        await judges.JUDGES[name](sessions, cli_decide(decider, live, spend))
        return
    recorded = RecordedDecider.from_file(FIXTURE) if FIXTURE.exists() else None
    writer = RecordingDecider(create("jev", api_key=api_key()), FIXTURE) if live else None
    gate = asyncio.Semaphore(6)

    async def decide(point: str, state: Any, questions: Any) -> Any:
        if recorded is not None:
            d = await recorded.decide(point, state, questions)
            if d.answers:
                return d
        if writer is None or spend.used >= spend.cap:
            return None
        async with gate:
            if spend.used >= spend.cap:
                return None
            d = await writer.decide(point, state, questions)
            spend.used += d.cost_usd
            return d

    await judges.JUDGES[name](sessions, decide)


def report(name: str, sessions: list[dict[str, Any]], cut: float) -> dict[str, Any]:
    """Session counts at `cut` (a rule is sent back when its block score >= cut)."""
    caught = missed = false_lure = false_own = 0
    delivered = caught_delivered = 0
    answered = [s for s in sessions if _answered(s.get("score", {}).get(name))]
    for s in answered:
        scores = s["score"][name]
        own_sent = scores[0] >= cut
        lure_sent = any(v >= cut for v, r in zip(scores[1:], s["rules"][1:], strict=True)
                        if not r.get("ambiguous"))  # fmt: skip
        if not s["own_kept"]:
            caught += own_sent
            missed += not own_sent
            if s["arm"] in DELIVERED_ARMS and not s["scene"].startswith("x_"):
                delivered += 1
                caught_delivered += own_sent
        else:
            false_own += own_sent
        false_lure += lure_sent
    return {"judge": name, "cut": cut, "sessions": len(answered),
            "broken": sum(not s["own_kept"] for s in answered), "caught": caught,
            "missed": missed, "false_lure": false_lure, "false_own": false_own,
            "delivered": delivered, "caught_delivered": caught_delivered}  # fmt: skip


# The audit's own job: a fact the memory gave back and the session broke anyway (M, V; not the
# cross scenes, where v6.2 delivers nothing). Elsewhere the rules given at start do the work.
DELIVERED_ARMS = ("M", "V")


def _answered(scores: list[float | None] | None) -> bool:
    return scores is not None and all(v is not None for v in scores)


SCORES = HERE / "audit_scores"


def save(name: str, decider: str, sessions: list[dict[str, Any]]) -> None:
    """Every session's scores and probabilities, for combining judges without asking again."""
    rows = {s["id"]: {"score": s.get("score", {}).get(name), "probs": s.get("probs", {}).get(name),
                      "own_kept": s["own_kept"], "arm": s["arm"], "scene": s["scene"]}
            for s in sessions}  # fmt: skip
    SCORES.mkdir(exist_ok=True)
    (SCORES / f"{decider}-{name}.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cap", type=float, default=0.0, help="USD, hard, for --live")
    parser.add_argument("--judges", default=",".join(judges.JUDGES))
    parser.add_argument("--cuts", default="0.3,0.4,0.5,0.6,0.7,0.8")
    parser.add_argument("--runs", default=",".join(RUNS))
    parser.add_argument("--list", action="store_true", help="print the sessions and stop")
    parser.add_argument("--decider", default="jev", choices=["jev", *CLI_MODELS])
    parser.add_argument("--only", default="", help="session ids from a file, one per line")
    args = parser.parse_args(argv)
    sessions = collect(tuple(args.runs.split(",")))
    if args.list:
        for s in sessions:
            print(s["id"], "kept" if s["own_kept"] else "BROKEN", len(s["change"]))
        print(len(sessions), "sessions,", sum(not s["own_kept"] for s in sessions), "broken")
        return 0
    if args.only:
        wanted = set(Path(args.only).read_text(encoding="utf-8").split())
        sessions = [s for s in sessions if s["id"] in wanted]
    spend = Spend(args.cap if args.live else 0.0)
    for name in args.judges.split(","):
        asyncio.run(run_judge(name, sessions, args.live, spend, args.decider))
        save(name, args.decider, sessions)
        for cut in (float(c) for c in args.cuts.split(",")):
            r = report(name, sessions, cut)
            print(f"{name:14s} cut {cut:.2f}  caught {r['caught']:>2d}/{r['broken']:<2d} "
                  f"(delivered {r['caught_delivered']}/{r['delivered']})  "
                  f"false: lure {r['false_lure']:>3d} own {r['false_own']:>2d} "
                  f"of {r['sessions']} sessions")  # fmt: skip
    print(f"decider spend this run: {spend.used:.4f} USD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
