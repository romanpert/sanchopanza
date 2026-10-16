"""Free replay of the memory bridge on F2's recorded S arms (no model, no paid call).

For each S triple of an F2 lot (`docs/results/2026-10-16-memory-f2`), from the files the night
left on the machine (rows in `<out>/<run>/f2.json`, each arm's store, hook log and clean Claude
Code folder under `<work>`):

1. `memory_native.native_dir` for session 1, against the folder Claude Code's own `init` event
   named (`memory_auto`): the folder rule checked on every arm.
2. `memory_native.refresh` on a scratch copy of that arm's auto-memory folder, with session 1's
   records from the arm's store: what the bridge would have done at session 1's Stop (written,
   or covered by a memory Claude Code saved itself), and the note's size.
3. What S injected in session 2 (its hook log): the standing rules at start, the record at the
   prompt and at file touches; which of those records the note carries (the bridge would not have
   given them again).

Claude Code's memory files are copied as they are now; a file it changed again in session 2 is
counted with its later text (flagged `later`). Tokens are estimated at CHARS_PER_TOKEN.

    python benchmarks/w17_native/replay_f2.py --run f2-sonnet [--out C:\\sp-runs\\memory-f2]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from sanchopanza.context import episodes as ep  # noqa: E402
from sanchopanza.harness import memory_native as mn  # noqa: E402

OUT = Path(r"C:\sp-runs\memory-f2")
CHARS_PER_TOKEN = 4.0
SLACK_S = 5.0


def hook_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def keys_of(value: Any) -> list[str]:
    """A logged list of keys (the hook log keeps lists; older rows kept their repr)."""
    if isinstance(value, list):
        return [str(v) for v in value]
    text = str(value or "").strip("[] ")
    return [k.strip(" '\"") for k in text.split(",") if k.strip(" '\"")]


def injected(rows: Sequence[Mapping[str, Any]], s2_start: float) -> dict[str, Any]:
    """What S gave session 2: rules at its start, records at the prompt and at touches."""
    after = [r for r in rows if float(r.get("at") or 0) >= s2_start]
    start = next((r for r in after if r.get("event") == "SessionStart"), {})
    prompt = [r for r in after if r.get("event") == "UserPromptSubmit"]
    touch = [r for r in after if r.get("event") == "PostToolUse" and int(r.get("chars") or 0)]
    return {
        "rules_chars": int(start.get("rules_chars") or 0),
        "prompt_chars": sum(int(r.get("chars") or 0) for r in prompt),
        "prompt_keys": [k for r in prompt for k in keys_of(r.get("shown"))],
        "touch_chars": sum(int(r.get("chars") or 0) for r in touch),
        "touch_keys": [k for r in touch for k in keys_of(r.get("shown"))],
    }


def rules_of(stores: Sequence[Path], session: str) -> list[str]:
    """The standing rules memory stored from `session` (not the seeded decoys)."""
    out: list[str] = []
    for store in stores:
        try:
            data = json.loads((store / "rules.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out += [str(r.get("text") or "") for r in data.get("rules") or []
                if r.get("session") == session]  # fmt: skip
    return out


def restated(rule: str, text: str) -> bool:
    """At least COVER_SHARE of the rule's words of five letters or more are in `text`."""
    words = set(mn._WORD.findall(rule.lower()))
    found = set(mn._WORD.findall(text))
    return bool(words) and len(words & found) / len(words) >= mn.COVER_SHARE


def copy_memory(source: Path, target: Path, until: float) -> int:
    """Claude Code's memory files into `target`, times kept; how many changed after `until`."""
    target.mkdir(parents=True, exist_ok=True)
    later = 0
    if source.is_dir():
        for path in source.glob("*.md"):
            shutil.copy2(path, target / path.name)
            later += path.stat().st_mtime > until
    return later


def replay_arm(row: Mapping[str, Any], scratch: Path) -> dict[str, Any]:
    folder = Path(row["folder"])
    s1, s2 = row["sessions"][0], row["sessions"][-1]
    sid1 = str((s1.get("init") or {}).get("session_id") or "")
    reported = Path(str((s1.get("init") or {}).get("memory_auto") or ""))
    transcripts = list((folder / "claude-config" / "projects").glob(f"*/{sid1}.jsonl"))
    event = {"session_id": sid1, "cwd": str(folder / "repo"),
             "transcript_path": str(transcripts[0]) if transcripts else ""}  # fmt: skip
    derived = mn.native_dir(event, env={})
    same = derived is not None and os.path.normcase(str(derived)).rstrip("\\/") == \
        os.path.normcase(str(reported)).rstrip("\\/")  # fmt: skip
    stores = [p for p in (folder / "store").iterdir() if p.is_dir() and p.name != ".keys"]
    records = [e for s in stores for e in ep.load(s, limit=0) if e.session == sid1]
    s1_end = transcripts[0].stat().st_mtime + SLACK_S if transcripts else 0.0
    native = scratch / folder.name / "memory"
    later = copy_memory(reported, native, s1_end)
    outcome = mn.refresh(native, records, session=sid1, store=scratch / folder.name / "store")
    note = (native / mn.NOTE).read_text(encoding="utf-8") if (native / mn.NOTE).exists() else ""
    s2_start = float(s2.get("started") or 0)
    given = injected(hook_rows(folder / "hook-log.jsonl"), s2_start)
    rules = rules_of(stores, sid1)
    claude_text = " ".join(
        p.read_text(encoding="utf-8", errors="replace").lower()
        for p in native.glob("*.md")
        if not p.name.startswith(mn.OWN_PREFIX)
    )
    in_claude = sum(1 for t in rules if restated(t, claude_text))
    given = {**given, "s1_rules": len(rules), "s1_rule_chars": sum(len(t) + 3 for t in rules),
             "s1_rules_in_claude_memory": in_claude}  # fmt: skip
    carried = set(outcome.get("keys") or [])
    deduped = [k for k in given["prompt_keys"] + given["touch_keys"] if k in carried]
    return {
        "scene": row["scene"], "repeat": row["repeat"], "folder_ok": same,
        "native": outcome.get("native"), "covered_by": outcome.get("covered_by", []),
        "later": later, "note_chars": len(note), "line_chars": outcome.get("line_chars", 0),
        "records": len(records), **given, "deduped_keys": deduped,
        "deduped_chars": (given["prompt_chars"] if set(given["prompt_keys"]) & carried else 0)
        + (given["touch_chars"] if set(given["touch_keys"]) & carried else 0),
        "s2_cache_write": s2["tokens"]["cache_write"],
    }  # fmt: skip


def summary(arms: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Counts and medians over the replayed arms, chars and estimated tokens."""

    def med(key: str, rows: Sequence[Mapping[str, Any]] = arms) -> float:
        values = [float(r[key]) for r in rows]
        return round(statistics.median(values), 1) if values else 0.0

    written = [r for r in arms if r["native"] in ("written", "unchanged")]
    covered = [r for r in arms if r["native"] == "covered"]
    states: dict[str, int] = {}
    for r in arms:
        states = {**states, str(r["native"]): states.get(str(r["native"]), 0) + 1}
    added = [r["line_chars"] + r["note_chars"] - r["deduped_chars"] for r in written]
    unread = [r["line_chars"] - r["deduped_chars"] for r in written]
    return {
        "arms": len(arms), "folder_ok": sum(1 for r in arms if r["folder_ok"]),
        "native": states, "later": sum(1 for r in arms if r["later"]),
        "note_chars_median": med("note_chars", written) if written else 0,
        "line_chars_median": med("line_chars", written) if written else 0,
        "s2_rules_chars_median": med("rules_chars"), "s2_prompt_chars_median": med("prompt_chars"),
        "s2_touch_chars_median": med("touch_chars"),
        "deduped_chars_median": med("deduped_chars", written) if written else 0,
        "deduped_arms": sum(1 for r in [*written, *covered] if r["deduped_chars"]),
        "covered_deduped_chars_median": med("deduped_chars", covered) if covered else 0,
        "s1_rules": sum(r["s1_rules"] for r in arms),
        "s1_rule_chars_median": med("s1_rule_chars"),
        "s1_rules_in_claude_memory": sum(r["s1_rules_in_claude_memory"] for r in arms),
        "covered_arm_record_chars_median": med(
            "prompt_chars", [r for r in arms if r["native"] == "covered"]),
        "net_chars_if_note_read_median": statistics.median(added) if added else 0,
        "net_chars_if_not_read_median": statistics.median(unread) if unread else 0,
        "net_tokens_if_note_read_median": round(
            (statistics.median(added) if added else 0) / CHARS_PER_TOKEN),
        "net_tokens_if_not_read_median": round(
            (statistics.median(unread) if unread else 0) / CHARS_PER_TOKEN),
    }  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", required=True, help="f2-sonnet | f2-opus | f2-pilot")
    parser.add_argument("--out", default=str(OUT), help="the F2 lot's folder")
    parser.add_argument("--json", default="", help="write every arm's row here")
    args = parser.parse_args(argv)
    os.environ["SANCHOPANZA_MEMORY_STORE_KEY"] = "folder"  # the slug from git, not a key file
    for name in ("CLAUDE_CONFIG_DIR", "CLAUDE_CODE_REMOTE_MEMORY_DIR"):
        os.environ.pop(name, None)
    rows = json.loads((Path(args.out) / args.run / "f2.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="w17-native-") as scratch:
        arms = [replay_arm(r, Path(scratch)) for r in rows if r["arm"] == "S"]
    if args.json:
        Path(args.json).write_text(json.dumps(arms, indent=1), encoding="utf-8")
    print(json.dumps(summary(arms), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
