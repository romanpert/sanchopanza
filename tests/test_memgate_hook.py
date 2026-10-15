"""Lot memgate-hook (benchmarks/memgate_hook/), with no network and no paid call: the two arms
through the installed hook's own recall, what each sends the decider, the pairs and their
order, the stops, the dry count, the seal before any spend, rows without text, and the verdict
rules and power on synthetic numbers."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from sanchopanza.answers import truth
from sanchopanza.context import episodes as ep
from sanchopanza.contract import Decision

ROOT = Path(__file__).resolve().parents[1]
FOLDERS = (ROOT / "benchmarks" / "memory_real", ROOT / "benchmarks" / "memgate_hook")


def _load() -> Any:
    """The runner, without leaving `benchmarks/memory_real`'s modules (`labels`, `score`...) or
    the paths it added behind: other benchmarks reuse those names (`helpers.bench_module`)."""
    own = {p.stem for folder in FOLDERS for p in folder.glob("*.py")}
    saved = {n: sys.modules.pop(n) for n in own if n in sys.modules}
    path, before = list(sys.path), set(sys.modules)
    spec = importlib.util.spec_from_file_location("memgate_hook", FOLDERS[1] / "memgate_hook.py")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = path
        for added in set(sys.modules) - before:
            source = str(getattr(sys.modules[added], "__file__", "") or "")
            if any(source.startswith(str(folder)) for folder in FOLDERS):
                del sys.modules[added]
        sys.modules.update(saved)
    return module


mg = _load()
an = mg.an
DEEP = "zebra-quartz"  # a word only the whole record holds: past the 880-character page
PROMPT = "Fix the carbon.py lexer for octal literals"


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(mg, "OUT", tmp_path / "out")
    monkeypatch.setattr(mg, "LEDGER_PATH", tmp_path / "ledger.json")
    monkeypatch.setattr(mg, "first_prompt", lambda item: item["request"])
    for name in ("SANCHOPANZA_MEMORY_WINDOW", "SANCHO_MEMORY_WINDOW"):
        monkeypatch.delenv(name, raising=False)
    mg.mgl.HALTED.clear()
    yield
    mg.mgl.HALTED.clear()


def record(session: str, index: int, request: str, report: str, changed: tuple = ()) -> Any:
    return ep.Episode(session=session, index=index, request=request, report=report,
                      changed=changed, at=1_700_000_000.0)  # fmt: skip


def item(n: int = 0, related: str = "lineage") -> dict[str, Any]:
    old = f"{n:04d}aaaa-old"
    deep = record(old, 1, "carbon lexer: hex literals", "Fixed carbon hex. " + "x " * 600 + DEEP,
                  ("src/carbon.py",))  # fmt: skip
    notes = record(old, 2, "carbon notes", "Wrote carbon notes.", ("docs/notes.md",))
    question = record(old, 3, "why does carbon lex octal so", "Explained carbon octal.")
    pool = [deep, notes, question]
    labels = {deep.key: related, notes.key: "none", question.key: "none"}
    return {"session": f"{n:04d}bbbb-new", "index": 1, "first": True, "group": n,
            "set": "selection", "cluster": f"selection:{n}", "request": PROMPT, "pool": pool,
            "labels": labels}  # fmt: skip


class Fake:
    """Says every record is related (0.9) when it can read DEEP, else 0.1. Logs each call."""

    name = "fake"
    accepts_attachments = False
    model = "jev-1.13.0"

    def __init__(self, calls: list | None = None, tag: str = "") -> None:
        self.calls = [] if calls is None else calls
        self.tag = tag

    async def decide(self, point: str, state: Any, questions: Mapping[str, Any]) -> Decision:
        self.calls.append({"tag": self.tag, "point": point, "state": state})
        p = 0.9 if DEEP in json.dumps(state) else 0.1
        return Decision(point, {k: truth(p) for k in questions}, self.name, "jev-1.13.0")


def ask(it: dict[str, Any], arm: str, decider: Any, root: Path) -> dict[str, Any]:
    return asyncio.run(mg.ask_hook(it, arm, decider, root / arm, it["request"]))


# ---- the arms ---------------------------------------------------------------------------------


def test_the_environment_is_the_installed_one_and_only_l_sets_the_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SANCHOPANZA_MEMORY_WINDOW", "short")
    monkeypatch.setenv("SANCHOPANZA_MEMORY_KEEP_AT", "0.1")  # the caller's: not the hook's
    with mg.hook_env("S", tmp_path, tmp_path / "log"):
        assert "SANCHOPANZA_MEMORY_WINDOW" not in os.environ
        assert "SANCHOPANZA_MEMORY_KEEP_AT" not in os.environ
        assert os.environ["SANCHOPANZA_MEMORY_SELECT"] == "decider"
        assert os.environ["SANCHOPANZA_MEMORY_PROMPT"] == "first"
    with mg.hook_env("L", tmp_path, tmp_path / "log"):
        assert os.environ["SANCHOPANZA_MEMORY_WINDOW"] == "long"
    assert os.environ["SANCHOPANZA_MEMORY_WINDOW"] == "short"
    assert os.environ["SANCHOPANZA_MEMORY_KEEP_AT"] == "0.1"


def test_the_arms_differ_only_in_how_the_hook_reads_the_records(tmp_path: Path) -> None:
    it = item()
    short, long = Fake(), Fake()
    s, l_ = ask(it, "S", short, tmp_path), ask(it, "L", long, tmp_path)
    (sent_s,), (sent_l,) = short.calls, long.calls
    assert sent_s["point"] == sent_l["point"] == "memory_recall"
    assert "### Earlier" not in sent_s["state"]["records"]  # pages
    assert "### Earlier" in sent_l["state"]["records"] and DEEP in sent_l["state"]["records"]
    assert s["candidates"] == l_["candidates"] and len(s["candidates"]) == 3
    assert s["asked"] and l_["asked"]
    assert s["shown"] == [] and "window" not in s  # the hook's default: the short window
    deep = it["pool"][0].key
    assert deep in l_["shown"] and l_["window"] == "long" and "window_fallback" not in l_
    assert it["pool"][1].key not in l_["shown"]  # the v5 name gate still drops notes.md
    row = mg.score_row(it, {"S": s, "L": l_})
    assert an.hit(row, "L") and not an.hit(row, "S") and an.has_related(row)


def test_a_request_the_hook_ran_out_of_time_on_is_asked_and_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Slow(Fake):
        async def decide(self, point, state, questions):
            await asyncio.sleep(2)
            return await super().decide(point, state, questions)

    vars_ = tuple(v for v in mg.HOOK_VARS if v != "MEMORY_DECIDER_SECONDS")
    monkeypatch.setattr(mg, "HOOK_VARS", vars_)
    monkeypatch.setenv("SANCHOPANZA_MEMORY_DECIDER_SECONDS", "1")
    got = ask(item(), "S", Slow(), tmp_path)
    assert got["asked"] and an.failed(got) and got["shown"] == []


def test_rows_hold_no_text(tmp_path: Path) -> None:
    rows = asyncio.run(mg.run([item(0), item(1)], {"S": Fake(), "L": Fake()}, live=False,
                              batch="b", cap_usd=1.0, root=tmp_path))  # fmt: skip
    text = json.dumps(rows)
    assert DEEP not in text and "lexer" not in text and "Fixed" not in text
    assert [r["rank"] for r in rows] == [0, 1]


def test_pairs_alternate_which_arm_goes_first(tmp_path: Path) -> None:
    calls: list = []
    deciders = {"S": Fake(calls, "S"), "L": Fake(calls, "L")}
    asyncio.run(mg.run([item(0), item(1), item(2)], deciders, live=False, batch="b",
                       cap_usd=1.0, root=tmp_path))  # fmt: skip
    assert [c["tag"] for c in calls] == ["S", "L", "L", "S", "S", "L"]


def test_a_halt_drops_the_pair_it_hit_and_ends_the_run(tmp_path: Path) -> None:
    class Halting(Fake):
        async def decide(self, point, state, questions):
            mg.mgl.halt(mg.mgl.PAUSE, "HTTP 503")
            return await super().decide(point, state, questions)

    rows = asyncio.run(mg.run([item(0), item(1)], {"S": Halting(), "L": Fake()}, live=False,
                              batch="b", cap_usd=1.0, root=tmp_path))  # fmt: skip
    assert rows == [] and mg.mgl.halt_kind() == mg.mgl.PAUSE
    assert mg.finish("run", rows, "b", 1.0) == 2
    assert not (tmp_path / "out" / "run-scored.jsonl").exists()


def test_no_pair_starts_when_the_room_left_would_not_hold_it(tmp_path: Path) -> None:
    calls: list = []
    deciders = mg.arm_deciders("run", True, "b", 1e-9, make_inner=lambda arm: Fake(calls))
    rows = asyncio.run(mg.run([item(0)], deciders, live=True, batch="b", cap_usd=1e-9,
                              root=tmp_path))  # fmt: skip
    assert rows == [] and calls == [] and not mg.mgl.HALTED


def test_a_cap_refusal_stops_the_lot_dead_without_calling(tmp_path: Path) -> None:
    calls: list = []
    deciders = mg.arm_deciders("run", True, "b", 1e-9, make_inner=lambda arm: Fake(calls))
    rows = asyncio.run(mg.run([item(0), item(1)], deciders, live=True, batch="b", cap_usd=1.0,
                              root=tmp_path))  # fmt: skip
    assert rows == [] and calls == [] and mg.mgl.halt_kind() == mg.mgl.CAP
    assert mg.spent() == 0.0
    assert mg.finish("run", rows, "b", 1.0) == 2  # refused with room left: a ledger fault


def test_the_live_run_refuses_without_the_seal_before_reading_any_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_key() -> None:
        raise AssertionError("the key was read")

    monkeypatch.setattr(mg.l4, "load_key", no_key)
    with pytest.raises(SystemExit, match="differ from the seal"):
        mg.go_live()


def test_the_caps_are_hard_and_under_a_dollar() -> None:
    assert mg.LEDGER_CAP_USD <= 1.0 and mg.BATCH_CAP_USD <= mg.LEDGER_CAP_USD
    assert mg.SMOKE_CAP_USD < mg.BATCH_CAP_USD and mg.MODEL == "jev-1.13.0"


# ---- dry --------------------------------------------------------------------------------------


def test_the_dry_decider_counts_every_call_and_never_makes_the_long_arm_fall_back(
    tmp_path: Path,
) -> None:
    tallies: dict[str, dict] = {"S": {}, "L": {}}
    deciders = {arm: mg.DryDecider(tallies[arm]) for arm in mg.ARMS}
    rows = asyncio.run(mg.run([item(0), item(1)], deciders, live=False, batch="b", cap_usd=1.0,
                              root=tmp_path))  # fmt: skip
    assert tallies["S"]["calls"] == tallies["L"]["calls"] == 2
    assert min(tallies["L"]["chars"]) > max(tallies["S"]["chars"])
    assert tallies["L"]["estimate_usd"] > tallies["S"]["estimate_usd"] > 0
    assert all("window_fallback" not in r["L"] and r["L"]["shown"] == [] for r in rows)


def test_the_smoke_is_taken_out_of_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    items = [item(n) for n in range(8)]
    monkeypatch.setattr(mg, "would_ask", lambda it: it["group"] % 2 == 0)
    smoke, rest = mg.split_smoke(items)
    assert len(smoke) == mg.SMOKE_REQUESTS and all(it["group"] % 2 == 0 for it in smoke)
    assert not {mg.item_id(i) for i in smoke} & {mg.item_id(i) for i in rest}
    assert len(rest) == len(items) - mg.SMOKE_REQUESTS
    assert mg.split_smoke(items)[1] == rest  # seeded: the same order every time


# ---- analysis ---------------------------------------------------------------------------------


def arm_row(shown: list[str], *, asked: bool = True, p: float | None = 0.9) -> dict[str, Any]:
    return {"candidates": ["k1", "k2"], "asked": asked, "shown": shown, "reason": "",
            "probabilities": {"k1": p, "k2": p} if asked else {}}  # fmt: skip


def scored(n: int, related: bool, s: list[str], l_: list[str], **kw: Any) -> dict[str, Any]:
    labels = {"k1": "file" if related else "none", "k2": "none"}
    return {"id": f"r{n}", "set": "selection", "cluster": f"g{n % 7}", "pool": 2,
            "related_in_pool": related, "labels": labels,
            "S": arm_row(s, **kw), "L": arm_row(l_, **kw)}  # fmt: skip


def test_a_clear_gain_with_no_extra_noise_reads_mejora() -> None:
    rows = [scored(n, True, [] if n % 3 else ["k1"], ["k1"]) for n in range(60)]
    rows += [scored(100 + n, False, [], []) for n in range(60)]
    summary = an.analyse(rows)
    assert summary["hit_L_vs_S"]["only_new"] == 40 and summary["hit_L_vs_S"]["only_old"] == 0
    assert summary["verdict"] == "mejora"
    assert summary["describe"]["L"]["recall"] == 1.0 and summary["describe"]["S"]["noise"] == 0


def test_too_few_requests_withhold_the_verdict() -> None:
    rows = [scored(n, True, [], ["k1"]) for n in range(10)]
    rows += [scored(100 + n, False, [], []) for n in range(60)]
    assert an.analyse(rows)["verdict"] == "no concluyente (n bajo)"


def test_more_noise_in_l_reads_peor_en_ruido_whatever_the_gain() -> None:
    rows = [scored(n, True, [], ["k1"]) for n in range(60)]
    rows += [scored(100 + n, False, [], ["k2"] if n % 2 else []) for n in range(60)]
    assert an.analyse(rows)["verdict"] == "peor en ruido"


def test_no_difference_reads_no_peor_and_failures_withhold() -> None:
    same = [scored(n, True, ["k1"], ["k1"]) for n in range(60)]
    same += [scored(100 + n, False, [], []) for n in range(60)]
    assert an.analyse(same)["verdict"] == "no peor"
    broken = [{**r, "L": arm_row([], p=None)} if n < 5 else r for n, r in enumerate(same)]
    summary = an.analyse(broken)
    assert summary["failed"] == {"S": 0, "L": 5} and summary["verdict"] == "no medido (fallos)"


def test_failed_means_asked_and_unanswered_or_timed_out() -> None:
    assert an.failed(arm_row([], p=None)) and not an.failed(arm_row([], asked=False))
    assert an.failed({**arm_row([]), "reason": "decider timed out after 15 s"})
    assert not an.failed(arm_row(["k1"]))


def test_power_grows_with_the_effect_and_the_requests() -> None:
    assert an.mcnemar_power(176, 0.10, 0.02) > an.mcnemar_power(176, 0.06, 0.02)
    assert an.mcnemar_power(400, 0.06, 0.02) > an.mcnemar_power(176, 0.06, 0.02)
    assert an.mcnemar_power(176, 0.03, 0.03) < 0.05
    table = an.power_table(176)
    assert table["n"] == 176 and 0.05 < table["L_only_for_80pct_at_S_only_0.02"] < 0.2
