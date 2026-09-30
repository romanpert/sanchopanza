"""Live probe, ~0.05 USD: does compaction at a request's end work inside Claude Code?

    python benchmarks/adopt/probe_boundary.py

A throwaway repository, `sanchopanza install --scope project --compact` plus the boundary
variables (threshold 5,000 tokens, native summary), the plugin loaded with --plugin-dir so the
owner's plugin registry is not touched, every sanchopanza hook through hook_env.py to log it.
Two Haiku calls in one session: the first should end with a compaction; the second resumes it.
Prints what happened: the plugin's marker lines, the classic hook events (the PreCompact trigger,
the SessionStart source), the transcript's compaction boundary, and the second answer.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import docker_env  # noqa: E402
import run  # noqa: E402

ROOT = run.ROOT / "probe-boundary"


def main() -> int:
    docker_env.remove_tree(ROOT)
    work, evidence, plugin = ROOT / "work", ROOT / "evidence", ROOT / "plugin"
    work.mkdir(parents=True)
    evidence.mkdir()
    for i in range(1, 7):
        (work / f"part{i}.txt").write_text(f"Part {i}: " + "filler text. " * 400 + "\n",
                                           encoding="utf-8")  # fmt: skip
    (work / "README.md").write_text("# Probe\n\nThe secret word of this repository is TOPAZ.\n",
                                    encoding="utf-8")  # fmt: skip
    subprocess.run(["git", "-C", str(work), "init", "-q"], check=True)
    env = run.child_env("", "")
    done = subprocess.run([str(run.SANCHO), "install", "--scope", "project", "--compact",
                           "--plugin-dir", str(plugin), "--write"], cwd=work, env=env,
                          capture_output=True, text=True)  # fmt: skip
    assert done.returncode == 0, done.stderr
    settings_path = work / ".claude" / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    settings.pop("extraKnownMarketplaces", None)  # loaded with --plugin-dir instead
    settings.pop("enabledPlugins", None)
    settings["env"] = {**settings.get("env", {}), "SANCHOPANZA_COMPACT_AT_TOKENS": "5000",
                       "SANCHOPANZA_COMPACT_NATIVE": "1",
                       "SANCHOPANZA_COMPACT_MARKER": str(evidence / "marker.log")}  # fmt: skip
    prefix = " ".join(p.as_posix() for p in (run.PYTHON, HERE / "hook_env.py", evidence,
                                             ROOT / "no.key"))  # fmt: skip
    text = json.dumps(settings, indent=1).replace('"sanchopanza ', f'"{prefix} ')
    settings_path.write_text(text, encoding="utf-8")
    base = ["claude", "-p", "--model", run.MODELS["haiku"], "--max-budget-usd", "0.20",
            "--output-format", "stream-json", "--verbose", "--setting-sources", "project",
            "--strict-mcp-config", "--permission-mode", "bypassPermissions",
            "--plugin-dir", str(plugin)]  # fmt: skip
    first = subprocess.run([*base, "Read README.md, then read part1.txt to part6.txt one by one with the Read tool, then tell me the secret word in one line."],
                           cwd=work, env=env, capture_output=True, text=True, timeout=600)  # fmt: skip
    (evidence / "stream-1.jsonl").write_text(first.stdout, encoding="utf-8")
    session = next((json.loads(x).get("session_id") for x in first.stdout.splitlines()
                    if x.startswith("{") and "session_id" in x), "")  # fmt: skip
    second = subprocess.run([*base, "--resume", session, "Without reading any file again: what "
                             "was the secret word? One word."], cwd=work, env=env,
                            capture_output=True, text=True, timeout=600)  # fmt: skip
    (evidence / "stream-2.jsonl").write_text(second.stdout, encoding="utf-8")
    for name, stream in (("first", first.stdout), ("second", second.stdout)):
        for line in stream.splitlines():
            if not line.startswith("{"):
                continue
            event = json.loads(line)
            if event.get("type") == "system" and event.get("subtype") == "compact_boundary":
                print(name, "compact_boundary", event.get("compact_metadata")
                      or event.get("compactMetadata"))  # fmt: skip
            if event.get("type") == "result":
                print(name, "result:", event.get("subtype"), round(event.get("total_cost_usd", 0), 4),
                      "|", str(event.get("result"))[:120].replace("\n", " "))  # fmt: skip
    marker = evidence / "marker.log"
    print("marker:", marker.read_text(encoding="utf-8") if marker.exists() else "(none)")
    hooks = evidence / "hooks.jsonl"
    print("hooks:", hooks.read_text(encoding="utf-8") if hooks.exists() else "(none)")
    transcript = next(Path.home().joinpath(".claude", "projects").glob(f"*/{session}.jsonl"), None)
    if transcript:
        boundaries = [json.loads(x).get("compactMetadata") for x in
                      transcript.read_text(encoding="utf-8").splitlines() if "compact_boundary" in x]  # fmt: skip
        print("transcript boundaries:", boundaries)
    print("stderr:", first.stderr[-400:], second.stderr[-400:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
