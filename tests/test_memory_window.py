"""The memory gate's long window (`SANCHOPANZA_MEMORY_WINDOW=long`, opt-in): every memory or
record read whole in one call with Jev's long-context header on that call only, a clean fall
back to the shipped short path when it cannot run, and the default path unchanged to the byte.
Fake deciders and a mocked transport; no network, no paid call."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx
import pytest

from sanchopanza import Decision
from sanchopanza.budget import SpendLedger
from sanchopanza.harness import memory_gate as mg
from sanchopanza.harness import memory_hook as mh
from sanchopanza.harness import memory_window as mw
from sanchopanza.limits import Limits
from sanchopanza.providers import CappedDecider, jev
from sanchopanza.providers.jev import JevDecider
from sanchopanza.providers.recorded import key_of
from sanchopanza.squire import Squire

from .helpers import squire, yes
from .test_memory_hook import CWD, lexer_request, say, starlette_request, write_transcript

WINDOW_ENV = ("SANCHOPANZA_MEMORY_WINDOW", "SANCHO_MEMORY_WINDOW")


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in (*WINDOW_ENV, "SANCHOPANZA_JEV_LONG_CONTEXT", "SANCHO_JEV_LONG_CONTEXT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SANCHOPANZA_FUNDS_DIR", str(tmp_path / "funds"))
    monkeypatch.setattr(jev, "BASE_WAIT_S", 0.0)


# ---- fakes ---------------------------------------------------------------------------------------


class Fake:
    """Answers `recall` yes and every page or record with `page_p(index)`; logs each request.
    `with_long_context()` gives a twin that logs into the same list, marked `long`."""

    name = "fake"
    accepts_attachments = False

    def __init__(self, page_p: Any = None, *, long: bool = False, calls: list | None = None,
                 cost: float = 0.0, long_answers: bool = True) -> None:  # fmt: skip
        self.page_p = page_p or (lambda i: 0.9 if i == 1 else 0.1)
        self.long = long
        self.calls: list[dict[str, Any]] = [] if calls is None else calls
        self.cost = cost
        self.long_answers = long_answers

    def with_long_context(self, **_: Any) -> Fake:
        return Fake(self.page_p, long=True, calls=self.calls, cost=self.cost,
                    long_answers=self.long_answers)  # fmt: skip

    async def decide(self, point: str, state: Mapping[str, Any], questions: Mapping[str, Any]):
        self.calls.append({"point": point, "state": state, "questions": questions,
                           "long": self.long})  # fmt: skip
        if point == "recall":
            return Decision(point, {"needs_memory": yes(0.9)}, self.name, "t", cost_usd=self.cost)
        if self.long and not self.long_answers:
            return Decision(point, {}, self.name, "t", error="HTTP 400 max_tokens_exceeded")
        answers = {}
        for key in questions:
            p = self.page_p(int(key[1:]) - 1)
            if p is not None:
                answers = {**answers, key: yes(p)}
        return Decision(point, answers, self.name, "t", cost_usd=self.cost)


class ShortOnly(Fake):
    """A decider with no long-context mode (a recording, a local model)."""

    with_long_context = None  # type: ignore[assignment]


def keys_of(calls: list[dict[str, Any]]) -> list[str]:
    return [key_of(c["point"], c["state"], c["questions"]) for c in calls]


def write_memory(directory: Path, file: str, name: str, body: str) -> None:
    text = f"---\nname: {name}\ndescription: about {name}\ntype: project\n---\n{body}\n"
    (directory / file).write_text(text, encoding="utf-8")


def memories(tmp_path: Path, n: int = 3, body_chars: int = 0) -> tuple[mg.Memory, ...]:
    d = tmp_path / "memory"
    d.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        filler = f" fact{i}" * (body_chars // 6) if body_chars else ""
        write_memory(d, f"m{i:03d}.md", f"memory {i}", f"deploy notes {i}{filler} tail{i}")
    return mg.load_memories(d)


# ---- the setting ---------------------------------------------------------------------------------


def test_the_window_is_short_unless_long_is_asked_for() -> None:
    assert mw.window_from_env({}) == "short"
    assert mw.window_from_env({"SANCHOPANZA_MEMORY_WINDOW": "long"}) == "long"
    assert mw.window_from_env({"SANCHOPANZA_MEMORY_WINDOW": " LONG "}) == "long"
    assert mw.window_from_env({"SANCHO_MEMORY_WINDOW": "long"}) == "long"
    for other in ("", "short", "on", "1", "big"):
        assert mw.window_from_env({"SANCHOPANZA_MEMORY_WINDOW": other}) == "short"


# ---- the default path, byte for byte -------------------------------------------------------------

# Recording keys (`providers.recorded.key_of`) of every request the default path sent, taken on
# main at 16d32fa before the long window existed. A change here changes what the shipped gate
# asks and invalidates every recording of it.
GOLDEN = {
    "gate_small": ["4a68d13e6ed646e0", "64844a1a3c7dfe42"],
    "gate_long_bodies": ["4a68d13e6ed646e0", "bbbe67b4514f16eb"],
    "gate_tournament": [
        "c222b865a5b3a75b",
        "9008d8d5f64679be",
        "190ccba2fcff3df2",
        "7d13be158786290d",
    ],
    "hook": ["755bdf16a99f62ff"],
}


def default_gate_keys(tmp_path: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    cases = {"gate_small": (3, 0), "gate_long_bodies": (3, 5_000), "gate_tournament": (40, 0)}
    for name, (n, chars) in cases.items():
        fake = Fake()
        s, _ = squire(fake)
        ms = memories(tmp_path / name, n, chars)
        asyncio.run(mg.gate(s, "deploy the service with the notes", ms))
        assert not any(c["long"] for c in fake.calls)
        out[name] = keys_of(fake.calls)
    return out


def hook_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SANCHOPANZA_MEMORY_STORE", str(tmp_path / "memory"))
    monkeypatch.setenv("SANCHOPANZA_MEMORY_STORE_LOG", str(tmp_path / "log.jsonl"))
    for name in ("SANCHOPANZA_PROVIDER", "TYPESAFE_API_KEY", "SANCHOPANZA_MEMORY_KEEP_AT",
                 "SANCHOPANZA_MEMORY_PROMPT_NAMED", "SANCHOPANZA_MEMORY_TREE"):  # fmt: skip
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SANCHOPANZA_MEMORY_PROMPT", "every")
    monkeypatch.setenv("SANCHOPANZA_MEMORY_SELECT", "decider")
    project = tmp_path / "projects" / "p"
    long_report = say("Fixed the hex rule. " + "Checked every literal form in carbon.py. " * 40)
    entries = [*lexer_request()[:-1], long_report, *starlette_request()]
    old = write_transcript(project / "s1.jsonl", entries)
    mh.handle({"hook_event_name": "Stop", "session_id": "s1", "transcript_path": str(old),
               "cwd": CWD, "prompt": ""})  # fmt: skip
    return project


def hook_prompt(project: Path, session: str = "s2") -> dict[str, Any]:
    path = write_transcript(project / f"{session}.jsonl", [])
    return {"hook_event_name": "UserPromptSubmit", "session_id": session,
            "transcript_path": str(path), "cwd": CWD,
            "prompt": "Carbon lexer octal literals, and StaticFiles too"}  # fmt: skip


def log_rows(tmp_path: Path) -> list[dict[str, Any]]:
    path = tmp_path / "log.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def default_hook_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    project = hook_store(tmp_path, monkeypatch)
    fake = Fake(lambda i: 0.95)
    s, _ = squire(fake)
    asyncio.run(mh.recall(hook_prompt(project), s))
    assert fake.calls and not any(c["long"] for c in fake.calls)
    return keys_of(fake.calls)


@pytest.mark.parametrize("setting", [None, "short", "nonsense"])
def test_the_default_path_sends_the_same_requests_as_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, setting: str | None
) -> None:
    if setting is not None:
        monkeypatch.setenv("SANCHOPANZA_MEMORY_WINDOW", setting)
    got = {**default_gate_keys(tmp_path), "hook": default_hook_keys(tmp_path, monkeypatch)}
    assert got == GOLDEN


# ---- the long window at the memory gate (memory files, the path lot L6 measured) -----------------

PROMPT = "deploy the service with the notes"


def long_gate(fake: Any, ms: Any, **changes: Any) -> tuple[mg.GateResult, Any]:
    s, journal = squire(fake, **changes)
    result = asyncio.run(mg.gate(s, PROMPT, ms, window="long"))
    return result, journal


def notes(journal: Any) -> list[dict[str, Any]]:
    return [e["data"] for e in journal.events if e["kind"] == "memory_window"]


def test_long_reads_every_memory_whole_in_one_call_on_the_long_decider(tmp_path: Path) -> None:
    fake = Fake()
    ms = memories(tmp_path, 3, body_chars=5_000)
    result, _ = long_gate(fake, ms)
    recall, triage = fake.calls  # needs_recall, then one triage call
    assert recall["point"] == "recall" and not recall["long"]  # the header on that call only
    assert triage["point"] == "triage_pages" and triage["long"]
    assert all(m.body in triage["state"]["pages"] for m in ms)  # whole, not 900 characters
    assert len(triage["questions"]) == 3
    assert result.injected == ("m001.md",) and result.report["window"] == "long"


def test_long_judges_forty_memories_in_one_call_not_a_tournament(tmp_path: Path) -> None:
    fake = Fake()
    long_gate(fake, memories(tmp_path, 40))
    assert [c["point"] for c in fake.calls] == ["recall", "triage_pages"]
    assert len(fake.calls[1]["questions"]) == 40


def test_the_environment_turns_it_on_and_an_explicit_window_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ms = memories(tmp_path, 3, body_chars=2_000)
    monkeypatch.setenv("SANCHOPANZA_MEMORY_WINDOW", "long")
    on = Fake()
    asyncio.run(mg.gate(squire(on)[0], PROMPT, ms))
    assert on.calls[-1]["long"]
    off = Fake()
    asyncio.run(mg.gate(squire(off)[0], PROMPT, ms, window="short"))
    assert not any(c["long"] for c in off.calls)


def test_over_the_long_window_it_falls_back_to_the_short_tournament_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(mw, "LONG_WINDOW_CHARS", 2_000)
    fake = Fake()
    ms = memories(tmp_path, 3, body_chars=5_000)
    result, journal = long_gate(fake, ms)
    assert not any(c["long"] for c in fake.calls)
    short = Fake()
    asyncio.run(mg.gate(squire(short)[0], PROMPT, ms))
    assert keys_of(fake.calls) == keys_of(short.calls)  # exactly the shipped path
    assert result.injected == ("m001.md",)
    assert result.report["window"] == "short"
    assert "over the long window" in result.report["window_fallback"]
    assert "long window" in capsys.readouterr().err
    (note,) = notes(journal)
    assert note["window"] == "short" and "over the long window" in note["fallback"]


def test_a_long_call_that_answers_nothing_falls_back_to_the_short_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = Fake(long_answers=False)
    result, _ = long_gate(fake, memories(tmp_path, 3, body_chars=3_000))
    assert [c["long"] for c in fake.calls] == [False, True, False]
    assert result.injected == ("m001.md",)
    assert "answered nothing" in result.report["window_fallback"]
    assert "long window" in capsys.readouterr().err


def test_a_decider_without_a_long_context_mode_stays_short_and_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = ShortOnly()
    result, _ = long_gate(fake, memories(tmp_path, 3))
    assert not any(c["long"] for c in fake.calls) and result.injected == ("m001.md",)
    assert "no long-context mode" in result.report["window_fallback"]
    assert "long window" in capsys.readouterr().err


def test_the_long_call_is_journaled_with_its_cost_and_counts_against_the_job_cap(
    tmp_path: Path,
) -> None:
    fake = Fake(cost=0.004)
    result, journal = long_gate(fake, memories(tmp_path, 3, body_chars=3_000))
    assert result.report["long_usd"] == pytest.approx(0.004)
    (note,) = notes(journal)
    assert note["window"] == "long" and note["usd"] == pytest.approx(0.004) and note["chars"] > 0
    costs = [d["cost_usd"] for d in journal.decisions() if d["point"] == "triage_pages"]
    assert costs == [pytest.approx(0.004)]
    # a job whose cap the recall question already spent asks no long call
    spent = Fake(cost=0.004)
    capped, _ = long_gate(spent, memories(tmp_path / "b", 3), max_usd=0.004)
    assert not any(c["long"] for c in spent.calls)
    assert "budget" in capped.report["window_fallback"]


def test_handle_user_prompt_reads_the_window_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    memories(tmp_path, 3, body_chars=2_000)
    monkeypatch.setenv("SANCHOPANZA_MEMORY_WINDOW", "long")
    fake = Fake()
    s, _ = squire(fake)
    event = {"prompt": "deploy the service"}
    out = asyncio.run(mg.handle_user_prompt(event, s, memory_dir=tmp_path / "memory"))
    assert "m001.md" in out["hookSpecificOutput"]["additionalContext"]
    assert fake.calls[-1]["long"]


# ---- the long window at the installed hook (records of earlier requests) -------------------------


def last_prompt_row(tmp_path: Path) -> dict[str, Any]:
    return [r for r in log_rows(tmp_path) if r.get("event") == "UserPromptSubmit"][-1]


def test_hook_long_reads_each_record_whole_on_the_long_decider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = hook_store(tmp_path, monkeypatch)
    monkeypatch.setenv("SANCHOPANZA_MEMORY_WINDOW", "long")
    fake = Fake(lambda i: 0.95, cost=0.0002)
    s, journal = squire(fake)
    out = asyncio.run(mh.recall(hook_prompt(project), s))
    (call,) = fake.calls
    assert call["point"] == "memory_recall" and call["long"]
    records = call["state"]["records"]
    assert "### Earlier request 1" in records
    context = out["hookSpecificOutput"]["additionalContext"]
    line = "Checked every literal form in carbon.py."
    # the record as stored and injected (its report bounded by code), not its 880-character page
    assert records.count(line) == context.count(line) > 20
    row = last_prompt_row(tmp_path)
    assert row["window"] == "long" and row["long_usd"] == pytest.approx(0.0002)
    assert notes(journal) and notes(journal)[0]["window"] == "long"


def test_hook_long_over_the_window_falls_back_to_the_pages_and_logs_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    project = hook_store(tmp_path, monkeypatch)
    monkeypatch.setenv("SANCHOPANZA_MEMORY_WINDOW", "long")
    monkeypatch.setattr(mw, "LONG_WINDOW_CHARS", 500)
    fake = Fake(lambda i: 0.95)
    s, _ = squire(fake)
    asyncio.run(mh.recall(hook_prompt(project), s))
    assert keys_of(fake.calls) == GOLDEN["hook"]  # the shipped request, unchanged
    row = last_prompt_row(tmp_path)
    assert row["window"] == "short" and "over the long window" in row["window_fallback"]
    assert "long window" in capsys.readouterr().err


def test_hook_long_call_that_answers_nothing_falls_back_to_the_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = hook_store(tmp_path, monkeypatch)
    monkeypatch.setenv("SANCHOPANZA_MEMORY_WINDOW", "long")
    fake = Fake(lambda i: 0.95, long_answers=False)
    s, _ = squire(fake)
    out = asyncio.run(mh.recall(hook_prompt(project), s))
    assert [c["long"] for c in fake.calls] == [True, False]
    assert keys_of(fake.calls[1:]) == GOLDEN["hook"]
    assert "carbon.py" in out["hookSpecificOutput"]["additionalContext"]


# ---- the pieces: Jev's twin, the cap's twin, the squire's fork -----------------------------------

OK = {"answers": {"P01": {"type": "noul", "noul": 0.9}}, "usage": {"input_tokens": 300}}


def mocked(seen: list[httpx.Request]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={**OK, "model": json.loads(request.content)["model"]})

    return httpx.AsyncClient(base_url=jev.BASE_URL, transport=httpx.MockTransport(handler))


def test_jev_twin_turns_on_only_the_long_context_header() -> None:
    seen: list[httpx.Request] = []
    short = JevDecider("k", model="jev-1.13.0", client=mocked(seen), long_context=False,
                       images=False, price_per_mtok=0.05)  # fmt: skip
    long = short.with_long_context()
    assert long.long_context and not short.long_context
    assert long.model == short.model and long.name == short.name and not long.images
    assert long._scope == short._scope  # one out-of-funds breaker for both (`funds`)
    asyncio.run(short.decide("recall", "s", {}))
    decision = asyncio.run(long.decide("triage_pages", "s", {}))
    assert jev.LONG_CONTEXT_HEADER not in seen[0].headers
    assert seen[1].headers[jev.LONG_CONTEXT_HEADER] == "true"
    assert decision.cost_usd == pytest.approx(300 * 0.05 / 1_000_000)


def test_the_gate_puts_the_header_on_the_triage_request_only(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    decider = JevDecider("k", client=mocked(seen), long_context=False, images=False)
    s, _ = squire(decider)
    asyncio.run(mg.gate(s, "deploy the service", memories(tmp_path, 2), window="long"))
    assert len(seen) == 2
    assert jev.LONG_CONTEXT_HEADER not in seen[0].headers  # needs_recall
    assert seen[1].headers[jev.LONG_CONTEXT_HEADER] == "true"  # the triage


def test_capped_twin_spends_through_the_same_ledger_and_cap(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    ledger = SpendLedger(tmp_path / "ledger.jsonl", cap_usd=1.0)
    inner = JevDecider("k", client=mocked(seen), long_context=False, images=False)
    capped = CappedDecider(inner, ledger=ledger, batch="b", max_usd=0.5)
    twin = capped.with_long_context()
    assert isinstance(twin, CappedDecider)
    asyncio.run(twin.decide("triage_pages", "s", {}))
    assert seen[-1].headers[jev.LONG_CONTEXT_HEADER] == "true"
    assert ledger.spent("b") > 0


def test_a_fork_can_take_another_decider_and_limits_and_keeps_the_rest() -> None:
    first, second = Fake(), Fake()
    s, journal = squire(first, max_usd=0.3)
    wide = Limits(page_chars=10_000)
    forked = s.fork(decider=second, limits=wide)
    assert forked.decider is second and s.decider is first
    assert forked.limits == wide and s.limits == Limits()
    assert forked.thresholds == s.thresholds and forked.journal is journal
    assert s.fork().decider is first and s.fork().limits == s.limits


def test_long_limits_are_lot_l6s() -> None:
    assert mw.LONG_LIMITS.page_chars == 400_000 and mw.LONG_LIMITS.pages_per_call == 1_000
    assert mw.LONG_LIMITS.memory_record_chars >= 400_000
    assert Squire(Fake(), limits=mw.LONG_LIMITS).limits == mw.LONG_LIMITS
