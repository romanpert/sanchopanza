"""Browse, development: the `sources` v2 trigger replayed on the FRAMES pilot's 80 sessions.

python benchmarks/browse/free_frames_trigger.py  # free: transcripts in, frames-trigger.json out

No model and no money. For every session of the first pilot, the transcripts as they stood at
its first stop (the main agent's up to the hook's block in the -SRC arms, the whole one in the
base arms; each subagent's entries before that moment) are written to a scratch folder and
handed to `sources_v2.assess`, the code the hook runs. The cap is each arm's -SRC cap (1.05 USD
Sonnet, 0.42 Haiku), the one the v2 arms of the second pilot run with. The grade is the hand
grade of the answer given at that stop (`free_frames_hand`).

Writes ids, arm, booleans, sign names, counts and dollars only: no question, answer or quote.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import statistics
import sys
import tempfile
from collections.abc import Mapping, Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from sanchopanza.harness import sources_v2  # noqa: E402


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


hand = _load("browse_free_frames_hand", HERE / "free_frames_hand.py")
frames = hand.frames
OUT = frames.RESULTS / "frames-trigger.json"
SRC_CAP = {"SONNET": 1.05, "SONNET-SRC": 1.05, "HAIKU": 0.42, "HAIKU-SRC": 0.42}
SIGNS = tuple(sources_v2.REASONS)


def _lines(path: pathlib.Path) -> list[str]:
    return [x for x in path.read_text(encoding="utf-8", errors="replace").splitlines() if x.strip()]


def at_first_stop(folder: pathlib.Path, into: pathlib.Path, marks: Sequence[str]) -> pathlib.Path:
    """The session's transcripts cut where its first stop was blocked, written under `into` in
    Claude Code's layout; the whole session when nothing blocked it."""
    main = next(p for p in sorted(folder.glob("*.jsonl")))
    lines = _lines(main)
    cut = next((i for i, x in enumerate(lines) if any(m in x for m in marks)), None)
    stamp = str(json.loads(lines[cut]).get("timestamp") or "") if cut is not None else None
    out = into / main.name
    out.write_text("\n".join(lines[:cut] if cut is not None else lines) + "\n", encoding="utf-8")
    for sub in sorted(folder.rglob("subagents/*.jsonl")):
        kept = [x for x in _lines(sub) if stamp is None or json.loads(x).get("timestamp") < stamp]
        target = into / main.stem / "subagents" / sub.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return out


def right_at_stop(row: Mapping[str, Any]) -> bool:
    graded = hand.graded(row)
    return bool(graded["ok_hand_before"] if row["arm"].endswith("-SRC") else graded["ok_hand"])


def spent_at_stop(row: Mapping[str, Any]) -> float:
    after = row.get("usd_after_block")
    return float(row["list_usd"]) - (float(after) if after not in (None, "None") else 0.0)


def replay(row: Mapping[str, Any], marks: Sequence[str]) -> dict[str, Any]:
    folder = frames.trace.folder_of(row["workdir"])
    with tempfile.TemporaryDirectory() as tmp:
        main = at_first_stop(folder, pathlib.Path(tmp), marks)
        cap = SRC_CAP[row["arm"]]
        seen = sources_v2.assess(main, "", {"SANCHOPANZA_SOURCES_CAP_USD": str(cap)})
    return {"task": row["task"], "arm": row["arm"], "right": right_at_stop(row),
            "web_calls": seen["web_calls"], "signs": seen["signs"], "over_cap": seen["over_cap"],
            "fires": seen["block"], "fires_without_cap_check": bool(seen["web_calls"] and
                                                                    seen["signs"]),
            "estimated_usd": seen["spent_usd"], "recorded_usd": round(spent_at_stop(row), 4),
            "cap_usd": cap}  # fmt: skip


def table(rows: Sequence[Mapping[str, Any]], key: str = "fires") -> dict[str, int]:
    def n(right: bool, fired: bool) -> int:
        return sum(1 for r in rows if r["right"] is right and bool(r[key]) is fired)

    return {"fires_right": n(True, True), "fires_wrong": n(False, True),
            "silent_right": n(True, False), "silent_wrong": n(False, False)}  # fmt: skip


def summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"sessions": len(rows), "cap_share": sources_v2.CAP_SHARE}
    groups = {"all": rows, "SONNET*": [r for r in rows if r["arm"].startswith("SONNET")],
              "HAIKU*": [r for r in rows if r["arm"].startswith("HAIKU")]}  # fmt: skip
    groups |= {arm: [r for r in rows if r["arm"] == arm] for arm in frames.ARMS}
    for name, group in groups.items():
        web = [r for r in group if r["web_calls"]]
        cell = {"web_sessions": len(web), "trigger": table(web),
                "trigger_without_cap_check": table(web, "fires_without_cap_check"),
                "over_cap": sum(bool(r["over_cap"]) for r in web)}  # fmt: skip
        for sign in SIGNS:
            flagged = [{**r, "has": sign in r["signs"]} for r in web]
            cell[f"sign_{sign}"] = table(flagged, "has")
        out[name] = cell
    ratios = [r["estimated_usd"] / r["recorded_usd"] for r in rows if r["recorded_usd"] > 0]
    out["estimate_over_recorded"] = {
        "median": round(statistics.median(ratios), 3),
        "min": round(min(ratios), 3),
        "max": round(max(ratios), 3),
    }
    return out


def main() -> int:
    rows = frames.phase.counted(frames.free.nav.done_sessions(frames.SESSIONS))
    marks = (frames.REQUEST[:48],)
    sessions = [replay(r, marks) for r in rows]
    result = {"summary": summary(sessions), "sessions": sessions}
    OUT.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result["summary"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
