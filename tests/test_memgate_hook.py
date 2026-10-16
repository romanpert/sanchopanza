"""Lot memgate-hook (benchmarks/memgate_hook/), with no network and no paid call: the two arms
through the installed hook's own recall, what each sends the decider, the pairs and their
order, the stops, one event loop per run, the dry count, the store's load limit, the live
conditions (seal, hours, sealed commit, clean tree, smoke first), the replay beside the rows of
record and in the run's time zone, rows without text, and the verdict rules and power on
synthetic numbers."""

from __future__ import annotations

import asyncio
import datetime
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
        # Only these two folders' paths go: the lots it imports (L6, memgate-long) stay cached
        # with the paths they added, which their own lazy imports need.
        mine = {str(folder) for folder in FOLDERS}
        sys.path[:] = [p for p in sys.path if p in path or p not in mine]
        for added in set(sys.modules) - before:
            source = str(getattr(sys.modules[added], "__file__", "") or "")
            if any(source.startswith(str(folder)) for folder in FOLDERS):
                del sys.modules[added]
        sys.modules.update(saved)
    return module


mg = _load()
an = mg.an
lr = mg.live_rules
DEEP = "zebra-quartz"  # a word only the whole record holds: past the 880-character page
PROMPT = "Fix the carbon.py lexer for octal literals"
NOON = datetime.datetime(2026, 10, 16, 12, 0)


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(mg, "OUT", tmp_path / "out")
    monkeypatch.setattr(mg, "LEDGER_PATH", tmp_path / "ledger.json")
    for name in ("SANCHOPANZA_MEMORY_WINDOW", "SANCHO_MEMORY_WINDOW"):
        monkeypatch.delenv(name, raising=False)
    mg.mgl.HALTED.clear()
    yield
    mg.mgl.HALTED.clear()


def record(session: str, index: int, request: str, report: str, changed: tuple = (),
           at: float = 1_700_000_000.0) -> Any:  # fmt: skip
    return ep.Episode(session=session, index=index, request=request, report=report,
                      changed=changed, at=at)  # fmt: skip


def item(n: int = 0, related: str = "lineage", prompt: str = PROMPT) -> dict[str, Any]:
    old = f"{n:04d}aaaa-old"
    deep = record(old, 1, "carbon lexer: hex literals", "Fixed carbon hex. " + "x " * 600 + DEEP,
                  ("src/carbon.py",))  # fmt: skip
    notes = record(old, 2, "carbon notes", "Wrote carbon notes.", ("docs/notes.md",))
    question = record(old, 3, "why does carbon lex octal so", "Explained carbon octal.")
    pool = [deep, notes, question]
    labels = {deep.key: related, notes.key: "none", question.key: "none"}
    return {"session": f"{n:04d}bbbb-new", "index": 1, "first": True, "group": n,
            "set": "selection", "cluster": f"selection:{n}", "request": prompt,
            "prompt": prompt, "pool": pool, "labels": labels}  # fmt: skip


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
    return asyncio.run(mg.ask_hook(it, arm, decider, root / arm, it["prompt"]))


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
    row = mg.score_row(it, {"S": s, "L": l_}, it["prompt"])
    assert an.hit(row, "L") and not an.hit(row, "S") and an.has_related(row)
    assert row["hittable"] and row["same_candidates"]
    assert row["changed"] == {deep: True, it["pool"][1].key: True, it["pool"][2].key: False}


def test_a_related_record_the_name_gate_drops_is_not_hittable(tmp_path: Path) -> None:
    it = item(prompt="Explain how the octal lexing works in carbon")  # names no file
    it = {**it, "labels": {k: ("file" if k.endswith("-002") else "none") for k in it["labels"]}}
    arms = {arm: ask(it, arm, Fake(), tmp_path) for arm in mg.ARMS}
    row = mg.score_row(it, arms, it["prompt"])
    assert an.has_related(row) and not row["hittable"]


def test_the_pool_is_dated_so_the_store_s_load_limit_keeps_the_newest(tmp_path: Path) -> None:
    pool = [record("s", i, f"request {i}", "done", at=1_600_000_000.0 + 1000 * i)
            for i in range(1, 6)]  # fmt: skip
    mg.save_pool(tmp_path, list(reversed(pool)))
    assert [e.index for e in ep.load(tmp_path, limit=2)] == [4, 5]


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


def test_an_item_without_its_stored_prompt_is_refused() -> None:
    with pytest.raises(SystemExit, match="rebuild"):
        mg.first_prompt({k: v for k, v in item().items() if k != "prompt"})


# ---- stops and the event loop -----------------------------------------------------------------


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


class LoopBound(Fake):
    """A client tied to the loop it was made in, as httpx's is: called from another loop, it
    fails as Jev's did in lot A3 ("Event loop is closed")."""

    def __init__(self, made: list) -> None:
        super().__init__()
        self.loop = asyncio.get_running_loop()  # no running loop: RuntimeError, made outside
        made.append(self)

    async def decide(self, point, state, questions):
        if asyncio.get_running_loop() is not self.loop:
            raise RuntimeError("Event loop is closed")
        return await super().decide(point, state, questions)


def test_each_execute_makes_its_live_deciders_inside_its_own_loop() -> None:
    made: list = []
    smoke = mg.execute("smoke", [item(0), item(1)], live=True, batch="b", cap_usd=1.0,
                       make_inner=lambda arm: LoopBound(made))  # fmt: skip
    run = mg.execute("run", [item(2), item(3), item(4)], live=True, batch="b", cap_usd=1.0,
                     make_inner=lambda arm: LoopBound(made))  # fmt: skip
    assert len(made) == 4 and len({id(d.loop) for d in made}) == 2  # two arms per loop
    rows = [*smoke, *run]
    assert len(rows) == 5 and not any(an.failed(r[a]) for r in rows for a in mg.ARMS)


def test_a_decider_shared_across_two_loops_fails_as_in_a3() -> None:
    made: list = []

    async def make() -> LoopBound:
        return LoopBound(made)

    shared = asyncio.run(make())
    rows = mg.execute("run", [item(0)], live=True, batch="b", cap_usd=1.0,
                      make_inner=lambda arm: shared)  # fmt: skip
    assert rows == [] or all(an.failed(r[a]) for r in rows for a in mg.ARMS)


# ---- live conditions, the replay and the time zone ----------------------------------------------


def fake_git(head: str = "abc", sealed: str = "abc", status: str = "") -> Any:
    def git(*args: str) -> str:
        return {"log": sealed, "rev-parse": head, "status": status}[args[0]]

    return git


def refusal(name: str, tmp_path: Path, now: datetime.datetime = NOON, **git: str) -> str:
    out = tmp_path / "docs" / "results" / "lot"
    out.mkdir(parents=True, exist_ok=True)
    return lr.live_refusal(name, repo=tmp_path, out=out, now=now, git=fake_git(**git))


def test_a_live_call_waits_for_the_sealed_commit_a_clean_tree_the_hours_and_the_smoke(
    tmp_path: Path,
) -> None:
    assert refusal("smoke", tmp_path) == ""
    assert "update window" in refusal("smoke", tmp_path, datetime.datetime(2026, 10, 16, 3, 5))
    assert refusal("smoke", tmp_path, datetime.datetime(2026, 10, 16, 8, 0)) == ""
    assert "not committed" in refusal("smoke", tmp_path, sealed="")
    assert "not the commit" in refusal("smoke", tmp_path, head="def")
    assert "changed outside" in refusal("smoke", tmp_path, status=" M src/x.py\n")
    ours = "?? docs/results/lot/run-answers-S.jsonl\n M docs/results/lot/smoke-scored.jsonl\n"
    assert refusal("smoke", tmp_path, status=ours) == ""
    assert "smoke is not scored" in refusal("run", tmp_path)
    (tmp_path / "docs" / "results" / "lot" / "smoke-scored.jsonl").write_text("{}\n")
    assert refusal("run", tmp_path) == ""


def test_the_live_run_refuses_without_the_seal_before_reading_any_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_key() -> None:
        raise AssertionError("the key was read")

    monkeypatch.setattr(mg.l4, "load_key", no_key)
    with pytest.raises(SystemExit, match="differ from the seal"):
        mg.go_live("smoke", now=NOON, git=fake_git())


def test_a_refused_live_call_reads_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_key() -> None:
        raise AssertionError("the key was read")

    monkeypatch.setattr(mg.l4, "load_key", no_key)
    monkeypatch.setattr(mg, "seal_ok", lambda: True)
    with pytest.raises(SystemExit, match="update window"):
        mg.go_live("smoke", now=datetime.datetime(2026, 10, 16, 2, 0), git=fake_git())


def test_the_replay_is_written_beside_the_rows_of_record_and_matches_them(
    tmp_path: Path,
) -> None:
    items = [item(0), item(1), item(2)]
    rows = mg.execute("run", items, live=True, batch="b", cap_usd=1.0,
                      make_inner=lambda arm: Fake())  # fmt: skip
    assert mg.finish("run", rows, "b", 1.0) == 0
    of_record = (tmp_path / "out" / "run-scored.jsonl").read_bytes()
    (tmp_path / "out" / "run-zone.json").write_text(json.dumps(lr.time_zone()))
    assert mg.replay("run", items, "b", 1.0) == 0  # the same rows, from the recordings alone
    assert (tmp_path / "out" / "run-scored.jsonl").read_bytes() == of_record
    assert mg.read_rows("run-replay") == mg.read_rows("run")


def test_a_replay_in_another_time_zone_is_refused(tmp_path: Path) -> None:
    other = {**lr.time_zone(), "tzname": ["Elsewhere", "Elsewhere DST"], "timezone_s": 12_345}
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "run-zone.json").write_text(json.dumps(other))
    assert mg.replay("run", [item(0)], "b", 1.0) == 2
    assert not (tmp_path / "out" / "run-replay-scored.jsonl").exists()
    assert lr.zone_mismatch(lr.time_zone(), lr.time_zone()) == ""


LAUNCHER = (
    "@echo off\r\nset WT=C:\\wt\r\n"
    'set "PY=<PYTHON>"\r\nset "SANCHOPANZA_KEYS_ENV=<KEYS_ENV_PATH>"\r\n'
    '"%PY%" benchmarks\\memgate_hook\\memgate_hook.py --run --live\r\n'
)


def filled(text: str) -> str:
    return text.replace("<PYTHON>", "C:\\py\\python.exe").replace("<KEYS_ENV_PATH>", "C:\\k\\.env")


def test_filling_the_launcher_s_two_local_lines_keeps_its_digest_and_nothing_else_does(
    tmp_path: Path,
) -> None:
    path = tmp_path / "run.cmd"
    path.write_bytes(LAUNCHER.encode())
    sealed = lr.launcher_digest(path)
    path.write_bytes(filled(LAUNCHER).encode())
    assert lr.launcher_digest(path) == sealed
    path.write_bytes(filled(LAUNCHER).replace("\r\n", "\n").encode())
    assert lr.launcher_digest(path) == sealed  # line ends do not count
    for change in (("C:\\wt", "C:\\other"), ("--run --live", "--run --live --x"),
                   ("@echo off", "@echo on")):  # fmt: skip
        path.write_bytes(filled(LAUNCHER).replace(*change).encode())
        assert lr.launcher_digest(path) != sealed, change


def test_the_seal_holds_the_launcher_by_its_placeholders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launcher = tmp_path / "run.cmd"
    launcher.write_bytes(LAUNCHER.encode())
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "prereg.md").write_text("# prereg\n")
    monkeypatch.setattr(mg, "LAUNCHER", launcher)
    monkeypatch.setattr(mg, "SEALED_DATA", ())
    monkeypatch.setattr(mg, "sealed_paths", lambda: ())
    assert not mg.seal_ok()
    mg.seal()
    assert mg.seal_ok()
    launcher.write_bytes(filled(LAUNCHER).encode())
    assert mg.seal_ok()  # the owner filled the two local lines
    launcher.write_bytes(filled(LAUNCHER).replace("C:\\wt", "C:\\other").encode())
    assert not mg.seal_ok()
    launcher.unlink()
    assert not mg.seal_ok()
    assert "C:\\" not in (tmp_path / "out" / "prereg.manifest.json").read_text()


def test_a_402_is_a_pause_and_a_relaunch_pays_only_what_is_missing(tmp_path: Path) -> None:
    from sanchopanza.contract import DeciderOutOfFunds

    class Broke(Fake):
        async def decide(self, point, state, questions):
            if len(self.calls) >= 2:
                raise DeciderOutOfFunds("jev did not answer: HTTP 402 (out of funds)")
            return await super().decide(point, state, questions)

    items = [item(0), item(1), item(2)]
    rows = mg.execute("run", items, live=True, batch="b", cap_usd=1.0,
                      make_inner=lambda arm: Broke())  # fmt: skip
    assert mg.mgl.halt_kind() == mg.mgl.PAUSE and "402" in mg.mgl.HALTED[0]
    assert mg.finish("run", rows, "b", 1.0) == 2
    assert mg.read_rows("run") is None  # nothing scored
    calls: list = []
    again = mg.execute("run", items, live=True, batch="b", cap_usd=1.0,
                       make_inner=lambda arm: Fake(calls))  # fmt: skip
    assert len(again) == 3 and not mg.mgl.HALTED
    assert 0 < len(calls) < 2 * len(items)  # what was paid before the 402 is replayed free
    more: list = []
    mg.execute("run", items, live=True, batch="b", cap_usd=1.0,
               make_inner=lambda arm: Fake(more))  # fmt: skip
    assert more == []  # everything recorded now


def test_the_caps_are_hard_and_under_a_dollar_and_the_client_waits_as_installed() -> None:
    assert mg.LEDGER_CAP_USD <= 1.0 and mg.BATCH_CAP_USD <= mg.LEDGER_CAP_USD
    assert mg.SMOKE_CAP_USD < mg.BATCH_CAP_USD and mg.MODEL == "jev-1.13.0"
    from sanchopanza.providers.jev import JevDecider

    assert mg.TIMEOUT_S == JevDecider.__init__.__kwdefaults__["timeout_s"] == 10.0


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
            "related_in_pool": related, "labels": labels, "changed": {"k1": True, "k2": False},
            "hittable": related, "same_candidates": True,
            "S": arm_row(s, **kw), "L": arm_row(l_, **kw)}  # fmt: skip


def quiet(n: int = 60) -> list[dict[str, Any]]:
    return [scored(100 + i, False, [], []) for i in range(n)]


def test_a_clear_gain_with_no_extra_noise_reads_mejora() -> None:
    rows = [scored(n, True, [] if n % 3 else ["k1"], ["k1"]) for n in range(60)] + quiet()
    summary = an.analyse(rows)
    assert summary["hit_L_vs_S"]["only_new"] == 40 and summary["hit_L_vs_S"]["only_old"] == 0
    assert summary["hit_L_vs_S"]["ci95_cluster"][0] > 0
    assert summary["verdict"] == "mejora"
    assert summary["describe"]["L"]["recall"] == 1.0 and summary["describe"]["S"]["noise"] == 0


def test_a_gain_paid_in_as_many_extra_false_alarms_is_not_mejora() -> None:
    hits = {"diff": 0.2, "p": 0.001, "only_new": 20, "only_old": 2,
            "ci95": (0.1, 0.3), "ci95_cluster": (0.05, 0.35)}  # fmt: skip
    noise = {"diff": 0.01, "p": 0.01, "only_new": 18, "only_old": 0,
             "ci95": (0.0, 0.03), "ci95_cluster": (0.0, 0.04)}  # fmt: skip
    assert an.verdict(hits, noise, 0.0, 100, 1000) == "mejora"  # 18 extra hits >= 18
    more = {**noise, "only_new": 19}
    assert an.verdict(hits, more, 0.0, 100, 1000) == "no peor"  # 18 extra hits < 19
    weak = {**hits, "ci95_cluster": (-0.01, 0.35)}  # the groups' CI touches 0
    assert an.verdict(weak, noise, 0.0, 100, 1000) == "no peor"


def test_the_guard_takes_the_wider_of_the_two_intervals() -> None:
    assert an._bounds({"ci95": (-0.01, 0.02), "ci95_cluster": (-0.03, 0.06)}) == (-0.03, 0.06)
    assert an._bounds({"ci95": None, "ci95_cluster": None}) is None


def test_too_few_requests_withhold_the_verdict() -> None:
    rows = [scored(n, True, [], ["k1"]) for n in range(10)] + quiet()
    assert an.analyse(rows)["verdict"] == "no concluyente (n bajo)"


def test_related_requests_the_gate_blocks_are_out_of_the_primary() -> None:
    rows = [scored(n, True, [], ["k1"]) for n in range(40)] + quiet()
    rows += [{**scored(200 + n, True, [], []), "hittable": False} for n in range(30)]
    summary = an.analyse(rows)
    assert summary["hittable"] == 40 and summary["related_but_gated"] == 30


def test_rows_whose_arms_saw_different_candidates_are_out_and_counted() -> None:
    rows = [scored(n, True, [], ["k1"]) for n in range(40)] + quiet()
    rows += [{**scored(300 + n, True, [], ["k1"]), "same_candidates": False} for n in range(5)]
    summary = an.analyse(rows)
    assert summary["candidates_differ"] == 5 and summary["hittable"] == 40


def test_more_noise_in_l_reads_peor_en_ruido_whatever_the_gain() -> None:
    rows = [scored(n, True, [], ["k1"]) for n in range(60)]
    rows += [scored(100 + n, False, [], ["k2"] if n % 2 else []) for n in range(60)]
    summary = an.analyse(rows)
    assert summary["verdict"] == "peor en ruido"
    split = summary["false_alarm_by_record"]
    assert split["changed_nothing"]["only_new"] == 30 and split["changed_files"]["only_new"] == 0


def test_no_difference_reads_no_peor_and_failures_withhold() -> None:
    same = [scored(n, True, ["k1"], ["k1"]) for n in range(60)] + quiet()
    assert an.analyse(same)["verdict"] == "no peor"
    broken = [{**r, "L": arm_row([], p=None)} if n < 5 else r for n, r in enumerate(same)]
    summary = an.analyse(broken)
    assert summary["failed"] == {"S": 0, "L": 5} and summary["verdict"] == "no medido (fallos)"


def test_failed_means_asked_and_unanswered_or_timed_out() -> None:
    assert an.failed(arm_row([], p=None)) and not an.failed(arm_row([], asked=False))
    assert an.failed({**arm_row([]), "reason": "decider timed out after 15 s"})
    assert not an.failed(arm_row(["k1"]))


def test_the_retest_is_descriptive_agreement_at_the_cut() -> None:
    assert an.retest([]) == {"records": 0}
    got = an.retest([(0.9, 0.85), (0.1, 0.2), (0.85, 0.5)])
    assert got["records"] == 3 and got["agree_at_cut"] == round(2 / 3, 4)


def test_power_grows_with_the_effect_and_the_requests() -> None:
    assert an.mcnemar_power(126, 0.10, 0.02) > an.mcnemar_power(126, 0.06, 0.02)
    assert an.mcnemar_power(400, 0.06, 0.02) > an.mcnemar_power(126, 0.06, 0.02)
    assert an.mcnemar_power(126, 0.03, 0.03) < 0.05
    table = an.power_table(126)
    assert table["n"] == 126 and 0.05 < table["L_only_for_80pct_at_S_only_0.02"] < 0.25
