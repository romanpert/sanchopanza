"""ROADMAP C8: a bare "continue" at a session's first prompt names no file, so the v5 gate gave
no record at the prompt (F2, docs/results/2026-10-16-memory-f2: 12 of 48 Sonnet arms got it only
at a file touch, 5 of them after their first shell write). It now gets the project's newest
record, by code (`memory_recall.continued`). No network: fake deciders only."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from sanchopanza import Decision
from sanchopanza.context import episodes as ep
from sanchopanza.harness import memory_hook as mh
from sanchopanza.harness import memory_recall as mrc

from .helpers import squire, yes
from .test_memory_c8_request import CWD, prompt, say

DAY = 86_400


def write(path: str, content: str, n: int) -> list[dict[str, Any]]:
    use = {"type": "tool_use", "id": f"t{n}", "name": "Write",
           "input": {"file_path": f"{CWD}/{path}", "content": content}}  # fmt: skip
    result = {"type": "tool_result", "tool_use_id": f"t{n}", "content": "ok"}
    return [{"type": "assistant", "message": {"role": "assistant", "content": [use]}},
            {"type": "user", "message": {"role": "user", "content": [result]}}]  # fmt: skip


PLAN = ("We're adding shipping labels, in two steps. Step 1, today: label_for(order) in "
        "app/labels.py. Step 2, in the next session: ship_all(orders, carrier) in the same "
        "module. Only do step 1 now.")  # fmt: skip


def labels_session(at: float) -> list[dict[str, Any]]:
    return [prompt(PLAN, at), *write("app/labels.py", "def label_for(order):\n    ...\n", 1),
            say("Step 1 is done: label_for is in app/labels.py.")]  # fmt: skip


def write_transcript(path: Path, entries: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    return path


class Fake:
    name = "fake"
    accepts_attachments = False

    def __init__(self, p: float) -> None:
        self.p = p
        self.states: list[Mapping[str, Any]] = []

    async def decide(self, point: str, state: Mapping[str, Any], questions: Mapping[str, Any]):
        self.states = [*self.states, state]
        return Decision(point, {k: yes(self.p) for k in questions}, self.name, "t")


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SANCHOPANZA_MEMORY_STORE", str(tmp_path / "memory"))
    monkeypatch.setenv("SANCHOPANZA_MEMORY_STORE_LOG", str(tmp_path / "log.jsonl"))
    for name in ("SANCHOPANZA_PROVIDER", "TYPESAFE_API_KEY", "SANCHOPANZA_MEMORY_TOUCH",
                 "SANCHOPANZA_MEMORY_KEEP_AT", "SANCHOPANZA_MEMORY_PROMPT_NAMED",
                 "SANCHOPANZA_MEMORY_TREE", "SANCHOPANZA_MEMORY_CONTINUE"):  # fmt: skip
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SANCHOPANZA_MEMORY_SELECT", "decider")
    monkeypatch.setenv("SANCHOPANZA_MEMORY_PROMPT", "first")  # the shipped default with a key
    return tmp_path


def event(path: Path, name: str, session: str, text: str = "") -> dict[str, Any]:
    return {"hook_event_name": name, "session_id": session, "transcript_path": str(path),
            "cwd": CWD, "prompt": text}  # fmt: skip


def context_of(out: Mapping[str, Any]) -> str:
    return out["hookSpecificOutput"]["additionalContext"] if out else ""


def last_log(store: Path) -> dict[str, Any]:
    rows = [json.loads(x) for x in (store / "log.jsonl").read_text("utf-8").splitlines()]
    return [r for r in rows if r.get("event") == "UserPromptSubmit"][-1]


# ---- a: a continuation at a session's first prompt -------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Let's continue with the shipping labels.",  # F2's lines, all twelve this shape
        "continue",
        "ok, let's continue",
        "resume",
        "Carry on with the importer please",
        "Howdy, do you recall where we left off last session?",  # SWE-chat first prompts
        "ready, keep continuing from last session",
        "what's the next step?",
        "Seguimos con las etiquetas de envío.",
        "Continuemos con el paso 2",
        "retomamos donde lo dejamos",
        # review of w17-memgaps, M5
        "let's continue",
        "seguimos",
        "sigue donde lo dejamos",
        "continue where we left off",
        "resume the work from last session",
        "¿por dónde íbamos?",
    ],
)
def test_a_continuation_is_told_by_its_opening_or_by_a_last_session(text: str) -> None:
    assert mrc.continuation(text)


@pytest.mark.parametrize(
    "text",
    [
        "fix the continue statement in parse()",
        "how can I run something like claude --resume but also list the session ids?",
        "/speckit.plan proceed while also doing research on prototypes",  # a slash command
        "Let's persist open tabs so users pick up where they left off.",  # a feature, not us
        "-\nYou are agent 1f2e (CTO). Continue your Paperclip work.",  # an orchestrator's brief
        "proceed with deep rename of codemode to climode",  # a new task
        "sigue fallando el test de login",
        "Let's continue. " + "Now add a CSV export to the report page with these columns. " * 5,
        "",
        # review of w17-memgaps, M5: a go-on verb that opens a bug report or a new task
        "Resume parsing fails on PDF uploads",
        "continue statement in loop.py skips items",
        "continue.py is broken",
        "Seguimos sin poder compilar el proyecto",
        "Continúa fallando el test de login",
        "Continua dando error el build",
        "Fix the bug where the last session token expires early",
        "Add the next step button to the onboarding wizard",
        "Go on the website and check the footer",
        "Pick up the latest changes from main and rebase",
        "previous session crashed with OOM, see log",
        "Continue the refactor of auth.py to JWT and also rename every handler accordingly",
    ],
)
def test_not_a_continuation(text: str) -> None:
    assert not mrc.continuation(text)


def record(session: str, index: int, request: str, at: float) -> ep.Episode:
    return ep.Episode(session=session, index=index, request=request, report="done",
                      changed=("app/labels.py",), at=at)  # fmt: skip


def test_continued_gives_the_newest_session_s_plan_record_else_its_newest() -> None:
    now = 1_800_000_000.0
    older = record("s0", 1, "Step 2, in the next session: the importer", now - 3 * DAY)
    plan = record("s1", 1, PLAN, now - DAY)
    commit = record("s1", 2, "commit it", now - DAY + 60)
    go = "Let's continue with the shipping labels."
    assert mrc.continued(go, [older, plan, commit], now) == plan
    assert mrc.continued(go, [older, commit], now) == commit  # no plan in the newest session
    assert mrc.continued("fix the parser", [older, plan, commit], now) is None
    assert mrc.continued(go, [], now) is None


def test_continued_gives_nothing_older_than_continue_days() -> None:
    now = 1_800_000_000.0
    old = record("s1", 1, PLAN, now - (mrc.CONTINUE_DAYS + 1) * DAY)
    young = record("s1", 1, PLAN, now - (mrc.CONTINUE_DAYS - 1) * DAY)
    go = "continue"
    assert mrc.continued(go, [old], now) is None
    assert mrc.continued(go, [young], now) == young
    assert mrc.continued(go, [record("s1", 1, PLAN, 0.0)], now) is None  # no time recorded


def test_f2_a_bare_continue_gets_the_newest_record_at_the_first_prompt_without_a_decider(
    store: Path,
) -> None:
    project = store / "projects" / "p"
    at = time.time() - 600
    mh.handle(event(write_transcript(project / "s1.jsonl", labels_session(at)), "Stop", "s1"))
    new = write_transcript(project / "s2.jsonl", [])
    fake = Fake(0.99)
    s, _ = squire(fake)
    # "shipping labels" would name labels.py by its stem (F2: 9 of 12 lines did); this one does not
    go = event(new, "UserPromptSubmit", "s2", "Let's continue with the shipping work.")
    context = context_of(asyncio.run(mh.recall(go, s)))
    assert "request 1 of session s1" in context and "Step 2, in the next session" in context
    assert fake.states == []  # given by code: the gate passes nothing, the decider is not asked
    assert last_log(store)["continued"] == "s1-001"


def test_a_continuation_mid_session_or_switched_off_gets_nothing(
    store: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = store / "projects" / "p"
    at = time.time() - 600
    mh.handle(event(write_transcript(project / "s1.jsonl", labels_session(at)), "Stop", "s1"))
    s, _ = squire(Fake(0.99))
    monkeypatch.setenv("SANCHOPANZA_MEMORY_CONTINUE", "off")
    new = write_transcript(project / "s2.jsonl", [])
    go = event(new, "UserPromptSubmit", "s2", "continue")
    assert asyncio.run(mh.recall(go, s)) == {}
    monkeypatch.delenv("SANCHOPANZA_MEMORY_CONTINUE")
    # every prompt, not the session's first: a continuation there is the live conversation's
    monkeypatch.setenv("SANCHOPANZA_MEMORY_PROMPT", "every")
    later = write_transcript(project / "s3.jsonl", [prompt("hi", at + 60), say("hello")])
    assert asyncio.run(mh.recall(event(later, "UserPromptSubmit", "s3", "continue"), s)) == {}


def test_a_continuation_that_names_a_file_keeps_the_decider_s_picks_and_the_record_once(
    store: Path,
) -> None:
    project = store / "projects" / "p"
    at = time.time() - 600
    mh.handle(event(write_transcript(project / "s1.jsonl", labels_session(at)), "Stop", "s1"))
    fake = Fake(0.95)
    s, _ = squire(fake)
    new = write_transcript(project / "s2.jsonl", [])
    go = event(new, "UserPromptSubmit", "s2", "Let's continue with labels.py")
    context = context_of(asyncio.run(mh.recall(go, s)))
    assert len(fake.states) == 1  # named: the decider is asked as before
    assert context.count("### Earlier") == 1


# ---- review of w17-memgaps -------------------------------------------------------------------

COMMAND = "<command-name>/model</command-name>\n<command-message>model</command-message>\n" \
    "<command-args></command-args>"  # fmt: skip


def opened_with_a_command(at: float) -> list[dict[str, Any]]:
    """A real transcript's shape when a session opens with /model or /clear (read on the owner's
    machine, 2026-10-16): Claude Code's caveat (meta), the command, a system line."""
    caveat = {**prompt("<local-command-caveat>Caveat: ...</local-command-caveat>", at),
              "isMeta": True}  # fmt: skip
    return [caveat, prompt(COMMAND, at), {"type": "system", "content": "", "timestamp": "x"}]


def test_m1_a_session_that_opened_with_a_slash_command_still_gets_the_continuation(
    store: Path,
) -> None:
    project = store / "projects" / "p"
    at = time.time() - 600
    mh.handle(event(write_transcript(project / "s1.jsonl", labels_session(at)), "Stop", "s1"))
    s, _ = squire(Fake(0.99))
    new = write_transcript(project / "s2.jsonl", opened_with_a_command(at + 300))
    context = context_of(
        asyncio.run(mh.recall(event(new, "UserPromptSubmit", "s2", "continue"), s))
    )
    assert "request 1 of session s1" in context


def test_l4_no_transcript_yet_a_compacted_one_and_a_windows_cwd(store: Path) -> None:
    project = store / "projects" / "p"
    at = time.time() - 600
    mh.handle(event(write_transcript(project / "s1.jsonl", labels_session(at)), "Stop", "s1"))
    s, _ = squire(Fake(0.99))
    missing = event(project / "s2.jsonl", "UserPromptSubmit", "s2", "continue")  # not written
    assert "session s1" in context_of(asyncio.run(mh.recall(missing, s)))
    windows = {**event(project / "s3.jsonl", "UserPromptSubmit", "s3", "continue"),
               "cwd": "C:\\work\\repo"}  # fmt: skip
    assert "session s1" in context_of(asyncio.run(mh.recall(windows, s)))
    # a compacted session (boundary and summary): Claude Code's summary carries the work
    boundary = {"type": "system", "subtype": "compact_boundary"}
    summary = {"type": "user", "isCompactSummary": True,
               "message": {"role": "user", "content": "This session is continued..."}}  # fmt: skip
    compacted = write_transcript(project / "s4.jsonl", [boundary, summary])
    assert asyncio.run(mh.recall(event(compacted, "UserPromptSubmit", "s4", "continue"), s)) == {}


def finished(session: str, at: float) -> ep.Episode:
    return record(session, 1, PLAN, at)


def test_m2_a_session_still_running_in_parallel_is_not_the_one_continued() -> None:
    now = 1_800_000_000.0
    ended = finished("ended", now - 3_600)
    cut = ep.UNFINISHED + "Reading the importer..."
    running = ep.Episode(session="running", index=1, request="Refactor the importer", report=cut,
                         at=now - 120)  # fmt: skip
    go = "continue"
    # its transcript changed a moment ago and its newest request is not finished: running
    assert mrc.continued(go, [ended, running], now, {"running": now - 5}) == ended
    # the same, long quiet: a session cut off (a crash, a limit) is the one to continue
    assert mrc.continued(go, [ended, running], now, {"running": now - 3_600}) == running
    # a session that just ended (its newest request finished) is continued, however recent
    just = finished("just", now - 30)
    assert mrc.continued(go, [ended, just], now, {"just": now - 5}) == just


class Slow:
    name = "slow"
    accepts_attachments = False

    async def decide(self, point: str, state: Any, questions: Any) -> Decision:
        await asyncio.sleep(5)
        return Decision(point, {}, self.name, "t")


def test_l5_a_decider_timeout_with_a_continuation_logs_one_row(
    store: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = store / "projects" / "p"
    at = time.time() - 600
    mh.handle(event(write_transcript(project / "s1.jsonl", labels_session(at)), "Stop", "s1"))
    monkeypatch.setenv("SANCHOPANZA_MEMORY_DECIDER_SECONDS", "1")
    s, _ = squire(Slow())
    new = write_transcript(project / "s2.jsonl", [])
    go = event(new, "UserPromptSubmit", "s2", "Let's continue with labels.py")  # names the file
    assert "session s1" in context_of(asyncio.run(mh.recall(go, s)))
    rows = [json.loads(x) for x in (store / "log.jsonl").read_text("utf-8").splitlines()]
    prompts = [r for r in rows if r.get("event") == "UserPromptSubmit"]
    assert len(prompts) == 1 and "timed out" in prompts[0]["reason"] and prompts[0]["shown"]
