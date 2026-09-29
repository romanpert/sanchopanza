"""Mechanics probe: does a function-hook compaction change what the model sees?

    python probe.py build              # free: the working files and the plugin
    python probe.py live <label>       # one headless session, auto-compaction forced low
    python probe.py resume <label>     # one resumed turn on that session
    python probe.py read <label>       # free: per-call context sizes, the marker, the chain

Not a hypothesis test: it checks the path the next experiment depends on. One session of
Haiku 4.5 reads twelve 9,000-character files one call at a time with
CLAUDE_AUTOCOMPACT_PCT_OVERRIDE low, so Claude Code's own auto-compaction fires mid-turn and
runs the `session.compact` function hook (arm `mask`, free, no decider). If the masking reaches
the model, the context of the first call after the compaction is smaller than the last before.
Everything lives under ~/.cache/sanchopanza/context-lean/probe; nothing is written to the repo
except `probe-results.jsonl` (numbers only, no paths).
"""

# ruff: noqa: E501, B905  (a measurement script, kept as it ran)

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
ROOT = Path.home() / ".cache" / "sanchopanza" / "context-lean" / "probe"
PYTHON = str(REPO / ".venv" / "Scripts" / "python.exe")
WRAPPER = str(REPO / "docs" / "results" / "2026-09-28-context-e2e" / "compact_wrapper.py")
HOOK_TS = REPO / "src" / "sanchopanza" / "harness" / "compact_hook.ts"
MODEL = "claude-haiku-4-5-20251001"
CAP = 0.40
STUB = ""  # e.g. " --stub-style index"
PCT = "75"  # of the effective window (100k window - 20k output reserve = 80k): 60,000 tokens; the empty session is ~38k
PROMPT = (
    "Start by reading start.txt with the Read tool. Each file names the next file to read on "
    "its NEXT line; follow the chain until a file says NEXT: none. Do not use any other tool. "
    "Then reply with the CODE line of the first and of the last file, nothing else."
)
FOLLOW = (
    "Without reading any file again, what was the CODE line of the third file in the chain? "
    "If you no longer have it, say so."
)
WORDS = [
    "ledger",
    "audit",
    "meter",
    "pallet",
    "invoice",
    "region",
    "window",
    "drift",
    "token",
    "probe",
    "helper",
    "batch",
]


def build() -> None:
    work = ROOT / "work"
    shutil.rmtree(ROOT, ignore_errors=True)
    work.mkdir(parents=True)
    rng = random.Random("context-lean-probe")
    names = ["start.txt"] + [f"{rng.getrandbits(40):010x}.txt" for _ in range(19)]
    for i, name in enumerate(names):
        code = f"CODE-{i + 1:02d}: {rng.randint(100000, 999999)}"
        nxt = names[i + 1] if i + 1 < len(names) else "none"
        lines = [code, f"NEXT: {nxt}"] + [
            " ".join(rng.choice(WORDS) for _ in range(12)) + f" {rng.randint(0, 99999)}"
            for _ in range(110)
        ]
        (work / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
    plugin = ROOT / "plugin" / "hooks"
    plugin.mkdir(parents=True)
    shutil.copy(HOOK_TS, plugin / "compact_hook.ts")
    (plugin / "hooks.json").write_text(json.dumps({"modules": ["./compact_hook.ts"]}), "utf-8")
    print("built", sum(len(p.read_text()) for p in work.glob("*.txt")), "chars")


def env_for(evidence: Path) -> dict[str, str]:
    drop = ("ANTHROPIC_", "TYPESAFE_", "SANCHOPANZA_", "SANCHO_")
    env = {k: v for k, v in os.environ.items() if not k.startswith(drop)}
    return {
        **env,
        "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": PCT,
        "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "100000",
        "CLAUDE_CODE_ENABLE_FUNCTION_HOOKS": "1",
        "SANCHOPANZA_COMPACT_COMMAND": f"{PYTHON} {WRAPPER} M {evidence} --mask-turns 3{STUB}",
        "SANCHOPANZA_COMPACT_MARKER": str(evidence / "marker.txt"),
    }


def run(label: str, prompt: str, resume: str | None) -> None:
    evidence = ROOT / label
    evidence.mkdir(parents=True, exist_ok=True)
    cmd = ["claude", "-p", prompt, "--model", MODEL, "--max-budget-usd", f"{CAP:.2f}",
           "--output-format", "json", "--setting-sources", "project", "--strict-mcp-config",
           "--permission-mode", "dontAsk", "--plugin-dir", str(ROOT / "plugin"),
           "--debug", "--allowedTools", "Read"]  # fmt: skip
    if resume:
        cmd[3:3] = ["--resume", resume]
    proc = subprocess.run(cmd, cwd=ROOT / "work", env=env_for(evidence), capture_output=True,
                          text=True, encoding="utf-8", timeout=600, stdin=subprocess.DEVNULL)  # fmt: skip
    name = "resume" if resume else "live"
    (evidence / f"{name}.json").write_text(proc.stdout or "", encoding="utf-8")
    (evidence / f"{name}.stderr.txt").write_text(proc.stderr or "", encoding="utf-8")
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    print(
        name,
        "exit",
        proc.returncode,
        "cost (cumulative)",
        result.get("total_cost_usd"),
        "session",
        result.get("session_id"),
        "\n",
        str(result.get("result"))[:300],
    )


def transcript(session: str) -> Path:
    hits = list((Path.home() / ".claude" / "projects").glob(f"*/{session}.jsonl"))
    if not hits:
        raise SystemExit(f"no transcript for {session}")
    return hits[0]


def read(label: str) -> None:
    evidence = ROOT / label
    live = json.loads((evidence / "live.json").read_text("utf-8").strip().splitlines()[-1])
    rows = [
        json.loads(x)
        for x in transcript(live["session_id"]).read_text("utf-8").splitlines()
        if x.strip()
    ]
    calls, seen = [], set()
    for row in rows:
        msg = row.get("message") or {}
        usage = msg.get("usage")
        if row.get("type") == "assistant" and usage and msg.get("id") not in seen:
            seen.add(msg.get("id"))
            calls.append(
                usage.get("input_tokens", 0)
                + usage.get("cache_read_input_tokens", 0)
                + usage.get("cache_creation_input_tokens", 0)
            )
        if row.get("type") == "system" and row.get("subtype") == "compact_boundary":
            calls.append("BOUNDARY")
    marker = (
        (evidence / "marker.txt").read_text("utf-8") if (evidence / "marker.txt").exists() else ""
    )
    stubs = sum("sanchopanza pruned" in json.dumps(r.get("message") or {}) for r in rows)
    out = {"label": label, "context_per_call": calls, "stubs_in_file": stubs,
           "marker": [line.split(" ", 1)[1] for line in marker.splitlines()]}  # fmt: skip
    print(json.dumps(out, indent=1))
    with (HERE / "probe-results.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(out) + "\n")


def main(argv: list[str]) -> int:
    if argv[0] == "build":
        build()
    elif argv[0] == "live":
        run(argv[1], PROMPT, None)
    elif argv[0] == "resume":
        live = json.loads(
            (ROOT / argv[1] / "live.json").read_text("utf-8").strip().splitlines()[-1]
        )
        run(argv[1], FOLLOW, live["session_id"])
    elif argv[0] == "read":
        read(argv[1])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
