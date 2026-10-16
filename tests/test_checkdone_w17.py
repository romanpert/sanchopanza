"""Lot jev114-checkdone-w17 (draft, docs/results/2026-10-16-checkdone-w17/prereg.md): the
runner's free parts and the analysis, with no network and no model.

Pins the arms to the record builder (old = the record every earlier lot asked about, new = the
same with `done_evidence`), the asking plan to each request once, the cut to the shipped 1.14
profile, and the verdict rule to the registration.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
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


def test_the_overlap_check_finds_a_request_recorded_under_1_13_keys(monkeypatch, tmp_path):
    import json as _json

    from sanchopanza.providers.recorded import key_of

    stop = runner.stop_of(_entry(), _data("tiny", "It is tiny."), "confirm")
    r = stop["old"]
    fixtures = tmp_path / "fixtures"
    (fixtures / "jev114").mkdir(parents=True)
    for model in (None, "jev-1.13.0", "jev-1.14.0"):
        (fixtures / "jev114" / "checkdone114-13r.jsonl").write_text(
            _json.dumps({"key": key_of(r["point"], r["state"], r["questions"], model)}) + "\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(runner, "ROOT", tmp_path)
        assert runner.overlap_with_seen([r]) == 1, model


def test_the_lot_is_one_model_capped_and_sealed_over_the_builder():
    lot = runner.LOT
    assert dict(lot.models) == {"14": "jev-1.14.0"}
    assert lot.batch_cap <= 0.25 and lot.ledger_cap == 4.50
    for rel in ("src/sanchopanza/points/done_evidence.py", "benchmarks/completion/run.py",
                "src/sanchopanza/points/completion.py", "checkdone-w17-run.cmd",
                "benchmarks/jev114/w17_inputs.jsonl"):  # fmt: skip
        assert rel in lot.sealed, rel
    assert runner.CUT == analysis.cut() == 0.30


def test_the_lot_spends_on_the_shared_ledger_and_needs_room_for_its_whole_batch(monkeypatch):
    lot, lots = runner.LOT, runner.lots
    assert lot.ledger == lots.LEDGER and lot.ledger_cap == lots.LEDGER_CAP == 4.50
    assert runner.PREREG == ROOT / "docs/results/2026-10-16-checkdone-w17/prereg.md"
    assert runner.PREREG.exists() and runner.OUT == analysis.OUT
    assert "docs/results/2026-10-16-checkdone-w17/prereg.md" in lot.sealed

    def room(left, spent=0.0):
        return lambda _: {"ledger_spent": 4.5 - left, "ledger_room": left, "batch_spent": spent}

    monkeypatch.setattr(lots, "ledger_room", room(0.48))
    assert runner.room_problem() is None
    monkeypatch.setattr(lots, "ledger_room", room(0.20))
    assert "0.2 USD left" in runner.room_problem()
    monkeypatch.setattr(lots, "ledger_room", room(0.20, spent=0.10))  # a relaunch: 0.15 to go
    assert runner.room_problem() is None
    own = lots.Lot(name="x", out=ROOT, run=ROOT, batch_cap=0.25, sealed=(), fixture_stem="x",
                   ledger=ROOT / "elsewhere.json")  # fmt: skip
    assert runner.room_problem(own).startswith("not the shared ledger")


def _filled_launcher(tmp_path: Path, extra: str = "") -> Path:
    """The run folder's copy: CRLF, its three local values filled, as the launch uses it."""
    text = (ROOT / "checkdone-w17-run.cmd").read_text(encoding="utf-8")
    filled = {"PY": r"C:\py\python.exe", "SANCHOPANZA_KEYS_ENV": r"C:\k\.keys",
              "WT": r"C:\wt\run-checkdone-w17"}  # fmt: skip
    placeholders = {"PY": "<PYTHON>", "SANCHOPANZA_KEYS_ENV": "<KEYS_ENV_PATH>", "WT": "<WORKTREE>"}
    for name, value in filled.items():
        placeholder = f'set "{name}={placeholders[name]}"'
        assert text.count(placeholder) == 1, placeholder
        text = text.replace(placeholder, f'set "{name}={value}"')
    path = tmp_path / "checkdone-w17-run.cmd"
    path.write_bytes((text + extra).replace("\n", "\r\n").encode("utf-8"))
    return path


def test_the_paid_path_reaches_the_launch_from_the_filled_launcher_and_no_other(
    monkeypatch, tmp_path
):
    import argparse
    import json as _json

    import pytest

    lots = runner.lots
    long = _listing(120, {100: "recipe-collection.docx"})
    confirm = [runner.stop_of(_entry(), _data(long, "recipe-collection.docx"), "confirm")]
    dev = [{**confirm[0], "set": "dev", "id": "dev-a"}]
    monkeypatch.setattr(runner, "load_confirm", lambda root=None: confirm)
    monkeypatch.setattr(runner, "load_dev", lambda root=None: dev)
    data = tmp_path / "data.sha256"
    data.write_text(_json.dumps({"stops": runner.digest_of(confirm, dev)}), encoding="utf-8")
    monkeypatch.setattr(runner, "DATA", data)
    monkeypatch.setattr(lots, "require_seal_commit", lambda lot: {"head": "h", "parent": "p"})
    monkeypatch.setattr(lots, "require_seal", lambda lot: None)
    monkeypatch.setattr(lots, "ledger_room", lambda lot: {"ledger_spent": 4.0163,
                                                          "ledger_room": 0.4837,
                                                          "batch_spent": 0.0})  # fmt: skip
    launched = []
    monkeypatch.setattr(lots, "paid_launch", lambda lot, run_all, commits: launched.append(
        (lot.name, commits)) or 0)  # fmt: skip
    args = argparse.Namespace(dry=False, paid=True, data_root=tmp_path)

    monkeypatch.setenv("SANCHOPANZA_LAUNCHER", str(_filled_launcher(tmp_path)))
    assert runner.cmd_run(args) == 0
    assert launched == [("jev114-checkdone-w17", {"head": "h", "parent": "p"})]

    monkeypatch.setenv("SANCHOPANZA_LAUNCHER", str(_filled_launcher(tmp_path, "rem changed\n")))
    with pytest.raises(SystemExit, match="differs from the sealed"):
        runner.cmd_run(args)
    monkeypatch.delenv("SANCHOPANZA_LAUNCHER")
    with pytest.raises(SystemExit, match="not started by the lot's launcher"):
        runner.cmd_run(args)
    assert len(launched) == 1


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


def test_the_published_result_reproduces():
    lines = analysis.ROWS.read_text(encoding="utf-8").splitlines()
    rows = [json.loads(x) for x in lines if x.strip()]
    result = analysis.analyse(rows)
    assert result["launch"] == "complete"
    assert result["verdict"] == "no se adopta (la guarda no se sostiene)"
    assert result["n"] == {"confirm": 1572, "answered": 1572, "dev": 950}
    old, new = result["arms"]["old"], result["arms"]["new"]
    assert (old["false_blocks"], new["false_blocks"], old["done"]) == (165, 123, 828)
    assert (old["caught"], new["caught"], old["not_done"]) == (598, 583, 744)
    assert result["primary"]["verdict"] == "mejora" and not result["guard"]["holds"]
    published = json.loads((analysis.OUT / "analysis.json").read_text(encoding="utf-8"))
    assert published == json.loads(json.dumps(result))
