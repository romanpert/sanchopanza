"""A10 with labels from the target environment: the local check_done classifier cross-fitted on
AgentDojo's own labels in the suites it is scored on, against Jev 1.14 on the same stops. Free:
no model is called.

    python benchmarks/a10_local/target.py run      # analysis.json, scored.jsonl (no text)

Planned in docs/results/2026-10-17-a10-target/plan.md. `run` refuses while the plan or this lot's
code differs from the commit (`git status --porcelain`), and when its outputs already exist; it
records the commit and the plan's sha256.

THE STOPS: checkdone114's 950 (`a10_data.load_test`, checked against that lot's sealed
`data.sha256`) and checkdone-w17's 1,572 confirmation stops (`checkdone_w17.load_confirm`, every
file checked by blob sha), with check_done's record as both lots asked Jev about it (the `old`
builder). THE LABELS: AgentDojo's `utility`. Jev's recorded p(done) (`p_14`, `p_old`) is joined
after the fits, for the comparison only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import a10_data as data  # noqa: E402
import a10_model as model  # noqa: E402
import a10_target as target  # noqa: E402

ROOT = data.ROOT
OUT = ROOT / "docs" / "results" / "2026-10-17-a10-target"
PLAN = OUT / "plan.md"
A10_MODEL = ROOT / "fixtures" / "a10_local" / "model.json"
CD = ROOT / "docs" / "results" / "2026-10-16-checkdone114"
W17 = ROOT / "docs" / "results" / "2026-10-16-checkdone-w17"
EXPECTED = 2522
PLANNED = (
    "docs/results/2026-10-17-a10-target/plan.md",
    "benchmarks/a10_local/a10_target.py",
    "benchmarks/a10_local/target.py",
)


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def git_dirty(paths: Sequence[str] = PLANNED) -> list[str]:
    found = subprocess.run(["git", "status", "--porcelain", "--", *paths], cwd=ROOT,
                           capture_output=True, text=True, check=True)  # fmt: skip
    return [line for line in found.stdout.splitlines() if line.strip()]


def require_clean(dirty: Sequence[str]) -> None:
    if dirty:
        raise SystemExit(f"commit the plan and the code first ({len(dirty)} not clean): {dirty}")


def head() -> str:
    found = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                           text=True, check=True)  # fmt: skip
    return found.stdout.strip()


def load_stops() -> list[data.Example]:
    first, digest = data.load_test()
    if digest != json.loads((CD / "data.sha256").read_text(encoding="utf-8"))["done"]:
        raise SystemExit("checkdone114's stops differ from its sealed inputs")
    import checkdone_w17  # benchmarks/jev114, on sys.path through a10_data

    second = []
    for stop in checkdone_w17.load_confirm():
        task, record = data.text_of(stop["old"]["state"])
        second.append(data.Example(stop["id"], stop["cluster"], stop["pipeline"],
                                   stop["label"] == "done", task, record))  # fmt: skip
    stops = [*first, *second]
    if len(stops) != EXPECTED or len({e.id for e in stops}) != EXPECTED:
        raise SystemExit(f"{len(stops)} stops, planned {EXPECTED}")
    return stops


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def cmd_run(_: argparse.Namespace) -> int:
    require_clean(git_dirty())
    done = [p.name for p in (OUT / "analysis.json", OUT / "scored.jsonl") if p.exists()]
    if done:
        raise SystemExit(f"{done} exist: the lot is judged once")
    commit = head()
    stops = load_stops()
    _log(f"{len(stops)} stops loaded")
    plans = {
        "target": target.primary_plan(stops),
        "strict": target.strict_plan(stops),
        "agent": target.agent_plan(stops),
    }
    p = {}
    for arm, plan in plans.items():
        p[arm] = target.cross_fit(stops, plan)
        _log(f"{arm}: {len(plan)} fits, {sum(x is not None for x in p[arm])} scored")
    p["a10"] = model.load(A10_MODEL).probabilities(stops)
    # Jev's recorded scores, joined only now, after every fit.
    jev = target.jev_scores(_jsonl(CD / "done-scored.jsonl"), _jsonl(W17 / "done-scored.jsonl"))
    fold = target.cluster_folds(stops)
    rows = []
    for i, e in enumerate(stops):
        label, p_jev = jev[e.id]
        if label != ("done" if e.done else "not_done"):
            raise SystemExit(f"label differs from the recorded row: {e.id}")
        rows.append({"id": e.id, "cluster": e.cluster, "agent": e.agent, "label": label,
                     "fold": fold[e.cluster], f"p_{target.JEV}": p_jev,
                     **{f"p_{a}": None if p[a][i] is None else round(p[a][i], 6)
                        for a in target.ARMS}})  # fmt: skip
    _log("bootstraps...")
    report = {
        "commit": commit,
        "plan_sha256": hashlib.sha256(PLAN.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
        "a10_model_sha256": model.file_sha256(A10_MODEL),
        "config": target.CONFIG.name,
        "fits": {arm: len(plan) for arm, plan in plans.items()},
        "fold_sizes": {str(f): sum(r["fold"] == f for r in rows) for f in range(target.FOLDS)},
        **target.analyse(rows),
    }
    keep = ("id", "cluster", "agent", "label", "fold", "p_target", "p_strict", "p_agent", "p_a10")
    (OUT / "scored.jsonl").write_text(
        "".join(json.dumps({k: r[k] for k in keep}) + "\n" for r in rows),
        encoding="utf-8",
        newline="\n",
    )
    (OUT / "analysis.json").write_text(
        json.dumps(report, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps({k: report[k] for k in ("n", "auc", "verdict")}, indent=1))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run").set_defaults(fn=cmd_run)
    args = parser.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
