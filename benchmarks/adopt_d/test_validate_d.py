"""validate_d's pure logic: replacement order, the seal refusal, resume. No Docker, no harness.

    python -m pytest benchmarks/adopt_d/test_validate_d.py -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate_d  # noqa: E402


def row(name: str, stratum: str) -> dict:
    return {"instance_id": name, "stratum": stratum, "repo": "r/r", "difficulty": "d",
            "image": f"img-{name}"}  # fmt: skip


DRAWN = {
    "held": [row("e1", "easy"), row("e2", "easy"), row("h1", "hard")],
    "spares": {"easy": [row("es1", "easy"), row("es2", "easy"), row("es3", "easy")],
               "hard": [row("hs1", "hard")]},  # fmt: skip
}


def res(name: str, ok: bool) -> dict:
    return {"instance_id": name, "pass": ok, "reason": None if ok else f"{name} broke"}


def results(**outcomes: bool) -> dict:
    return {k: res(k, v) for k, v in outcomes.items()}


def test_table_order_first():
    assert validate_d.walk(DRAWN, {})[0] == "e1"
    assert validate_d.walk(DRAWN, results(e1=True))[0] == "e2"
    assert validate_d.walk(DRAWN, results(e1=True, e2=True))[0] == "h1"


def test_a_failure_takes_the_next_spare_before_moving_on():
    assert validate_d.walk(DRAWN, results(e1=False))[0] == "es1"
    assert validate_d.walk(DRAWN, results(e1=False, es1=True))[0] == "e2"


def test_a_failed_spare_is_skipped_for_good_in_spare_order():
    done = results(e1=False, es1=False, es2=True, e2=False, es3=True, h1=True)
    pending, sel = validate_d.walk(DRAWN, done)
    assert pending is None
    picked = [(s["instance_id"], s["drawn_as"], s["replaces"]) for s in sel["selected"]]
    assert picked == [("es2", "spare", "e1"), ("es3", "spare", "e2"), ("h1", "held", None)]
    first = sel["replacements"][0]
    assert first["failed"] == "e1" and first["replaced_by"] == "es2"
    assert first["spares_failed_first"] == [{"instance_id": "es1", "reason": "es1 broke"}]
    assert sel["replacements"][1]["spares_failed_first"] == []
    assert sel["shortfall"] == {}


def test_second_failure_does_not_reuse_a_spare():
    # es1 replaced e1; e2 fails too and must go to es2, never es1 again.
    done = results(e1=False, es1=True, e2=False)
    assert validate_d.walk(DRAWN, done)[0] == "es2"


def test_a_stratum_out_of_spares_runs_short_and_says_so():
    pending, sel = validate_d.walk(DRAWN, results(e1=True, e2=True, h1=False, hs1=False))
    assert pending is None
    assert sel["shortfall"] == {"hard": 1}
    assert sel["replacements"] == [{"stratum": "hard", "failed": "h1", "reason": "h1 broke",
                                    "replaced_by": None,
                                    "spares_failed_first": [{"instance_id": "hs1",
                                                             "reason": "hs1 broke"}]}]  # fmt: skip
    assert [s["instance_id"] for s in sel["selected"]] == ["e1", "e2"]


def test_refuses_once_the_seal_exists(tmp_path, monkeypatch):
    seal = tmp_path / "prereg.sha256"
    assert validate_d.seal_refusal(seal) is None
    seal.write_text("x")
    assert "sealed" in validate_d.seal_refusal(seal)
    monkeypatch.setattr(validate_d, "SEAL", seal)
    monkeypatch.setattr(validate_d, "VD", tmp_path / "vd")
    monkeypatch.setattr(validate_d, "LOG", tmp_path / "vd" / "validate.log")
    monkeypatch.setattr(validate_d, "PULLED", tmp_path / "vd" / "pulled.json")
    monkeypatch.setattr(validate_d, "OUT", tmp_path / "singles-validated.json")

    def no_docker(*_a, **_k):
        raise AssertionError("the refusal must come before any Docker or harness work")

    for name in ("validate", "docker_alive", "gold_patches"):
        monkeypatch.setattr(validate_d, name, no_docker)
    monkeypatch.setattr(validate_d.singles_run, "rows", no_docker)
    with pytest.raises(SystemExit, match="sealed"):
        validate_d.main(["run", "--limit", "1"])
    with pytest.raises(SystemExit, match="sealed"):
        validate_d.main(["summary"])


def test_resume_skips_what_the_output_holds(tmp_path, monkeypatch):
    out = tmp_path / "singles-validated.json"
    drawn_path = tmp_path / "singles-d.json"
    drawn_path.write_text(json.dumps(DRAWN))
    monkeypatch.setattr(validate_d, "OUT", out)
    monkeypatch.setattr(validate_d, "DRAWN", drawn_path)
    monkeypatch.setattr(validate_d, "harness_record", lambda: {})
    done = {k: {**v, "order": i} for i, (k, v) in enumerate(results(e1=False, es1=True).items())}
    validate_d.write_out(DRAWN, done)
    loaded = validate_d.load(out)
    assert set(loaded) == {"e1", "es1"}
    assert validate_d.walk(DRAWN, loaded)[0] == "e2"
    written = json.loads(out.read_text())
    assert written["complete"] is False and written["next"] == "e2"
    assert "selected" not in written


def test_complete_output_has_the_selection(tmp_path, monkeypatch):
    out = tmp_path / "singles-validated.json"
    drawn_path = tmp_path / "singles-d.json"
    drawn_path.write_text(json.dumps(DRAWN))
    monkeypatch.setattr(validate_d, "OUT", out)
    monkeypatch.setattr(validate_d, "DRAWN", drawn_path)
    monkeypatch.setattr(validate_d, "harness_record", lambda: {})
    done = results(e1=True, e2=False, es1=True, h1=True)
    done = {k: {**v, "order": i} for i, (k, v) in enumerate(done.items())}
    validate_d.write_out(DRAWN, done)
    written = json.loads(out.read_text())
    assert written["complete"] is True
    assert written["selected_per_stratum"] == {"easy": 2, "hard": 1}
    assert [r["instance_id"] for r in written["results"]] == ["e1", "e2", "es1", "h1"]


def ok_steps(**override: dict) -> dict:
    steps = {"pull": {"ok": True}, "export": {"ok": True},
             "gold": {"report": True, "resolved": True},
             "empty_literal": {"report": True, "resolved": False},
             "empty": {"report": True, "resolved": False}}  # fmt: skip
    return {**steps, **override}


def test_verdict_reasons_in_order():
    assert validate_d.verdict(ok_steps()) is None
    pull = {"pull": {"ok": False, "error": "manifest unknown"}}
    assert validate_d.verdict(pull).startswith("image did not pull")
    export = {"pull": {"ok": True}, "export": {"ok": False, "error": "archive"}}
    assert validate_d.verdict(export).startswith("export failed")
    gold = {"pull": {"ok": True}, "export": {"ok": True},
            "gold": {"report": True, "resolved": False}}  # fmt: skip
    assert validate_d.verdict(gold) == "gold patch does not resolve"
    assert "no report" in validate_d.verdict(ok_steps(gold={"report": False, "resolved": False}))
    resolves = ok_steps(empty={"report": True, "resolved": True})
    assert validate_d.verdict(resolves) == "empty (no-op) patch resolves"


def test_noop_patch_is_a_new_file_only():
    lines = validate_d.NOOP_PATCH.splitlines()
    assert lines[1] == "new file mode 100644" and lines[3] == "--- /dev/null"
    assert sum(1 for line in lines if line.startswith("diff --git")) == 1
