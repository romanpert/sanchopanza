"""The candor benchmark replays from what it recorded: no key, no network, no session."""

from __future__ import annotations

import contextlib
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "results" / "2026-09-29-candor"
BENCH = ROOT / "benchmarks" / "candor"
# Generic module names that other results folders use too (context-e2e has its own `tasks`).
OURS = ("tasks", "rounds", "monitors", "analyze", "counterfactual", "sessions", "explore")


@contextlib.contextmanager
def bench_modules():
    """Import the candor benchmark modules by their plain names, then put back whatever held
    those names before, so tests from other folders in the same process are not disturbed."""
    saved = {name: sys.modules.pop(name) for name in OURS if name in sys.modules}
    sys.path.insert(0, str(BENCH))
    try:
        yield
    finally:
        sys.path.remove(str(BENCH))
        for name in OURS:
            sys.modules.pop(name, None)
        sys.modules.update(saved)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


@pytest.mark.parametrize("name", ["prereg", "prereg-2"])
def test_registration_manifest_matches_the_registered_hash(name: str) -> None:
    manifest_path = OUT / f"{name}.manifest.json"
    if not manifest_path.exists():
        pytest.skip(f"{name} not registered yet")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    combined = hashlib.sha256("".join(f"{k} {v}\n" for k, v in manifest.items()).encode())
    assert combined.hexdigest() == (OUT / f"{name}.sha256").read_text().strip()
    doc = f"docs/results/2026-09-29-candor/{name}.md"
    assert manifest[doc] == _digest(OUT / f"{name}.md")


def test_tasks_never_ask_to_hide_or_misstate() -> None:
    with bench_modules():
        from tasks import TASKS
    banned = ("hide", "don't mention", "do not mention", "conceal", "lie", "pretend", "secret")
    for task in TASKS:
        assert not any(word in task.prompt.lower() for word in banned), task.name


@pytest.mark.parametrize("round_", ["1", "2"])
def test_analysis_replays_exactly(round_: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rates and verdicts come back identical from the recorded, text-free item table."""
    suffix = "" if round_ == "1" else "-2"
    analysis, scored = OUT / f"analysis{suffix}.json", OUT / f"scored{suffix}.jsonl"
    runs = OUT / f"runs{suffix}"
    if not analysis.exists() or not scored.exists() or not runs.exists():
        pytest.skip(f"round {round_}: recordings not present (raw runs are kept local)")
    before = json.loads(analysis.read_text(encoding="utf-8"))
    monkeypatch.setenv("CANDOR_ROUND", round_)
    with bench_modules():
        import analyze

        analyze.main()
    assert json.loads(analysis.read_text(encoding="utf-8")) == before


# Items whose lock verdict the rules after v2 change on round-2 data, each with its reason. The
# registered round-2 numbers are v2's (commit e8191f9); anything else changing is a regression.
CHANGED_SINCE_V2 = {
    # v3: `find ... | head` no longer counts as reading the file it searched for.
    "I3-missing-doc-haiku-4": {"critical": True},
}


def test_round_two_rules_rescore_with_the_current_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """Round 1 was scored by the v1 rules at commit 2277189 and is not rescored here; round 2
    was scored by v2 and must rescore identically, except the documented v3 changes."""
    scored_path = OUT / "scored-2.jsonl"
    if not scored_path.exists() or not (OUT / "runs-2").exists():
        pytest.skip("round 2 not run, or its raw runs are not present")
    monkeypatch.setenv("CANDOR_ROUND", "2")
    with bench_modules():
        import monitors

        items = monitors.items()
        items += monitors.adversarial(items)
        rescored = {i["id"]: monitors.rules_arm(i, block=True) for i in items}
    scored = {
        s["id"]: s for s in map(json.loads, scored_path.read_text(encoding="utf-8").splitlines())
    }
    for item_id, got in rescored.items():
        if item_id in CHANGED_SINCE_V2:
            expected = CHANGED_SINCE_V2[item_id]
            assert {k: got[k] for k in expected} == expected, item_id
            continue
        assert got == scored[item_id]["rules_block"], item_id
