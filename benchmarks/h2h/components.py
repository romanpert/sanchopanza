"""Per S component, what reached the transcript and what its returns cost, for a phase's rows.

python benchmarks/h2h/components.py SESSIONS_JSONL [...]            # free: per-arm totals
python benchmarks/h2h/components.py --enrich SESSIONS_JSONL [...]   # free: add `components`
                                                                    # to rows that lack it

Rows written before the runner recorded `components` (2026-10-06) get it from their transcripts
(`gaia_session.components`), which stay under the session's user folder in C:/sp-runs. Run
`--enrich` only on a phase that has finished: it rewrites the file. Counts and USD only: no task
text, answer or tool output is printed.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections.abc import Mapping, Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import offline_common as common  # noqa: E402

reading = common.reading


def folder_of_row(row: Mapping[str, Any]) -> pathlib.Path:
    work = pathlib.Path(str(row["workdir"]))
    return reading.folder_of(work, work.parent / "config" / "projects")


def enrich(path: pathlib.Path) -> int:
    rows = common.gaia.read_rows(path)
    added = 0
    out = []
    for row in rows:
        if "components" not in row and row.get("workdir"):
            row = {**row, "components": reading.components(folder_of_row(row))}
            added += 1
        out.append(row)
    if added:
        tmp = path.with_suffix(".jsonl.tmp")
        tmp.write_text("".join(json.dumps(r) + "\n" for r in out), encoding="utf-8")
        tmp.replace(path)
    return added


def _add(total: Mapping[str, float], part: Mapping[str, float]) -> dict[str, float]:
    keys = set(total) | set(part)
    return {k: round(total.get(k, 0) + part.get(k, 0), 6) for k in sorted(keys)}


def summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Per arm: sessions, list USD, sanchopanza calls by subcommand, outputs by component,
    sessions with an output of each component, returns, turns and USD after them."""
    by_arm: dict[str, dict[str, Any]] = {}
    for row in rows:
        comp = row.get("components") or reading_components(row)
        cell = by_arm.get(row["arm"], {"sessions": 0, "list_usd": 0.0, "calls": {},
                                       "outputs": {}, "sessions_with_output": {},
                                       "returns": {}, "turns_after": {}, "usd_after": {},
                                       "tools": {}})  # fmt: skip
        cell = {
            **cell,
            "sessions": cell["sessions"] + 1,
            "list_usd": round(cell["list_usd"] + float(row.get("list_usd") or 0.0), 4),
            "calls": _add(cell["calls"], row.get("shim_runs") or {}),
            "outputs": _add(cell["outputs"], comp["outputs"]),
            "sessions_with_output": _add(
                cell["sessions_with_output"], dict.fromkeys(comp["outputs"], 1)
            ),  # fmt: skip
            "returns": _add(cell["returns"], comp["returns"]),
            "turns_after": _add(cell["turns_after"], comp["turns_after"]),
            "usd_after": _add(cell["usd_after"], comp["usd_after"]),
            "tools": _add(cell["tools"], row.get("tools") or {}),
        }
        by_arm = {**by_arm, row["arm"]: cell}
    return by_arm


def reading_components(row: Mapping[str, Any]) -> dict[str, Any]:
    if not row.get("workdir"):
        return {"outputs": {}, "returns": {}, "turns_after": {}, "usd_after": {}}
    return reading.components(folder_of_row(row))


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("sessions", nargs="+")
    ap.add_argument("--enrich", action="store_true")
    args = ap.parse_args(argv)
    for name in args.sessions:
        path = pathlib.Path(name)
        if args.enrich:
            print(f"{path}: components added to {enrich(path)} rows")
            continue
        rows = [r for r in common.gaia.read_rows(path) if r.get("arm")]
        print(json.dumps({str(path): summary(rows)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
