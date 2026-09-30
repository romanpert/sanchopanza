"""The shell guard in a person's repository: the sandbox profile against the coding profile.

    python benchmarks/guard_coding/measure.py            # code layer only, free
    python benchmarks/guard_coding/measure.py --live     # + Jev on a sample, ~0.01 USD, capped

Three sets:
- the owner's real Bash commands from their Claude Code transcripts (local, never published:
  counts only), all of them for the code layer and a seeded sample of SAMPLE for the decider.
  They are work a person did, so a denial there is work the guard would have stopped; it is
  not by itself a false positive (a deliberate `mkfs` is still dangerous unattended);
- the guard bench (`benches/safety.jsonl`, point `command`, 32 labelled commands);
- R-Judge's trajectories with a shell action (27, labelled per trajectory; flagged when any of
  its commands is denied), as in docs/results/2026-09-28-claude-code-broad.

Writes `docs/results/2026-09-30-guard-coding/measure.json` and, with --live, records every Jev
answer in the local cache (it holds the sampled commands) so the numbers replay without a key.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "docs" / "results" / "2026-09-28-claude-code-broad"))

from sanchopanza.points import guard  # noqa: E402

OUT = REPO / "docs" / "results" / "2026-09-30-guard-coding"
CACHE = Path.home() / ".cache" / "sanchopanza" / "guard-coding"
# The answers hold the sampled commands verbatim (the owner's paths and hosts): local only.
FIXTURE = CACHE / "jev.jsonl"
SEED = 20260930
SAMPLE = 300
JEV_CAP_USD = 0.05
WORKSPACE = "C:/Users/someone/project"  # the decider sees a workspace, never the owner's paths


def real_commands() -> list[str]:
    cached = CACHE / "real.json"
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))
    out: list[str] = []
    for path in (Path.home() / ".claude" / "projects").glob("*/*.jsonl"):
        for line in path.open(encoding="utf-8", errors="replace"):
            if '"tool_use"' not in line or '"Bash"' not in line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("type") != "assistant" or d.get("isSidechain"):
                continue
            for b in (d.get("message") or {}).get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Bash":
                    out.append(str((b.get("input") or {}).get("command", "")))
    out = sorted(set(out))
    CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(out), encoding="utf-8")
    return out


def bench_commands() -> list[tuple[str, bool]]:
    rows = []
    for line in (REPO / "benches" / "safety.jsonl").read_text(encoding="utf-8").splitlines():
        if line.startswith("{"):
            row = json.loads(line)
            if row.get("point") == "command":
                rows.append((row["input"]["command"], bool(row["expected"])))
    return rows


def rjudge_trajectories() -> list[tuple[list[str], bool]]:
    import os

    import cases

    clone = Path(os.environ.get("SANCHOPANZA_RJUDGE", Path.home() / ".cache/sancho/R-Judge"))
    if not clone.exists():
        return []
    return [([c["tool_input"]["command"] for c in case["calls"]], case["label"] == "unsafe")
            for case in cases.rjudge_cases(clone)]  # fmt: skip


def code_layer() -> dict[str, Any]:
    real = real_commands()
    bench = bench_commands()
    rjudge = rjudge_trajectories()
    out: dict[str, Any] = {}
    for name, deny in (("sandbox", guard.code_denial), ("coding", guard.coding_denial)):
        denied_real = [c for c in real if deny(c)]
        reasons: dict[str, int] = {}
        for c in denied_real:
            reasons[deny(c) or ""] = reasons.get(deny(c) or "", 0) + 1
        out[name] = {
            "real_commands": len(real), "real_denied": len(denied_real),
            "real_denied_share": round(len(denied_real) / max(len(real), 1), 4),
            "real_denied_by_reason": reasons,
            "bench_unsafe_denied": sum(1 for c, bad in bench if bad and deny(c)),
            "bench_unsafe": sum(1 for _, bad in bench if bad),
            "bench_safe_denied": sum(1 for c, bad in bench if not bad and deny(c)),
            "bench_safe": sum(1 for _, bad in bench if not bad),
            "rjudge_unsafe_flagged": sum(1 for cs, bad in rjudge
                                         if bad and any(deny(c) for c in cs)),
            "rjudge_unsafe": sum(1 for _, bad in rjudge if bad),
            "rjudge_safe_flagged": sum(1 for cs, bad in rjudge
                                       if not bad and any(deny(c) for c in cs)),
            "rjudge_safe": sum(1 for _, bad in rjudge if not bad),
        }  # fmt: skip
        CACHE.joinpath(f"denied-{name}.json").write_text(json.dumps(denied_real), "utf-8")
    return out


async def decider_layer(live: bool) -> dict[str, Any]:
    """The coding profile end to end (code, then Jev at the shipped threshold) on the sample,
    the bench and R-Judge. Live answers are recorded; without --live they are replayed."""
    from sanchopanza import Squire
    from sanchopanza.journal import JsonlJournal
    from sanchopanza.providers import create
    from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider

    if live:
        decider = RecordingDecider(create("jev"), FIXTURE)
    else:
        decider = RecordedDecider.from_file(FIXTURE)
    journal = CACHE / "journal.jsonl"
    squire = Squire(decider, journal=JsonlJournal(journal))
    environment = guard.coding_environment(WORKSPACE)
    rng = random.Random(SEED)
    sample = rng.sample(real_commands(), SAMPLE)

    async def denied(command: str) -> bool:
        lines = journal.read_text("utf-8").splitlines() if journal.exists() else []
        spent = sum(json.loads(x).get("data", {}).get("cost_usd", 0.0) for x in lines)
        if live and spent > JEV_CAP_USD:
            raise SystemExit(f"Jev cap reached ({spent:.4f} USD)")
        result = await squire.guard_command(command, environment=environment, profile="coding")
        return result.denied

    sample_denied = [c for c in sample if await denied(c)]
    bench = [(bad, await denied(c)) for c, bad in bench_commands()]
    rjudge = []
    for cs, bad in rjudge_trajectories():
        flags = [await denied(c) for c in cs]
        rjudge.append((bad, any(flags)))
    CACHE.joinpath("sample-denied.json").write_text(json.dumps(sample_denied), "utf-8")
    return {
        "sample": SAMPLE, "sample_denied": len(sample_denied),
        "bench_unsafe_denied": sum(1 for bad, d in bench if bad and d),
        "bench_safe_denied": sum(1 for bad, d in bench if not bad and d),
        "rjudge_unsafe_flagged": sum(1 for bad, d in rjudge if bad and d),
        "rjudge_safe_flagged": sum(1 for bad, d in rjudge if not bad and d),
    }  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)
    result: dict[str, Any] = {"code_layer": code_layer()}
    if args.live or FIXTURE.exists():
        result["coding_with_decider"] = asyncio.run(decider_layer(args.live))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "measure.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
