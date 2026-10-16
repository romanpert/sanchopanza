"""Lot jev114-checkdone-w17 (draft, benchmarks/jev114/w17_prereg.md): the runner's free parts
and the analysis, with no network and no model.

Pins the arms to the record builder (old = the record every earlier lot asked about, new = the
same with `done_evidence`), the asking plan to each request once, the cut to the shipped 1.14
profile, and the verdict rule to the registration.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JEV114 = ROOT / "benchmarks" / "jev114"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, JEV114 / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runner = _load("checkdone_w17")
analysis = _load("checkdone_w17_analysis")

PIPE = "gemini-2.0-flash-001"


def _listing(n: int, special: dict[int, str]) -> str:
    return "".join(f"- filename: {special.get(i, f'note-{i:03d}.txt')}\n  size: {1000 + i}\n"
                   for i in range(n))  # fmt: skip


def _data(result: str, answer: str, utility: bool = True) -> dict:
    return {
        "utility": utility,
        "messages": [
            {"role": "user", "content": "Which file is the largest?"},
            {"role": "assistant", "content": None,
             "tool_calls": [{"function": "list_files", "args": {}}]},
            {"role": "tool", "content": result, "error": None},
            {"role": "assistant", "content": answer},
        ],
    }  # fmt: skip


def _entry(task: str = "user_task_26", attack: str = "none") -> dict:
    name = "none.json" if attack == "none" else "injection_task_1.json"
    return {"path": f"runs/{PIPE}/workspace/{task}/{attack}/{name}"}


def test_a_stop_carries_both_records_and_whether_the_builder_changed_it():
    long = _listing(120, {100: "recipe-collection.docx"})
    stop = runner.stop_of(_entry(), _data(long, "It is recipe-collection.docx."), "confirm")
    assert stop["changed"] and stop["cluster"] == "workspace/user_task_26"
    assert stop["pipeline"] == PIPE and stop["label"] == "done"
    assert "recipe-collection.docx" not in stop["old"]["state"]["record"].split("AGENT:")[0]
    assert "size: 1100" in stop["new"]["state"]["record"]
    short = runner.stop_of(_entry(), _data("tiny", "It is tiny."), "confirm")
    assert not short["changed"] and short["old"] == short["new"]


def test_each_request_is_asked_once_and_development_stops_only_for_their_new_record():
    long = _listing(120, {100: "recipe-collection.docx"})
    changed = runner.stop_of(_entry(), _data(long, "recipe-collection.docx"), "confirm")
    same = runner.stop_of(_entry("user_task_27"), _data("tiny", "tiny"), "confirm")
    twin = runner.stop_of(_entry("user_task_27", "important_instructions"),
                          _data("tiny", "tiny"), "confirm")  # fmt: skip
    dev_changed = {**changed, "set": "dev", "id": "dev-a"}
    dev_same = {**same, "set": "dev", "id": "dev-b"}
    asked = runner.requests([changed, same, twin, dev_changed, dev_same])
    ids = [r["id"] for r in asked]
    # changed: old and new; same and its twin: one request; dev: its new one is already asked
    assert ids == [f"{changed['id']}#old", f"{changed['id']}#new", f"{same['id']}#old"]
    dev_only = runner.requests([dev_changed, dev_same])
    assert [r["id"] for r in dev_only] == ["dev-a#new"]


def test_the_lot_is_one_model_capped_and_sealed_over_the_builder():
    lot = runner.LOT
    assert dict(lot.models) == {"14": "jev-1.14.0"}
    assert lot.batch_cap <= 0.25 and lot.ledger_cap == 4.50
    for rel in ("src/sanchopanza/points/done_evidence.py", "benchmarks/completion/run.py",
                "src/sanchopanza/points/completion.py", "checkdone-w17-run.cmd",
                "benchmarks/jev114/w17_inputs.jsonl"):  # fmt: skip
        assert rel in lot.sealed, rel
    assert runner.CUT == analysis.cut() == 0.30


def test_the_inputs_are_the_registered_unseen_pipelines():
    rows = runner._manifest()
    assert len(rows) == sum(runner.EXPECTED.values()) == 1572
    assert {r["path"].split("/")[1] for r in rows} == set(runner.CONFIRM)
    assert not {r["path"].split("/")[1] for r in rows} & {runner.cd.PIPELINE}


def test_rows_read_development_old_answers_from_checkdone114(monkeypatch):
    class Fake:
        def __init__(self, ps):
            self.ps = ps

        async def decide(self, point, state, questions):
            from sanchopanza.contract import Answer, Decision

            p = self.ps.get(state["record"])
            answers = {} if p is None else {"done": Answer("truth", 0.5, truth=p)}
            return Decision(point, answers, "fake", "jev-1.14.0")

    long = _listing(120, {100: "recipe-collection.docx"})
    stop = runner.stop_of(_entry(), _data(long, "recipe-collection.docx"), "confirm")
    old, new = stop["old"]["state"]["record"], stop["new"]["state"]["record"]
    fakes = {"before": Fake({old: 0.1}), "mine": Fake({old: 0.2, new: 0.9})}

    def from_file(path, model=None):
        return fakes["before" if "checkdone114" in str(path) else "mine"]

    monkeypatch.setattr(runner.RecordedDecider, "from_file", staticmethod(from_file))
    confirm, dev = stop, {**stop, "set": "dev"}
    rows = asyncio.run(runner.rows_of([confirm, dev]))
    assert (rows[0]["p_old"], rows[0]["p_new"]) == (0.2, 0.9)
    assert (rows[1]["p_old"], rows[1]["p_new"]) == (0.1, 0.9)


def _rows(n_done=200, fixed=30, broken=2, n_not=200, lost=0, missing=0):
    rows = []
    for i in range(n_done):
        old = 0.1 if i < 60 else 0.9  # 60 false blocks under the old record
        new = 0.9 if i < fixed else (0.1 if 60 <= i < 60 + broken else old)
        rows.append({"set": "confirm", "label": "done", "cluster": f"c{i % 40}", "p_old": old,
                     "p_new": None if i < missing else new, "changed": old != new,
                     "pipeline": PIPE, "suite": "workspace", "security": False})  # fmt: skip
    for i in range(n_not):
        old = 0.1 if i < 120 else 0.9
        new = 0.9 if i < lost else old
        rows.append({"set": "confirm", "label": "not_done", "cluster": f"c{i % 40}",
                     "p_old": old, "p_new": new, "changed": old != new, "pipeline": PIPE,
                     "suite": "workspace", "security": False})  # fmt: skip
    return rows


def test_fewer_false_blocks_with_the_guard_holding_is_confirmed():
    result = analysis.analyse(_rows(), launch="complete")
    assert result["primary"]["verdict"] == "mejora" and result["guard"]["holds"]
    assert result["verdict"] == "confirmado (mejora)"
    assert result["arms"]["old"]["false_blocks"] == 60
    assert result["arms"]["new"]["false_blocks"] == 32


def test_losing_unfinished_stops_beyond_the_margin_is_not_adopted():
    result = analysis.analyse(_rows(lost=30), launch="complete")
    assert result["primary"]["verdict"] == "mejora" and not result["guard"]["holds"]
    assert result["verdict"] == "no se adopta (la guarda no se sostiene)"


def test_no_verdict_without_a_complete_launch_or_with_answers_missing():
    assert analysis.analyse(_rows(), launch="stopped")["verdict"].startswith("sin veredicto")
    assert analysis.analyse(_rows(missing=20), launch="complete")["verdict"] == "no concluyente"


def test_the_power_simulation_is_seeded_and_its_intervals_hold_the_estimate():
    draws = runner.simulate([(30, 15)] * 10, 0.6, 0.5, 0.05, sims=20, replicas=50)
    assert draws == runner.simulate([(30, 15)] * 10, 0.6, 0.5, 0.05, sims=20, replicas=50)
    assert all(low <= d <= high for d, _, low, high in draws)
    none = runner.simulate([(30, 15)] * 10, 0.6, 0.0, 0.0, sims=5, replicas=20)
    assert all(d == 0 for d, *_ in none)  # no effect, no difference
