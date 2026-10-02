"""Browse, development: is the answer in what the model sees, without the hook and with it?

python benchmarks/browse/visible.py collect         # from the PLAIN sessions' transcripts
python benchmarks/browse/visible.py score OUT.json  # with the sanchopanza on sys.path
python benchmarks/browse/visible.py score OUT.json --jev  # ranked by Jev, at most JEV_MAX_USD

Every large snapshot a PLAIN session of the end-to-end phases received (PLAIN results are never
touched by the hook) is replayed through the hook, ranked by BM25 (free, no Jev), and scored by
what Claude Code would show the model: a `Bash` output past 30,000 characters is saved to a
file, the hook is handed that prefix and the model sees the first 2,000 characters of the reply
(or of the output, untouched); an MCP result past its limit is a notice the hook may replace
with up to 60,000 characters. "Visible" means every required answer of the task is in what the
model sees. Run `score` once per version of the hook (`PYTHONPATH` at that version's `src`) and
compare. The transcripts are local (`~/.claude/projects`), so `collect` writes the snapshots to
the cache, not to the repository; the scores carry hashes only.
"""

from __future__ import annotations

import asyncio
import glob
import hashlib
import importlib.util
import json
import os
import pathlib
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
RESULTS = HERE.parents[1] / "docs" / "results" / "2026-09-30-browse"
CORPUS = pathlib.Path.home() / ".cache" / "sanchopanza" / "browse-visible" / "corpus.jsonl"
BASH_SAVE_CHARS = 30_000  # past this Claude Code saves a Bash output and shows 2,000 characters
PREVIEW_CHARS = 2_000
MIN_CHARS = 6_000  # the hook's default trigger
JEV_MAX_USD = 0.60  # --jev: a hard ceiling, checked before each snapshot
PHASES = {  # sessions file -> tool
    "e2e-sessions.jsonl": "cli", "e2e-cli-new-sessions.jsonl": "cli",
    "e2e-cli-wide-sessions.jsonl": "cli", "e2e-cli-x-sessions.jsonl": "cli",
    "e2e-cli-y-sessions.jsonl": "cli", "e2e-mcp-sessions.jsonl": "mcp",
    "e2e-mcp-fixed-sessions.jsonl": "mcp", "e2e-mcp-new-sessions.jsonl": "mcp",
    "e2e-mcp-wide-sessions.jsonl": "mcp", "e2e-mcp-x-sessions.jsonl": "mcp",
    "e2e-mcp-y-sessions.jsonl": "mcp", "e2e-mcp-z-sessions.jsonl": "mcp",
    "e2e-cli-z-sessions.jsonl": "cli", "e2e-mcp-u-sessions.jsonl": "mcp",
    "e2e-cli-u-sessions.jsonl": "cli", "e2e-mcp-v-sessions.jsonl": "mcp",
}  # fmt: skip


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _tasks() -> dict[str, tuple]:
    mcp = _load("browse_e2e_mcp", HERE / "e2e_mcp.py")
    every = [*mcp.base.TASKS, *mcp.TASKS, *mcp.NEW_TASKS, *mcp.WIDE_TASKS, *mcp.X_TASKS,
             *mcp.Y_TASKS, *mcp.Z_TASKS, *mcp.U_TASKS, *mcp.V_TASKS]  # fmt: skip
    return {t[0]: t for t in every}


def _transcript(workdir: str) -> list[str]:
    name = pathlib.PureWindowsPath(workdir).name.replace("_", "-")
    folders = glob.glob(os.path.expanduser(f"~/.claude/projects/*{name}"))
    return glob.glob(folders[0] + "/*.jsonl") if folders else []


def _results(path: str) -> list[dict[str, Any]]:
    """Each tool result of a transcript: tool, input, the text the hook was handed, and the
    whole output if Claude Code saved it."""
    calls, out = {}, []
    for event in map(json.loads, pathlib.Path(path).read_text(encoding="utf-8").splitlines()):
        for c in (event.get("message") or {}).get("content") or []:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "tool_use":
                calls[c["id"]] = (c["name"], c.get("input") or {})
            elif c.get("type") == "tool_result" and c.get("tool_use_id") in calls:
                body = c.get("content")
                if isinstance(body, list):
                    body = "".join(b.get("text", "") for b in body if isinstance(b, dict))
                tool, tool_input = calls[c["tool_use_id"]]
                raw = event.get("toolUseResult")
                saved = raw.get("persistedOutputPath") if isinstance(raw, dict) else None
                if isinstance(raw, dict) and isinstance(raw.get("stdout"), str):
                    body = raw["stdout"]
                if isinstance(raw, dict) and isinstance(raw.get("file"), dict):
                    body = raw["file"].get("content", body)
                if saved is None and "exceeds maximum allowed tokens" in str(body):
                    saved = str(body).split("saved to ", 1)[-1].split(".txt", 1)[0] + ".txt"
                out.append({"tool": tool, "input": tool_input, "text": str(body or ""),
                            "saved": saved})  # fmt: skip
    return out


def collect() -> int:
    from sanchopanza.browse import snapshot_block

    tasks, rows = _tasks(), []
    for name, tool_kind in PHASES.items():
        path = RESULTS / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            session = json.loads(line)
            if session["arm"] != "PLAIN" or session["run"] <= 0:
                continue
            for transcript in _transcript(session["workdir"]):
                for result in _results(transcript):
                    whole = result["text"]
                    if result["saved"] and pathlib.Path(result["saved"]).is_file():
                        whole = pathlib.Path(result["saved"]).read_text(encoding="utf-8")
                    span = snapshot_block(whole)
                    if span is None or span[1] - span[0] < MIN_CHARS:
                        continue
                    task = tasks[session["task"]]
                    rows.append({
                        "phase": name, "kind": tool_kind, "task": task[0], "url": task[1],
                        "question": task[2], "required": task[3], "tool": result["tool"],
                        "input": result["input"], "whole": whole,
                        "saved": bool(result["saved"]), "transcript": transcript,
                    })  # fmt: skip
    CORPUS.parent.mkdir(parents=True, exist_ok=True)
    with CORPUS.open("w", encoding="utf-8") as sink:
        for row in rows:
            sink.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"{len(rows)} snapshots from {len({r['transcript'] for r in rows})} sessions")
    return 0


def _event(row: dict[str, Any], tmp: pathlib.Path) -> tuple[dict[str, Any], bool]:
    """The event the hook would have been handed, and whether Claude Code saved the output."""
    goal = tmp / "t.jsonl"
    prompt = f"Start at {row['url']}. {row['question']}"
    goal.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": prompt}})
                    + "\n", encoding="utf-8")  # fmt: skip
    whole, tool = row["whole"], row["tool"]
    saved = tmp / "t" / "tool-results" / "out.txt"
    saved.parent.mkdir(parents=True, exist_ok=True)
    saved.write_text(whole, encoding="utf-8")
    event: dict[str, Any] = {
        "hook_event_name": "PostToolUse", "tool_name": tool, "tool_input": row["input"],
        "tool_use_id": "toolu_v", "session_id": "v", "cwd": str(tmp), "transcript_path": str(goal),
    }  # fmt: skip
    if tool == "Bash":
        cut = len(whole) > BASH_SAVE_CHARS
        response: dict[str, Any] = {"stdout": whole[:BASH_SAVE_CHARS] if cut else whole,
                                    "stderr": ""}  # fmt: skip
        if cut:
            response = {**response, "persistedOutputPath": str(saved),
                        "persistedOutputSize": len(whole)}  # fmt: skip
        return {**event, "tool_response": response}, cut
    if tool == "Read":
        file = {"filePath": "page.yml", "content": whole}
        return {**event, "tool_response": {"type": "text", "file": file}}, False
    if row["saved"]:  # an MCP result past Claude Code's limit: the hook is handed the notice
        notice = (f"Error: result ({len(whole)} characters) exceeds maximum allowed tokens. "
                  f"Output has been saved to {saved}.")  # fmt: skip
        return {**event, "tool_response": [{"type": "text", "text": notice}]}, True
    return {**event, "tool_response": [{"type": "text", "text": whole}]}, False


def _shown(out: dict[str, Any], row: dict[str, Any], saved: bool) -> tuple[str, bool]:
    """What the model reads, and whether the hook acted."""
    acted = bool(out)
    if row["tool"] == "Bash":
        text = out["hookSpecificOutput"]["updatedToolOutput"]["stdout"] if acted else row["whole"]
        return (text[:PREVIEW_CHARS] if saved else text), acted
    if row["tool"] == "Read":
        return (out["hookSpecificOutput"]["updatedToolOutput"]["file"]["content"] if acted
                else row["whole"]), acted  # fmt: skip
    if acted:
        new = out["hookSpecificOutput"]["updatedToolOutput"]
        return (new if isinstance(new, str) else new[0]["text"]), acted
    return ("(notice only)" if saved else row["whole"]), acted


def _jev_spent(journal: pathlib.Path) -> float:
    if not journal.exists():
        return 0.0
    events = [json.loads(x) for x in journal.read_text(encoding="utf-8").splitlines() if x]
    return sum(float((e.get("data") or {}).get("cost_usd") or 0.0) for e in events
               if e.get("kind") == "decision")  # fmt: skip


def _replay(rows: list[dict[str, Any]], jev: bool, journal: pathlib.Path) -> list[dict[str, Any]]:
    import tempfile

    from sanchopanza.harness import browse_hook
    from sanchopanza.harness.claude_code import squire_from_env
    from sanchopanza.squire import Squire

    e2e = _load("browse_e2e", HERE / "e2e.py")
    scored = []
    for index, row in enumerate(rows):
        if jev and _jev_spent(journal) > JEV_MAX_USD - 0.04:  # 0.04: the dearest snapshot seen
            raise SystemExit(f"Jev ceiling: {_jev_spent(journal):.4f} USD spent, stopped")
        squire = squire_from_env(redact=True) if jev else Squire()
        with tempfile.TemporaryDirectory() as tmp:
            event, saved = _event(row, pathlib.Path(tmp))
            event = {**event, "session_id": f"v{index}"}  # each its own session ceiling
            out = asyncio.run(browse_hook.post_tool_use(event, squire))
            text, acted = _shown(out, row, saved)
        plain = row["whole"][:PREVIEW_CHARS] if saved and row["tool"] == "Bash" else (
            "(notice only)" if saved else row["whole"])  # fmt: skip
        scored.append({
            "id": hashlib.sha256(row["whole"].encode()).hexdigest()[:12], "phase": row["phase"],
            "task": row["task"], "tool": row["tool"], "saved": saved, "acted": acted,
            "chars_whole": len(row["whole"]), "chars_shown": len(text),
            "visible": e2e.graded(text, row["required"]),
            "visible_plain": e2e.graded(plain, row["required"]),
        })  # fmt: skip
    return scored


def score(out_path: str, jev: bool = False) -> int:
    """Replay every snapshot; the archive and the journal live in a folder removed at the end."""
    import tempfile

    from sanchopanza import browse

    if jev and not os.environ.get("TYPESAFE_API_KEY"):
        raise SystemExit("--jev ranks with Jev: no TYPESAFE_API_KEY, nothing spent")
    rows = [json.loads(x) for x in CORPUS.read_text(encoding="utf-8").splitlines()]
    with tempfile.TemporaryDirectory(prefix="sp-visible-") as work:
        journal = pathlib.Path(work) / "journal.jsonl"
        os.environ["SANCHOPANZA_ARCHIVE"] = str(pathlib.Path(work) / "archive")
        if jev:
            os.environ["SANCHOPANZA_JOURNAL"] = str(journal)
        scored = _replay(rows, jev, journal)
        jev_usd = round(_jev_spent(journal), 4)
    summary: dict[str, Any] = {
        "source": str(pathlib.Path(browse.__file__).parent), "snapshots": len(scored),
        "ranked_by": "jev" if jev else "bm25", "jev_usd": jev_usd,
    }  # fmt: skip
    for key in ("all", "saved Bash", "acted"):
        part = [s for s in scored if key == "all" or (key == "acted" and s["acted"])
                or (key == "saved Bash" and s["saved"] and s["tool"] == "Bash")]  # fmt: skip
        summary[key] = {
            "n": len(part),
            "visible_with_hook": sum(s["visible"] for s in part),
            "visible_without": sum(s["visible_plain"] for s in part),
            "chars_shown_mean": round(sum(s["chars_shown"] for s in part) / max(1, len(part))),
        }
    pathlib.Path(out_path).write_text(json.dumps({"summary": summary, "rows": scored}, indent=1),
                                      encoding="utf-8")  # fmt: skip
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["collect"]:
        raise SystemExit(collect())
    if sys.argv[1:2] == ["score"] and len(sys.argv) in (3, 4):
        raise SystemExit(score(sys.argv[2], jev=sys.argv[3:4] == ["--jev"]))
    raise SystemExit(__doc__)
