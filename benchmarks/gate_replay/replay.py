"""Replay the change gate (`harness.change_gate`) over recorded sessions. Free: no model call.

    python benchmarks/gate_replay/replay.py [--runs C:/sp-runs/h2h] [--out PATH]

For every recorded Claude Code session under the h2h run folders (one `config/settings.json`
and one transcript per session), it reads what check-done and candor did and asks whether the
gate would have let them act:

- check-done: the send-backs ("Stop hook feedback: sanchopanza: the transcript does not show
  this request done"), and what followed each one: turns, and the share of the session's
  list cost spent after it (tokens priced at Sonnet's ratios, input 1, cache write 1.25,
  cache read 0.1, output 5, applied to the row's own `list_usd` when the runner kept one);
- candor: the status-block requests (hook context with `STATUS: done | partial | blocked`) and
  the Stop findings that engage the lock (critical);
- the gate: whether the session's request changed anything, as `change_gate` reads it.

It writes ids and counts only: no question, answer or document text.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections import Counter
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from sanchopanza.harness import change_gate  # noqa: E402

RUNS = pathlib.Path("C:/sp-runs/h2h")
# GAIA dev (`dev`) ran S0 without check-done or candor: nothing of theirs to replay there.
PHASES = ("bcp-dev", "longdoc-dev", "dev")
SEND_BACK = "sanchopanza: the transcript does not show this request done"
BLOCK = "STATUS: done | partial | blocked"
WEIGHTS = {"input_tokens": 1.0, "cache_creation_input_tokens": 1.25,
           "cache_read_input_tokens": 0.1, "output_tokens": 5.0}  # fmt: skip


def _entries(path: pathlib.Path) -> list[dict[str, Any]]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _text(entry: dict[str, Any]) -> str:
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(b.get("text") or "") for b in content if isinstance(b, dict))
    return ""


def _weight(usage: dict[str, Any]) -> float:
    return sum(float(usage.get(k) or 0) * w for k, w in WEIGHTS.items())


def hooks_of(settings: pathlib.Path) -> dict[str, bool]:
    data = json.loads(settings.read_text(encoding="utf-8"))
    hooks = data.get("hooks") or {}
    env = data.get("env") or {}

    def wired(event: str, command: str) -> bool:
        return any(h.get("command", "").endswith(command) for e in hooks.get(event, [])
                   for h in e.get("hooks", []))  # fmt: skip

    return {
        "check_done": wired("Stop", "sanchopanza hook")
        and env.get("SANCHOPANZA_CHECK_DONE") == "1",
        "candor": wired("Stop", "candor-hook"),
    }


def session(transcript: pathlib.Path, home: pathlib.Path) -> dict[str, Any]:
    entries = _entries(transcript)
    usage: dict[str, float] = {}  # message id -> weight (a message spans several entries)
    order: list[str] = []
    send_backs: list[int] = []
    blocks = 0
    for index, entry in enumerate(entries):
        if entry.get("type") == "assistant":
            message = entry.get("message") or {}
            key = str(message.get("id") or index)
            if key not in usage:
                order.append(key)
            usage[key] = _weight(message.get("usage") or {})
        elif entry.get("type") == "user" and SEND_BACK in _text(entry):
            send_backs.append(len(order))
        elif entry.get("type") == "attachment":
            attachment = entry.get("attachment") or {}
            content = attachment.get("content")
            if attachment.get("type") == "hook_additional_context" and BLOCK in json.dumps(content):
                blocks += 1
    total = sum(usage.values()) or 1.0
    after = order[send_backs[0] :] if send_backs else []
    locks = 0
    findings = home / ".sanchopanza" / "candor" / "findings.jsonl"
    if findings.exists():
        for row in _entries(findings):
            severe = any(f.get("severity") == "critical" for f in row.get("findings", []))
            locks += row.get("event") == "Stop" and severe
    return {
        "changed": change_gate.transcript_changed(transcript),
        "send_backs": len(send_backs),
        "turns": len(order),
        "turns_after": len(after),
        "share_after": round(sum(usage[k] for k in after) / total, 4),
        "block_requests": blocks,
        "lock_findings": locks,
    }


def _transcript(config: pathlib.Path) -> pathlib.Path | None:
    found = [p for p in (config / "projects").glob("*/*.jsonl")]
    return found[0] if len(found) == 1 else None


def _costs(runs: pathlib.Path) -> dict[str, float]:
    """`list_usd` by work folder, from the runners' private rows when they are on this machine."""
    cache = pathlib.Path.home() / ".cache" / "sanchopanza"
    out: dict[str, float] = {}
    for rows in cache.glob("*/h2h/*/sessions.jsonl"):
        for row in _entries(rows):
            work = str(row.get("workdir") or "")
            if work and row.get("list_usd") is not None:
                out[str(pathlib.Path(work).parent).lower()] = float(row["list_usd"])
    return out


def replay(runs: pathlib.Path, phases: tuple[str, ...] = PHASES) -> dict[str, Any]:
    costs = _costs(runs)
    out: dict[str, Any] = {}
    for phase in phases:
        rows = []
        for settings in sorted((runs / phase).glob("**/config/settings.json")):
            folder = settings.parent.parent
            transcript = _transcript(settings.parent)
            hooks = hooks_of(settings)
            if transcript is None or not (hooks["check_done"] or hooks["candor"]):
                continue
            row = {"session": folder.relative_to(runs).as_posix(), **hooks,
                   **session(transcript, folder / "side" / "home")}  # fmt: skip
            usd = costs.get(str(folder).lower())
            if usd is not None:
                row["list_usd"] = usd
                row["usd_after"] = round(usd * row["share_after"], 4)
            rows.append(row)
        out[phase] = {"sessions": rows, "summary": summary(rows)}
    return out


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    gated = [r for r in rows if not r["changed"]]
    counts: Counter[str] = Counter({"sessions": 0})
    for r in rows:
        counts["sessions"] += 1
        counts["changed"] += r["changed"]
        counts["send_backs"] += r["send_backs"]
        counts["block_requests"] += r["block_requests"]
        counts["lock_findings"] += r["lock_findings"]
    for r in gated:
        counts["send_backs_avoided"] += r["send_backs"]
        counts["turns_avoided"] += r["turns_after"]
        counts["block_requests_avoided"] += r["block_requests"]
        counts["lock_findings_avoided"] += r["lock_findings"]
    usd = [r for r in rows if "list_usd" in r]
    return {
        **counts,
        "list_usd": round(sum(r["list_usd"] for r in usd), 4),
        "usd_after_send_back_avoided": round(sum(r.get("usd_after", 0) for r in gated), 4),
        "sessions_priced": len(usd),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--runs", type=pathlib.Path, default=RUNS)
    ap.add_argument("--out", type=pathlib.Path)
    ap.add_argument("--phases", default=",".join(PHASES))
    args = ap.parse_args()
    result = replay(args.runs, tuple(p for p in args.phases.split(",") if p))
    text = json.dumps(result, indent=1, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8", newline="\n")
    for phase, block in result.items():
        print(phase, json.dumps(block["summary"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
