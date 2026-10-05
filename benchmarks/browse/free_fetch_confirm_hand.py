"""Browse, sealed confirmation of fetch v2 (fetch1): blind grading and the registered verdicts.

python benchmarks/browse/free_fetch_confirm_hand.py --blind-sheet  # free: sheet and key, private
python benchmarks/browse/free_fetch_confirm_hand.py --apply        # free: the graded sheet in
python benchmarks/browse/free_fetch_confirm_hand.py                # free: the verdicts, JSON out

Blind grading, as `prereg-fetch1.md` registers it. `--blind-sheet` writes, outside the repository,
`blind-sheet.json`: one entry per session with a random id, the task, its question and gold and
the session's last ANSWER, shuffled (task order and the four answers within a task), with no arm,
no cost and no tool count; and `blind-key.json` apart, id -> (task, arm). The grader opens only
the sheet and sets each `right` to true or false. `--apply` checks every entry is graded and
writes `blind-grades.json` (task, arm, right). The verdicts read those grades, never the
runner's.

Rules applied on top of the grades (registered): a session with no ANSWER line is wrong; a
session that ended at its cap counts with its last ANSWER; a session marked leak (the runner's
flag, or the wider scan of `free_frames_hand.session_leak`) makes both arms of its model wrong on
that task, and is reported. A session the runner killed is charged its cap.

Writes to the repository task ids, booleans, counts and dollars only: no question, no answer.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import random
import secrets
import sys
from collections.abc import Mapping, Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


conf = _load("browse_free_fetch_confirm", HERE / "free_fetch_confirm.py")
hand = _load("browse_free_frames_hand", HERE / "free_frames_hand.py")
pilot, frames, phase = conf.pilot, conf.frames, conf.phase

SHEET = conf.PRIVATE / "blind-sheet.json"
KEY = conf.PRIVATE / "blind-key.json"
GRADES = conf.PRIVATE / "blind-grades.json"
OUT = frames.RESULTS / "fetch-confirm-hand.json"
MAX_RATIO = 0.80  # total cost of -FETCH2 over its base, at most
MIN_CHEAPER = 0.55  # share of tasks where -FETCH2 cost less, at least
EPS = 1e-9  # floating-point sums: 60 x 0.20 is not 12.0 exactly


# --- blind sheet --------------------------------------------------------------------------------


def blind_sheet(
    rows: Sequence[Mapping[str, Any]],
    tasks: Mapping[str, tuple],
    rng: random.Random | None = None,
    new_id=None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, str]]]:
    """(sheet, key): one entry per session, shuffled by task and within a task, with no arm."""
    rng = rng or random.SystemRandom()
    new_id = new_id or (lambda: secrets.token_hex(6))
    by_task: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        by_task.setdefault(row["task"], []).append(row)
    order = sorted(by_task)
    rng.shuffle(order)
    sheet: list[dict[str, Any]] = []
    key: dict[str, dict[str, str]] = {}
    for tid in order:
        group = list(by_task[tid])
        rng.shuffle(group)
        for row in group:
            bid = new_id()
            while bid in key:
                bid = new_id()
            key[bid] = {"task": tid, "arm": row["arm"]}
            sheet.append({"id": bid, "task": tid, "question": tasks[tid][2],
                          "gold": tasks[tid][3], "answer": str(row.get("answer_after") or ""),
                          "right": None})  # fmt: skip
    return sheet, key


def apply_sheet(
    sheet: Sequence[Mapping[str, Any]], key: Mapping[str, Mapping[str, str]]
) -> list[dict[str, Any]]:
    """The grades by (task, arm); every entry graded true or false, every key id once."""
    ids = [e["id"] for e in sheet]
    if sorted(ids) != sorted(key) or len(set(ids)) != len(ids):
        raise SystemExit("the sheet and the key do not hold the same ids")
    ungraded = [e["id"] for e in sheet if not isinstance(e.get("right"), bool)]
    if ungraded:
        raise SystemExit(f"{len(ungraded)} entries are not graded true or false")
    return [{**key[e["id"]], "right": e["right"]} for e in sheet]


# --- verdicts -----------------------------------------------------------------------------------


def model_of(arm: str) -> str:
    return arm.split("-")[0]


def charged(row: Mapping[str, Any]) -> float:
    """A session the runner killed reports no cost: it is charged its arm's cap."""
    if str(row.get("subtype") or "").startswith("runner:"):
        return float(conf.CAPS[row["arm"]])
    return float(row.get("list_usd") or 0.0)


def leaked(row: Mapping[str, Any], scan=None) -> bool:
    """Marked leak: by the runner, or by the wider scan of tool inputs and results."""
    scan = scan or hand.session_leak
    return bool(row.get("leak")) or bool(scan(row))


def right_of(
    row: Mapping[str, Any], grades: Mapping[tuple[str, str], bool], leaks: set[tuple[str, str]]
) -> bool:
    """The blind grade, wrong with no ANSWER line, wrong on a task its model leaked on."""
    if not str(row.get("answer_after") or "").strip():
        return False
    if (row["task"], model_of(row["arm"])) in leaks:
        return False
    return bool(grades[(row["task"], row["arm"])])


def compare(rows: Sequence[Mapping[str, Any]], base: str, arm: str, right) -> dict[str, Any]:
    """The registered comparison of one model with and without fetch v2."""
    a = {r["task"]: r for r in rows if r["arm"] == base}
    b = {r["task"]: r for r in rows if r["arm"] == arm}
    tasks = sorted(set(a) & set(b))
    total_a = sum(charged(a[t]) for t in tasks)
    total_b = sum(charged(b[t]) for t in tasks)
    ratio = total_b / total_a if total_a > 0 else float("inf")
    cheaper = sum(charged(b[t]) < charged(a[t]) for t in tasks)
    share = cheaper / len(tasks) if tasks else 0.0
    wins_a = sum(right(a[t]) for t in tasks)
    wins_b = sum(right(b[t]) for t in tasks)
    price = total_b <= MAX_RATIO * total_a + EPS and share >= MIN_CHEAPER - EPS
    answers = wins_b >= wins_a
    return {
        "tasks": len(tasks),
        "price": {"total_usd": {base: round(total_a, 4), arm: round(total_b, 4)},
                  "ratio_total": round(ratio, 4), "tasks_cheaper": cheaper,
                  "share_cheaper": round(share, 4), "holds": price},
        "answers": {base: wins_a, arm: wins_b, "holds": answers},
        "beats_the_harness": price and answers,
    }  # fmt: skip


def verdicts(
    rows: Sequence[Mapping[str, Any]],
    grades: Mapping[tuple[str, str], bool],
    leaks: set[tuple[str, str]],
    ids: Sequence[str],
) -> dict[str, Any]:
    """The hypotheses of prereg-fetch1.md, model by model; a result on one model is not claimed
    for the other."""
    cells = {(r["task"], r["arm"]) for r in rows}
    complete = len(rows) == len(ids) * len(conf.ARMS) and cells == {
        (t, arm) for t in ids for arm in conf.ARMS
    }

    def right(row: Mapping[str, Any]) -> bool:
        return right_of(row, grades, leaks)

    out: dict[str, Any] = {"complete": complete}
    for base, arm in conf.PAIRS:
        out[base] = compare(rows, base, arm, right)
    return out


# --- described, not tested ----------------------------------------------------------------------


def described(rows: Sequence[Mapping[str, Any]], right) -> dict[str, Any]:
    graded_rows = [{**r, "ok_hand": right(r)} for r in rows]
    by_arm = {arm: [r for r in graded_rows if r["arm"] == arm] for arm in conf.ARMS}
    out: dict[str, Any] = {"by_arm": {}}
    for arm, group in by_arm.items():
        if not group:
            continue
        cell = pilot.cell(group, "ok_hand")
        cell["right_runner"] = sum(bool(r.get("ok_auto")) for r in group)
        cell["no_answer_line"] = sum(not str(r.get("answer_after") or "").strip() for r in group)
        cell["killed_by_the_runner"] = sum(
            str(r.get("subtype") or "").startswith("runner:") for r in group
        )  # fmt: skip
        cell["sessions_calling_fetch_passages"] = sum(
            bool((r.get("calls") or {}).get("fetch_passages")) for r in group
        )  # fmt: skip
        cell["versions"] = sorted({str(r.get("version") or "") for r in group})
        out["by_arm"][arm] = cell
    for base, arm in conf.PAIRS:
        if by_arm[base] and by_arm[arm]:
            out[f"paired_{arm}_vs_{base}"] = hand.paired(by_arm[base], by_arm[arm])
    return out


# --- files --------------------------------------------------------------------------------------


def read_grades(path: pathlib.Path = GRADES) -> dict[tuple[str, str], bool] | None:
    if not path.exists():
        return None
    return {(g["task"], g["arm"]): bool(g["right"]) for g in json.loads(path.read_text("utf-8"))}


def leak_marks(rows: Sequence[Mapping[str, Any]], scan=None) -> list[dict[str, str]]:
    return [{"task": r["task"], "arm": r["arm"]} for r in rows if leaked(r, scan)]


def report(rows: Sequence[Mapping[str, Any]], grades, marks: Sequence[Mapping[str, str]]) -> dict:
    ids = conf.IDS.read_text(encoding="utf-8").split()
    leaks = {(m["task"], model_of(m["arm"])) for m in marks}
    out: dict[str, Any] = {
        "sessions": len(rows),
        "list_usd": round(sum(r["list_usd"] for r in rows), 2),
        "prereg_sha256": conf.digest(),
        "registered": conf.registered(),
        "leaks": list(marks),
    }
    if grades is None:
        out["verdicts"] = None
        out["note"] = "not graded yet: run --blind-sheet, grade the sheet, then --apply"
        return out
    missing = [(r["task"], r["arm"]) for r in rows if (r["task"], r["arm"]) not in grades]
    if missing:
        raise SystemExit(f"{len(missing)} sessions have no blind grade: grade the sheet again")
    out["verdicts"] = verdicts(rows, grades, leaks, ids)
    out["described"] = described(rows, lambda r: right_of(r, grades, leaks))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--blind-sheet", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    rows = phase.counted(conf.free.nav.done_sessions(conf.SESSIONS))
    if args.blind_sheet:
        if SHEET.exists():
            raise SystemExit(f"{SHEET} exists: it may hold grades; move it away first")
        ids = conf.IDS.read_text(encoding="utf-8").split()
        tasks = {t[0]: t for t in frames.tasks(frames.read_frames(), ids)}
        sheet, key = blind_sheet(rows, tasks)
        SHEET.write_text(json.dumps(sheet, indent=1, ensure_ascii=False), encoding="utf-8")
        KEY.write_text(json.dumps(key, indent=1), encoding="utf-8")
        print(f"{len(sheet)} entries: grade {SHEET} (set each right to true or false)")
        return 0
    if args.apply:
        sheet = json.loads(SHEET.read_text(encoding="utf-8"))
        grades = apply_sheet(sheet, json.loads(KEY.read_text(encoding="utf-8")))
        GRADES.write_text(json.dumps(grades, indent=1), encoding="utf-8")
        print(f"{len(grades)} grades written to {GRADES}")
        return 0
    result = report(rows, read_grades(), leak_marks(rows))
    OUT.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
