"""Head to head on BrowseComp-Plus: Claude Code alone (CC, N) against Claude Code with the
sanchopanza install line (SP, S), over a fixed corpus instead of the web.

python benchmarks/h2h/h2h_bcp.py --draw                       # free: the seeded 100 ids
python benchmarks/h2h/h2h_bcp.py --draw-dev                   # free: 10 of them for dev
python benchmarks/h2h/h2h_bcp.py --plan [--limit 10]          # free: the run order and caps
python benchmarks/h2h/h2h_bcp.py --preflight                  # free: data, index, arms, hooks
python benchmarks/h2h/h2h_bcp.py --live --limit 10 --ceiling 25   # PAID (through launch.ps1)
python benchmarks/h2h/h2h_bcp.py --judge --judge-ceiling 3    # PAID (subscription): the judge
python benchmarks/h2h/h2h_bcp.py --review                     # free: the blind read, private
python benchmarks/h2h/h2h_bcp.py --verdict QID ARM RUN yes|no # a hand grade
python benchmarks/h2h/h2h_bcp.py                              # free: the report

One headless Claude Code session per query and arm, a clean user each (GAIA's runner,
`h2h_gaia.clean_session`). The prompt is the official QUERY_TEMPLATE with the query decrypted
in memory (`bcp_data`). Both arms get the same retrieval server (`bcp_server.py`, MCP `bcp`:
`search` and `get_document` over the corpus with bm25s), the web taken away (WebSearch and
WebFetch disallowed, the local hook on every tool), and Claude Code's other tools. S adds the
sealed install line and whatever MCP servers it registers.

Grading (`bcp_grade.py`): exact match after normalisation, else the official judge template on
Claude Haiku 4.5 instead of Qwen3-32B, and a blind hand read of the doubtful ones. Per row:
search and get calls, evidence and gold recall of the docids the searches returned, citation
precision and recall. Rows keep answers and live in the private cache; the report holds ids and
counts. The query text and the gold answer are never printed, logged or written to the repo.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import random
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import bcp_data  # noqa: E402
import bcp_grade  # noqa: E402
import bcp_server  # noqa: E402
import offline_common as common  # noqa: E402

gaia, phase, arms, reading, stats = (
    common.gaia,
    common.phase,
    common.arms,
    common.reading,
    common.stats,
)

PRIVATE = bcp_data.CACHE / "h2h"  # rows keep answers: never in the repository
RESULTS = ROOT / "docs" / "results" / "2026-10-06-h2h-bcp"
IDS = HERE / "bcp-ids.txt"
DEV_IDS = HERE / "bcp-dev-ids.txt"  # out of every phase that does not name it with --ids
SEED = 20261006
SIZE = 100
LEAK_WORD = "BrowseComp"
# Per-session caps, USD at list. BrowseComp with WebSearch hit GAIA's Sonnet cap of 1.50; with a
# local retriever a session reads more and searches more, so S and N get twice GAIA's caps.
CAPS = {key: round(2 * value, 2) for key, value in gaia.CAPS.items()}
# bcp-dev runs beside longdoc-dev under one ceiling for both (--joint-with), at most this.
PHASE_CEILINGS = {"bcp-dev": 50.0}
EXTRA_ALLOW = ("mcp__bcp__search", "mcp__bcp__get_document")


# --- the draw and the prompt --------------------------------------------------------------------


def draw(queries: Sequence[bcp_data.Query], size: int = SIZE, seed: int = SEED) -> list[str]:
    return random.Random(seed).sample(sorted(q.query_id for q in queries), size)


def write_ids() -> list[str]:
    ids = draw(bcp_data.load())
    head = (f"# {SIZE} of the 830 BrowseComp-Plus query ids: random.Random({SEED}).sample of the "
            "sorted ids. Ids only: the queries stay encrypted in the private cache.\n")  # fmt: skip
    IDS.write_text(head + "\n".join(ids) + "\n", encoding="utf-8")
    return ids


def write_dev_ids() -> list[str]:
    ids = common.draw_dev(gaia.read_ids(IDS))
    common.write_ids(DEV_IDS, ids, f"{len(ids)} of the {SIZE} ids of bcp-ids.txt for the dev "
                     f"phase: random.Random({common.DEV_SEED}).sample of the sorted ids. Out of "
                     "every other phase.")  # fmt: skip
    return ids


def flag_settings() -> dict[str, Any]:
    return common.base_settings(EXTRA_ALLOW)


def server_entry(side: pathlib.Path) -> dict[str, Any]:
    return {"bcp": bcp_server.entry(str(bcp_data.VENV_PYTHON), bcp_data.DOCS, bcp_data.INDEX,
                                    side / "bcp.jsonl")}  # fmt: skip


# --- one session --------------------------------------------------------------------------------


def server_log(path: pathlib.Path) -> dict[str, Any]:
    searches, gets, retrieved = 0, 0, []
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("tool") == "search":
            searches += 1
            retrieved.extend(entry.get("docids") or [])
        elif entry.get("tool") == "get":
            gets += 1
            retrieved.append(str(entry.get("docid")))
    return {"search_calls": searches, "get_calls": gets, "retrieved": sorted(set(retrieved))}


def graded_fields(reply: str, gold: str, evidence: Sequence[str], gold_docs: Sequence[str],
                  log: Mapping[str, Any]) -> dict[str, Any]:  # fmt: skip
    answer = bcp_grade.exact_answer(reply)
    cited = bcp_grade.citations(reply)
    return {
        "final_answer": answer,
        "em": bcp_grade.exact_match(answer, gold),
        "judged": None,
        "confidence": bcp_grade.confidence(reply),
        "search_calls": log["search_calls"], "get_calls": log["get_calls"],
        "evidence_recall": bcp_grade.recall(log["retrieved"], evidence),
        "gold_recall": bcp_grade.recall(log["retrieved"], gold_docs),
        "citations": bcp_grade.citation_metrics(cited, evidence),
    }  # fmt: skip


def session_root(phase_name: str, query_id: str, arm: str, run: int) -> pathlib.Path:
    digest = hashlib.sha256(f"bcp|{phase_name}|{query_id}|{arm}|{run}".encode()).hexdigest()[:16]
    return gaia.RUNS / phase_name / digest


def one_session(query: bcp_data.Query, run: int, arm: str, ctx: Mapping[str, Any]) -> dict:
    secret = bcp_data.password()
    question = bcp_data.decrypt(query.query, secret)
    root = session_root(ctx["phase"], query.query_id, arm, run)
    side = root / "side"
    qrels = ctx["qrels"]

    def make_row(out, stderr, work, side_, wall, projects):  # noqa: ANN001, ANN202
        folder = reading.folder_of(work, projects)
        reply = common.reply_text(out, folder, lambda t: bcp_grade.exact_answer(t) is not None)
        gold = bcp_data.decrypt(query.answer, secret)
        row = common.common_row(query.query_id, run, arm, out, stderr, work, side_, wall,
                                projects, LEAK_WORD, CAPS)  # fmt: skip
        log = server_log(side_ / "bcp.jsonl")
        evidence = qrels["evidence"].get(query.query_id, [])
        gold_docs = qrels["gold"].get(query.query_id, [])
        return {**row, **graded_fields(reply, gold, evidence, gold_docs, log),
                "reply_sha": hashlib.sha256(reply.encode()).hexdigest()[:16]}  # fmt: skip

    return gaia.clean_session(ctx, root, arm, bcp_grade.prompt(question),
                              flag_settings=flag_settings(), make_row=make_row,
                              mcp_servers=server_entry(side), tools=common.TOOLS,
                              disallowed=common.DISALLOWED, caps=CAPS)  # fmt: skip


def session_for(log_to: pathlib.Path, ctx: Mapping[str, Any]):
    def session(item: tuple, run: int, arm: str) -> dict[str, Any]:
        row = one_session(item[3], run, arm, ctx)
        if phase.usage_limited(row):
            phase._log(log_to, f"STOP-LIMIT {item[0]} {arm}: 429 or usage limit in the session")
        return row

    return session


# --- the judge (paid: subscription) -------------------------------------------------------------


def last_reply(row: Mapping[str, Any]) -> str:
    """The session's reply, read back from its own transcript (rows keep no reply text)."""
    work = pathlib.Path(row["workdir"])
    folder = reading.folder_of(work, work.parent / "config" / "projects")
    texts = [t for t in reading.last_assistant_texts(folder) if bcp_grade.exact_answer(t)]
    return texts[-1] if texts else (reading.last_assistant_texts(folder) or [""])[-1]


def judge_row(row: Mapping[str, Any], query: bcp_data.Query, secret: str) -> dict[str, Any]:
    """One judge call on a clean user; the verdict and its cost, no text kept."""
    key = f"{row['phase']}|{row['task']}|{row['arm']}|{row['run']}"
    root = gaia.RUNS / "bcp-judge" / hashlib.sha256(key.encode()).hexdigest()[:16]
    config, side = root / "config", root / "side"
    for folder in (config, side):
        folder.mkdir(parents=True, exist_ok=True)
    mcp = side / "mcp.json"
    mcp.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
    text = bcp_grade.judge_prompt(bcp_data.decrypt(query.query, secret), last_reply(row),
                                  bcp_data.decrypt(query.answer, secret))  # fmt: skip
    env = arms.session_env("CC", config, side, None)
    argv = bcp_grade.judge_argv(shutil.which("claude") or "claude", str(mcp))
    done = subprocess.run(argv, input=text.encode("utf-8"), cwd=side, env=env,
                          capture_output=True, timeout=600)  # fmt: skip
    out = json.loads(done.stdout.decode("utf-8", errors="replace") or "{}")
    arms.scrub(root, arms.secrets_of(env))
    reply = str(out.get("result") or "")
    return {"judged": bcp_grade.parse_judge(reply), "judge_usd": float(out.get("total_cost_usd")
            or 0.0), "judge_limited": gaia.limited(reply, done.stderr.decode(errors="replace"),
            bool(out.get("is_error")))}  # fmt: skip


def judge_pending(rows: Sequence[Mapping], ceiling: float) -> tuple[int, list[dict]]:
    """Judge the rows exact match did not settle, under a ceiling counted from what the judge
    calls cost; stops at a usage limit. Every row comes back, judged or not."""
    by_id = {q.query_id: q for q in bcp_data.load()}
    secret = bcp_data.password()
    spent, out, code = 0.0, [], 0
    for row in rows:
        if code or row.get("em") or row.get("judge_done") or row.get("not_run"):
            out.append(dict(row))
            continue
        if spent + bcp_grade.JUDGE_CAP_USD > ceiling:
            code = 1
            out.append(dict(row))
            continue
        result = judge_row(row, by_id[row["task"]], secret)
        spent += result["judge_usd"]
        if result["judge_limited"]:
            code = 2
            out.append(dict(row))
            continue
        out.append(
            {
                **row,
                "judged": result["judged"],
                "judge_usd": result["judge_usd"],
                "judge_done": True,
            }
        )
    print(f"judge: {spent:.4f} USD", file=sys.stderr)
    return code, out


# --- review and report --------------------------------------------------------------------------


def paths(phase_name: str) -> dict[str, pathlib.Path]:
    own = PRIVATE / phase_name
    return {"sessions": own / "sessions.jsonl", "hand": own / "hand.jsonl",
            "review": own / "review-blind.jsonl", "graded": own / "graded.jsonl",
            "report": RESULTS / f"report-{phase_name}.json"}  # fmt: skip


def with_grades(rows: Sequence[Mapping], graded: pathlib.Path) -> list[dict]:
    judged = {(r["task"], r["arm"], r["run"]): r for r in gaia.read_rows(graded)}
    keys = ("judged", "judge_usd", "judge_done")
    out = []
    for r in rows:
        done = judged.get((r["task"], r["arm"], r["run"]))
        out.append({**r, **{k: done.get(k) for k in keys}} if done else dict(r))
    return out


def graded_ok(row: Mapping[str, Any], hand: Mapping[tuple, bool]) -> bool:
    return bcp_grade.verdict(bool(row.get("em")), row.get("judged"),
                             hand.get((row["task"], row["arm"], row["run"])))  # fmt: skip


def blind_review(rows: Sequence[Mapping], hand: Mapping[tuple, bool], path: pathlib.Path) -> int:
    """The doubtful rows for a person, shuffled, with no arm: question, gold, extracted answer,
    and a key to give the verdict back. Written to the private cache, never printed."""
    by_id = {q.query_id: q for q in bcp_data.load()}
    secret = bcp_data.password()
    todo = [r for r in rows if r.get("judge_done")
            and bcp_grade.doubtful(bool(r.get("em")), r.get("judged"))
            and (r["task"], r["arm"], r["run"]) not in hand]  # fmt: skip
    items = [{"key": f"{r['task']} {r['arm']} {r['run']}",
              "question": bcp_data.decrypt(by_id[r["task"]].query, secret),
              "gold": bcp_data.decrypt(by_id[r["task"]].answer, secret),
              "answer": r.get("final_answer")} for r in todo]  # fmt: skip
    random.Random(SEED).shuffle(items)
    path.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in items),
                    encoding="utf-8")  # fmt: skip
    return len(items)


def arm_cell(mine: Sequence[Mapping], hand: Mapping[tuple, bool]) -> dict[str, Any]:
    base = stats.arm_cell([{**r, "ok_oficial": graded_ok(r, hand), "level": 0} for r in mine],
                          hand)  # fmt: skip
    base.pop("by_level", None)

    def mean(key: str) -> float | None:
        values = [r[key] for r in mine if r.get(key) is not None]
        return round(sum(values) / len(values), 4) if values else None

    return {
        **base,
        "em": sum(bool(r.get("em")) for r in mine),
        "judge_yes_without_em": sum(r.get("judged") is True and not r.get("em") for r in mine),
        "unjudged": sum(r.get("judged") is None and not r.get("em") for r in mine),
        "mean_search_calls": mean("search_calls"), "mean_get_calls": mean("get_calls"),
        "mean_evidence_recall": mean("evidence_recall"), "mean_gold_recall": mean("gold_recall"),
        "mean_citation_precision": round(sum(r["citations"]["precision"] for r in mine)
                                         / len(mine), 4) if mine else None,
        "judge_usd": round(sum(float(r.get("judge_usd") or 0.0) for r in mine), 4),
    }  # fmt: skip


def report(rows: Sequence[Mapping], hand: Mapping[tuple, bool]) -> dict[str, Any]:
    """Counts, costs and ids only; the paired comparison on the final grade."""
    graded = [{**r, "ok_oficial": graded_ok(r, hand)} for r in rows]
    out: dict[str, Any] = {"sessions": len(rows),
                           "list_usd": round(sum(r["list_usd"] for r in rows), 2)}  # fmt: skip
    out["by_arm"] = {arm: arm_cell([r for r in rows if r["arm"] == arm], hand)
                     for arm in sorted({r["arm"] for r in rows})}  # fmt: skip
    out["paired"] = {m: stats.paired(graded, {}, f"{m}-SP", f"{m}-CC")
                     for m in sorted({r["model_key"] for r in rows})}  # fmt: skip
    out["verdict"] = {m: stats.verdict(pair) for m, pair in out["paired"].items()}
    out["grading"] = (
        "exact match after normalisation, else the official judge template on "
        f"{bcp_grade.JUDGE_MODEL} (official: Qwen3-32B), hand verdicts first"
    )
    return out


# --- main ---------------------------------------------------------------------------------------


def parse(argv: Sequence[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    for flag in ("--plan", "--preflight", "--live", "--judge", "--review", "--draw", "--draw-dev"):
        mode.add_argument(flag, action="store_true")
    mode.add_argument("--verdict", nargs=4, metavar=("QID", "ARM", "RUN", "YES_NO"))
    ap.add_argument("--phase", default="bcp-dev")
    ap.add_argument("--models", nargs="+", default=["SONNET"], choices=sorted(gaia.MODELS))
    ap.add_argument("--brazos", nargs="+", default=["CC", "SP"], choices=gaia.ARMS)
    ap.add_argument("--ids", default=str(IDS))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ceiling", type=float, default=gaia.DEFAULT_CEILING_USD)
    ap.add_argument("--judge-ceiling", type=float, default=3.0)
    common.add_joint_args(ap)
    gaia.add_line_args(ap)
    return ap.parse_args(argv)


def chosen(args: argparse.Namespace) -> list[bcp_data.Query]:
    by_id = {q.query_id: q for q in bcp_data.load()}
    path = pathlib.Path(args.ids)
    order = [i for i in common.leave_out_dev(gaia.read_ids(path), path, DEV_IDS) if i in by_id]
    picked = [by_id[i] for i in order]
    return picked[: args.limit] if args.limit else picked


def planned(queries: Sequence[bcp_data.Query], models: Sequence[str],
            brazos: Sequence[str]) -> list[tuple]:  # fmt: skip
    return [(i, (q.query_id, "", "", q), 1, f"{m}-{b}")
            for i, q in enumerate(queries) for m in models for b in brazos]  # fmt: skip


def data_problems() -> list[str]:
    problems = []
    for path, what in ((bcp_data.QUERIES, "--fetch"), (bcp_data.CANARY, "--fetch"),
                       (bcp_data.DOCS, "--build"),
                       (bcp_data.INDEX / "params.index.json", "--build"),
                       (bcp_data.VENV_PYTHON, "the bcp venv"), (IDS, "--draw")):  # fmt: skip
        if not path.exists():
            problems.append(f"{path.name} missing: bcp_data.py {what}")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    args = parse(argv)
    files = paths(args.phase)
    files["sessions"].parent.mkdir(parents=True, exist_ok=True)
    if args.draw:
        print(f"{len(write_ids())} ids written to {IDS}")
        return 0
    if args.draw_dev:
        print(f"{len(write_dev_ids())} ids written to {DEV_IDS}")
        return 0
    if args.verdict:
        qid, arm, run, yes = args.verdict
        with files["hand"].open("a", encoding="utf-8") as sink:
            sink.write(json.dumps({"task": qid, "arm": arm, "run": int(run),
                                   "ok": yes.lower() in ("yes", "y", "si")}) + "\n")  # fmt: skip
        return 0
    steps = planned(chosen(args), args.models, args.brazos)
    if args.plan:
        for i, item, run, arm in steps:
            print(i, item[0], arm, run, CAPS[gaia.split_arm(arm)[0]])
        print(
            f"{len(steps)} sessions; caps sum {sum(CAPS[gaia.split_arm(s[3])[0]] for s in steps):g}"
        )
        return 0
    line = gaia.arms.s_line.load(pathlib.Path(args.s_line))
    problems = (common.preflight(args.brazos, flag_settings(), data_problems(), line,
                                 args.phase)
                if args.preflight or args.live else [])  # fmt: skip
    if args.preflight:
        print("preflight: " + ("; ".join(problems) or "ok"), file=sys.stderr)
        return 3 if problems else 0
    rows = gaia.read_rows(files["sessions"])
    code = 0
    if args.live:
        make = lambda ctx: session_for(files["sessions"], {**ctx, "qrels": qrels()})  # noqa: E731
        code, rows = common.run_live(args, steps, rows, make, files["sessions"], CAPS,
                                     PHASE_CEILINGS, problems)  # fmt: skip
    counted = with_grades(phase.counted(rows), files["graded"])
    hand = gaia.hand_verdicts(files["hand"])
    if args.judge:
        code, judged = judge_pending(counted, args.judge_ceiling)
        files["graded"].write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                                           for r in judged), encoding="utf-8")  # fmt: skip
        counted = judged
    if args.review:
        n = blind_review(counted, hand, files["review"])
        print(f"{n} sessions to read blind: {files['review']}")
        return 0
    if counted:
        result = report(counted, hand)
        common.write_report(result, files["report"])
        print(json.dumps(result, indent=1))
    return code


def qrels() -> dict[str, dict[str, list[str]]]:
    return {name: bcp_data.read_qrels(path) for name, path in bcp_data.QRELS.items()}


if __name__ == "__main__":
    raise SystemExit(main())
