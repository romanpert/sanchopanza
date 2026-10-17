"""Lot longdoc-free (docs/results/2026-10-16-longdoc-free/): the Claude Code sessions, arms N, H,
H0 and HC, on ∞Bench En.QA with free-text answers graded by ∞Bench's own `qa_f1_score`.

    python benchmarks/h2h/h2h_lfree.py --dry --stage dev        # free: the plan and the money
    python benchmarks/h2h/h2h_lfree.py --preflight --stage dev  # free: seal, data, pin, passages
    powershell -File benchmarks/h2h/launch.ps1 -Runner h2h_lfree.py -RunnerArgs "--stage dev" `
        -Pin $env:USERPROFILE\\.cache\\sanchopanza\\claude-pin\\2.1.287 -KeysEnv <path> `
        -Log C:\\sp-runs\\longdoc-free\\driver.log -PidFile C:\\sp-runs\\longdoc-free\\driver.pids
    python benchmarks/h2h/h2h_lfree.py --stage dev              # free: rows without text

Every arm is one headless Claude Code 2.1.287 session (pinned) with a clean user and its own
CLAUDE_CONFIG_DIR, the web taken away and the local hook on every tool (h2h_longdoc's session),
and the same prompt, ∞Bench's En.QA instruction ("Read the book ... Be very concise") with the
book named as a file and a last line `ANSWER: ...` asked for; the arms differ only in the model
and in what `document.txt` holds:

- N: Sonnet 5.5, the whole novel.
- H: Haiku 4.5, the passages Jev kept for the question (phase J's file, jev_phase.py).
- H0: Haiku 4.5, the whole novel (no Jev: what Haiku alone does).
- HC: Haiku 4.5, no file and a closed-book prompt (what is answered from memory; dev only).

One phase per model: N's, then Haiku's with H, H0 and HC interleaved per question (their order
rotating with the question's position), so each phase reserves one worst turn. The money and
each session's health are lb162x's (`cap_for`: a session's cap while cap + one worst turn fits
under the phase's ceiling; lb162x_guard.Budget), the clock and STOP lb162's, the exits
h2h_lb162x's (done 0, ceiling 1, limit 2, preflight 3, clock 5, manual 6, error 7, outage 8,
smoke 9). The reply's answer is the text after its last `ANSWER:` line, else its last non-empty
line; a reply with no text has none (infrastructure, for the guard).
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import importlib.util
import json
import pathlib
import random
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "benchmarks" / "jev114"))
sys.path.insert(0, str(ROOT / "benchmarks"))
import h2h_lb162x as x  # noqa: E402
import lb162x  # noqa: E402
import lb162x_guard as guard_mod  # noqa: E402
import meter  # noqa: E402
import paid_once  # noqa: E402

ld, s162, common, gaia, phase_loop = x.ld, x.s162, x.common, x.gaia, x.phase_loop


def _load(name: str, path: pathlib.Path) -> Any:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


LF = ROOT / "benchmarks" / "longdoc_free"
pool = _load("lf_pool", LF / "pool.py")
jev_phase = _load("lf_jev_phase", LF / "jev_phase.py")
score = _load("lf_infbench_score", LF / "infbench_score.py")

LOT = "longdoc-free"
OUT = pool.LOT_DIR
PRIVATE = pool.CACHE / "h2h"
RUN_DIR = pathlib.Path("C:/sp-runs/longdoc-free")
LAUNCHER = HERE / "launch.ps1"
DOC_NAME = "document.txt"
LEAK_WORD = "InfiniteBench"
ORDER_SEED = pool.SEED + 1
BRAZO = "CC"
VARIANTS = {"SONNET": ("N",), "HAIKU": ("H", "H0", "HC")}
CAPS = {"SONNET": 3.00, "HAIKU": 1.50}  # h2h_longdoc's (twice GAIA's) for long documents
# The instrument a Claude phase is bound to: everything it imports and the package.
INSTRUMENT = ("src", "benchmarks", jev_phase.IDS_REL)
BOOK = (
    "Read the book in the file {doc} (in your working directory) and answer the question. Be "
    "very concise in your answer.\n\nQuestion: {question}\n\nEnd your reply with one line: "
    "ANSWER: <your answer, in a few words>"
)
CLOSED = (
    "Answer the question about a novel from what you already know; there is no file. Be very "
    "concise in your answer, and if you do not know, give your best guess.\n\nQuestion: "
    "{question}\n\nEnd your reply with one line: ANSWER: <your answer, in a few words>"
)
ANSWER_LINE = re.compile(r"^\W*(?:final\s+)?answer\W*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
SHORT_TOKENS = 12  # the design's length sensitivity: F1 of the answer's first 12 tokens

Phase = lb162x.Phase
IDS = pool.IDS_FILE
DEV_N = Phase("DN", "lfree-dev-sonnet", "SONNET", meter.SONNET_55, IDS, 41, ceiling=12.00,
              full_cap=CAPS["SONNET"], floor=0.50, wall_mean_s=60.0, cost_scale=1.0,
              rows=OUT / "dev-sonnet-rows.jsonl", stop=OUT / "dev-sonnet-stop.json")  # fmt: skip
DEV_HAIKU = Phase("DH", "lfree-dev-haiku", "HAIKU", meter.HAIKU_45, IDS, 123, ceiling=9.00,
                  full_cap=CAPS["HAIKU"], floor=0.30, wall_mean_s=45.0, cost_scale=1.0,
                  rows=OUT / "dev-haiku-rows.jsonl", stop=OUT / "dev-haiku-stop.json")  # fmt: skip
SMOKE = Phase("S", "lfree-smoke", "SONNET", meter.SONNET_55, IDS, 1, ceiling=0.80, full_cap=0.80,
              floor=0.80, wall_mean_s=60.0, cost_scale=1.0, rows=OUT / "smoke-rows.jsonl",
              stop=OUT / "smoke-stop.json")  # fmt: skip
STAGES: dict[str, tuple[Phase, ...]] = {"dev": (SMOKE, DEV_N, DEV_HAIKU)}
STAGE_OF = {p.key: stage for stage, phases in STAGES.items() for p in phases}


@dataclasses.dataclass(frozen=True)
class FreeTask:
    key: str  # "<id>:<variant>"
    item: int
    variant: str
    novel: str
    question: str
    answers: tuple[str, ...]
    stage: str

    @property
    def task_id(self) -> str:
        return self.key


# ---- the answer ------------------------------------------------------------------------------


def extract(reply: str | None, ok: bool = True) -> str | None:
    """The text after the reply's last `ANSWER:` line, else (when the session ended well, `ok`)
    its last non-empty line; None for no text, and for a session that failed or met its cap
    without an ANSWER line (an error message or a half-done turn is no answer: the guard sees
    it, review of 2026-10-17)."""
    if not reply or not reply.strip():
        return None
    found = ANSWER_LINE.findall(reply)
    if found:
        answer = found[-1].strip().strip("*").strip()
        if answer:
            return answer
    if not ok:
        return None
    lines = [line.strip().strip("*").strip() for line in reply.splitlines() if line.strip()]
    return lines[-1] if lines else None


def grade(answer: str | None, answers: Sequence[str]) -> float:
    return float(score.qa_f1_score(answer or "", list(answers)))


def grade_short(answer: str | None, answers: Sequence[str]) -> float:
    """F1 of the answer cut to its first SHORT_TOKENS whitespace tokens (registered secondary)."""
    return grade(" ".join((answer or "").split()[:SHORT_TOKENS]), answers)


# ---- tasks and sessions ----------------------------------------------------------------------


def stage_items(stage: str) -> list[Any]:
    phase_name = "dev" if stage == "dev" else "confirm"
    ids = set(pool.phase_ids(pool.read_frozen(), phase_name))
    items, _ = pool.items(pool.rows())
    chosen = sorted((i for i in items if i.id in ids), key=lambda i: i.id)
    random.Random(ORDER_SEED).shuffle(chosen)
    return chosen


def variants_at(model: str, position: int) -> list[str]:
    own = list(VARIANTS[model])
    shift = position % len(own)
    return own[shift:] + own[:shift]


def tasks_of(phase: Phase) -> list[FreeTask]:
    stage = STAGE_OF[phase.key]
    items = stage_items(stage)
    if phase.key == SMOKE.key:
        items = items[:1]
    out = []
    for position, item in enumerate(items):
        for variant in variants_at(phase.model, position):
            out.append(FreeTask(f"{item.id}:{variant}", item.id, variant, item.novel,
                                item.question, item.answers, stage))  # fmt: skip
    return out


def document_of(task: FreeTask) -> pathlib.Path | None:
    if task.variant in ("N", "H0"):
        return pool.novel_path(task.novel)
    if task.variant == "H":
        return jev_phase.passages_path("dev" if task.stage == "dev" else "confirm", task.item)
    return None


def prompt(task: FreeTask) -> str:
    template = CLOSED if task.variant == "HC" else BOOK
    return template.format(doc=DOC_NAME, question=task.question.strip())


def session_root(phase_name: str, key: str, arm: str, run: int) -> pathlib.Path:
    digest = hashlib.sha256(f"lfree|{phase_name}|{key}|{arm}|{run}".encode()).hexdigest()
    return gaia.RUNS / phase_name / digest[:16]


def make_row_for(task: FreeTask, run: int, arm: str, caps: Mapping[str, float],
                 extra: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None):  # fmt: skip
    def make_row(out, stderr, work, side, wall, projects):  # noqa: ANN001, ANN202
        folder = common.reading.folder_of(work, projects)
        ended_well = not out.get("is_error", True)  # as common_row: no JSON is an error
        reply = common.reply_text(out, folder, lambda t: extract(t, ended_well) is not None)
        row = common.common_row(task.key, run, arm, out, stderr, work, side, wall, projects,
                                LEAK_WORD, caps)  # fmt: skip
        answer = extract(reply, bool(row.get("ok", False)))
        f1 = grade(answer, task.answers)
        return {**row, "item": task.item, "variant": task.variant, "final_answer": answer,
                "f1": f1, "f1_short": grade_short(answer, task.answers),
                "ok_oficial": f1 == 1.0, "success": f1 > 0,
                "has_answer_line": bool(reply and ANSWER_LINE.search(reply)),
                "answer_words": len((answer or "").split()),
                **(extra(out) if extra else {})}  # fmt: skip

    return make_row


def one_session(task: FreeTask, run: int, arm: str, ctx: Mapping[str, Any], phase_name: str,
                caps: Mapping[str, float],
                extra: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
                ) -> dict:  # fmt: skip
    document = document_of(task)
    copies = [(document, DOC_NAME)] if document is not None else []
    return gaia.clean_session(ctx, session_root(phase_name, task.key, arm, run), arm,
                              prompt(task), flag_settings=ld.flag_settings(),
                              make_row=make_row_for(task, run, arm, caps, extra), copies=copies,
                              tools=common.TOOLS, disallowed=common.DISALLOWED,
                              caps=caps)  # fmt: skip


def sessions_of(phase: Phase) -> pathlib.Path:
    return PRIVATE / phase.name / "sessions.jsonl"


def reservations_of(phase: Phase) -> pathlib.Path:
    return sessions_of(phase).with_name("reservations.jsonl")


def steps(phase: Phase, tasks: Sequence[FreeTask]) -> list[tuple]:
    return [(i, (t.key, "", "", t), 1, phase.arm) for i, t in enumerate(tasks)]


def done_now(phase: Phase) -> int:
    rows = gaia.read_rows(sessions_of(phase))
    return sum(1 for r in rows
               if r.get("arm") == phase.arm and not r.get("not_run") and r["run"] > 0)  # fmt: skip


def session_for(phase: Phase, ctx: Mapping[str, Any]) -> Callable:
    def session(item: tuple, run: int, arm: str, cap: float) -> dict[str, Any]:
        row = one_session(item[3], run, arm, ctx, phase.name, {phase.model: cap},
                          extra=guard_mod.reply_flags)  # fmt: skip
        if phase_loop.usage_limited(row):
            phase_loop._log(sessions_of(phase), f"STOP-LIMIT {item[0]} {arm}: usage limit")
        return row

    return session


# ---- rows without text -------------------------------------------------------------------------


def public_rows(rows: Sequence[Mapping[str, Any]], phase: Phase) -> list[dict[str, Any]]:
    out = []
    for r in phase_loop.counted(list(rows)):
        if r.get("arm") != phase.arm:
            continue
        served = guard_mod.served_by(r)
        out.append({"key": r["task_id"], "id": r.get("item"), "variant": r.get("variant"),
                    "f1": r.get("f1"), "f1_short": r.get("f1_short"),
                    "answer_words": r.get("answer_words"),
                    "has_answer_line": r.get("has_answer_line"),
                    "no_answer": r.get("final_answer") is None,
                    "usd": round(float(r["list_usd"]), 6), "wall_s": r.get("wall_s"),
                    "turns": r.get("turns"), "hit_cap": bool(r.get("hit_cap")),
                    "is_error": not r.get("ok", False), "subtype": r.get("subtype"),
                    "cap_usd": r.get("cap_usd"),
                    "served_ok": served is None or served == phase.model_id})  # fmt: skip
    return out


def export(phase: Phase, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    mine = public_rows(rows, phase)
    x.lb162.write_jsonl(phase.rows, mine)
    return {"sessions": len(mine), "list_usd": round(sum(r["usd"] for r in mine), 4)}


def smoke_passed(rows: Sequence[Mapping[str, Any]]) -> bool:
    """The path, not the answer: a counted session served by Sonnet, above 0 USD, that ended
    without an error with an answer, or stopped by its cap."""
    return any(r.get("arm") == SMOKE.arm and guard_mod.served_by(r) == SMOKE.model_id
               and float(r.get("list_usd") or 0.0) > 0
               and ((r.get("ok", False) and r.get("final_answer") is not None) or r.get("hit_cap"))
               for r in phase_loop.counted(list(rows)))  # fmt: skip


def settle_smoke(kind: str) -> str:
    if kind not in ("done", "ceiling"):
        return kind
    if smoke_passed(gaia.read_rows(sessions_of(SMOKE))):
        return "done"
    guard_mod.void_free(sessions_of(SMOKE), "smoke failed at 0 USD: repeated on a relaunch")
    return "smoke"


def smoke_cap(spent: float) -> float | None:
    return SMOKE.full_cap if spent + SMOKE.full_cap <= SMOKE.ceiling + 1e-9 else None


def final_kind(phase: Phase) -> str | None:
    kind = (lb162x.stop_of(phase) or {}).get("kind")
    finals = ("done",) if phase.key == SMOKE.key else lb162x.FINAL
    return kind if kind in finals else None


# ---- money ------------------------------------------------------------------------------------


def stage_spent(stage: str) -> float:
    """What the stage's phases have really spent: every counted session and every open
    reservation (at its cap and one worst turn), as the guard counts it."""
    return sum(guard_mod.spent_now(sessions_of(p), reservations_of(p), p.full_cap + p.worst_turn)
               for p in STAGES[stage])  # fmt: skip


def money(stage: str) -> dict[str, Any]:
    """Per phase: sessions, its ceiling, and the most it can spend (the ceiling; the smoke's
    cap plus one worst turn, since its cap reserves none)."""
    out = {}
    for phase in STAGES[stage]:
        worst = phase.full_cap + phase.worst_turn if phase.key == SMOKE.key else phase.ceiling
        out[phase.key] = {"name": phase.name, "model": phase.model_id, "sessions": phase.n,
                          "ceiling": phase.ceiling, "full_cap": phase.full_cap,
                          "worst_turn": phase.worst_turn, "most_usd": round(worst, 2)}  # fmt: skip
    out["most_usd"] = round(sum(v["most_usd"] for v in out.values()), 2)
    return out


# ---- refusals -----------------------------------------------------------------------------------


def claude_lot(stage: str) -> paid_once.Lot:
    """The Jev phase's lot with the Claude phases' wider instrument."""
    return dataclasses.replace(jev_phase.lot("dev" if stage == "dev" else "confirm"),
                               instrument=INSTRUMENT)  # fmt: skip


def git_out(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          check=False, timeout=60)  # fmt: skip


def passages_problems(stage: str) -> list[str]:
    """Every question of the stage has phase J's passages, as long as its public row says (the
    private folder is shared by worktrees)."""
    phase_name = "dev" if stage == "dev" else "confirm"
    ids = pool.phase_ids(pool.read_frozen(), phase_name)
    missing = [i for i in ids if not jev_phase.passages_path(phase_name, i).is_file()]
    if missing:
        return [f"{len(missing)} questions without phase J's passages: jev_phase.py rows"]
    rows = OUT / f"jev-{phase_name}.jsonl"
    if not rows.is_file():
        return [f"no {rows.name}: jev_phase.py rows --phase {phase_name}"]
    lines = [json.loads(x) for x in rows.read_text("utf-8").splitlines() if x.strip()]
    kept = {int(r["id"]): r["kept_chars"] for r in lines}
    wrong = [
        i
        for i in ids
        if kept.get(i) != len(jev_phase.passages_path(phase_name, i).read_text("utf-8"))
    ]
    return [f"{len(wrong)} passages files differ from {rows.name}"] if wrong else []


def data_problems(stage: str) -> list[str]:
    """The pinned input, the stage's novels as their keys say, and its passages."""
    try:
        pool.require_pinned()
    except SystemExit as why:
        return [str(why)]
    phase_name = "dev" if stage == "dev" else "confirm"
    novels = {r["novel"] for r in pool.read_frozen()["items"] if r["phase"] == phase_name}
    missing = [k for k in novels if not pool.novel_path(k).is_file()]
    if missing:
        return [f"{len(missing)} novels missing: pool.py --prepare"]
    changed = [k for k in novels if pool.novel_key(pool.novel_path(k).read_text("utf-8")) != k]
    if changed:
        return [f"{len(changed)} novels differ from their key: pool.py --prepare"]
    return passages_problems(stage)


def launcher_problems(path: pathlib.Path = LAUNCHER) -> list[str]:
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    return [] if "'h2h_lfree.py'" in text else [f"{path.name} does not accept -Runner h2h_lfree.py"]


def model_problems(pin_dir: pathlib.Path = s162.PIN_DIR) -> list[str]:
    found = gaia.model_ids_in(pin_dir / "claude.exe", [meter.SONNET_55, meter.HAIKU_45])
    return [f"{m} not in the pinned claude.exe" for m, ok in found.items() if not ok]


Git = Callable[..., subprocess.CompletedProcess]


def refusal(stage: str, now: dt.datetime, run_dir: pathlib.Path = RUN_DIR,
            git: Git = git_out) -> tuple[str, str] | None:  # fmt: skip
    """Before any session: (kind, why) when the stage may not start, else None."""
    try:
        the_lot = claude_lot(stage)
        paid_once.require_sealed(the_lot)
        paid_once.require_instrument(the_lot)
        paid_once.require_inputs(the_lot)
        found = [*jev_phase.sealed_head_problems(the_lot, git), *x.pin_problems(),
                 *data_problems(stage), *launcher_problems()]  # fmt: skip
        if found:
            return "preflight", "; ".join(found)
    except SystemExit as why:
        return "preflight", str(why)
    if (run_dir / "LIMIT.flag").exists():
        return "limit", "LIMIT.flag in the run folder: the last run met a usage limit"
    todo = [p for p in STAGES[stage] if not final_kind(p)]
    if not todo:
        return "done", "every phase is over: nothing to run"
    sessions = sum(p.n - done_now(p) for p in todo)
    seconds = sessions * max(p.wall_mean_s for p in todo) * s162.WALL_FACTOR
    if now.hour < s162.EARLIEST_HOUR:
        return "clock", f"{now:%H:%M} is before {s162.EARLIEST_HOUR:02d}:00"
    if s162.crosses_midnight(now, seconds + s162.MIDNIGHT_MARGIN_S):
        return "clock", f"{sessions} sessions started at {now:%H:%M} would cross midnight"
    return None


# ---- the driver ---------------------------------------------------------------------------------


def run_phase(phase: Phase, found: Sequence[str]) -> str:  # pragma: no cover - paid sessions
    tasks = tasks_of(phase)
    now = dt.datetime.now()
    if why := x.clock_refusal(phase, now, len(tasks) - done_now(phase)):
        print(why, file=sys.stderr)
        return "clock"
    sessions, reservations = sessions_of(phase), reservations_of(phase)
    sessions.parent.mkdir(parents=True, exist_ok=True)
    smoke = phase.key == SMOKE.key
    guard = guard_mod.Budget(phase, now, sessions, reservations,
                             cap_rule=smoke_cap if smoke else None, run_dir=RUN_DIR)  # fmt: skip
    reserve = SMOKE.full_cap if smoke else phase.loop_reserve
    code, rows = common.run_live(x.live_args(phase), steps(phase, tasks),
                                 guard_mod.known_rows(sessions, reservations),
                                 lambda ctx: guard.wrap(session_for(phase, ctx)), sessions,
                                 {phase.model: reserve}, {phase.name: phase.ceiling},
                                 found)  # fmt: skip
    kind = s162.stop_kind(code, guard)
    said = export(phase, rows)
    if smoke:
        kind = settle_smoke(kind)
    print(json.dumps({"phase": phase.key, **said, "stop": kind}), file=sys.stderr)
    return kind


def live(stage: str, now: dt.datetime | None = None) -> int:  # pragma: no cover - paid sessions
    if stop := refusal(stage, now or dt.datetime.now()):
        print(f"refused: {stop[1]}", file=sys.stderr)
        return x.exit_code(stop[0])
    found = [*model_problems(), *common.preflight([BRAZO], ld.flag_settings(), [], None, LOT)]
    kind, kinds = x.drive(STAGES[stage],
                          lambda p: x.guarded_run(p, found, run=run_phase, run_dir=RUN_DIR),
                          final=final_kind)  # fmt: skip
    print(json.dumps({"stage": stage, "kind": kind, "phases": kinds}), file=sys.stderr)
    return x.exit_code(kind)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    for flag in ("--dry", "--preflight", "--live"):
        mode.add_argument(flag, action="store_true")
    ap.add_argument("--stage", choices=sorted(STAGES), required=True)
    args = ap.parse_args(argv)
    if args.dry:
        plan = {p.key: len(tasks_of(p)) for p in STAGES[args.stage]}
        print(json.dumps({"sessions": plan, "money": money(args.stage)}, indent=1))
        return 0
    if args.preflight:
        stop = refusal(args.stage, dt.datetime.now())
        found = [*model_problems(), *([stop[1]] if stop else [])]
        print("preflight: " + ("; ".join(found) or "ok"), file=sys.stderr)
        return 3 if found else 0
    if args.live:
        return live(args.stage)
    said = {p.key: export(p, gaia.read_rows(sessions_of(p))) for p in STAGES[args.stage]}
    print(json.dumps(said, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
