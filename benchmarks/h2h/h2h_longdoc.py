"""Head to head on very long documents (LongBench v2): Claude Code alone (CC, N) against Claude
Code with the sanchopanza install line (SP, S).

python benchmarks/h2h/h2h_longdoc.py --plan [--limit 10]         # free: the run order and caps
python benchmarks/h2h/h2h_longdoc.py --draw-dev                  # free: 10 of the 60 for dev
python benchmarks/h2h/h2h_longdoc.py --preflight                 # free: data, arms, hooks
python benchmarks/h2h/h2h_longdoc.py --live --limit 10 --ceiling 25   # PAID (through launch.ps1)
python benchmarks/h2h/h2h_longdoc.py                             # free: the report

The 60 tasks of `longdoc_data.py` (Single- and Multi-Document QA, contexts of 103K to 2M
characters, seeded draw). One headless session per task and arm, a clean user each (GAIA's
runner). The context is copied into the session's folder as `document.txt`; the prompt is
LongBench v2's official zero-shot template with the `<text>` block replaced by a pointer to that
file. Both arms: the web taken away (WebSearch and WebFetch disallowed, the local hook on every
tool: no network from a shell, no path outside the folder), Claude Code's other tools.

Grading is the official one and needs no model: LongBench v2's `extract_answer` regex on the
reply ("The correct answer is (X)"), taken from the last line that has it, against the gold
letter. Reported overall and by the set's difficulty and length bands, with the paired McNemar
and cost bootstrap of GAIA. Rows keep the extracted letter only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from collections.abc import Mapping, Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import longdoc_data  # noqa: E402
import offline_common as common  # noqa: E402

gaia, phase, reading, stats = common.gaia, common.phase, common.reading, common.stats

PRIVATE = longdoc_data.CACHE / "h2h"
RESULTS = ROOT / "docs" / "results" / "2026-10-06-h2h-longdoc"
DEV_IDS = HERE / "longdoc-dev-ids.txt"  # out of every phase that does not name it with --ids
DOC_NAME = "document.txt"
LEAK_WORD = "LongBench"
# A median context of 330K characters is ~80K tokens: reading much of it costs more than a GAIA
# task, so the caps are twice GAIA's.
CAPS = {key: round(2 * value, 2) for key, value in gaia.CAPS.items()}
# longdoc-dev runs beside bcp-dev under one ceiling for both (--joint-with), at most this.
PHASE_CEILINGS = {"longdoc-dev": 50.0}
# LongBench v2's prompts/0shot.txt, with the <text> block replaced by the file's place.
TEMPLATE = (
    "Please read the text in the file {doc} (in your working directory) and answer the question "
    "below.\n\nWhat is the correct answer to this question: {question}\nChoices:\n(A) {a}\n"
    '(B) {b}\n(C) {c}\n(D) {d}\n\nFormat your response as follows: "The correct answer is '
    '(insert answer here)".'
)


def prompt(task: longdoc_data.Task) -> str:
    a, b, c, d = task.choices
    return TEMPLATE.format(doc=DOC_NAME, question=task.question.strip(), a=a, b=b, c=c, d=d)


def write_dev_ids(tasks: Sequence[longdoc_data.Task]) -> list[str]:
    ids = common.draw_dev([t.task_id for t in tasks])
    common.write_ids(DEV_IDS, ids, f"{len(ids)} of the {len(tasks)} long-document tasks for the "
                     f"dev phase: random.Random({common.DEV_SEED}).sample of the sorted ids. Out "
                     "of every other phase.")  # fmt: skip
    return ids


def chosen(tasks: Sequence[longdoc_data.Task], ids: str | None) -> list[longdoc_data.Task]:
    """The tasks of `ids` in its order (all, in the draw's order, without one), dev ids out."""
    by_id = {t.task_id: t for t in tasks}
    path = pathlib.Path(ids) if ids else None
    order = gaia.read_ids(path) if path else [t.task_id for t in tasks]
    return [by_id[i] for i in common.leave_out_dev(order, path, DEV_IDS) if i in by_id]


def flag_settings() -> dict[str, Any]:
    return common.base_settings()


def session_root(phase_name: str, task_id: str, arm: str, run: int) -> pathlib.Path:
    digest = hashlib.sha256(f"longdoc|{phase_name}|{task_id}|{arm}|{run}".encode()).hexdigest()
    return gaia.RUNS / phase_name / digest[:16]


def one_session(task: longdoc_data.Task, run: int, arm: str, ctx: Mapping[str, Any]) -> dict:
    root = session_root(ctx["phase"], task.task_id, arm, run)

    def make_row(out, stderr, work, side, wall, projects):  # noqa: ANN001, ANN202
        folder = reading.folder_of(work, projects)
        reply = common.reply_text(out, folder, lambda t: longdoc_data.last_answer(t) is not None)
        row = common.common_row(task.task_id, run, arm, out, stderr, work, side, wall,
                                projects, LEAK_WORD, CAPS)  # fmt: skip
        pred = longdoc_data.last_answer(reply)
        return {**row, "final_answer": pred, "ok_oficial": pred == task.gold,
                "success": pred == task.gold, "difficulty": task.difficulty,
                "length": task.length, "domain": task.domain, "chars": task.chars}  # fmt: skip

    return gaia.clean_session(ctx, root, arm, prompt(task), flag_settings=flag_settings(),
                              make_row=make_row,
                              copies=[(pathlib.Path(task.doc_path), DOC_NAME)],
                              tools=common.TOOLS, disallowed=common.DISALLOWED,
                              caps=CAPS)  # fmt: skip


def session_for(log_to: pathlib.Path, ctx: Mapping[str, Any]):
    def session(item: tuple, run: int, arm: str) -> dict[str, Any]:
        row = one_session(item[3], run, arm, ctx)
        if phase.usage_limited(row):
            phase._log(log_to, f"STOP-LIMIT {item[0]} {arm}: 429 or usage limit in the session")
        return row

    return session


# --- report -------------------------------------------------------------------------------------


def paths(phase_name: str) -> dict[str, pathlib.Path]:
    own = PRIVATE / phase_name
    return {"sessions": own / "sessions.jsonl", "report": RESULTS / f"report-{phase_name}.json"}


def bands(mine: Sequence[Mapping], key: str) -> dict[str, str]:
    return {band: f"{sum(bool(r['ok_oficial']) for r in mine if r[key] == band)}/"
                  f"{sum(r[key] == band for r in mine)}"
            for band in sorted({r[key] for r in mine})}  # fmt: skip


def report(rows: Sequence[Mapping]) -> dict[str, Any]:
    """Counts, costs and ids only, per arm, by band, and the paired comparison per model."""
    out: dict[str, Any] = {"sessions": len(rows),
                           "list_usd": round(sum(r["list_usd"] for r in rows), 2)}  # fmt: skip
    cells = {}
    for arm in sorted({r["arm"] for r in rows}):
        mine = [r for r in rows if r["arm"] == arm]
        cell = stats.arm_cell([{**r, "level": 0} for r in mine], {})
        cell.pop("by_level", None)
        cells[arm] = {**cell, "by_difficulty": bands(mine, "difficulty"),
                      "by_length": bands(mine, "length"),
                      "no_letter": sum(r["final_answer"] is None for r in mine)}  # fmt: skip
    out["by_arm"] = cells
    out["paired"] = {m: stats.paired(rows, {}, f"{m}-SP", f"{m}-CC")
                     for m in sorted({r["model_key"] for r in rows})}  # fmt: skip
    return out


# --- main ---------------------------------------------------------------------------------------


def parse(argv: Sequence[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    for flag in ("--plan", "--preflight", "--live", "--draw-dev"):
        mode.add_argument(flag, action="store_true")
    ap.add_argument("--phase", default="longdoc-dev")
    ap.add_argument("--models", nargs="+", default=["SONNET"], choices=sorted(gaia.MODELS))
    ap.add_argument("--brazos", nargs="+", default=["CC", "SP"], choices=gaia.ARMS)
    ap.add_argument("--ids", default=None, help="a file of task ids: only these, in its order")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ceiling", type=float, default=gaia.DEFAULT_CEILING_USD)
    common.add_joint_args(ap)
    gaia.add_line_args(ap)
    return ap.parse_args(argv)


def planned(tasks: Sequence[longdoc_data.Task], models: Sequence[str],
            brazos: Sequence[str]) -> list[tuple]:  # fmt: skip
    return [(i, (t.task_id, "", "", t), 1, f"{m}-{b}")
            for i, t in enumerate(tasks) for m in models for b in brazos]  # fmt: skip


def data_problems() -> list[str]:
    if not longdoc_data.TASKS.exists():
        return ["no long-document tasks: longdoc_data.py --fetch --draw"]
    missing = longdoc_data.summary(longdoc_data.load())["docs_missing"]
    return [f"{len(missing)} documents missing: longdoc_data.py --draw"] if missing else []


def main(argv: Sequence[str] | None = None) -> int:
    args = parse(argv)
    files = paths(args.phase)
    files["sessions"].parent.mkdir(parents=True, exist_ok=True)
    if args.draw_dev:
        print(f"{len(write_dev_ids(longdoc_data.load()))} ids written to {DEV_IDS}")
        return 0
    tasks = chosen(longdoc_data.load(), args.ids)
    steps = planned(tasks[: args.limit] if args.limit else tasks, args.models, args.brazos)
    if args.plan:
        for i, item, run, arm in steps:
            print(i, item[0], arm, run, CAPS[gaia.split_arm(arm)[0]])
        print(
            f"{len(steps)} sessions; caps sum {sum(CAPS[gaia.split_arm(s[3])[0]] for s in steps):g}"
        )
        return 0
    line = gaia.arms.s_line.load(pathlib.Path(args.s_line))
    problems = (common.preflight(args.brazos, flag_settings(), data_problems(), line)
                if args.preflight or args.live else [])  # fmt: skip
    if args.preflight:
        print("preflight: " + ("; ".join(problems) or "ok"), file=sys.stderr)
        return 3 if problems else 0
    rows = gaia.read_rows(files["sessions"])
    code = 0
    if args.live:
        code, rows = common.run_live(args, steps, rows,
                                     lambda ctx: session_for(files["sessions"], ctx),
                                     files["sessions"], CAPS, PHASE_CEILINGS, problems)  # fmt: skip
    counted = phase.counted(rows)
    if counted:
        result = report(counted)
        common.write_report(result, files["report"])
        print(json.dumps(result, indent=1))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
