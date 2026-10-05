"""Wall time of the v6 events, a new process each as Claude Code runs them: a Bash call that
names no recorded file (most of them), one that gives a record, and a prompt and a Stop with the
working-tree snapshot on and off, on a local clone of this repository with three dirty files.
Free.

    python benchmarks/memory_real/latency_v6.py [--runs 15]
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from sanchopanza.context import episodes as ep  # noqa: E402

LINE = "    return [part.strip() for part in text.split(',')]"


def run(event: dict, env: dict, runs: int) -> tuple[float, float]:
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        subprocess.run([sys.executable, "-m", "sanchopanza.cli", "memory-hook"],
                       input=json.dumps(event), text=True, capture_output=True, env=env,
                       check=False)  # fmt: skip
        times.append(time.perf_counter() - start)
    return statistics.median(times), max(times)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=15)
    parser.add_argument("--stale-index", action="store_true", help="a fresh clone, never refreshed")
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory() as tmp:
        clone = Path(tmp) / "clone"
        subprocess.run(["git", "clone", "-q", "--local", str(REPO), str(clone)], check=True)
        for rel in ("README.md", "src/sanchopanza/text.py", "tests/test_memory_hook.py"):
            path = clone / rel
            path.write_text(path.read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8")
        if not args.stale_index:  # as after the person's own git commands: the index is fresh
            subprocess.run(["git", "-C", str(clone), "status", "-s"], capture_output=True)
        cwd = str(clone).replace("\\", "/")
        store = Path(tmp) / "memory"
        env = {**os.environ, "PYTHONPATH": str(REPO / "src"),
               "SANCHOPANZA_MEMORY_STORE": str(store)}  # fmt: skip
        project = Path(tmp) / "projects" / "p"
        project.mkdir(parents=True)
        transcript = project / "s2.jsonl"
        transcript.write_text(json.dumps({"type": "user", "cwd": cwd, "message": {
            "role": "user", "content": "go"}}) + "\n", encoding="utf-8")  # fmt: skip
        record = ep.Episode(session="s1", index=1, request="fix parse", report="done",
                            changed=("pkg/parse.py",), changed_raw=("pkg/parse.py",),
                            wrote=(("pkg/parse.py", (ep.line_print(LINE),)),), at=time.time())
        ep.save(store / "p", [record])
        base = {"session_id": "s2", "transcript_path": str(transcript), "cwd": cwd}
        rows = {}
        bash = {**base, "hook_event_name": "PostToolUse", "tool_name": "Bash"}
        rows["Bash, no recorded file"] = run({**bash, "tool_input": {
            "command": "pytest -q tests/test_text.py"}, "tool_response": {"stdout": "3 passed"}},
            env, args.runs)  # fmt: skip
        rows["Bash, gives a record"] = run({**bash, "tool_input": {
            "command": "sed -n 1,9p pkg/parse.py"}, "tool_response": {"stdout": LINE}},
            env, args.runs)  # fmt: skip
        prompt = {**base, "hook_event_name": "UserPromptSubmit", "prompt": "go"}
        stop = {**base, "hook_event_name": "Stop"}
        first = transcript.read_text(encoding="utf-8")
        answer = {"type": "assistant", "message": {"role": "assistant", "content": "done"}}
        second = [{"type": "user", "cwd": cwd, "message": {"role": "user", "content": "again"}},
                  {"type": "assistant", "message": {"role": "assistant", "content": [
                      {"type": "tool_use", "id": "t1", "name": "Bash",
                       "input": {"command": "sed -i s/a/b/ README.md"}}]}},
                  {"type": "user", "message": {"role": "user", "content": [
                      {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}},
                  answer]  # fmt: skip
        for label, tree in (("tree on", "on"), ("tree off", "off")):
            env_tree = {**env, "SANCHOPANZA_MEMORY_TREE": tree}
            # the prompt hook runs before its prompt is written; the Stop after its answer
            transcript.write_text(first + json.dumps(answer) + "\n", encoding="utf-8")
            rows[f"prompt, {label}"] = run(prompt, env_tree, args.runs)
            transcript.write_text(first + json.dumps(answer) + "\n"
                                  + "".join(json.dumps(e) + "\n" for e in second), "utf-8")
            rows[f"Stop, {label}"] = run(stop, env_tree, args.runs)
            done = list((store / "p" / "tree").glob("s2-*.json")) if (store / "p").exists() else []
            print(f"{label}: Stop wrote {len(done)} tree record(s)")
    for name, (median, worst) in rows.items():
        print(f"{name:28} median {median:.3f} s  max {worst:.3f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
