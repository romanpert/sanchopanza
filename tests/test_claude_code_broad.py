"""The broad Claude Code run in `docs/results/2026-09-28-claude-code-broad/`, pinned.

No key, no network. Three things are checked:

1. The registration: `prereg.md` hashes to what `prereg.sha256` recorded before any paid call.
2. The headline numbers: rescored from `hook-verdicts.jsonl` and the per-session rows, they
   are the ones `analysis.json` and the README state.
3. The hook-level verdicts themselves: every case of the sets this repository ships (guard
   bench, both injection sets, the non-fetching control, the 655 AgentDojo Stop inputs) is
   rebuilt and run through `sanchopanza.harness.claude_code` in-process, the same `main` path
   minus stdin, with the `recorded` provider answering from
   `fixtures/claude-code-broad-jev.jsonl`. Each must produce the verdict the live Jev run
   produced. ATBench-Codex and R-Judge are replayed too when a local copy is present
   (`SANCHOPANZA_ATBENCH`, `SANCHOPANZA_RJUDGE`); they are not redistributed here.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs" / "results" / "2026-09-28-claude-code-broad"
FIXTURE = ROOT / "fixtures" / "claude-code-broad-jev.jsonl"
PREREG_SHA256 = "c52b207ebedfb6128e359737b8a3116e41f38c92684ab513a3fbe683eebdef8b"
_CACHE = pathlib.Path.home() / ".cache" / "sancho"
ATBENCH = pathlib.Path(os.environ.get("SANCHOPANZA_ATBENCH", _CACHE / "atbench-codex-test.json"))
RJUDGE = pathlib.Path(
    os.environ.get("SANCHOPANZA_RJUDGE", pathlib.Path.home() / ".cache/sancho/R-Judge")
)

if not (RESULTS / "analysis.json").exists():  # pragma: no cover
    pytest.skip("broad claude code results not present", allow_module_level=True)


def _module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(RESULTS))
cases = _module("broad_cases", RESULTS / "cases.py")
analyze = _module("broad_analyze", RESULTS / "analyze.py")


def _saved() -> dict:
    return json.loads((RESULTS / "analysis.json").read_text(encoding="utf-8"))


def _verdicts() -> dict[tuple[str, str], dict]:
    rows = analyze._jsonl(RESULTS / "hook-verdicts.jsonl")
    return {(r["set"], r["id"]): r for r in rows}


# --- 1. registration ---------------------------------------------------------------------------


def test_prereg_hash_is_the_registered_one() -> None:
    raw = (RESULTS / "prereg.md").read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(raw).hexdigest() == PREREG_SHA256
    assert (RESULTS / "prereg.sha256").read_text().strip() == PREREG_SHA256


# --- 2. headline numbers -------------------------------------------------------------------------


def test_hook_level_rescores_to_the_saved_analysis() -> None:
    rows = list(_verdicts().values())
    assert analyze.score_hooks(rows) == _saved()["hooks"]


def test_e2e_rescores_to_the_saved_analysis() -> None:
    saved = _saved()["e2e"]
    rescored = analyze.score_e2e(saved["runs"])
    assert rescored == {k: v for k, v in saved.items() if k != "runs"}


PINNED_HOOKS: dict[str, tuple[int, int]] = {
    "guard_recall": (17, 17),
    "guard_false_blocks": (0, 15),
    "atbench_recall": (0, 250),
    "atbench_false_blocks": (1, 250),
    "rjudge_recall": (7, 15),
    "rjudge_false_blocks": (3, 12),
    "inject_ad_recall": (121, 124),
    "inject_ad_false_alarms": (0, 149),
    "inject_own_recall": (11, 12),
    "inject_own_false_alarms": (1, 16),
    "stop_block_precision": (286, 299),
    "stop_recall": (286, 313),
    "stop_false_blocks": (13, 342),
}
PINNED_E2E: dict[str, tuple[int, int]] = {
    "destructive_stopped_sancho": (16, 16),
    "destructive_executed_plain": (15, 15),
    "planted_flagged_sancho": (16, 16),
    "benign_false_alarms": (0, 93),
}


def test_headline_numbers_are_pinned() -> None:
    saved = _saved()
    hooks = saved["hooks"]
    got_hooks = {
        "guard_recall": hooks["guard"]["recall"],
        "guard_false_blocks": hooks["guard"]["false_positive_rate"],
        "atbench_recall": hooks["atbench"]["recall"],
        "atbench_false_blocks": hooks["atbench"]["false_positive_rate"],
        "rjudge_recall": hooks["rjudge"]["recall"],
        "rjudge_false_blocks": hooks["rjudge"]["false_positive_rate"],
        "inject_ad_recall": hooks["inject_ad"]["recall"],
        "inject_ad_false_alarms": hooks["inject_ad"]["false_positive_rate"],
        "inject_own_recall": hooks["inject_own"]["recall"],
        "inject_own_false_alarms": hooks["inject_own"]["false_positive_rate"],
        "stop_block_precision": hooks["stop"]["block_precision"],
        "stop_recall": hooks["stop"]["recall_not_done"],
        "stop_false_blocks": hooks["stop"]["false_block_rate_done"],
    }
    assert {k: (v["k"], v["n"]) for k, v in got_hooks.items()} == PINNED_HOOKS
    head = saved["e2e"]["headline"]
    assert {k: (v["k"], v["n"]) for k, v in head.items()} == PINNED_E2E


# --- 3. the verdicts, replayed through the hook ---------------------------------------------------


def _replay(inputs: list[dict], tmp: pathlib.Path) -> list[str]:
    from sanchopanza.harness import claude_code

    hook_replay = _module("broad_hook_replay", RESULTS / "hook_replay.py")
    env = {
        **hook_replay.INSTALLED_ENV,
        "SANCHOPANZA_PROVIDER": "recorded",
        "SANCHOPANZA_FIXTURE": str(FIXTURE),
        "SANCHOPANZA_JOURNAL": str(tmp / "j.jsonl"),
    }
    config = claude_code.config_from_env(env)

    async def run_all() -> list[str]:
        kinds = []
        for call in inputs:
            output = {}
            if claude_code.needs_decision(call, config):
                # A fresh squire per input, as a fresh process per hook event has.
                output = await claude_code.handle(call, claude_code.guardian_from_env(env))
            text = json.dumps(output) if output else ""
            kinds.append(hook_replay.kind_of(call["hook_event_name"], text))
        return kinds

    return asyncio.run(run_all())


def _check(built: list[dict], tmp: pathlib.Path) -> None:
    saved = _verdicts()
    inputs, expected, owners = [], [], []
    for case in built:
        row = saved[(case["set"], case["id"])]
        assert len(row["calls"]) == len(case["calls"])
        for call, live in zip(case["calls"], row["calls"], strict=True):
            inputs.append(call)
            expected.append(live["kind"])
            owners.append((case["set"], case["id"]))
    got = _replay(inputs, tmp)
    differ = [(o, e, g) for o, e, g in zip(owners, expected, got, strict=True) if e != g]
    assert not differ, differ[:10]


def test_guard_and_injection_verdicts_replay(tmp_path: pathlib.Path) -> None:
    _check(cases.guard_cases() + cases.injection_cases(), tmp_path)


def test_stop_verdicts_replay(tmp_path: pathlib.Path) -> None:
    _check(cases.stop_cases(tmp_path / "transcripts"), tmp_path)


@pytest.mark.skipif(not ATBENCH.exists(), reason="ATBench-Codex not present locally")
def test_atbench_verdicts_replay(tmp_path: pathlib.Path) -> None:
    _check(cases.atbench_cases(ATBENCH), tmp_path)


@pytest.mark.skipif(not RJUDGE.exists(), reason="R-Judge clone not present locally")
def test_rjudge_verdicts_replay(tmp_path: pathlib.Path) -> None:
    _check(cases.rjudge_cases(RJUDGE), tmp_path)
