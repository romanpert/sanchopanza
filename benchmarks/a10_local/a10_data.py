"""The data of lot A10: check_done's state for each AgentDojo stop, and the benchmark's label.

TRAIN: 393 of the 655 slack trajectories of docs/results/2026-09-25-completion/ (this
repository's own AgentDojo v1.2.2 runs of 2026-09-24), loaded by `benchmarks/completion/run.py`'s
own `load()`: Sonnet 5 undefended, Sonnet 5 with spotlighting, and Haiku 4.5 undefended. The two
`squire` pipelines are excluded: in them Jev was the injection detector, and when it flagged a
tool result the harness replaced it ("<Data omitted because a prompt injection was detected>")
or appended a "SECURITY NOTE from the harness". Their records and their labels are effects of
Jev's decisions, and TypeSafe's MCA 2.3(b) forbids training on Jev's outputs. The runs live in
the untracked `runs/` trees of docs/results/2026-09-24-agentdojo-{e2e,haiku}/; `runs_root`
points at a checkout holding them.

TEST: the 950 stops of docs/results/2026-10-16-checkdone114/ (AgentDojo's published runs of
claude-3-7-sonnet-20250219 in banking, travel and workspace), loaded by that lot's `load()`,
which checks every file's git blob sha against its `inputs.jsonl`.

Both go through the same record builder as Jev did (`completion/run.py`'s `render`, tool results
cut at 1,500 characters, then `points.completion.questions`), so the classifier reads the very
`task` and `record` strings Jev read. The label is AgentDojo's `utility`. An `Example` carries
nothing else: no model's probability or answer can reach a feature through it.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for extra in (ROOT / "src", ROOT / "benchmarks", ROOT / "benchmarks" / "jev114"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

EXPECTED_TRAIN = 393
EXPECTED_TRAIN_DONE = 286
# Pipelines whose tool results went through Jev (benchmarks/agentdojo/run.py, defense.py).
JEV_PIPELINE_MARK = "squire"
# What Jev's detector wrote into a record; no training record may hold either.
JEV_MARKERS = ("prompt injection was detected", "SECURITY NOTE from the harness")


@dataclass(frozen=True)
class Example:
    id: str
    cluster: str  # suite/task directory: the resampling and fold unit
    agent: str  # the pipeline or model that produced the trajectory
    done: bool  # AgentDojo's `utility`
    task: str  # check_done's state["task"]
    record: str  # check_done's state["record"]


def _by_path(name: str, path: Path) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def completion_runner() -> ModuleType:
    """benchmarks/completion/run.py (several benches ship a `run.py`: loaded by path)."""
    return _by_path("completion_run", ROOT / "benchmarks" / "completion" / "run.py")


def checkdone_runner() -> ModuleType:
    return _by_path("checkdone114", ROOT / "benchmarks" / "jev114" / "checkdone114.py")


def text_of(state: Mapping[str, Any]) -> tuple[str, str]:
    """The only two fields of check_done's state the classifier reads."""
    return str(state["task"]), str(state["record"])


def train_cluster(case_id: str) -> str:
    """`.../runs/<pipeline>/slack/<task dir>/<attack>/<file>.json` -> `slack/<task dir>`."""
    parts = case_id.split("/")
    at = parts.index("runs")
    return f"{parts[at + 2]}/{parts[at + 3]}"


def load_train(runs_root: Path | None = None) -> list[Example]:
    runner = completion_runner()
    where = runner.ROOT if runs_root is None else Path(runs_root)
    saved, runner.ROOT = runner.ROOT, where
    try:
        cases = runner.load()
    finally:
        runner.ROOT = saved
    out = []
    for case in cases:
        if JEV_PIPELINE_MARK in case["pipeline"]:
            continue  # its records and labels are effects of Jev's decisions: MCA 2.3(b)
        task, record = text_of(case["state"])
        out.append(Example(case["id"], train_cluster(case["id"]), case["pipeline"],
                           case["label"] == "done", task, record))  # fmt: skip
    done = sum(e.done for e in out)
    if len(out) != EXPECTED_TRAIN or done != EXPECTED_TRAIN_DONE:
        raise SystemExit(
            f"train: {len(out)} stops ({done} done), registered {EXPECTED_TRAIN} "
            f"({EXPECTED_TRAIN_DONE} done): are the 2026-09-24 runs under {where}?"
        )
    touched = [e.id for e in out if any(m in e.task + e.record for m in JEV_MARKERS)]
    if touched:
        raise SystemExit(f"{len(touched)} training records carry Jev's marks, first {touched[0]}")
    return out


def load_test(data_root: Path | None = None) -> tuple[list[Example], str]:
    """The 950 stops and their inputs digest (`checkdone114.inputs_digest`, sealed in that
    lot's data.sha256). Loading is not scoring: eval.py scores only behind the A10 seal."""
    runner = checkdone_runner()
    cases = runner.load(runner.DATA_ROOT if data_root is None else Path(data_root))
    out = []
    for case in cases:
        task, record = text_of(case["state"])
        out.append(Example(case["id"], case["cluster"], runner.PIPELINE,
                           case["label"] == "done", task, record))  # fmt: skip
    return out, runner.inputs_digest(cases)


def digest(examples: Sequence[Example]) -> str:
    """One sha256 over every stop's id, label and the two strings, in order."""
    h = hashlib.sha256()
    for e in examples:
        h.update(f"{e.id}|{e.done}|".encode())
        h.update(hashlib.sha256(e.task.encode("utf-8")).digest())
        h.update(hashlib.sha256(e.record.encode("utf-8")).digest())
    return h.hexdigest()


def overlap(train: Sequence[Example], test: Sequence[Example]) -> dict[str, Any]:
    """What the two sets share: clusters (suite/task), bare task directory names (the same
    name in another suite is another task), request texts, records, and agents."""

    def bare(e: Example) -> str:
        return e.cluster.split("/", 1)[1]

    shared_bare = sorted({bare(e) for e in train} & {bare(e) for e in test})
    return {
        "train": len(train),
        "test": len(test),
        "train_suites": dict(Counter(e.cluster.split("/")[0] for e in train)),
        "test_suites": dict(Counter(e.cluster.split("/")[0] for e in test)),
        "train_agents": sorted({e.agent for e in train}),
        "test_agents": sorted({e.agent for e in test}),
        "shared_clusters": sorted({e.cluster for e in train} & {e.cluster for e in test}),
        "shared_task_dir_names": len(shared_bare),
        "shared_task_texts": len({e.task for e in train} & {e.task for e in test}),
        "shared_records": len({e.record for e in train} & {e.record for e in test}),
        "shared_ids": len({e.id for e in train} & {e.id for e in test}),
    }
