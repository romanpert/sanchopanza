"""The memory gate's long window: every memory or record read whole in one call, Jev's
long-context header only on the call that needs it, a clean fall back to the shipped short path
when it cannot run, the job's cap enforced, and the short path unchanged to the byte. The long
window is the library gate's default (`SANCHOPANZA_MEMORY_WINDOW=short` turns it off) and opt-in
at the installed hook. Fake deciders and a mocked transport; no network, no paid call."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import httpx
import pytest

from sanchopanza import Decision
from sanchopanza.budget import Meter, SpendLedger
from sanchopanza.harness import memory_gate as mg
from sanchopanza.harness import memory_hook as mh
from sanchopanza.harness import memory_window as mw
from sanchopanza.limits import Limits
from sanchopanza.providers import CappedDecider, jev
from sanchopanza.providers.capped import SpendCapReached
from sanchopanza.providers.jev import JevDecider
from sanchopanza.providers.recorded import key_of
from sanchopanza.squire import Squire

from .helpers import squire, yes
from .test_memory_hook import CWD, lexer_request, say, starlette_request, write_transcript

WINDOW_ENV = ("SANCHOPANZA_MEMORY_WINDOW", "SANCHO_MEMORY_WINDOW")


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in (*WINDOW_ENV, "SANCHOPANZA_JEV_LONG_CONTEXT", "SANCHO_JEV_LONG_CONTEXT",
                 "SANCHOPANZA_MEMORY_DECIDER_SECONDS"):  # fmt: skip
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SANCHOPANZA_FUNDS_DIR", str(tmp_path / "funds"))
    monkeypatch.setattr(jev, "BASE_WAIT_S", 0.0)


# ---- fakes ---------------------------------------------------------------------------------------


def whole(call: Mapping[str, Any]) -> bool:
    """A request that reads records whole (`Episode.text()`), not their pages."""
    return "### Earlier" in str(call["state"].get("records", ""))


class Fake:
    """Answers `recall` yes and every page or record with `page_p(index)`; logs each request.
    `with_long_context()` gives a twin that logs into the same list, marked `long`. `delay`
    gives each call's seconds of latency."""

    name = "fake"
    accepts_attachments = False

    def __init__(self, page_p: Any = None, *, long: bool = False, calls: list | None = None,
                 cost: float = 0.0, long_answers: bool = True,
                 long_raises: Exception | None = None,
                 delay: Callable[[Mapping[str, Any]], float] | None = None) -> None:  # fmt: skip
        self.page_p = page_p or (lambda i: 0.9 if i == 1 else 0.1)
        self.long = long
        self.calls: list[dict[str, Any]] = [] if calls is None else calls
        self.cost = cost
        self.long_answers = long_answers
        self.long_raises = long_raises
        self.delay = delay

    def with_long_context(self, **_: Any) -> Fake:
        return Fake(self.page_p, long=True, calls=self.calls, cost=self.cost,
                    long_answers=self.long_answers, long_raises=self.long_raises,
                    delay=self.delay)  # fmt: skip

    async def decide(self, point: str, state: Mapping[str, Any], questions: Mapping[str, Any]):
        call = {"point": point, "state": state, "questions": questions, "long": self.long}
        self.calls.append(call)
        if self.delay is not None and self.delay(call) > 0:
            await asyncio.sleep(self.delay(call))
        if point == "recall":
            return Decision(point, {"needs_memory": yes(0.9)}, self.name, "t", cost_usd=self.cost)
        if self.long and self.long_raises is not None:
            raise self.long_raises
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


def mocked(seen: list[httpx.Request]) -> httpx.AsyncClient:
    """Jev's wire, answering every question yes at 0.9 for 300 input tokens."""

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = json.loads(request.content)
        answers = {key: {"type": "noul", "noul": 0.9} for key in body["questions"]}
        reply = {"answers": answers, "usage": {"input_tokens": 300}, "model": body["model"]}
        return httpx.Response(200, json=reply)

    return httpx.AsyncClient(base_url=jev.BASE_URL, transport=httpx.MockTransport(handler))


def jev_mocked(seen: list[httpx.Request], **options: Any) -> JevDecider:
    return JevDecider("k", client=mocked(seen), long_context=False, images=False, **options)


# ---- the setting ---------------------------------------------------------------------------------


def test_the_window_is_short_unless_long_is_asked_for(capsys: pytest.CaptureFixture[str]) -> None:
    assert mw.window_from_env({}) == "short"
    assert mw.window_from_env({"SANCHOPANZA_MEMORY_WINDOW": "long"}) == "long"
    assert mw.window_from_env({"SANCHOPANZA_MEMORY_WINDOW": " LONG "}) == "long"
    assert mw.window_from_env({"SANCHO_MEMORY_WINDOW": "long"}) == "long"
    for other in ("", "short", " Short "):
        assert mw.window_from_env({"SANCHOPANZA_MEMORY_WINDOW": other}) == "short"
    assert capsys.readouterr().err == ""
    for other in ("on", "1", "big"):  # unknown: the short window, and it says so
        assert mw.window_from_env({"SANCHOPANZA_MEMORY_WINDOW": other}) == "short"
        assert f"SANCHOPANZA_MEMORY_WINDOW={other!r}" in capsys.readouterr().err


def test_the_default_when_unset_is_the_caller_s_and_an_unknown_value_is_short(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (mw.GATE_DEFAULT, mw.HOOK_DEFAULT) == ("long", "short")
    assert mw.window_from_env({}, default="long") == "long"
    assert mw.window_from_env({"SANCHOPANZA_MEMORY_WINDOW": " "}, default="long") == "long"
    assert mw.window_from_env({"SANCHOPANZA_MEMORY_WINDOW": "short"}, default="long") == "short"
    assert capsys.readouterr().err == ""
    assert mw.window_from_env({"SANCHOPANZA_MEMORY_WINDOW": "on"}, default="long") == "short"
    assert "SANCHOPANZA_MEMORY_WINDOW='on'" in capsys.readouterr().err


def test_an_explicit_window_must_be_short_or_long(tmp_path: Path) -> None:
    assert mw.normalize_window(" Long ") == "long"
    with pytest.raises(ValueError, match="short or long"):
        mw.normalize_window("big")
    with pytest.raises(ValueError):
        asyncio.run(mg.gate(squire(Fake())[0], "deploy it", memories(tmp_path), window="big"))


# ---- the short path, byte for byte ---------------------------------------------------------------

# Taken on main at 16d32fa, before the long window existed: the recording keys
# (`providers.recorded.key_of`) of every request the default path sent, a digest of every
# journal event (without latency and timestamps) and the keys of every memory log row. A change
# here changes what the short gate asks or reports, and invalidates its recordings. Recorded on
# the short window when it was every default: the gate's runs pin `window="short"` (unset is the
# long window there now); the hook's run reads the setting, whose default there is still short.
TREE_ROW = ["at", "event", "key", "session", "why"]
PROMPT_ROW = "at candidates caught_up chars event mode pool probabilities prompt_mode shown written"
GOLDEN = {
    "gate_small": {
        "keys": ["4a68d13e6ed646e0", "64844a1a3c7dfe42"],
        "journal": "7ca6c4807ac30301",
    },
    "gate_long_bodies": {
        "keys": ["4a68d13e6ed646e0", "bbbe67b4514f16eb"],
        "journal": "7ca6c4807ac30301",
    },
    "gate_tournament": {
        "keys": ["c222b865a5b3a75b", "9008d8d5f64679be", "190ccba2fcff3df2", "7d13be158786290d"],
        "journal": "05dbee607daf6bd5",
    },
    "hook": {
        "keys": ["755bdf16a99f62ff"],
        "journal": "ab4bd040069110ff",
        "log_keys": [
            TREE_ROW,
            ["at", "episodes", "event", "written"],
            ["added", "at", "audit", "broken", "checked", "event"],
            TREE_ROW,
            PROMPT_ROW.split(),
        ],
    },
}


def journal_digest(journal: Any) -> str:
    events = [{"kind": e["kind"],
               "data": {k: v for k, v in e["data"].items() if k != "latency_ms"}}
              for e in journal.events]  # fmt: skip
    text = json.dumps(events, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def default_gate_run(tmp_path: Path, window: str | None = "short") -> dict[str, Any]:
    out: dict[str, Any] = {}
    cases = {"gate_small": (3, 0), "gate_long_bodies": (3, 5_000), "gate_tournament": (40, 0)}
    for name, (n, chars) in cases.items():
        fake = Fake()
        s, journal = squire(fake)
        ms = memories(tmp_path / name, n, chars)
        asyncio.run(mg.gate(s, "deploy the service with the notes", ms, window=window))
        assert not any(c["long"] for c in fake.calls)
        out[name] = {"keys": keys_of(fake.calls), "journal": journal_digest(journal)}
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


def default_hook_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    project = hook_store(tmp_path, monkeypatch)
    fake = Fake(lambda i: 0.95)
    s, journal = squire(fake)
    asyncio.run(mh.recall(hook_prompt(project), s))
    assert fake.calls and not any(c["long"] for c in fake.calls)
    return {"keys": keys_of(fake.calls), "journal": journal_digest(journal),
            "log_keys": [sorted(row) for row in log_rows(tmp_path)]}  # fmt: skip


@pytest.mark.parametrize("setting", [None, "short", "nonsense"])
def test_the_short_path_sends_and_reports_the_same_as_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, setting: str | None
) -> None:
    if setting is not None:
        monkeypatch.setenv("SANCHOPANZA_MEMORY_WINDOW", setting)
    gate = default_gate_run(tmp_path, "short" if setting is None else None)
    got = {**gate, "hook": default_hook_run(tmp_path, monkeypatch)}
    assert got == GOLDEN


def test_the_short_path_never_sends_the_long_context_header(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[httpx.Request] = []
    s, _ = squire(jev_mocked(seen))
    asyncio.run(mg.gate(s, "deploy the service", memories(tmp_path, 40), window="short"))
    project = hook_store(tmp_path, monkeypatch)
    asyncio.run(mh.recall(hook_prompt(project), squire(jev_mocked(seen))[0]))
    points = [json.loads(r.content)["questions"] for r in seen]
    assert len(points) >= 4 and any("R1" in q for q in points)  # the gate and the hook asked
    assert all(jev.LONG_CONTEXT_HEADER not in r.headers for r in seen)


# ---- the long window at the memory gate (memory files, the path lot L6 measured) -----------------

PROMPT = "deploy the service with the notes"


def long_gate(fake: Any, ms: Any, **changes: Any) -> tuple[mg.GateResult, Any, Squire]:
    s, journal = squire(fake, **changes)
    result = asyncio.run(mg.gate(s, PROMPT, ms, window="long"))
    return result, journal, s


def notes(journal: Any) -> list[dict[str, Any]]:
    return [e["data"] for e in journal.events if e["kind"] == "memory_window"]


def test_long_reads_every_memory_whole_in_one_call_on_the_long_decider(tmp_path: Path) -> None:
    fake = Fake()
    ms = memories(tmp_path, 3, body_chars=5_000)
    result, _, _ = long_gate(fake, ms)
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


def test_the_library_gate_is_long_unless_short_is_asked_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ms = memories(tmp_path, 3, body_chars=2_000)
    unset = Fake()  # no setting: the long window, as lot memgate-long confirmed it
    result = asyncio.run(mg.gate(squire(unset)[0], PROMPT, ms))
    assert [c["long"] for c in unset.calls] == [False, True]
    assert result.report["window"] == "long" and result.injected == ("m001.md",)
    monkeypatch.setenv("SANCHOPANZA_MEMORY_WINDOW", "short")  # the setting turns it off
    off = Fake()
    result = asyncio.run(mg.gate(squire(off)[0], PROMPT, ms))
    assert not any(c["long"] for c in off.calls) and "window" not in result.report
    monkeypatch.delenv("SANCHOPANZA_MEMORY_WINDOW")
    pinned = Fake()  # and so does the argument
    asyncio.run(mg.gate(squire(pinned)[0], PROMPT, ms, window="short"))
    assert keys_of(pinned.calls) == keys_of(off.calls)


def test_the_library_gate_by_default_falls_back_to_short_without_a_long_decider(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ms = memories(tmp_path, 3)
    fake = ShortOnly()
    result = asyncio.run(mg.gate(squire(fake)[0], PROMPT, ms))
    short = ShortOnly()
    asyncio.run(mg.gate(squire(short)[0], PROMPT, ms, window="short"))
    assert keys_of(fake.calls) == keys_of(short.calls)  # the shipped requests, unchanged
    assert result.injected == ("m001.md",) and result.report["window"] == "short"
    assert "no long-context mode" in result.report["window_fallback"]
    assert "long window" in capsys.readouterr().err


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
    result, journal, _ = long_gate(fake, ms)
    assert not any(c["long"] for c in fake.calls)
    short = Fake()
    asyncio.run(mg.gate(squire(short)[0], PROMPT, ms, window="short"))
    assert keys_of(fake.calls) == keys_of(short.calls)  # exactly the shipped path
    assert result.injected == ("m001.md",)
    assert result.report["window"] == "short"
    assert "over the long window" in result.report["window_fallback"]
    assert "long window" in capsys.readouterr().err
    (note,) = notes(journal)
    assert note["window"] == "short" and "over the long window" in note["fallback"]


def test_the_size_counts_the_questions_too() -> None:
    state = {"purpose": "p", "pages": "x" * 100}
    from sanchopanza.contract import Truth

    qs = {f"P{i:02d}": Truth(f"Does page P{i:02d} hold a needed fact?") for i in range(50)}
    assert mw.request_chars(state, qs) > len(json.dumps(state)) + 50 * 40


def test_a_long_call_that_answers_nothing_falls_back_and_names_the_cause(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = Fake(long_answers=False)
    result, _, _ = long_gate(fake, memories(tmp_path, 3, body_chars=3_000))
    assert [c["long"] for c in fake.calls] == [False, True, False]
    assert result.injected == ("m001.md",)
    assert "answered nothing" in result.report["window_fallback"]
    assert "max_tokens_exceeded" in result.report["window_fallback"]
    assert "max_tokens_exceeded" in result.report["long_error"]
    assert "long window" in capsys.readouterr().err


def test_a_long_call_refused_by_the_spend_cap_names_it(tmp_path: Path) -> None:
    fake = Fake(long_raises=SpendCapReached("spend cap: does not fit; not called"))
    result, _, _ = long_gate(fake, memories(tmp_path, 3, body_chars=3_000))
    assert "SpendCapReached" in result.report["long_error"]
    assert "SpendCapReached" in result.report["window_fallback"]
    assert result.injected == ("m001.md",)


def test_a_decider_without_a_long_context_mode_stays_short_and_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = ShortOnly()
    result, _, _ = long_gate(fake, memories(tmp_path, 3))
    assert not any(c["long"] for c in fake.calls) and result.injected == ("m001.md",)
    assert "no long-context mode" in result.report["window_fallback"]
    assert "long window" in capsys.readouterr().err


def test_a_clm_server_gets_no_long_twin_and_no_header(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    local = jev.clm(client=mocked(seen))
    with pytest.raises(AttributeError):
        local.with_long_context()
    custom = JevDecider("k", base_url="https://proxy.example", client=mocked(seen))
    with pytest.raises(AttributeError):
        custom.with_long_context()
    result, _, _ = long_gate(local, memories(tmp_path, 2))
    assert "no long-context mode" in result.report["window_fallback"]
    assert seen and all(jev.LONG_CONTEXT_HEADER not in r.headers for r in seen)


def test_the_long_call_is_journaled_with_its_cost_and_charged_to_the_job(tmp_path: Path) -> None:
    fake = Fake(cost=0.004)
    result, journal, s = long_gate(fake, memories(tmp_path, 3, body_chars=3_000))
    assert result.report["long_usd"] == pytest.approx(0.004)
    (note,) = notes(journal)
    assert note["window"] == "long" and note["usd"] == pytest.approx(0.004) and note["chars"] > 0
    costs = [d["cost_usd"] for d in journal.decisions() if d["point"] == "triage_pages"]
    assert costs == [pytest.approx(0.004)]
    # the job's meter holds the recall question and the long call
    assert s.meter.decisions == 2 and s.meter.cost_usd == pytest.approx(0.008)


def test_no_long_call_when_the_job_s_budget_is_spent_or_would_not_hold_it(tmp_path: Path) -> None:
    spent = Fake(cost=0.004)
    capped, _, _ = long_gate(spent, memories(tmp_path / "a", 3), max_usd=0.004)
    assert not any(c["long"] for c in spent.calls)
    assert "budget" in capped.report["window_fallback"]
    tight = Fake()  # nothing spent, but the long call's estimate is over what is left
    result, _, _ = long_gate(tight, memories(tmp_path / "b", 3, 3_000), max_usd=1e-9)
    assert not any(c["long"] for c in tight.calls)
    assert "would not fit the job's budget" in result.report["window_fallback"]
    assert result.injected == ("m001.md",)


def test_handle_user_prompt_is_long_by_default_and_short_when_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    memories(tmp_path, 3, body_chars=2_000)
    event = {"prompt": "deploy the service"}
    directory = tmp_path / "memory"
    unset = Fake()
    asyncio.run(mg.handle_user_prompt(event, squire(unset)[0], memory_dir=directory))
    assert unset.calls[-1]["long"]
    monkeypatch.setenv("SANCHOPANZA_MEMORY_WINDOW", "short")
    off = Fake()
    out = asyncio.run(mg.handle_user_prompt(event, squire(off)[0], memory_dir=directory))
    assert "m001.md" in out["hookSpecificOutput"]["additionalContext"]
    assert not any(c["long"] for c in off.calls)


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


def test_the_installed_hook_stays_on_the_short_window_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`sanchopanza install` (memory on by default) wires `memory_hook`, not the library gate,
    and sets no window; with nothing set, the hook judges the records' pages on the short
    window, even with a decider that has the long mode and a call past Jev's short window."""
    from sanchopanza import cli
    from sanchopanza.harness.install import MEMORY_COMMAND

    settings = tmp_path / "proj" / ".claude" / "settings.json"
    assert cli.main(["install", "--path", str(settings), "--write"]) == 0
    data = json.loads(settings.read_text("utf-8"))
    assert not [k for k in data.get("env", {}) if k.endswith("MEMORY_WINDOW")]
    (entry,) = data["hooks"]["UserPromptSubmit"]
    assert [h["command"] for h in entry["hooks"]] == [MEMORY_COMMAND]
    assert "memory-gate" not in settings.read_text("utf-8")
    project = hook_store(tmp_path, monkeypatch)
    monkeypatch.setattr(mw, "SHORT_WINDOW_CHARS", 500)  # a long call would need the header
    fake = Fake(lambda i: 0.95)
    s, journal = squire(fake)
    out = asyncio.run(mh.recall(hook_prompt(project), s))
    assert "carbon.py" in out["hookSpecificOutput"]["additionalContext"]
    assert keys_of(fake.calls) == GOLDEN["hook"]["keys"]  # the shipped request, unchanged
    assert not any(c["long"] or whole(c) for c in fake.calls)
    row = last_prompt_row(tmp_path)
    assert "window" not in row and "window_fallback" not in row
    assert notes(journal) == []


def last_prompt_row(tmp_path: Path) -> dict[str, Any]:
    return [r for r in log_rows(tmp_path) if r.get("event") == "UserPromptSubmit"][-1]


def long_hook(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    project = hook_store(tmp_path, monkeypatch)
    monkeypatch.setenv("SANCHOPANZA_MEMORY_WINDOW", "long")
    return project


def test_hook_long_reads_each_record_whole_on_the_same_decider_inside_the_short_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = long_hook(tmp_path, monkeypatch)
    fake = Fake(lambda i: 0.95, cost=0.0002)
    s, journal = squire(fake)
    out = asyncio.run(mh.recall(hook_prompt(project), s))
    (call,) = fake.calls
    assert call["point"] == "memory_recall" and not call["long"] and whole(call)
    context = out["hookSpecificOutput"]["additionalContext"]
    line = "Checked every literal form in carbon.py."
    # the record as stored and injected (its report bounded by code), not its 880-character page
    assert call["state"]["records"].count(line) == context.count(line) > 20
    row = last_prompt_row(tmp_path)
    assert row["window"] == "long" and row["long_usd"] == pytest.approx(0.0002)
    assert row["long_header"] is False
    assert notes(journal) and notes(journal)[0]["window"] == "long"


def test_hook_long_on_jev_shares_the_client_and_sends_the_header_only_past_the_short_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = long_hook(tmp_path, monkeypatch)
    seen: list[httpx.Request] = []
    decider = jev_mocked(seen)
    asyncio.run(mh.recall(hook_prompt(project), squire(decider)[0]))
    assert "### Earlier" in json.loads(seen[-1].content)["state"]["records"]
    assert jev.LONG_CONTEXT_HEADER not in seen[-1].headers  # whole, but small: no header
    monkeypatch.setattr(mw, "SHORT_WINDOW_CHARS", 500)
    asyncio.run(mh.recall(hook_prompt(project, "s3"), squire(decider)[0]))
    assert seen[-1].headers[jev.LONG_CONTEXT_HEADER] == "true"
    assert seen[-1].extensions["timeout"]["read"] == mw.LONG_TIMEOUT_S  # per request
    assert last_prompt_row(tmp_path)["long_header"] is True


def test_hook_long_over_the_window_falls_back_to_the_pages_and_logs_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    project = long_hook(tmp_path, monkeypatch)
    monkeypatch.setattr(mw, "LONG_WINDOW_CHARS", 500)
    fake = Fake(lambda i: 0.95)
    s, _ = squire(fake)
    asyncio.run(mh.recall(hook_prompt(project), s))
    assert keys_of(fake.calls) == GOLDEN["hook"]["keys"]  # the shipped request, unchanged
    row = last_prompt_row(tmp_path)
    assert row["window"] == "short" and "over the long window" in row["window_fallback"]
    assert "long window" in capsys.readouterr().err


def test_hook_long_call_that_answers_nothing_falls_back_to_the_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = long_hook(tmp_path, monkeypatch)
    monkeypatch.setattr(mw, "SHORT_WINDOW_CHARS", 500)  # the long twin answers
    fake = Fake(lambda i: 0.95, long_answers=False)
    s, _ = squire(fake)
    out = asyncio.run(mh.recall(hook_prompt(project), s))
    assert [c["long"] for c in fake.calls] == [True, False]
    assert keys_of(fake.calls[1:]) == GOLDEN["hook"]["keys"]
    assert "carbon.py" in out["hookSpecificOutput"]["additionalContext"]
    assert "max_tokens_exceeded" in last_prompt_row(tmp_path)["long_error"]


def test_hook_a_slow_long_call_leaves_time_for_the_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = long_hook(tmp_path, monkeypatch)
    monkeypatch.setenv("SANCHOPANZA_MEMORY_DECIDER_SECONDS", "2")
    monkeypatch.setattr(mw, "SHORT_RESERVE_S", 1.5)  # the long call gets 0.5 s
    fake = Fake(lambda i: 0.95, delay=lambda call: 1.0 if whole(call) else 0.0)
    s, _ = squire(fake)
    out = asyncio.run(mh.recall(hook_prompt(project), s))
    assert "carbon.py" in out["hookSpecificOutput"]["additionalContext"]  # the pages ran
    assert [whole(c) for c in fake.calls] == [True, False]
    row = last_prompt_row(tmp_path)
    assert row["window"] == "short" and "over its 0.5 s" in row["window_fallback"]
    assert "TimeoutError" in row["long_error"]


def test_hook_the_window_is_in_the_row_even_when_the_whole_choice_times_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = long_hook(tmp_path, monkeypatch)
    monkeypatch.setenv("SANCHOPANZA_MEMORY_DECIDER_SECONDS", "1")
    monkeypatch.setattr(mw, "SHORT_RESERVE_S", 0.5)
    fake = Fake(lambda i: 0.95, delay=lambda call: 0.8)
    s, _ = squire(fake)
    assert asyncio.run(mh.recall(hook_prompt(project), s)) == {}
    row = last_prompt_row(tmp_path)
    assert "timed out" in row["reason"] and row["window"] == "long"


def test_hook_a_long_call_cut_by_its_deadline_is_charged_at_its_estimate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = long_hook(tmp_path, monkeypatch)
    monkeypatch.setenv("SANCHOPANZA_MEMORY_DECIDER_SECONDS", "2")
    monkeypatch.setattr(mw, "SHORT_RESERVE_S", 1.5)  # the long call gets 0.5 s
    ledger = SpendLedger(tmp_path / "ledger.jsonl", cap_usd=1.0)
    fake = Fake(lambda i: 0.95, delay=lambda call: 1.0 if whole(call) else 0.0)
    s, _ = squire(CappedDecider(fake, ledger=ledger, batch="b", max_usd=0.5))
    out = asyncio.run(mh.recall(hook_prompt(project), s))
    assert "carbon.py" in out["hookSpecificOutput"]["additionalContext"]  # the pages ran
    row = last_prompt_row(tmp_path)
    assert "over its 0.5 s" in row["window_fallback"]
    # the server may bill a request it received: the cut call counts at its estimate
    assert row["long_usd"] > 0 and row["long_usd_estimated"] is True
    assert s.meter.cost_usd >= row["long_usd"]
    assert ledger.spent("b") > 0


def test_a_capped_call_cancelled_in_flight_keeps_its_reservation(tmp_path: Path) -> None:
    ledger = SpendLedger(tmp_path / "ledger.jsonl", cap_usd=1.0)
    capped = CappedDecider(Fake(delay=lambda call: 1.0), ledger=ledger, batch="b", max_usd=0.5)

    async def cut() -> None:
        await asyncio.wait_for(capped.decide("triage_pages", {"pages": "x" * 3_000}, {}), 0.05)

    with pytest.raises(TimeoutError):
        asyncio.run(cut())
    assert ledger.spent("b") > 0 and capped.meter.cost_usd > 0


# ---- the pieces: Jev's twin, the cap's twin, the squire's fork and absorb ------------------------


def test_a_twin_does_not_close_the_client_it_shares() -> None:
    short = jev_mocked([])
    long = short.with_long_context()
    asyncio.run(long.aclose())
    assert not short._client().is_closed
    asyncio.run(short.aclose())
    assert short._client().is_closed


def test_jev_twin_turns_on_only_the_long_context_header_on_the_same_client() -> None:
    seen: list[httpx.Request] = []
    short = jev_mocked(seen, model="jev-1.13.0", price_per_mtok=0.05)
    long = short.with_long_context(timeout_s=8.0)
    assert long.long_context and not short.long_context
    assert long.model == short.model and long.name == short.name and not long.images
    assert long.price_per_mtok == short.price_per_mtok == 0.05
    assert long._scope == short._scope  # one out-of-funds breaker for both (`funds`)
    assert long._client() is short._client()  # no new connection per prompt
    asyncio.run(short.decide("recall", "s", {}))
    decision = asyncio.run(long.decide("triage_pages", "s", {}))
    assert jev.LONG_CONTEXT_HEADER not in seen[0].headers
    assert seen[1].headers[jev.LONG_CONTEXT_HEADER] == "true"
    assert seen[1].extensions["timeout"]["read"] == 8.0
    assert decision.cost_usd == pytest.approx(300 * 0.05 / 1_000_000)


def test_a_jev_decider_can_be_named_at_construction() -> None:
    assert JevDecider("k", client=mocked([]), name="mine").name == "mine"
    assert JevDecider("k", client=mocked([])).name == "jev"


def test_the_gate_puts_the_header_on_the_triage_request_only(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    s, _ = squire(jev_mocked(seen))
    asyncio.run(mg.gate(s, "deploy the service", memories(tmp_path, 2), window="long"))
    assert len(seen) == 2
    assert jev.LONG_CONTEXT_HEADER not in seen[0].headers  # needs_recall
    assert seen[1].headers[jev.LONG_CONTEXT_HEADER] == "true"  # the triage


def test_capped_twin_spends_through_the_same_ledger_and_cap(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    ledger = SpendLedger(tmp_path / "ledger.jsonl", cap_usd=1.0)
    capped = CappedDecider(jev_mocked(seen), ledger=ledger, batch="b", max_usd=0.5,
                           price_per_mtok=0.07)  # fmt: skip
    twin = capped.with_long_context()
    assert isinstance(twin, CappedDecider) and twin.price_per_mtok == 0.07
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


def test_a_squire_absorbs_a_fork_s_meter() -> None:
    s = Squire(Fake())
    before = s.meter
    s.absorb(Meter(decisions=2, cost_usd=0.01))
    assert before == Meter() and s.meter == Meter(decisions=2, cost_usd=0.01)


def test_long_limits_and_timeouts() -> None:
    assert mw.LONG_LIMITS.page_chars == 400_000 and mw.LONG_LIMITS.pages_per_call == 1_000
    assert mw.LONG_LIMITS.memory_record_chars >= 400_000
    assert Squire(Fake(), limits=mw.LONG_LIMITS).limits == mw.LONG_LIMITS
    assert mw.LONG_TIMEOUT_S <= 10 and 0 < mw.SHORT_RESERVE_S < 15
    assert mw.SHORT_WINDOW_CHARS < mw.LONG_WINDOW_CHARS
