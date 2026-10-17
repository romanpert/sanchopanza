"""A10 with labels from the target environment (docs/results/2026-10-17-a10-target/plan.md).

Free, no network, no model call. Pins the splits (no scored stop shares a user task, or in the
strict split an injection task, with any stop its model was fitted on), that fitting reads only
`a10_data.Example` (no Jev probability can reach it), how Jev's recorded scores are joined for
the comparison, and the analysis' shape and refusals.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
A10 = ROOT / "benchmarks" / "a10_local"
sys.path.insert(0, str(A10))

import a10_data as data  # noqa: E402
import a10_model as model  # noqa: E402
import a10_target as target  # noqa: E402


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, A10 / file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


a10_train = _load("a10_train_t", "train.py")
target_cli = _load("a10_target_cli", "target.py")

PIPES = ("agent-a", "agent-b")


def _stop(pipe: str, suite: str, task_dir: str, attack: str, file: str, done: bool) -> data.Example:
    sid = f"runs/{pipe}/{suite}/{task_dir}/{attack}/{file}"
    word = "sent paid booked" if done else "error failed could not"
    record = f"AGENT ACTION: act({task_dir})\nTOOL RESULT: ok {file}\nAGENT: I {word}."
    return data.Example(sid, f"{suite}/{task_dir}", pipe, done, f"please {task_dir}", record)


def _world() -> list[data.Example]:
    """Two agents, two suites; per suite 6 user tasks x (benign + 5 injections) and 5
    injection tasks run as user tasks."""
    out = []
    for pipe in PIPES:
        for suite in ("banking", "travel"):
            for u in range(6):
                td = f"user_task_{u}"
                out.append(_stop(pipe, suite, td, "none", "none.json", True))
                for i in range(5):
                    done = (u + i) % 3 != 0
                    out.append(_stop(pipe, suite, td, "important_instructions",
                                     f"injection_task_{i}.json", done))  # fmt: skip
            for i in range(5):
                out.append(
                    _stop(pipe, suite, f"injection_task_{i}", "none", "none.json", i % 2 == 0)
                )
    return out


# --- groups ----------------------------------------------------------------------------------


def test_injection_group_reads_the_path():
    attacked = "runs/p/banking/user_task_3/important_instructions/injection_task_2.json"
    as_user = "runs/p/banking/injection_task_2/none/none.json"
    benign = "runs/p/banking/user_task_3/none/none.json"
    assert target.injection_group(attacked) == "banking/injection_task_2"
    assert target.injection_group(as_user) == "banking/injection_task_2"
    assert target.injection_group(benign) is None
    assert target.agent_of(attacked) == "p"


def test_greedy_folds_is_a10s_rule_on_one_suite():
    examples = [e for e in _world() if e.cluster.startswith("banking/")]
    sizes: dict[str, int] = {}
    for e in examples:
        sizes[e.cluster] = sizes.get(e.cluster, 0) + 1
    mine = target.greedy_folds(sizes, 5)
    theirs = a10_train.folds(examples, 5)
    assert [mine[e.cluster] for e in examples] == theirs


def test_stratified_folds_spread_every_suite_and_keep_clusters_whole():
    examples = _world()
    fold = target.cluster_folds(examples, 3)
    for suite in ("banking", "travel"):
        used = {f for c, f in fold.items() if c.startswith(suite + "/")}
        assert used == {0, 1, 2}
    assert set(fold) == {e.cluster for e in examples}


# --- the plans ---------------------------------------------------------------------------------


def _check_plan(examples, plan):
    for fit, score in plan:
        assert not set(fit) & set(score)
        fit_clusters = {examples[i].cluster for i in fit}
        assert not fit_clusters & {examples[i].cluster for i in score}


def test_primary_scores_every_stop_once_never_by_a_model_that_saw_its_user_task():
    examples = _world()
    plan = target.primary_plan(examples, 3)
    _check_plan(examples, plan)
    scored = sorted(i for _, score in plan for i in score)
    assert scored == list(range(len(examples)))


def test_strict_shares_neither_user_task_nor_injection_task():
    examples = _world()
    plan = target.strict_plan(examples, 3)
    _check_plan(examples, plan)
    for fit, score in plan:
        fit_inj = {target.injection_group(examples[i].id) for i in fit} - {None}
        score_inj = {target.injection_group(examples[i].id) for i in score} - {None}
        assert not fit_inj & score_inj
    scored = [i for _, score in plan for i in score]
    assert len(scored) == len(set(scored))
    benign = [i for i, e in enumerate(examples) if target.injection_group(e.id) is None]
    assert set(benign) <= set(scored)
    as_user = [i for i, e in enumerate(examples) if e.cluster.split("/")[1].startswith("inj")]
    assert set(as_user) <= set(scored)
    attacked = [i for i, e in enumerate(examples) if e.id.endswith(".json")
                and "injection_task_" in e.id.rsplit("/", 1)[1]]  # fmt: skip
    assert 0 < len(set(attacked) & set(scored)) < len(attacked)


def test_agent_plan_fits_on_the_scored_agent_only():
    examples = _world()
    plan = target.agent_plan(examples, 3)
    _check_plan(examples, plan)
    for fit, score in plan:
        agents = {examples[i].agent for i in fit} | {examples[i].agent for i in score}
        assert len(agents) == 1
    scored = sorted(i for _, score in plan for i in score)
    assert scored == list(range(len(examples)))


# --- fitting ----------------------------------------------------------------------------------


def test_cross_fit_learns_only_from_the_fitting_stops(monkeypatch):
    examples = _world()
    plan = target.primary_plan(examples, 3)
    seen: list[set[str]] = []
    real = model.fit

    def spy(fit_examples, config, counts=None):
        assert all(isinstance(e, data.Example) for e in fit_examples)
        seen.append({e.id for e in fit_examples})
        return real(fit_examples, config, counts)

    monkeypatch.setattr(target.model, "fit", spy)
    p = target.cross_fit(examples, plan, target.CONFIG)
    assert len(seen) == len(plan)
    for (_, score), ids in zip(plan, seen, strict=True):
        assert not ids & {examples[i].id for i in score}
    assert all(p_i is not None and 0 < p_i < 1 for p_i in p)
    assert target.cross_fit(examples, plan, target.CONFIG) == p  # deterministic


def test_cross_fit_leaves_unscored_stops_empty():
    examples = _world()
    plan = target.strict_plan(examples, 3)
    p = target.cross_fit(examples, plan, target.CONFIG)
    scored = {i for _, score in plan for i in score}
    assert all((p[i] is None) == (i not in scored) for i in range(len(examples)))


def test_config_is_a10s_chosen_one():
    assert model.Config(("w", "c", "l", "s"), 2, 1.0, 2) == target.CONFIG


# --- Jev's scores: comparison only -------------------------------------------------------------


def test_jev_scores_join_both_lots_and_refuse_a_label_mismatch():
    cd = [{"id": "a", "label": "done", "p_14": 0.9, "p_13r": 0.8}]
    w17 = [
        {"set": "confirm", "id": "b", "label": "not_done", "p_old": 0.1, "p_new": 0.2},
        {"set": "dev", "id": "a", "label": "done", "p_old": 0.5, "p_new": 0.5},
    ]
    assert target.jev_scores(cd, w17) == {"a": ("done", 0.9), "b": ("not_done", 0.1)}
    with pytest.raises(SystemExit):
        target.jev_scores(cd, [{**w17[0], "id": "a"}])


# --- the analysis ------------------------------------------------------------------------------


def _rows(n: int = 60) -> list[dict]:
    rows = []
    for i in range(n):
        done = i % 3 != 0
        rows.append({
            "id": f"s{i}", "cluster": f"{'banking' if i % 2 else 'travel'}/user_task_{i % 12}",
            "agent": PIPES[i % 2], "label": "done" if done else "not_done", "fold": i % 3,
            "p_14": (0.7 if done else 0.4) + (i % 5) / 50,
            "p_target": (0.8 if done else 0.3) + (i % 7) / 50,
            "p_strict": None if i % 4 == 0 else 0.6 + (i % 5) / 20,
            "p_agent": 0.5 + (i % 9) / 30, "p_a10": 0.5 + (i % 4) / 10,
        })  # fmt: skip
    return rows


def test_analyse_reports_every_registered_comparison(monkeypatch):
    monkeypatch.setattr(target.l4_stats, "BOOT", 50)
    report = target.analyse(_rows())
    assert report["n"] == 60
    assert report["primary"]["verdict"] in {"mejor", "no peor", "peor", "no concluyente"}
    assert report["verdict"] == report["primary"]["verdict"]
    assert report["strict"]["n"] == 45
    assert set(report["by_suite"]) == {"banking", "travel"}
    assert set(report["by_agent"]) == set(PIPES)
    assert set(report["by_agent"][PIPES[0]]) == {"target", "agent"}
    for key in ("agent", "a10_vs_jev", "target_vs_a10", "per_fold"):
        assert key in report
    assert set(report["per_fold"]["folds"]) == {"0", "1", "2"}


def test_analyse_refuses_a_missing_jev_score():
    rows = _rows()
    rows[3]["p_14"] = None
    with pytest.raises(SystemExit):
        target.analyse(rows)


# --- the run's guard ---------------------------------------------------------------------------


def test_run_refuses_unless_plan_and_code_are_committed():
    assert "docs/results/2026-10-17-a10-target/plan.md" in target_cli.PLANNED
    assert "benchmarks/a10_local/a10_target.py" in target_cli.PLANNED
    with pytest.raises(SystemExit):
        target_cli.require_clean([" M docs/results/2026-10-17-a10-target/plan.md"])
    target_cli.require_clean([])


def _benchmarks_off_the_path() -> None:
    """As in test_a10_local: benchmarks/ on sys.path breaks the agentdojo skip of later tests."""
    entry = str(ROOT / "benchmarks")
    while entry in sys.path:
        sys.path.remove(entry)


_benchmarks_off_the_path()
