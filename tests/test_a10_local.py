"""Lot A10 (docs/results/2026-10-16-a10-local/): the local check_done classifier's free parts.

No network, no model call, and nothing here scores the test set. Pins that the classifier reads
only check_done's `task` and `record` strings (no Jev probability can reach a feature), that the
record is the one check_done's builder makes (tool results cut at 1,500 characters), that the
eval refuses to score without a matching seal, and that training is deterministic.
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
A10 = ROOT / "benchmarks" / "a10_local"
sys.path.insert(0, str(A10))

import a10_analysis as analysis  # noqa: E402
import a10_data as data  # noqa: E402
import a10_features as features  # noqa: E402
import a10_logreg as logreg  # noqa: E402
import a10_model as model  # noqa: E402

TRAIN_RUNS = ROOT / "docs" / "results" / "2026-09-24-agentdojo-e2e" / "runs"


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, A10 / file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


a10_eval = _load("a10_eval", "eval.py")
a10_train = _load("a10_train", "train.py")

RECORD = "\n".join(
    [
        "AGENT: I'll look up the channels first.",
        "AGENT ACTION: get_channels({})",
        "TOOL RESULT: - general",
        "- random",
        "TOOL RESULT: ERROR: not found",
        "AGENT: Which channel do you mean?",
    ]
)


def _example(i: int, done: bool, cluster: str = "slack/user_task_0") -> data.Example:
    word = "sent message invited" if done else "error failed could not"
    record = f"AGENT ACTION: send({i})\nTOOL RESULT: ok {i}\nAGENT: I {word} item {i % 3}."
    return data.Example(f"run/{i}", cluster, "pipe", done, f"please do task {i % 4}", record)


def _synthetic(n: int = 40) -> list[data.Example]:
    return [_example(i, i % 2 == 0, f"slack/user_task_{i % 8}") for i in range(n)]


# --- the record and the features -------------------------------------------------------------


def test_steps_and_structure_read_the_record_lines():
    steps = features.steps_of(RECORD)
    assert [k for k, _ in steps] == ["agent", "action", "tool", "tool", "agent"]
    assert steps[2][1] == "- general\n- random"
    shape = set(features.structure(RECORD))
    assert {"actions=1", "results=2", "errors=1", "last=agent", "last_asks=True"} <= shape
    assert features.last_agent_text(RECORD) == "Which channel do you mean?"


def test_tokens_come_only_from_task_and_record():
    state = {"task": "invite Dora", "record": RECORD}
    leaky = {**state, "p_14": 0.03, "p_13r": 0.9, "probability": 0.1, "label": "done"}
    assert data.text_of(leaky) == data.text_of(state) == ("invite Dora", RECORD)
    fields = set(data.Example.__dataclass_fields__)
    assert fields == {"id", "cluster", "agent", "done", "task", "record"}
    a = features.tokens("invite Dora", RECORD, features.FAMILIES, 2)
    assert {t.split(":", 1)[0] for t in a} == set(features.FAMILIES)
    # Same text, different id, label and agent: the same tokens.
    one = data.Example("a", "x/1", "p", True, "invite Dora", RECORD)
    two = data.Example("b", "y/2", "q", False, "invite Dora", RECORD)
    config = model.Config(features.FAMILIES, 2, 1.0)
    assert model.counts_of([one], config) == model.counts_of([two], config)


def test_unknown_family_is_refused():
    with pytest.raises(ValueError):
        features.tokens("t", "r", ("w", "jev"), 1)


def test_vectors_have_unit_norm_and_sorted_columns():
    docs = [features.tokens(e.task, e.record, ("w", "l", "s"), 2) for e in _synthetic(10)]
    vec = features.Vectorizer.fit(docs, min_df=2)
    assert list(vec.terms) == sorted(vec.terms)
    for idx, val in vec.transform_all(docs):
        assert list(idx) == sorted(idx)
        assert math.isclose(sum(v * v for v in val), 1.0, rel_tol=1e-9)


def test_record_is_check_dones_with_tool_results_cut_at_1500(tmp_path):
    runner = data.completion_runner()
    long = "x" * 3_000
    messages = [
        {"role": "user", "content": [{"type": "text", "content": "list my files"}]},
        {"role": "assistant", "content": [], "tool_calls": [{"function": "ls", "args": {}}]},
        {"role": "tool", "content": [{"type": "text", "content": long}]},
        {"role": "assistant", "content": [{"type": "text", "content": "Done."}]},
    ]
    task, record = runner.render(messages)
    assert task == "list my files"
    assert "x" * 1_500 in record and "x" * 1_501 not in record
    assert record.endswith("AGENT: Done.")


def test_train_cluster_reads_the_task_directory():
    path = ("docs/results/2026-09-24-agentdojo-e2e/runs/claude-sonnet-5-none/slack/user_task_3/"
            "none/none.json")  # fmt: skip
    assert data.train_cluster(path) == "slack/user_task_3"


@pytest.mark.skipif(not TRAIN_RUNS.exists(), reason="the 2026-09-24 runs are untracked")
def test_the_training_set_is_the_registered_393_and_jev_never_touched_it():
    train = data.load_train()
    assert len(train) == 393 and sum(e.done for e in train) == 286
    assert {e.agent for e in train} == {
        "claude-sonnet-5-none",
        "claude-sonnet-5-spotlighting",
        "claude-haiku-4-5-none",
    }
    assert not any("squire" in e.agent for e in train)
    for e in train:
        assert "prompt injection was detected" not in e.task + e.record
        assert "SECURITY NOTE from the harness" not in e.task + e.record
    assert {e.cluster.split("/")[0] for e in train} == {"slack"}
    assert len({e.cluster for e in train}) == 26
    assert all(e.task and e.record for e in train)


class _FakeRunner:
    ROOT = Path("nowhere")

    def __init__(self, cases):
        self.cases = cases

    def load(self):
        return self.cases


def _case(i: int, pipeline: str, label: str, record: str = "AGENT: done") -> dict:
    path = f"docs/results/x/runs/{pipeline}/slack/user_task_{i}/none/none.json"
    return {"id": path, "pipeline": pipeline, "label": label,
            "state": {"task": f"task {i}", "record": record}}  # fmt: skip


def test_the_loader_drops_jevs_pipelines_and_refuses_jevs_marks(monkeypatch):
    monkeypatch.setattr(data, "EXPECTED_TRAIN", 2)
    monkeypatch.setattr(data, "EXPECTED_TRAIN_DONE", 1)
    clean = [_case(0, "s5-none", "done"), _case(1, "s5-spotlighting", "not_done")]
    jev = [_case(2, "s5-squire", "not_done"), _case(3, "s5-squire-mark", "done")]
    monkeypatch.setattr(data, "completion_runner", lambda: _FakeRunner(clean + jev))
    assert [e.agent for e in data.load_train()] == ["s5-none", "s5-spotlighting"]
    marked = _case(1, "s5-none", "not_done", "TOOL RESULT: <Data omitted because a prompt "
                                             "injection was detected>")  # fmt: skip
    monkeypatch.setattr(data, "completion_runner", lambda: _FakeRunner([clean[0], marked]))
    with pytest.raises(SystemExit, match="Jev's marks"):
        data.load_train()


def test_the_loader_refuses_a_set_that_is_not_the_registered_one(tmp_path):
    with pytest.raises(SystemExit):
        data.load_train(tmp_path)  # no runs there: 0 stops


def test_overlap_counts_shared_names_but_not_shared_tasks():
    train = [data.Example("a", "slack/user_task_1", "s5", True, "t1", "r1")]
    test = [data.Example("b", "banking/user_task_1", "c37", True, "t2", "r2")]
    found = data.overlap(train, test)
    assert found["shared_clusters"] == [] and found["shared_task_dir_names"] == 1
    assert found["shared_task_texts"] == 0 and found["shared_records"] == 0


# --- the model -------------------------------------------------------------------------------


def test_logreg_gradient_matches_finite_differences():
    rows = [((0, 2), (0.6, 0.8)), ((1,), (1.0,)), ((0, 1), (0.8, 0.6))]
    y = [1, -1, 1]
    theta = [0.3, -0.2, 0.1, 0.05]
    _, grad = logreg.loss_grad(rows, y, theta, 2.0)
    for k in range(len(theta)):
        up, down = list(theta), list(theta)
        up[k] += 1e-6
        down[k] -= 1e-6
        numeric = logreg.loss_grad(rows, y, up, 2.0)[0] - logreg.loss_grad(rows, y, down, 2.0)[0]
        assert math.isclose(grad[k], numeric / 2e-6, rel_tol=1e-4, abs_tol=1e-6)


def test_logreg_separates_separable_data():
    examples = _synthetic(40)
    config = model.Config(("w",), 1, 10.0)
    vec, w, b, info = model.fit(examples, config)
    rows = vec.transform_all(model.counts_of(examples, config))
    p = logreg.predict(rows, w, b)
    assert all((x >= 0.5) == e.done for x, e in zip(p, examples, strict=True))
    assert info["iterations"] < logreg.MAX_ITER


def _fitted(examples: list[data.Example]) -> model.Model:
    config = model.Config(("w", "l", "s"), 2, 1.0)
    vec, w, b, _ = model.fit(examples, config)
    return model.Model(config, vec, tuple(w), b, 0.4, {"lot": "test"})


def test_training_is_deterministic(tmp_path, monkeypatch):
    examples = _synthetic(40)
    first, second = _fitted(examples), _fitted(examples)
    assert model.to_json(first) == model.to_json(second)
    a = model.save(first, tmp_path / "a" / "model.json")
    b = model.save(second, tmp_path / "b" / "model.json")
    assert a.read_bytes() == b.read_bytes()
    monkeypatch.setattr(model, "GZIP_ABOVE", 10)
    ga = model.save(first, tmp_path / "a" / "model.json")
    gb = model.save(second, tmp_path / "b" / "model.json")
    assert ga.suffix == ".gz" and ga.read_bytes() == gb.read_bytes()
    assert not (tmp_path / "a" / "model.json").exists()


def test_a_saved_model_scores_as_it_was_fitted(tmp_path):
    examples = _synthetic(40)
    fitted = _fitted(examples)
    back = model.load(model.save(fitted, tmp_path / "model.json"))
    assert back.config == fitted.config and back.cut == fitted.cut
    for x, y in zip(back.probabilities(examples), fitted.probabilities(examples), strict=True):
        assert math.isclose(x, y, abs_tol=1e-4)


# --- CV, the cut and the verdict rule --------------------------------------------------------


def test_folds_keep_each_cluster_whole_and_are_deterministic():
    examples = _synthetic(40) + [_example(99, True, "slack/injection_task_1")]
    fold_of = a10_train.folds(examples)
    assert fold_of == a10_train.folds(examples)
    seen: dict[str, int] = {}
    for e, f in zip(examples, fold_of, strict=True):
        assert seen.setdefault(e.cluster, f) == f
    assert len(set(fold_of)) == a10_train.FOLDS


def test_cut_rule_takes_the_most_recall_that_keeps_block_precision():
    # 100 unfinished + 1 finished at p 0.1 (block precision 100/101, Wilson lower 0.946);
    # 100 finished + 20 unfinished at p 0.9 (blocking them too drops precision to 120/221).
    p = [0.1] * 101 + [0.9] * 120
    done = [False] * 100 + [True] + [True] * 100 + [False] * 20
    assert a10_train.derive_cut(p, done) == 0.11  # the lowest cut that blocks p = 0.1
    # 60/63 has a Wilson lower bound of 0.87: no cut clears 0.90.
    assert a10_train.derive_cut([0.1] * 63, [False] * 60 + [True] * 3) is None


def test_the_cut_ladder_goes_090_then_080_then_max_accuracy():
    assert a10_train.PRECISION_TARGETS == (0.90, 0.80)
    # 0.90 reachable: 100/101 blocked right.
    p = [0.1] * 101 + [0.9] * 120
    done = [False] * 100 + [True] + [True] * 100 + [False] * 20
    assert a10_train.cut_by_ladder(p, done) == (0.11, "D at 0.9")
    # Only 0.80: 60/63 (Wilson lower 0.87); blocking the 0.9s too drops it to 60/113.
    p = [0.1] * 63 + [0.9] * 50
    done = [False] * 60 + [True] * 3 + [True] * 50
    assert a10_train.cut_by_ladder(p, done) == (0.11, "D at 0.8")
    # Neither: 6/10 at 0.1. Every cut from 0.11 to 0.90 is right on 36 of 42; the lowest wins.
    p = [0.1] * 10 + [0.9] * 32
    done = [False] * 6 + [True] * 4 + [True] * 30 + [False] * 2
    assert a10_train.max_accuracy_cut(p, done) == 0.11
    assert a10_train.accuracy_at(p, done, 0.11) == 36 / 42
    assert a10_train.cut_by_ladder(p, done) == (0.11, "max out-of-fold accuracy")


@pytest.mark.parametrize(
    ("ci", "expected"),
    [
        ((0.001, 0.03), "mejor"),
        ((-0.049, 0.02), "no peor"),
        ((-0.049, -0.01), "no peor"),
        ((-0.08, -0.01), "no concluyente"),  # below 0, not wholly below the margin
        ((-0.09, -0.051), "peor"),  # wholly below -5 points
        ((-0.09, -0.05), "no concluyente"),
        ((-0.06, 0.01), "no concluyente"),
        (None, "no medido"),
    ],
)
def test_verdict_rule(ci, expected):
    assert analysis.verdict({"diff": 0.0, "ci95_cluster": ci}) == expected


def test_verdict_reads_the_unrounded_bounds():
    rounded = {"diff": 0.0, "ci95_cluster": (-0.05, 0.01)}
    assert analysis.verdict(rounded) == "no concluyente"
    assert analysis.verdict({**rounded, "ci95_cluster_raw": (-0.04999, 0.01)}) == "no peor"


def test_the_primary_is_the_auc_difference_with_its_margin():
    assert analysis.AUC_MARGIN == -0.05
    # Local ranks every finished stop above every unfinished one; Jev 1.14 ranks at random.
    rows = [{"id": str(i), "cluster": f"c{i % 6}", "label": "done" if i % 2 else "not_done",
             "p_local": 0.9 if i % 2 else 0.1, "p_14": (i * 37 % 100) / 100}
            for i in range(60)]  # fmt: skip
    found = analysis.paired_auc(rows, "local", "14")
    assert found["new"] == 1.0 and found["diff"] > 0
    assert found["ci95_cluster_raw"][0] > 0 and found["verdict"] == "mejor"
    swapped = analysis.paired_auc(rows, "14", "local")
    assert swapped["verdict"] == "peor"


def test_paired_gives_l4_stats_intervals():
    import l4_stats

    rows = [{"cluster": f"c{i % 7}", "a": i % 3 != 0, "b": i % 4 != 0} for i in range(60)]
    mine = analysis.paired(rows, lambda r: r["a"], lambda r: r["b"])
    theirs = l4_stats.paired_binary([r["a"] for r in rows], [r["b"] for r in rows],
                                    [r["cluster"] for r in rows])  # fmt: skip
    for key in ("diff", "only_new", "only_old", "p", "ci95", "ci95_cluster"):
        assert mine[key] == theirs[key]


def test_jev_cuts_are_the_ones_checkdone114_scored():
    from sanchopanza.policy import Thresholds

    for arm, name in analysis.MODELS.items():
        assert analysis.JEV_CUTS[arm] == Thresholds.for_model(name).done
    assert analysis.JEV_CUTS == {"14": 0.30, "13r": 0.5}


def test_analysis_on_synthetic_rows_has_every_registered_block():
    rows = [{"id": str(i), "cluster": f"bank/u{i % 5}", "label": "done" if i % 3 else "not_done",
             "p_local": (i % 10) / 10, "p_14": ((i * 7) % 10) / 10, "p_13r": 0.6}
            for i in range(30)]  # fmt: skip
    found = analysis.analyse(rows, 0.35)
    assert found["cuts"] == {"local": 0.35, "14": 0.30, "13r": 0.5}
    assert set(found["arms"]) == {"local", "14", "13r", "never"}
    never = found["arms"]["never"]
    assert never["blocks"] == 0 and never["auc"] == 0.5
    assert never["accuracy"]["k"] == sum(r["label"] == "done" for r in rows)
    for block in ("accuracy", "not_falsely_blocked", "caught", "auc"):
        assert block in found["primary_vs_14"] and block in found["secondary_vs_13r"]
    # The primary is the AUC difference; accuracy's reading is descriptive.
    assert found["verdict"] == found["primary_vs_14"]["auc"]["verdict"]
    assert "verdict" not in found["primary_vs_14"]["accuracy"]
    assert found["primary_vs_14"]["auc"]["replicas"] == 10_000
    with pytest.raises(SystemExit):
        analysis.analyse([{**rows[0], "p_14": None}], 0.35)


# --- the seal --------------------------------------------------------------------------------


def _sealed_tree(root: Path) -> Path:
    for rel in a10_eval.SEALED:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(f"content of {rel}\n".encode())
    path = root / "fixtures" / "a10_local" / "model.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    return path


def test_the_gate_refuses_without_a_seal(tmp_path):
    model_path = _sealed_tree(tmp_path)
    with pytest.raises(SystemExit, match="not sealed"):
        a10_eval.require_seal(tmp_path, tmp_path / "prereg.sha256", model_path)


def test_the_gate_refuses_when_a_sealed_file_or_the_model_changed(tmp_path):
    model_path = _sealed_tree(tmp_path)
    seal = tmp_path / "prereg.sha256"
    seal.write_text(a10_eval.digest(tmp_path, model_path) + "\n", encoding="utf-8")
    assert a10_eval.require_seal(tmp_path, seal, model_path) == seal.read_text().strip()
    # CRLF checkouts hash as LF.
    first = tmp_path / a10_eval.SEALED[0]
    first.write_bytes(first.read_bytes().replace(b"\n", b"\r\n"))
    assert a10_eval.require_seal(tmp_path, seal, model_path)
    first.write_bytes(b"changed\n")
    with pytest.raises(SystemExit, match="does not match"):
        a10_eval.require_seal(tmp_path, seal, model_path)
    first.write_bytes(f"content of {a10_eval.SEALED[0]}\n".encode())
    model_path.write_text('{"weights": []}', encoding="utf-8")
    with pytest.raises(SystemExit, match="does not match"):
        a10_eval.require_seal(tmp_path, seal, model_path)


def test_run_reads_no_test_stop_before_the_seal(tmp_path, monkeypatch):
    def forbidden(*_a, **_k):
        raise AssertionError("a test stop was read before the seal was checked")

    monkeypatch.setattr(a10_eval, "SEAL", tmp_path / "prereg.sha256")
    monkeypatch.setattr(a10_eval.data, "load_test", forbidden)
    monkeypatch.setattr(a10_eval.model, "load", forbidden)
    with pytest.raises(SystemExit, match="not sealed"):
        a10_eval.cmd_run(type("Args", (), {"data_root": None})())


def test_seal_refuses_to_overwrite(tmp_path, monkeypatch):
    seal = tmp_path / "prereg.sha256"
    seal.write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(a10_eval, "SEAL", seal)
    with pytest.raises(SystemExit, match="sealed once"):
        a10_eval.cmd_seal(None)


def test_seal_refuses_while_a_sealed_file_is_not_committed(tmp_path, monkeypatch):
    monkeypatch.setattr(a10_eval, "SEAL", tmp_path / "prereg.sha256")
    monkeypatch.setattr(a10_eval, "uncommitted", lambda: ["?? fixtures/a10_local/model.json"])
    with pytest.raises(SystemExit, match="commit the sealed files first"):
        a10_eval.cmd_seal(None)
    assert not (tmp_path / "prereg.sha256").exists()


def test_run_is_judged_once(tmp_path, monkeypatch):
    def forbidden(*_a, **_k):
        raise AssertionError("a test stop was read")

    (tmp_path / "analysis.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(a10_eval, "OUT", tmp_path)
    monkeypatch.setattr(a10_eval, "require_seal", lambda: "sealed")
    monkeypatch.setattr(a10_eval.data, "load_test", forbidden)
    monkeypatch.setattr(a10_eval.model, "load", forbidden)
    with pytest.raises(SystemExit, match="judged once"):
        a10_eval.cmd_run(type("Args", (), {"data_root": None})())


# --- the shipped model, when it exists ------------------------------------------------------


@pytest.mark.skipif(not (a10_train.CV_FILE.exists() and (
    a10_train.MODEL.exists() or a10_train.MODEL.with_name("model.json.gz").exists())),
    reason="model not fitted")  # fmt: skip
def test_the_shipped_model_is_the_cv_choice():
    report = json.loads(a10_train.CV_FILE.read_text(encoding="utf-8"))
    fitted = model.load(a10_train.MODEL)
    assert fitted.config.name == report["chosen"]["name"]
    assert fitted.cut == report["cut"]
    assert fitted.meta["train_digest"] == report["train_digest"]
    assert len(fitted.weights) == len(fitted.vectorizer.terms) == fitted.meta["terms"]
    assert {t.split(":", 1)[0] for t in fitted.vectorizer.terms} <= set(features.FAMILIES)
