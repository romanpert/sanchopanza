"""Live probe: does the split guard reach the model whole, every part inline, after a compaction?

    python benchmarks/guard_split/probe.py                      # free: the plan and the estimate
    python benchmarks/guard_split/probe.py --run --cap 0.60     # one real session, Haiku 4.5

Estimated cost at list prices, from the arithmetic in `estimate()`: about 0.25 USD (between 0.15
and 0.40), against the subscription the coordinating session uses (ANTHROPIC_* and CLAUDE_CODE_*
are dropped from the child's environment, as in benchmarks/adopt). `--cap` is a hard ceiling: each
`claude -p` call gets `--max-budget-usd` of what is left, and the probe stops when the reported
cost reaches it. One run; nothing retries.

What it does, in a throwaway project under the system temp folder (or `--root`):

1. Writes `emit.py`, which prints 60 lines `E07-L23: <32 hex>` for its argument, and a
   `.claude/settings.json` holding only the guard's hooks, split in `--parts` parts (6, as
   `sanchopanza install` writes them), run with this worktree's `src` on PYTHONPATH and the guard's
   state and log inside the project folder. `--setting-sources project`: the person's own
   settings and hooks are not loaded. HOME is kept, so the subscription login is too; the
   transcript lands in ~/.claude/projects/<the temp folder's slug>/.
2. Call 1: Haiku runs `python emit.py 1` to `python emit.py N` (`--emits`, 18: about 44,000
   characters of one-shot output, the guard's whole budget), one Bash call each.
3. Call 2: `/compact` on the same session (`--resume`): PreCompact splits the guard, the K
   SessionStart(compact) commands print one part each.
4. Reads the transcript after the compaction boundary: the `hook_additional_context` attachment of
   SessionStart, how many parts it holds, each part's size, and whether any part came back as a
   `<persisted-output>` notice (the 10,000-character limit). Takes a marker label from the part
   that names itself last ("part N of N").
5. Call 3: asks, without running anything, for the value after that label. The value is 32 random
   hex characters inside 60 like it, so a summary does not carry it; only the last part does.

Passes when every part the guard kept is in the attachment inline (no persisted notice), their
count matches the guard's log, and the model answers the marker's value.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"
MODELS = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-5-5",
    "opus": "claude-opus-5-5",
}
# List prices per million tokens (input, cache write 5 min, cache read, output). Opus 5.5 as in
# benchmarks/meter.py; Sonnet 5.5 is not in that table, so it is priced at Opus's rates, an upper
# bound. The hard ceiling is Claude Code's own --max-budget-usd, not this table.
PRICES = {
    "haiku": {"input": 1.00, "write": 1.25, "read": 0.10, "output": 5.00},
    "sonnet": {"input": 5.00, "write": 6.25, "read": 0.50, "output": 25.00},
    "opus": {"input": 5.00, "write": 6.25, "read": 0.50, "output": 25.00},
}
MODEL = MODELS["haiku"]
PRICE = PRICES["haiku"]
LINES = 60
DROP = ("ANTHROPIC_", "CLAUDE_CODE_", "CLAUDE_EFFORT", "CLAUDECODE", "CLAUDE_AGENT_SDK",
        "CLAUDE_PID", "SANCHOPANZA_", "SANCHO_", "TYPESAFE_")  # fmt: skip

EMIT = """import hashlib
import sys

i = int(sys.argv[1])
for n in range(1, {lines} + 1):
    value = hashlib.sha256(f"{{i}}-{{n}}".encode()).hexdigest()[:32]
    print(f"E{{i:02d}}-L{{n:02d}}: {{value}}")
"""


def value_of(i: int, n: int) -> str:
    return hashlib.sha256(f"{i}-{n}".encode()).hexdigest()[:32]


def estimate(emits: int, price: dict[str, float] | None = None) -> dict[str, float]:
    """Tokens and USD at list prices. A hex line is about 25 tokens; Claude Code's system prompt
    and tools about 20,000; one turn per command, the context growing by one output each."""
    system, per_output, turns = 20_000, LINES * 25, emits + 1
    reads = sum(system + k * per_output for k in range(turns))
    writes = system + emits * (per_output + 150)
    compaction_in = system + emits * per_output
    guard_tokens = emits * per_output  # what the parts carry back after the compaction
    tokens = {
        "read": reads + system,
        "write": writes + guard_tokens + 3_000,
        "input": compaction_in,
        "output": turns * 120 + 3_000 + 100,
    }
    rates = PRICE if price is None else price
    usd = sum(tokens[k] * rates[k] / 1_000_000 for k in tokens)
    return {**{f"{k}_tokens": float(v) for k, v in tokens.items()}, "usd": round(usd, 3)}


def hook_command(python: Path, part: int, parts: int) -> str:
    base = f"{python.as_posix()} -m sanchopanza guard-hook"
    return f"{base} --part {part} --parts {parts}" if part else f"{base} --parts {parts}"


def settings(python: Path, parts: int) -> dict[str, Any]:
    starts = [{"type": "command", "command": hook_command(python, i, parts)}
              for i in range(1, parts + 1)]  # fmt: skip
    return {"hooks": {
        "PreCompact": [{"matcher": "manual|auto",
                        "hooks": [{"type": "command", "command": hook_command(python, 0, parts)}]}],
        "SessionStart": [{"matcher": "compact", "hooks": starts}],
    }}  # fmt: skip


def child_env(state: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(DROP)}
    return {**env, "PYTHONPATH": str(SRC), "DISABLE_AUTOUPDATER": "1",
            "SANCHOPANZA_GUARD_DIR": str(state / "kept"),
            "SANCHOPANZA_GUARD_LOG": str(state / "guard.jsonl")}  # fmt: skip


def prepare(root: Path, parts: int) -> Path:
    work = root / "work"
    (work / ".claude").mkdir(parents=True)
    (work / "emit.py").write_text(EMIT.format(lines=LINES), encoding="utf-8", newline="\n")
    text = json.dumps(settings(Path(sys.executable), parts), indent=1)
    (work / ".claude" / "settings.json").write_text(text, encoding="utf-8", newline="\n")
    return work


def claude(
    work: Path, env: dict[str, str], budget: float, prompt: str, session: str = ""
) -> dict[str, Any]:
    """One `claude -p` call; its session id, reported cost and answer."""
    command = ["claude", "-p", "--model", MODEL, "--max-budget-usd", f"{budget:.2f}",
               "--output-format", "stream-json", "--verbose", "--setting-sources", "project",
               "--strict-mcp-config", "--permission-mode", "bypassPermissions",
               *(["--resume", session] if session else []), prompt]  # fmt: skip
    done = subprocess.run(command, cwd=work, env=env, capture_output=True, text=True,
                          encoding="utf-8", timeout=900)  # fmt: skip
    out: dict[str, Any] = {
        "session": session,
        "cost": 0.0,
        "answer": "",
        "stderr": done.stderr[-400:],
    }
    for line in done.stdout.splitlines():
        if not line.startswith("{"):
            continue
        event = json.loads(line)
        out["session"] = event.get("session_id") or out["session"]
        if event.get("type") == "result":
            out["cost"] = float(event.get("total_cost_usd") or 0.0)
            out["answer"] = str(event.get("result") or "")
    (work.parent / f"stream-{len(list(work.parent.glob('stream-*')))+1}.jsonl").write_text(
        done.stdout, encoding="utf-8")  # fmt: skip
    return out


def attachment_after_compaction(session: str) -> list[str] | None:
    """The SessionStart `hook_additional_context` parts after the last compaction boundary."""
    transcript = next(Path.home().joinpath(".claude", "projects").glob(f"*/{session}.jsonl"), None)
    if transcript is None:
        return None
    lines = transcript.read_text(encoding="utf-8").splitlines()
    boundary = max((i for i, x in enumerate(lines) if "compact_boundary" in x), default=-1)
    if boundary < 0:
        return None
    for line in lines[boundary:]:
        if "hook_additional_context" not in line:
            continue
        attachment = json.loads(line).get("attachment") or {}
        if attachment.get("hookEvent") == "SessionStart":
            return [str(c) for c in attachment.get("content") or []]
    return []


def marker(parts: list[str]) -> tuple[str, str] | None:
    """(label, expected value) from the part that names itself last."""
    numbered = [p for p in parts if p.startswith("[sanchopanza guard, part ")]
    if not numbered:
        return None
    last = max(numbered, key=lambda p: int(p.split("part ", 1)[1].split(" ", 1)[0]))
    for line in last.splitlines():
        if line.startswith("E") and "-L" in line[:6] and ": " in line:
            label = line.split(": ", 1)[0]
            i, n = int(label[1:3]), int(label.split("-L", 1)[1])
            return label, value_of(i, n)
    return None


def room_for(spent: float, last: float, cap: float) -> bool:
    """Whether the next call fits under the cap. `--max-budget-usd` stops between turns, never
    inside one, and a resumed call reloads the whole context: with Opus 5.5 the third call cost
    0.94 USD with 0.34 left. The context only grows, so the next call costs at least the last."""
    return spent + last <= cap


def probe_root(given: str) -> Path:
    """Absolute: the hooks run with the throwaway project as cwd, so a relative root would put
    the guard log inside it and the report would read it as missing."""
    return (Path(given) if given else Path(tempfile.mkdtemp(prefix="guard-split-"))).resolve()


def run(args: argparse.Namespace) -> int:
    root = probe_root(args.root)
    work = prepare(root, args.parts)
    env = child_env(root)
    spent, report = 0.0, {"root": str(root)}
    emits = " ; ".join(f"python emit.py {i}" for i in range(1, args.emits + 1))
    first = claude(work, env, args.cap, "Run each of these commands with the Bash tool, one "
                   f"command per call, in this order: {emits}. Do not repeat or summarise their "
                   "output. Then reply only DONE.")  # fmt: skip
    spent += first["cost"]
    report["call1"] = {k: first[k] for k in ("cost", "answer")}
    if not first["session"] or not room_for(spent, first["cost"], args.cap):
        report["stopped"] = "no session" if not first["session"] else "cap reached after call 1"
        return finish(report, root, args)
    second = claude(work, env, args.cap - spent, "/compact", first["session"])
    spent += second["cost"]
    report["call2"] = {"cost": second["cost"]}
    parts = attachment_after_compaction(first["session"])
    log = root / "guard.jsonl"
    report["guard_log"] = (
        [json.loads(x) for x in log.read_text("utf-8").splitlines()] if log.exists() else []
    )
    if parts is None:
        report["stopped"] = "no compaction boundary in the transcript"
        return finish(report, root, args)
    report["parts_inline"] = len(parts)
    report["part_chars"] = [len(p) for p in parts]
    report["persisted_notices"] = sum("<persisted-output>" in p for p in parts)
    found = marker(parts)
    if found is None or not room_for(spent, second["cost"], args.cap):
        report["stopped"] = (
            "no marker in the parts" if found is None else "cap reached after call 2"
        )
        return finish(report, root, args)
    label, expected = found
    question = (
        "Without running any command or reading any file: in the tool output recorded before "
        f"the compaction, what value follows the label {label}:? Reply with the value only."
    )
    third = claude(work, env, args.cap - spent, question, first["session"])
    spent += third["cost"]
    report["call3"] = {"cost": third["cost"], "answer": third["answer"][:80]}
    report["marker"] = {"label": label, "expected": expected, "seen": expected in third["answer"]}
    kept = next(
        (r.get("parts") for r in report["guard_log"] if r.get("event") == "PreCompact"), None
    )
    report["passed"] = (report["persisted_notices"] == 0 and kept == len(parts)
                        and report["marker"]["seen"])  # fmt: skip
    report["spent_usd"] = round(spent, 4)
    return finish(report, root, args)


def finish(report: dict[str, Any], root: Path, args: argparse.Namespace) -> int:
    print(json.dumps(report, indent=1, ensure_ascii=False))
    (root / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    if not args.keep and not args.root:
        shutil.rmtree(root / "work", ignore_errors=True)  # the report and streams stay
    return 0 if report.get("passed") else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", action="store_true", help="spend: one real session")
    parser.add_argument(
        "--model",
        choices=sorted(MODELS),
        default="haiku",
        help="haiku checks the mechanism; sonnet and opus check the use",
    )
    parser.add_argument("--cap", type=float, default=0.0, help="hard ceiling in USD (required)")
    parser.add_argument("--parts", type=int, default=6)
    parser.add_argument("--emits", type=int, default=18)
    parser.add_argument("--root", default="", help="folder for the project (default: temp)")
    parser.add_argument("--keep", action="store_true", help="keep the throwaway project")
    args = parser.parse_args(argv)
    global MODEL, PRICE
    MODEL, PRICE = MODELS[args.model], PRICES[args.model]
    cost = estimate(args.emits)
    print(f"model {MODEL}; estimate: {cost['usd']:.2f} USD at list prices; "
          f"tokens {json.dumps({k: int(v) for k, v in cost.items() if k != 'usd'})}")  # fmt: skip
    print("settings:", json.dumps(settings(Path(sys.executable), args.parts))[:400], "...")
    if not args.run:
        print("dry: nothing run. Pass --run --cap USD to spend.")
        return 0
    if args.cap <= 0 or args.cap < cost["usd"]:
        print(f"--cap must be set and at least the estimate ({cost['usd']:.2f} USD)")
        return 2
    if shutil.which("claude") is None:
        print("claude is not on PATH")
        return 2
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
